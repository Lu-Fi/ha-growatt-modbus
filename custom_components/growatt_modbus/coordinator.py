"""Data update coordinator for the Growatt Modbus integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_ENTITY,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)
from .modbus_client import GrowattModbusClient, GrowattModbusError
from .registers import (
    REG_DERIVED,
    REG_HOLDING,
    REG_INPUT,
    DeviceProfile,
    EnumDef,
    FaultDef,
    SensorDef,
)

_LOGGER = logging.getLogger(__name__)

RegisterData = dict[str, dict[int, int]]


class GrowattCoordinator(DataUpdateCoordinator[RegisterData]):
    """Polls all register blocks of one inverter."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GrowattModbusClient,
        profile: DeviceProfile,
    ) -> None:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.title}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.client = client
        self.profile = profile
        self.slave_id: int = entry.data.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID)
        self._blocks = profile.read_blocks()
        self._had_fault: bool | None = None

    async def _async_update_data(self) -> RegisterData:
        data: RegisterData = {REG_INPUT: {}, REG_HOLDING: {}}
        try:
            for reg_type, blocks in self._blocks.items():
                for address, count in blocks:
                    values = await self.client.read_registers(
                        reg_type, address, count, self.slave_id
                    )
                    for offset, value in enumerate(values):
                        data[reg_type][address + offset] = value
        except GrowattModbusError as err:
            raise UpdateFailed(str(err)) from err
        await self._async_check_fault_notification(data)
        return data

    # ------------------------------------------------------------------
    # Fault notifications
    # ------------------------------------------------------------------

    def _fault_summary(self, data: RegisterData) -> tuple[bool, list[str]] | None:
        """Return (has_fault, active fault names) from fresh register data.

        Warning bits are ignored; unknown bits count as faults. Returns
        None when no fault register could be read.
        """
        found = False
        active: list[str] = []
        for fault in self.profile.faults:
            raw = data[REG_INPUT].get(fault.address)
            if raw is None:
                continue
            found = True
            known_mask = 0
            for bit, name in fault.bits.items():
                known_mask |= 1 << bit
                if raw & (1 << bit) and bit not in fault.warning_bits:
                    active.append(name)
            unknown = raw & ~known_mask & 0xFFFF
            if unknown:
                active.append(f"{fault.key}=0x{unknown:04X}")
        # Inverter status register: value mapped to "fault" counts too.
        for enum in self.profile.enums:
            if enum.key != "inverter_status":
                continue
            raw = data.get(enum.register_type, {}).get(enum.address)
            if raw is not None:
                found = True
                if enum.options.get(raw) == "fault":
                    active.append("InverterStatusFault")
        if not found:
            return None
        return bool(active), active

    async def _async_check_fault_notification(self, data: RegisterData) -> None:
        """Send a notification when a real fault appears or clears."""
        summary = self._fault_summary(data)
        if summary is None:
            return
        has_fault, names = summary
        previous, self._had_fault = self._had_fault, has_fault
        # No notification on the very first poll or without a change.
        if previous is None or previous == has_fault:
            return
        if not self.entry.options.get(CONF_NOTIFY_ENABLED, False):
            return
        notify_entity = self.entry.options.get(CONF_NOTIFY_ENTITY)
        if not notify_entity:
            return
        de = (self.hass.config.language or "en").startswith("de")
        if has_fault:
            faults = ", ".join(names)
            message = (
                f"⚠️ {self.entry.title}: Störung erkannt: {faults}"
                if de
                else f"⚠️ {self.entry.title}: fault detected: {faults}"
            )
        else:
            message = (
                f"✅ {self.entry.title}: Störung behoben"
                if de
                else f"✅ {self.entry.title}: fault cleared"
            )
        try:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"entity_id": notify_entity, "message": message},
            )
        except Exception:  # noqa: BLE001 - notification must never break polling
            _LOGGER.exception("Fault notification via %s failed", notify_entity)

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a holding register and refresh state afterwards."""
        try:
            await self.client.write_register(address, value, self.slave_id)
        except GrowattModbusError as err:
            raise UpdateFailed(str(err)) from err
        # Optimistically update local cache, then poll for confirmation.
        if self.data is not None:
            self.data[REG_HOLDING][address] = value
            self.async_set_updated_data(self.data)
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Decoding helpers
    # ------------------------------------------------------------------

    def raw_value(self, register_type: str, address: int) -> int | None:
        if self.data is None:
            return None
        return self.data.get(register_type, {}).get(address)

    def _read_typed(
        self, register_type: str, address: int, data_type: str
    ) -> int | None:
        raw = self.raw_value(register_type, address)
        if raw is None:
            return None
        if data_type == "u32":
            low = self.raw_value(register_type, address + 1)
            if low is None:
                return None
            return (raw << 16) | low
        if data_type == "i16" and raw >= 0x8000:
            return raw - 0x10000
        return raw

    def sensor_value(self, defn: SensorDef) -> float | int | None:
        """Decoded, scaled value for a sensor definition."""
        if defn.register_type == REG_DERIVED:
            return self._derived_value(defn)
        value = self._read_typed(defn.register_type, defn.address, defn.data_type)
        if value is None:
            return None
        scaled = value * defn.scale
        if defn.precision is not None:
            scaled = round(scaled, defn.precision)
            if defn.precision == 0:
                scaled = int(scaled)
        return scaled

    def _derived_value(self, defn: SensorDef) -> float | None:
        if defn.key == "battery_power":
            charge = self._read_typed(REG_INPUT, 1011, "u32")
            discharge = self._read_typed(REG_INPUT, 1009, "u32")
            if charge is None or discharge is None:
                return None
            return round((charge - discharge) * 0.1, 1)
        if defn.key == "power_factor":
            raw = self.raw_value(REG_INPUT, defn.address)
            if raw is None:
                return None
            return round(raw / 10000, 3)
        return None

    def enum_value(self, defn: EnumDef) -> str | None:
        raw = self.raw_value(defn.register_type, defn.address)
        if raw is None:
            return None
        return defn.options.get(raw)

    def fault_bits(self, defn: FaultDef) -> list[str] | None:
        raw = self.raw_value(REG_INPUT, defn.address)
        if raw is None:
            return None
        return [name for bit, name in defn.bits.items() if raw & (1 << bit)]

    def _active_bits(self, defn: FaultDef, warnings: bool) -> list[str] | None:
        """Active bit names, filtered to warnings or real faults."""
        raw = self.raw_value(REG_INPUT, defn.address)
        if raw is None:
            return None
        return [
            name
            for bit, name in defn.bits.items()
            if raw & (1 << bit) and (bit in defn.warning_bits) == warnings
        ]

    def fault_state(self, defn: FaultDef) -> str | None:
        """State of one fault register: fault > warning > ok."""
        faults = self._active_bits(defn, warnings=False)
        warnings = self._active_bits(defn, warnings=True)
        if faults is None or warnings is None:
            return None
        # Unknown bits (not in the map) count as faults to stay safe.
        raw = self.raw_value(REG_INPUT, defn.address) or 0
        known = sum(1 << bit for bit in defn.bits)
        if faults or raw & ~known:
            return "fault"
        if warnings:
            return "warning"
        return "ok"

    def any_fault(self) -> bool | None:
        """True if any real (non-warning) fault bit is set."""
        found = False
        for fault in self.profile.faults:
            state = self.fault_state(fault)
            if state is None:
                continue
            found = True
            if state == "fault":
                return True
        return False if found else None

    def any_warning(self) -> bool | None:
        """True if any warning bit is set."""
        found = False
        for fault in self.profile.faults:
            bits = self._active_bits(fault, warnings=True)
            if bits is None:
                continue
            found = True
            if bits:
                return True
        return False if found else None

    def serial_number(self) -> str | None:
        """ASCII serial number from holding registers, if configured."""
        if self.profile.serial_registers is None:
            return None
        start, count = self.profile.serial_registers
        chars: list[str] = []
        for offset in range(count):
            raw = self.raw_value(REG_HOLDING, start + offset)
            if raw is None:
                return None
            chars.append(chr((raw >> 8) & 0xFF))
            chars.append(chr(raw & 0xFF))
        serial = "".join(c for c in chars if c.isprintable() and c != " ").strip()
        return serial or None

    def firmware_version(self) -> str | None:
        if self.profile.firmware_register is None:
            return None
        raw = self.raw_value(REG_HOLDING, self.profile.firmware_register)
        if raw is None:
            return None
        return f"Modbus {raw / 100:.2f}"
