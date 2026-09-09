"""Onkyo FlareConnect: multiroom-groepen lezen en zetten vanuit Home Assistant."""
from __future__ import annotations

import asyncio
import logging
import random

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_COMMANDS,
    ATTR_DELAY,
    ATTR_GROUP_ID,
    ATTR_HOST,
    ATTR_MAX_DELAY,
    ATTR_MEMBERS,
    ATTR_SOURCE,
    CONF_HOSTS,
    DOMAIN,
    SERVICE_JOIN,
    SERVICE_REFRESH,
    SERVICE_SEND_COMMAND,
    SERVICE_UNJOIN,
)
from .coordinator import FlareConnectCoordinator
from .eiscp import async_clear_group, async_send_raw, async_set_group

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]

JOIN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SOURCE): cv.string,
        vol.Required(ATTR_MEMBERS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_GROUP_ID): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
        vol.Optional(ATTR_MAX_DELAY, default=5000): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
UNJOIN_SCHEMA = vol.Schema({vol.Required(ATTR_SOURCE): cv.string})
SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_HOST): cv.string,
        vol.Required(ATTR_COMMANDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DELAY, default=2.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=30)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Zet de integratie op."""
    coordinator = FlareConnectCoordinator(hass, entry.data[CONF_HOSTS])
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ruim de integratie op."""
    ontladen = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ontladen:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_JOIN)
            hass.services.async_remove(DOMAIN, SERVICE_UNJOIN)
            hass.services.async_remove(DOMAIN, SERVICE_SEND_COMMAND)
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
    return ontladen


def _register_services(hass: HomeAssistant) -> None:
    """Registreer join/unjoin. Idempotent: bij een tweede entry gebeurt er niets."""
    if hass.services.has_service(DOMAIN, SERVICE_JOIN):
        return

    def _coordinator() -> FlareConnectCoordinator:
        coordinators = list(hass.data[DOMAIN].values())
        if not coordinators:
            raise HomeAssistantError("Onkyo FlareConnect is niet geladen")
        return coordinators[0]

    def _resolve(coordinator: FlareConnectCoordinator, waarde: str) -> str:
        """Accepteer zowel een IP-adres als een device-id."""
        if waarde in (coordinator.data or {}):
            return waarde
        host = coordinator.host_for_device_id(waarde)
        if host:
            return host
        raise HomeAssistantError(f"Onbekend toestel: {waarde}")

    async def _join(call: ServiceCall) -> None:
        coordinator = _coordinator()
        bron = _resolve(coordinator, call.data[ATTR_SOURCE])

        leden: list[str] = []
        for lid in call.data[ATTR_MEMBERS]:
            host = _resolve(coordinator, lid)
            if host == bron:
                raise HomeAssistantError("De bron kan niet ook lid van zijn eigen groep zijn")
            info = coordinator.data[host]
            if not info.device_id:
                raise HomeAssistantError(f"Geen device-id bekend voor {host}")
            leden.append(info.device_id)

        # Zonder expliciet id kiezen we er zelf een; de officiele app doet hetzelfde.
        group_id = call.data.get(ATTR_GROUP_ID) or random.randint(2, 250)
        await async_set_group(bron, group_id, leden, max_delay=call.data[ATTR_MAX_DELAY])
        _LOGGER.info("Groep %s aangemaakt vanaf %s met %s", group_id, bron, leden)
        await coordinator.async_request_refresh()

    async def _unjoin(call: ServiceCall) -> None:
        coordinator = _coordinator()
        bron = _resolve(coordinator, call.data[ATTR_SOURCE])
        await async_clear_group(bron)
        _LOGGER.info("Groep verbroken vanaf %s", bron)
        await coordinator.async_request_refresh()

    async def _send_command(call: ServiceCall) -> None:
        """Stuur ruwe eISCP-commando's op een rij, met pauze ertussen.

        Menucommando's (NSV, NLSI) zijn stateful: het toestel moet tijd krijgen om de
        volgende lijst op te bouwen voordat het volgende commando aankomt.
        """
        coordinator = _coordinator()
        host = _resolve(coordinator, call.data[ATTR_HOST])
        pauze = call.data[ATTR_DELAY]
        for i, commando in enumerate(call.data[ATTR_COMMANDS]):
            if i:
                await asyncio.sleep(pauze)
            _LOGGER.debug("Naar %s: %s", host, commando)
            await async_send_raw(host, commando)

    hass.services.async_register(DOMAIN, SERVICE_JOIN, _join, schema=JOIN_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UNJOIN, _unjoin, schema=UNJOIN_SCHEMA)
    async def _refresh(call: ServiceCall) -> None:
        """Lees de groepsstatus opnieuw uit. Nodig na koppelen buiten Home Assistant om."""
        await _coordinator().async_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, _send_command, schema=SEND_COMMAND_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh, schema=vol.Schema({}))
