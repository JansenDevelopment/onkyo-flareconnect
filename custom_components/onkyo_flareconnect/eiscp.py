"""Minimale eISCP-client voor FlareConnect-groepen.

Twee commando's dragen de multiroomstatus, geen van beide gedocumenteerd:

* ``MDI``  leest de groepsstatus als XML (zone, groupid, role, roomname, delay).
* ``MGS``  zet de groep. Write-only: het antwoordt niet op ``QSTN``, dus het is
  onzichtbaar voor een gewone commando-scan. Het gaat altijd naar de **bron**,
  die de leden zelf aanstuurt.

Gevonden door het verkeer van de officiele Onkyo-app af te tappen.
"""
from __future__ import annotations

import asyncio
import logging
import re
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

EISCP_PORT = 60128
_MDI_RE = re.compile(r"<mdi>.*?</mdi>", re.S)
_ECN_RE = re.compile(r"!1ECN([^/]+)/(\d+)/([^/]*)/([0-9A-Fa-f]+)")
_TERMINATOR = b"\r\n"


def _frame_raw(message: str) -> bytes:
    """Verpak een complete ISCP-boodschap (inclusief prefix) in een eISCP-frame."""
    body = message.encode("ascii") + _TERMINATOR
    header = b"ISCP" + (16).to_bytes(4, "big") + len(body).to_bytes(4, "big")
    return header + bytes([0x01, 0x00, 0x00, 0x00]) + body


def _frame(message: str) -> bytes:
    """Verpak een boodschap voor de hoofdeenheid (prefix !1)."""
    return _frame_raw("!1" + message)


@dataclass
class ZoneInfo:
    """Een zone van een toestel."""

    zone_id: int
    group_id: int
    role: str  # src | dst | none
    room_name: str
    power: bool
    delay: int


@dataclass
class DeviceInfo:
    """Wat MDI over een toestel vertelt."""

    host: str
    device_id: str
    zones: list[ZoneInfo] = field(default_factory=list)

    @property
    def active_zone(self) -> ZoneInfo | None:
        """De zone die in een groep zit, of anders de eerste zone."""
        for zone in self.zones:
            if zone.role != "none":
                return zone
        return self.zones[0] if self.zones else None

    @property
    def group_id(self) -> int:
        zone = self.active_zone
        return zone.group_id if zone else 0

    @property
    def role(self) -> str:
        zone = self.active_zone
        return zone.role if zone else "none"

    @property
    def room_name(self) -> str:
        zone = self.active_zone
        return zone.room_name if zone else ""


async def _request(host: str, message: str, read_seconds: float = 1.2) -> str:
    """Stuur een boodschap en lees terug wat er binnen read_seconds binnenkomt."""
    reader, writer = await asyncio.open_connection(host, EISCP_PORT)
    try:
        writer.write(_frame(message))
        await writer.drain()
        buffer = b""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + read_seconds
        while True:
            resterend = deadline - loop.time()
            if resterend <= 0:
                break
            try:
                chunk = await asyncio.wait_for(reader.read(65536), timeout=resterend)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buffer += chunk
        return buffer.decode("ascii", "replace")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 - sluiten mag de aanroeper nooit breken
            pass


async def async_get_device_info(host: str) -> DeviceInfo | None:
    """Lees de groepsstatus van een toestel via MDI."""
    antwoord = await _request(host, "MDIQSTN")
    treffer = _MDI_RE.search(antwoord)
    if not treffer:
        _LOGGER.debug("Geen MDI-antwoord van %s", host)
        return None
    try:
        root = ET.fromstring(treffer.group(0))
    except ET.ParseError as err:
        _LOGGER.warning("Onleesbare MDI-XML van %s: %s", host, err)
        return None

    zones = [
        ZoneInfo(
            zone_id=int(zone.get("id", "0")),
            group_id=int(zone.get("groupid", "0")),
            role=zone.get("role", "none"),
            room_name=zone.get("roomname", ""),
            power=zone.get("powerstate") == "1",
            delay=int(zone.get("delay", "0")),
        )
        for zone in root.findall("./zonelist/zone")
    ]
    return DeviceInfo(
        host=host, device_id=(root.findtext("deviceid") or "").strip(), zones=zones
    )


async def async_set_group(
    host: str,
    group_id: int,
    members: list[str],
    max_delay: int = 5000,
    zone: int = 1,
) -> None:
    """Maak een groep aan vanaf de bron. members zijn device-id's (MAC zonder scheiding)."""
    devices = "".join('<device id="%s" zoneid="1" />' % m for m in members)
    payload = (
        '<mgs zone="%d"><groupid>%d</groupid><maxdelay>%d</maxdelay>'
        "<devices>%s</devices></mgs>" % (zone, group_id, max_delay, devices)
    )
    await _request(host, "MGS" + payload, read_seconds=2.0)
    # De officiele app stuurt hierna de protocolversie; dat doen wij ook.
    await _request(host, "MGV200", read_seconds=0.5)


async def async_clear_group(host: str, zone: int = 1) -> None:
    """Verbreek de groep waarvan host de bron is."""
    payload = '<mgs zone="%d"><groupid>0</groupid></mgs>' % zone
    await _request(host, "MGS" + payload, read_seconds=2.0)


def _broadcast_adressen() -> list[str]:
    """255.255.255.255 plus het subnet-broadcast van elke lokale interface.

    Op een machine met meerdere interfaces belandt het beperkte broadcast lang niet
    altijd op het juiste netwerk; het subnet-broadcast wel.
    """
    adressen = ["255.255.255.255"]
    try:
        _, _, ips = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        ips = []
    for ip in ips:
        if ip.startswith("127."):
            continue
        delen = ip.split(".")
        if len(delen) == 4:
            adressen.append(".".join(delen[:3] + ["255"]))
    return list(dict.fromkeys(adressen))


async def async_discover(timeout: float = 3.0) -> dict[str, str]:
    """Zoek Onkyo-toestellen via de eISCP-broadcast. Geeft {ip: model}."""
    loop = asyncio.get_running_loop()
    gevonden: dict[str, str] = {}

    class _Protocol(asyncio.DatagramProtocol):
        def datagram_received(self, data: bytes, addr) -> None:
            treffer = _ECN_RE.search(data.decode("ascii", "replace"))
            if treffer:
                gevonden[addr[0]] = treffer.group(1)

    transport, _ = await loop.create_datagram_endpoint(
        _Protocol, local_addr=("0.0.0.0", 0), allow_broadcast=True
    )
    try:
        # Discovery gebruikt prefix !x in plaats van !1.
        pakket = _frame_raw("!xECNQSTN")
        for adres in _broadcast_adressen():
            try:
                transport.sendto(pakket, (adres, EISCP_PORT))
            except OSError as err:  # sommige interfaces weigeren broadcast
                _LOGGER.debug("Broadcast naar %s mislukt: %s", adres, err)
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return gevonden
