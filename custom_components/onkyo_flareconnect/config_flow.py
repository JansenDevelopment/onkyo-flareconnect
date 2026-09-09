"""Configuratiestroom: zoekt Onkyo-toestellen of laat ze met de hand invullen."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_HOSTS, DOMAIN
from .eiscp import async_discover, async_get_device_info


class FlareConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Eén entry voor alle toestellen; groeperen vraagt immers overzicht over alles."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            hosts = [h.strip() for h in user_input[CONF_HOSTS].split(",") if h.strip()]
            bereikbaar = [h for h in hosts if await async_get_device_info(h) is not None]
            if not bereikbaar:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Onkyo FlareConnect", data={CONF_HOSTS: bereikbaar}
                )
            gevonden = user_input[CONF_HOSTS]
        else:
            ontdekt = await async_discover()
            gevonden = ", ".join(sorted(ontdekt)) if ontdekt else ""

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOSTS, default=gevonden): str}),
            errors=errors,
        )
