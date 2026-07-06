"""Button platform for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.profile.clock_register is not None:
        async_add_entities([GrowattSyncClockButton(coordinator)])


class GrowattSyncClockButton(GrowattEntity, ButtonEntity):
    """Writes the current HA local time to the inverter clock.

    Growatt clocks tend to drift; the inverter's internal daily energy
    counters depend on its clock, so keeping it in sync matters.

    Disabled by default: several SPH firmwares reject Modbus writes to
    the clock registers entirely (illegal data address) — enable and try
    it; if the press fails, your firmware only allows setting the clock
    via the display or Growatt's own tools.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: GrowattCoordinator) -> None:
        super().__init__(coordinator, "sync_clock")

    async def async_press(self) -> None:
        await self.coordinator.async_sync_clock()
