"""Sensor platform for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity
from .registers import EnumDef, FaultDef, SensorDef

FAULT_STATES = ["ok", "warning", "fault"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all sensors of one inverter."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        GrowattSensor(coordinator, defn) for defn in coordinator.profile.sensors
    ]
    entities.extend(
        GrowattEnumSensor(coordinator, defn) for defn in coordinator.profile.enums
    )
    entities.extend(
        GrowattFaultSensor(coordinator, defn) for defn in coordinator.profile.faults
    )
    if coordinator.profile.clock_register is not None:
        entities.append(GrowattClockDriftSensor(coordinator))
    if coordinator.profile.faults:
        entities.append(GrowattActiveFaultsSensor(coordinator))
        entities.append(GrowattLastFaultSensor(coordinator))
    async_add_entities(entities)


class GrowattSensor(GrowattEntity, SensorEntity):
    """Numeric sensor backed by one or two modbus registers."""

    def __init__(self, coordinator: GrowattCoordinator, defn: SensorDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn
        self._attr_native_unit_of_measurement = defn.unit
        if defn.device_class:
            self._attr_device_class = SensorDeviceClass(defn.device_class)
        if defn.state_class:
            self._attr_state_class = SensorStateClass(defn.state_class)
        if defn.precision is not None:
            self._attr_suggested_display_precision = defn.precision
        if defn.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = defn.enabled_default

    @property
    def native_value(self) -> float | int | None:
        return self.coordinator.sensor_value(self._defn)


class GrowattEnumSensor(GrowattEntity, SensorEntity):
    """Sensor with translated enum states (status, mode, ...)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: GrowattCoordinator, defn: EnumDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn
        # Preserve definition order, drop duplicates (e.g. repeated "normal").
        self._attr_options = list(dict.fromkeys(defn.options.values()))

    @property
    def native_value(self) -> str | None:
        return self.coordinator.enum_value(self._defn)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {
            "raw_value": self.coordinator.raw_value(
                self._defn.register_type, self._defn.address
            )
        }


class GrowattClockDriftSensor(GrowattEntity, SensorEntity):
    """Deviation of the inverter clock from real time, in seconds.

    Only changes when the drift actually changes (rounded to 5 s), so it
    does not flood the logbook the way a timestamp sensor would. The
    absolute inverter time is exposed as an attribute. The inverter's
    daily energy counters reset based on its own clock, so drift matters.
    """

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: GrowattCoordinator) -> None:
        super().__init__(coordinator, "clock_drift")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.clock_drift_seconds()

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        inverter_time = self.coordinator.inverter_time()
        return {
            "inverter_time": inverter_time.isoformat() if inverter_time else None
        }


class GrowattActiveFaultsSensor(GrowattEntity, SensorEntity):
    """Decoded names of all currently active (non-warning) fault bits."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: GrowattCoordinator) -> None:
        super().__init__(coordinator, "active_faults")

    @property
    def native_value(self) -> str:
        return ", ".join(self.coordinator.active_faults) or "OK"


class GrowattLastFaultSensor(GrowattEntity, RestoreEntity, SensorEntity):
    """The most recent fault with start/end timestamps, kept after clearing.

    Restored across restarts so the diagnosis of a past fault survives.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:history"

    def __init__(self, coordinator: GrowattCoordinator) -> None:
        super().__init__(coordinator, "last_fault")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if (
            last is not None
            and self.coordinator.last_fault is None
            and last.state not in ("unknown", "unavailable", "-")
        ):
            self.coordinator.last_fault = {
                "faults": last.state,
                "started_at": last.attributes.get("started_at"),
                "cleared_at": last.attributes.get("cleared_at"),
            }

    @property
    def native_value(self) -> str:
        if self.coordinator.last_fault is None:
            return "-"
        return self.coordinator.last_fault.get("faults") or "-"

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        last = self.coordinator.last_fault or {}
        return {
            "started_at": last.get("started_at"),
            "cleared_at": last.get("cleared_at"),
        }


class GrowattFaultSensor(GrowattEntity, SensorEntity):
    """Decoded fault/warning bitfield register."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = FAULT_STATES

    def __init__(self, coordinator: GrowattCoordinator, defn: FaultDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn

    @property
    def native_value(self) -> str | None:
        return self.coordinator.fault_state(self._defn)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "raw_value": self.coordinator.raw_value("input", self._defn.address),
            "active_faults": self.coordinator.fault_bits(self._defn) or [],
        }
