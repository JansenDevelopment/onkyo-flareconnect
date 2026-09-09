"""Haalt periodiek de FlareConnect-groepsstatus van alle toestellen op."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .eiscp import DeviceInfo, async_get_device_info

_LOGGER = logging.getLogger(__name__)


class FlareConnectCoordinator(DataUpdateCoordinator[dict[str, DeviceInfo]]):
    """Pollt MDI op elk toestel; groepswijzigingen worden namelijk niet gepusht."""

    def __init__(self, hass: HomeAssistant, hosts: list[str]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.hosts = hosts

    async def _async_update_data(self) -> dict[str, DeviceInfo]:
        resultaten = await asyncio.gather(
            *(async_get_device_info(host) for host in self.hosts),
            return_exceptions=True,
        )
        data: dict[str, DeviceInfo] = {}
        for host, resultaat in zip(self.hosts, resultaten):
            if isinstance(resultaat, Exception):
                _LOGGER.debug("Kon %s niet bereiken: %s", host, resultaat)
                continue
            if resultaat is not None:
                data[host] = resultaat
        return data

    def host_for_device_id(self, device_id: str) -> str | None:
        """Zoek het IP bij een device-id, zodat services met beide overweg kunnen."""
        for host, info in (self.data or {}).items():
            if info.device_id.lower() == device_id.lower():
                return host
        return None

    def members_of(self, group_id: int) -> list[DeviceInfo]:
        """Alle toestellen in een groep. Groep 0 betekent: geen groep."""
        if not group_id:
            return []
        return [i for i in (self.data or {}).values() if i.group_id == group_id]
