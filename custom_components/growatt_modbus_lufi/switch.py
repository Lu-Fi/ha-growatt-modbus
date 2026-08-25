"""Switch platform for the Growatt Modbus integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity
from .registers import REG_HOLDING, SwitchDef


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable switch entities."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GrowattSwitch(coordinator, defn) for defn in coordinator.profile.switches
    )


class GrowattSwitch(GrowattEntity, SwitchEntity):
    """Writable holding register as a switch entity."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: GrowattCoordinator, defn: SwitchDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.raw_value(REG_HOLDING, self._defn.address)
        if raw is None:
            return None
        return raw == self._defn.command_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_register(
            self._defn.address, self._defn.command_on
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_register(
            self._defn.address, self._defn.command_off
        )
