"""Select platform for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity
from .registers import REG_HOLDING, SelectDef


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up writable select entities."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GrowattSelect(coordinator, defn) for defn in coordinator.profile.selects
    )


class GrowattSelect(GrowattEntity, SelectEntity):
    """Writable holding register as a select entity."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: GrowattCoordinator, defn: SelectDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn
        self._attr_options = list(defn.options.values())
        self._reverse = {name: raw for raw, name in defn.options.items()}

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.raw_value(REG_HOLDING, self._defn.address)
        if raw is None:
            return None
        return self._defn.options.get(raw)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write_register(
            self._defn.address, self._reverse[option]
        )
