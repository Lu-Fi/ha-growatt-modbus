"""Register definitions (device profiles) for Growatt inverters.

The integration is profile based: every supported inverter series gets its
own ``DeviceProfile``. Adding support for another series (MIN, MOD, SPA, ...)
only requires adding a new profile to ``PROFILES`` — no changes to the
platform code are needed.

Register addresses follow the official "Growatt Inverter Modbus RTU
Protocol V1.20" (SPH / mixed storage series).
"""
from __future__ import annotations

from dataclasses import dataclass, field

REG_INPUT = "input"
REG_HOLDING = "holding"
REG_DERIVED = "derived"

# Modbus limits for automatic block planning
MAX_BLOCK_SIZE = 110
MAX_BLOCK_GAP = 30

# Identification registers (holding), common to all Growatt inverters
# per protocol V1.20 / V3.05:
#   43 "DTC"  - Device Type Code
#   44 "TP"   - input tracker count (high byte) / output phase count (low byte),
#               e.g. 0x0203 = 2 MPPT trackers, 3-phase output
REG_DEVICE_TYPE_CODE = 43
REG_TRACKER_PHASE = 44


def parse_tracker_phase(value: int) -> tuple[int, int]:
    """Split holding register 44 into (tracker_count, phase_count)."""
    return (value >> 8) & 0xFF, value & 0xFF


@dataclass(frozen=True)
class SensorDef:
    """A numeric sensor read from one or two modbus registers."""

    key: str
    register_type: str
    address: int
    data_type: str = "u16"  # u16 | u32 | i16
    scale: float = 1.0
    precision: int | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    diagnostic: bool = False
    enabled_default: bool = True


@dataclass(frozen=True)
class EnumDef:
    """A sensor whose raw register value maps to a translatable state."""

    key: str
    register_type: str
    address: int
    options: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FaultDef:
    """A fault/warning bitfield register (input register).

    ``warning_bits`` lists bit positions that are mere warnings (e.g.
    "PV voltage low" at night); they do not trigger the fault binary
    sensor, only the warning binary sensor.
    """

    key: str
    address: int
    bits: dict[int, str] = field(default_factory=dict)
    warning_bits: frozenset[int] = frozenset()


@dataclass(frozen=True)
class NumberDef:
    """A writable holding register exposed as a number entity."""

    key: str
    address: int
    min_value: float
    max_value: float
    step: float = 1.0
    scale: float = 1.0
    unit: str | None = None
    device_class: str | None = None


@dataclass(frozen=True)
class SelectDef:
    """A writable holding register exposed as a select entity."""

    key: str
    address: int
    options: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SwitchDef:
    """A writable holding register exposed as a switch entity."""

    key: str
    address: int
    command_on: int = 1
    command_off: int = 0


@dataclass(frozen=True)
class DeviceProfile:
    """Complete register map of one inverter series."""

    key: str
    name: str
    sensors: tuple[SensorDef, ...] = ()
    enums: tuple[EnumDef, ...] = ()
    faults: tuple[FaultDef, ...] = ()
    numbers: tuple[NumberDef, ...] = ()
    selects: tuple[SelectDef, ...] = ()
    switches: tuple[SwitchDef, ...] = ()
    firmware_register: int | None = None  # holding register with modbus version
    # (start, count) of ASCII serial number holding registers, or None
    serial_registers: tuple[int, int] | None = None

    def required_registers(self) -> dict[str, set[int]]:
        """All register addresses that must be polled, per register type."""
        needed: dict[str, set[int]] = {REG_INPUT: set(), REG_HOLDING: set()}
        for sensor in self.sensors:
            if sensor.register_type == REG_DERIVED:
                continue
            needed[sensor.register_type].add(sensor.address)
            if sensor.data_type == "u32":
                needed[sensor.register_type].add(sensor.address + 1)
        for enum in self.enums:
            needed[enum.register_type].add(enum.address)
        for fault in self.faults:
            needed[REG_INPUT].add(fault.address)
        for number in self.numbers:
            needed[REG_HOLDING].add(number.address)
        for select in self.selects:
            needed[REG_HOLDING].add(select.address)
        for switch in self.switches:
            needed[REG_HOLDING].add(switch.address)
        if self.firmware_register is not None:
            needed[REG_HOLDING].add(self.firmware_register)
        if self.serial_registers is not None:
            start, count = self.serial_registers
            needed[REG_HOLDING].update(range(start, start + count))
        return needed

    def read_blocks(self) -> dict[str, list[tuple[int, int]]]:
        """Group required registers into efficient (address, count) blocks."""
        blocks: dict[str, list[tuple[int, int]]] = {}
        for reg_type, addresses in self.required_registers().items():
            blocks[reg_type] = _plan_blocks(sorted(addresses))
        return blocks


def _plan_blocks(addresses: list[int]) -> list[tuple[int, int]]:
    """Merge sorted addresses into read blocks with limited gaps and size."""
    blocks: list[tuple[int, int]] = []
    if not addresses:
        return blocks
    start = prev = addresses[0]
    for addr in addresses[1:]:
        if addr - prev > MAX_BLOCK_GAP or addr - start + 1 > MAX_BLOCK_SIZE:
            blocks.append((start, prev - start + 1))
            start = addr
        prev = addr
    blocks.append((start, prev - start + 1))
    return blocks


# ---------------------------------------------------------------------------
# SPH series (hybrid / mixed storage inverters, e.g. SPH 4000-10000 TL3 BH)
# ---------------------------------------------------------------------------

SPH_SENSORS: tuple[SensorDef, ...] = (
    # PV
    SensorDef("pv_power", REG_INPUT, 1, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("pv1_voltage", REG_INPUT, 3, "u16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("pv1_current", REG_INPUT, 4, "u16", 0.1, 1, "A", "current", "measurement"),
    SensorDef("pv1_power", REG_INPUT, 5, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("pv2_voltage", REG_INPUT, 7, "u16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("pv2_current", REG_INPUT, 8, "u16", 0.1, 1, "A", "current", "measurement"),
    SensorDef("pv2_power", REG_INPUT, 9, "u32", 0.1, 1, "W", "power", "measurement"),
    # Grid / AC output
    SensorDef("grid_output_power", REG_INPUT, 35, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("grid_frequency", REG_INPUT, 37, "u16", 0.01, 2, "Hz", "frequency", "measurement"),
    SensorDef("grid_voltage_l1", REG_INPUT, 38, "u16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("grid_output_power_l1", REG_INPUT, 40, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("output_power_percent", REG_INPUT, 101, "u16", 1, 0, "%", None, "measurement"),
    SensorDef("power_factor", REG_DERIVED, 100, state_class="measurement"),
    # Temperatures
    SensorDef("inverter_temperature", REG_INPUT, 93, "u16", 0.1, 1, "°C", "temperature", "measurement"),
    SensorDef("ipm_temperature", REG_INPUT, 94, "u16", 0.1, 1, "°C", "temperature", "measurement", diagnostic=True),
    SensorDef("boost_temperature", REG_INPUT, 95, "u16", 0.1, 1, "°C", "temperature", "measurement", diagnostic=True),
    # Battery
    SensorDef("battery_discharge_power", REG_INPUT, 1009, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("battery_charge_power", REG_INPUT, 1011, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("battery_power", REG_DERIVED, 0, unit="W", device_class="power", state_class="measurement"),
    SensorDef("battery_voltage", REG_INPUT, 1013, "i16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("battery_soc", REG_INPUT, 1014, "u16", 1, 0, "%", "battery", "measurement"),
    # Power flows
    SensorDef("grid_import_power", REG_INPUT, 1021, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("grid_export_power", REG_INPUT, 1029, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("local_load_power", REG_INPUT, 1037, "u32", 0.1, 1, "W", "power", "measurement"),
    # EPS / off-grid output
    SensorDef("eps_frequency", REG_INPUT, 1067, "i16", 0.01, 2, "Hz", "frequency", "measurement"),
    SensorDef("eps_voltage", REG_INPUT, 1068, "i16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("eps_power", REG_INPUT, 1070, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("eps_load", REG_INPUT, 1080, "u16", 0.1, 1, "%", None, "measurement"),
    # Energy
    SensorDef("ac_output_energy_today", REG_INPUT, 53, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("ac_output_energy_total", REG_INPUT, 55, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("pv1_energy_today", REG_INPUT, 59, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("pv1_energy_total", REG_INPUT, 61, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("pv2_energy_today", REG_INPUT, 63, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("pv2_energy_total", REG_INPUT, 65, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("pv_energy_total", REG_INPUT, 91, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("energy_to_user_today", REG_INPUT, 1044, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("energy_to_user_total", REG_INPUT, 1046, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("energy_to_grid_today", REG_INPUT, 1048, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("energy_to_grid_total", REG_INPUT, 1050, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("energy_discharge_today", REG_INPUT, 1052, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("energy_discharge_total", REG_INPUT, 1054, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("energy_charge_today", REG_INPUT, 1056, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("energy_charge_total", REG_INPUT, 1058, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    SensorDef("local_load_energy_today", REG_INPUT, 1060, "u32", 0.1, 1, "kWh", "energy", "total"),
    SensorDef("local_load_energy_total", REG_INPUT, 1062, "u32", 0.1, 1, "kWh", "energy", "total_increasing"),
    # Battery / BMS (scales are undocumented by Growatt and were verified
    # against live values; disabled by default except battery temperature,
    # since third-party BMSes may leave them empty)
    # Note: protocol claims 0.1 °C for 1040/1089, real hardware sends 1 °C
    SensorDef("battery_temperature", REG_INPUT, 1040, "u16", 1, 0, "°C", "temperature", "measurement"),
    SensorDef("bms_soc", REG_INPUT, 1086, "u16", 1, 0, "%", "battery", "measurement", enabled_default=False),
    SensorDef("bms_battery_voltage", REG_INPUT, 1087, "u16", 0.01, 2, "V", "voltage", "measurement", enabled_default=False),
    SensorDef("bms_battery_current", REG_INPUT, 1088, "i16", 0.01, 2, "A", "current", "measurement", enabled_default=False),
    SensorDef("bms_battery_temperature", REG_INPUT, 1089, "u16", 1, 0, "°C", "temperature", "measurement", enabled_default=False),
    SensorDef("bms_max_current", REG_INPUT, 1090, "u16", 0.01, 2, "A", "current", None, diagnostic=True, enabled_default=False),
    SensorDef("bms_delta_volt", REG_INPUT, 1094, "u16", 1, 0, "mV", None, "measurement", diagnostic=True, enabled_default=False),
    SensorDef("bms_cycle_count", REG_INPUT, 1095, "u16", 1, 0, None, None, "total_increasing", diagnostic=True, enabled_default=False),
    SensorDef("bms_soh", REG_INPUT, 1096, "u16", 1, 0, "%", None, "measurement", diagnostic=True, enabled_default=False),
    # Settings / diagnostics (holding registers, read only)
    SensorDef("modbus_version", REG_HOLDING, 88, "u16", 0.01, 2, None, None, None, diagnostic=True),
    SensorDef("vbat_min", REG_HOLDING, 1006, "u16", 0.01, 2, "V", "voltage", None, diagnostic=True),
    SensorDef("vbat_max", REG_HOLDING, 1007, "u16", 0.01, 2, "V", "voltage", None, diagnostic=True),
    SensorDef("pv_start_voltage", REG_HOLDING, 17, "u16", 0.1, 1, "V", "voltage", None, diagnostic=True),
    SensorDef("max_output_reactive_power", REG_HOLDING, 4, "u16", 1, 0, "%", None, None, diagnostic=True),
)

SPH_ENUMS: tuple[EnumDef, ...] = (
    EnumDef(
        "inverter_status",
        REG_INPUT,
        0,
        {
            0: "waiting",
            1: "normal",
            2: "normal",
            3: "fault",
            4: "flash",
            5: "normal_hybrid",
            6: "normal_hybrid",
            7: "normal_hybrid",
            8: "normal_hybrid",
        },
    ),
    EnumDef(
        "inverter_mode",
        REG_INPUT,
        1000,
        {
            0: "waiting",
            1: "self_test",
            2: "reserved",
            3: "sys_fault",
            4: "flash",
            5: "pv_bat_online",
            6: "bat_online",
            7: "pv_offline",
            8: "bat_offline",
        },
    ),
    EnumDef(
        "derating_mode",
        REG_INPUT,
        104,
        {
            0: "no_derating",
            1: "pv_voltage",
            3: "grid_voltage",
            4: "grid_frequency",
            5: "boost_temperature",
            6: "inverter_temperature",
            7: "control",
            9: "overtemp_recovery",
        },
    ),
    EnumDef(
        "ct_mode",
        REG_HOLDING,
        1037,
        {0: "wired_ct", 1: "wireless_ct", 2: "meter"},
    ),
)

SPH_FAULTS: tuple[FaultDef, ...] = (
    FaultDef(
        "fault_0",
        1001,
        {
            0: "MasterForceINVFault",
            1: "MasterForceSPFault",
            2: "BusVoltHigh_TZ",
            3: "BusVoltHigh_ISR",
            8: "GridZClossFault",
            11: "GFCIHigh",
            12: "GridR_VFault",
            13: "GridS_VFault",
            14: "GridT_VFault",
            15: "GridFFault",
        },
    ),
    FaultDef(
        "fault_1",
        1002,
        {
            0: "RelayFault",
            1: "GFCIDamage",
            2: "GridR_VLowFault",
            3: "GridR_VHighFault",
            4: "GridS_VLowFault",
            5: "GridS_VHighFault",
            6: "GridT_VLowFault",
            7: "GridT_VHighFault",
            8: "INVCurrOCP_ISR",
            9: "INVCurrOCP_TZ",
            10: "DCIHigh",
            12: "INVR_CurrOCP_Rms",
            13: "INVS_CurrOCP_Rms",
            14: "INVT_CurrOCP_Rms",
            15: "NoUtility",
        },
    ),
    FaultDef(
        "fault_2",
        1003,
        {
            0: "GridFLowFault",
            1: "GridFHighFault",
            2: "GridVolt_Unbalance_Fault",
            3: "AC_PLL_Fault",
            4: "OverLoadFault",
            8: "EPS_LineVoltR_Loss",
            9: "EPS_LineVoltS_Loss",
            10: "EPS_LineVoltT_Loss",
        },
    ),
    FaultDef(
        "fault_3",
        1004,
        {
            0: "BatTerminalReversed",
            1: "BMS_Battery_Open",
            2: "BatteryVoltageLow",
        },
    ),
    FaultDef(
        "fault_4",
        1005,
        {
            5: "PV1_VoltLowWarn",
            6: "PV2_VoltLowWarn",
        },
        warning_bits=frozenset({5, 6}),
    ),
    FaultDef(
        "fault_5",
        1006,
        {
            0: "NE_DetectFault",
            1: "PVISOFault",
            3: "BusVoltHighFault_ISR",
            4: "BusSampleFault",
            5: "UHCTFault",
            6: "AComFault",
            7: "BComFault",
            9: "AutoTestFault",
            11: "NTCOpenFault",
            13: "BBHeatsink_TempOver",
            14: "BBOCP_FaultISR",
            15: "INVHeatsink_Overtemp",
        },
    ),
    FaultDef(
        "fault_6",
        1007,
        {
            0: "PV1_VoltHighFault",
            1: "PV2_VoltHighFault",
            2: "BTHeatsink_Overtemp",
            3: "INVHeatsink_Overtemp",
            8: "BoostDriver1Warn",
            9: "BoostDriver2Warn",
            10: "WARN104",
            11: "PV1_ShortFault",
            12: "PV2_ShortFault",
            13: "Meter_COM_Loss",
            14: "PairingTimeOut",
            15: "CT_LN_Reversed",
        },
        warning_bits=frozenset({8, 9, 10}),
    ),
)

SPH_NUMBERS: tuple[NumberDef, ...] = (
    NumberDef("discharge_soc_min", 608, 10, 100, 1, 1, "%", "battery"),
    NumberDef("max_output_active_power", 3, 0, 100, 1, 1, "%", None),
    # Export limit rate, holding 123, 0.1 % steps (protocol V1.20)
    NumberDef("export_limit_rate", 123, 0, 100, 0.5, 0.1, "%", None),
)

SPH_SELECTS: tuple[SelectDef, ...] = (
    SelectDef("priority", 1044, {0: "load_first", 1: "battery_first", 2: "grid_first"}),
)

SPH_SWITCHES: tuple[SwitchDef, ...] = (
    SwitchDef("power_state", 0, 1, 0),
    # Export limitation (zero feed-in), holding 122 (protocol V1.20)
    SwitchDef("export_limit", 122, 1, 0),
)

SPH_PROFILE = DeviceProfile(
    key="sph",
    name="SPH series (hybrid, 1-phase)",
    sensors=SPH_SENSORS,
    enums=SPH_ENUMS,
    faults=SPH_FAULTS,
    numbers=SPH_NUMBERS,
    selects=SPH_SELECTS,
    switches=SPH_SWITCHES,
    firmware_register=88,
    serial_registers=(23, 5),
)

# ---------------------------------------------------------------------------
# SPH TL3 series (three-phase hybrid, e.g. SPH 4000-10000 TL3 BH-UP)
# Same register map as SPH plus per-phase grid and EPS registers
# (protocol V1.20: input 42-52 grid L2/L3, 1072-1079 EPS L2/L3).
# ---------------------------------------------------------------------------

SPH_TL3_EXTRA_SENSORS: tuple[SensorDef, ...] = (
    SensorDef("grid_voltage_l2", REG_INPUT, 42, "u16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("grid_output_power_l2", REG_INPUT, 44, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("grid_voltage_l3", REG_INPUT, 46, "u16", 0.1, 1, "V", "voltage", "measurement"),
    SensorDef("grid_output_power_l3", REG_INPUT, 48, "u32", 0.1, 1, "W", "power", "measurement"),
    SensorDef("grid_voltage_l1_l2", REG_INPUT, 50, "u16", 0.1, 1, "V", "voltage", "measurement", enabled_default=False),
    SensorDef("grid_voltage_l2_l3", REG_INPUT, 51, "u16", 0.1, 1, "V", "voltage", "measurement", enabled_default=False),
    SensorDef("grid_voltage_l3_l1", REG_INPUT, 52, "u16", 0.1, 1, "V", "voltage", "measurement", enabled_default=False),
    SensorDef("eps_voltage_l2", REG_INPUT, 1072, "i16", 0.1, 1, "V", "voltage", "measurement", enabled_default=False),
    SensorDef("eps_power_l2", REG_INPUT, 1074, "u32", 0.1, 1, "W", "power", "measurement", enabled_default=False),
    SensorDef("eps_voltage_l3", REG_INPUT, 1076, "i16", 0.1, 1, "V", "voltage", "measurement", enabled_default=False),
    SensorDef("eps_power_l3", REG_INPUT, 1078, "u32", 0.1, 1, "W", "power", "measurement", enabled_default=False),
)

SPH_TL3_PROFILE = DeviceProfile(
    key="sph_tl3",
    name="SPH TL3 series (hybrid, 3-phase)",
    sensors=SPH_SENSORS + SPH_TL3_EXTRA_SENSORS,
    enums=SPH_ENUMS,
    faults=SPH_FAULTS,
    numbers=SPH_NUMBERS,
    selects=SPH_SELECTS,
    switches=SPH_SWITCHES,
    firmware_register=88,
    serial_registers=(23, 5),
)

PROFILES: dict[str, DeviceProfile] = {
    "sph": SPH_PROFILE,
    "sph_tl3": SPH_TL3_PROFILE,
}


def profile_for_phase_count(phases: int) -> str:
    """Pick the best profile key for a detected output phase count."""
    return "sph_tl3" if phases == 3 else "sph"
