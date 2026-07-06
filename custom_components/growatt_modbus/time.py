"""Time platform for the Growatt SPH Modbus integration.

Start/stop times of the Grid First / Battery First windows. The register
packs the hour into the high byte and the minute into the low byte.
"""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity
from .registers import REG_HOLDING, TimeWindowDef


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up start/stop time entities for all time windows."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[TimeEntity] = []
    for window in coordinator.profile.time_windows:
        entities.append(GrowattWindowTime(coordinator, window, "start"))
        entities.append(GrowattWindowTime(coordinator, window, "stop"))
    async_add_entities(entities)


class GrowattWindowTime(GrowattEntity, TimeEntity):
    """One boundary (start or stop) of a charge/discharge time window."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: GrowattCoordinator, window: TimeWindowDef, which: str
    ) -> None:
        super().__init__(coordinator, f"{window.key}_{which}")
        self._address = (
            window.start_address if which == "start" else window.stop_address
        )

    @property
    def native_value(self) -> dt_time | None:
        raw = self.coordinator.raw_value(REG_HOLDING, self._address)
        if raw is None:
            return None
        hour, minute = (raw >> 8) & 0xFF, raw & 0xFF
        if hour > 23 or minute > 59:
            return None
        return dt_time(hour=hour, minute=minute)

    async def async_set_value(self, value: dt_time) -> None:
        raw = (value.hour << 8) | value.minute
        await self.coordinator.async_write_register(self._address, raw)
