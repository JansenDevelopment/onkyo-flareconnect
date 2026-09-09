"""Sensor per toestel met de FlareConnect-groepsstatus."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo as HaDeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FlareConnectCoordinator

# De rollen zoals MDI ze rapporteert, vertaald naar stabiele statussleutels.
ROLE_STATES = {"src": "source", "dst": "receiver", "none": "not_grouped"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FlareConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        FlareConnectSensor(coordinator, host) for host in coordinator.data or {}
    )


class FlareConnectSensor(CoordinatorEntity[FlareConnectCoordinator], SensorEntity):
    """Toont of dit toestel gekoppeld is, en zo ja met wie."""

    _attr_has_entity_name = True
    _attr_translation_key = "group_role"
    _attr_icon = "mdi:speaker-multiple"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["source", "receiver", "not_grouped"]

    def __init__(self, coordinator: FlareConnectCoordinator, host: str) -> None:
        super().__init__(coordinator)
        self._host = host
        info = coordinator.data[host]
        self._attr_unique_id = f"{DOMAIN}_{info.device_id or host}"
        self._attr_device_info = HaDeviceInfo(
            identifiers={(DOMAIN, info.device_id or host)},
            name=info.room_name or host,
            manufacturer="Onkyo",
            configuration_url=f"http://{host}",
        )

    @property
    def _info(self):
        return (self.coordinator.data or {}).get(self._host)

    @property
    def available(self) -> bool:
        return super().available and self._info is not None

    @property
    def native_value(self) -> str | None:
        info = self._info
        if info is None:
            return None
        return ROLE_STATES.get(info.role, "not_grouped")

    @property
    def extra_state_attributes(self) -> dict:
        info = self._info
        if info is None:
            return {}
        members = self.coordinator.members_of(info.group_id)
        return {
            "group_id": info.group_id,
            "grouped": info.group_id != 0,
            "room": info.room_name,
            "device_id": info.device_id,
            "host": info.host,
            "members": [m.room_name or m.host for m in members if m.host != info.host],
            "source": next(
                (m.room_name or m.host for m in members if m.role == "src"), None
            ),
        }
