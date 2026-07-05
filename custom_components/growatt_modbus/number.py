"""Number platform for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity
from .registers import REG_HOLDING, NumberDef


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable number entities."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GrowattNumber(coordinator, defn) for defn in coordinator.profile.numbers
    )


class GrowattNumber(GrowattEntity, NumberEntity):
    """Writable holding register as a number entity."""

    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GrowattCoordinator, defn: NumberDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn
        self._attr_native_min_value = defn.min_value
        self._attr_native_max_value = defn.max_value
        self._attr_native_step = defn.step
        self._attr_native_unit_of_measurement = defn.unit
        if defn.device_class:
            self._attr_device_class = NumberDeviceClass(defn.device_class)

    @property
    def native_value(self) -> float | None:
        raw = self.coordinator.raw_value(REG_HOLDING, self._defn.address)
        if raw is None:
            return None
        return raw * self._defn.scale

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value / self._defn.scale))
        await self.coordinator.async_write_register(self._defn.address, raw)
