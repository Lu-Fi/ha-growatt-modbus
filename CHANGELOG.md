# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.9.0] - 2026-08-25

### Changed

- **BREAKING: domain renamed from `growatt_modbus` to `growatt_modbus_lufi`.** The `growatt_modbus` domain (and its `custom_components/growatt_modbus/` install path) was already claimed by two other HACS-listed integrations (`jacobbjerregaard/homeassistant-growatt-modbus`, `0xAHA/Growatt_ModbusTCP`); anyone with one of those installed and then this one would have silently overwritten it, with no way for HACS to warn them. Existing installs must remove the old config entry, replace `custom_components/growatt_modbus/` with `custom_components/growatt_modbus_lufi/`, restart, and re-add the integration with the same connection settings. Entity unique IDs are tied to the config entry, not the domain, so as long as the old entry is removed before the new one is added, entities are recreated under the same entity IDs and recorder history keeps lining up under those IDs.

### Fixed

- README listed a writable priority select (Load/Battery/Grid) that doesn't exist — the underlying holding register is read-only per the protocol, so `SPH_SELECTS` has always been empty and no select entity is ever created. Dropped the claim from the feature list.

## [0.8.1] - 2026-08-21

### Fixed
- **Fault notifications could fail silently.** The `notify.send_message` call in the coordinator's fault-change handler used the default `blocking=False`, so a real delivery failure happened in a detached background task the surrounding `try`/`except` never saw. Now calls with `blocking=True`, so a failure is at least logged instead of vanishing (same class of bug already fixed in the sibling `ha-em2go-pvsc` and `ha-lacrosse-jeelink` integrations).
- `hacs.json` didn't declare a Home Assistant floor. The in-tree `custom_components/growatt_modbus/brand/` icons only load on 2026.3+, so declared `"homeassistant": "2026.3.0"` explicitly instead of leaving it unbounded.

## [0.8.0] - 2026-07-06

### Added
- "Active faults" sensor: decoded names of all currently active fault
  bits in plain text ("OK" when clear)
- "Last fault" sensor: keeps the decoded fault names of the most recent
  fault with start/end timestamps, restored across restarts — so a
  fault can still be diagnosed after it cleared

## [0.7.0] - 2026-07-06

### Added
- Full time-window control matching Growatt's own Setting dialog:
  Grid First (discharge rate, stop SoC, 3 windows) and Battery First
  (charge rate, stop SoC, AC charging switch, 3 windows). Window starts
  and ends are native time entities, each window has an enable switch
  (holding 1070/1071, 1080-1088, 1090-1092, 1100-1108)

### Changed
- Integration renamed to "Growatt SPH Modbus" to avoid confusion with
  cloud-based Growatt integrations
- Priority is now a read-only enum sensor: holding 1044 is marked "R"
  in the protocol — the active mode results from the enabled time
  windows (Load First is the default outside any window). The previous
  priority select never had an effect and was removed.

## [0.6.1] - 2026-07-06

### Changed
- Replaced the "inverter time" timestamp sensor with a "clock drift"
  sensor (seconds, rounded to 5 s): it only changes state when the
  inverter clock actually drifts, so it no longer floods the logbook.
  The absolute inverter time remains available as an attribute.
- Clock sync uses a Modbus block write (fn 16) with a 7-register
  fallback including the weekday; the button is disabled by default
  because several SPH firmwares reject clock writes entirely

## [0.6.0] - 2026-07-05

### Added
- Real firmware versions (ASCII, holding 9–14) shown in the device info
  instead of only the modbus protocol version
- "Synchronize clock" button: writes the current HA local time to the
  inverter clock (holding 45–50) — Growatt clocks drift, and the
  inverter's internal daily counters depend on its clock; the log shows
  the previous inverter time on each sync
- "Inverter time" diagnostic sensor showing the inverter's internal
  clock, so drift is visible before it matters
- GitHub Actions workflow: hassfest + HACS validation on every push

## [0.5.0] - 2026-07-05

### Added
- Three independent, configurable polling intervals: live values
  (default 30 s), energy counters (default 300 s) and settings/holding
  registers (default 300 s) — all adjustable in the integration options
- Registers are grouped automatically: total/total_increasing sensors
  form the energy group, everything else stays in the live group

### Changed
- Replaces the fixed every-10th-cycle settings polling from 0.4.1

## [0.4.1] - 2026-07-05

### Changed
- Two-tier polling: holding registers (settings, serial number, limits)
  are now read only every 10th cycle instead of every cycle — input
  registers (live measurements) remain on the configured interval.
  Reduces bus traffic from 7 to 2 reads per typical cycle.
- After a write, the next refresh always re-reads the holding registers,
  so switches, numbers and selects confirm immediately.

## [0.4.0] - 2026-07-05

### Added
- BMS sensors (input registers 1082–1096): BMS SOC, battery voltage,
  current, temperature, max current, cell voltage delta, cycle count and
  SOH — disabled by default, since third-party BMSes may not fill them
- Battery temperature sensor (input register 1040), enabled by default
- Export limit switch (holding 122) and export limit rate number
  (holding 123, 0.1 % resolution) for zero feed-in setups
- ASCII serial number (holding 23–27) shown in the device info panel

### Fixed
- Temperature scale for registers 1040/1089: the protocol document
  claims 0.1 °C, real hardware sends whole °C (verified on SPH 4600)

## [0.3.0] - 2026-07-05

### Added
- Configurable fault notifications: new options `notify_enabled` and
  `notify_entity` (notify domain selector). Sends a message via
  `notify.send_message` when a real fault appears or clears, bilingual
  (DE/EN) based on the Home Assistant language
- Notification failures never interrupt polling

## [0.2.1] - 2026-07-05

### Changed
- Warning bits (PV1/PV2_VoltLowWarn, BoostDriver1/2Warn, WARN104) no
  longer trigger the fault binary sensor — prevents the nightly false
  "fault" caused by low PV voltage
- Fault register sensors now report three states: ok / warning / fault

### Added
- New binary sensor `any_warning` for warning bits

## [0.2.0] - 2026-07-05

### Added
- Initial release
- Serial RTU and Modbus TCP connections, multiple inverters per bus
  (shared, lock-protected client)
- Automatic inverter detection via holding registers 43/44 (device type
  code, tracker/phase count) with manual override
- Device profiles: SPH (1-phase, tested on SPH 4600) and SPH TL3
  (3-phase, per-phase grid/EPS sensors)
- 65+ entities: PV, grid, battery, EPS, energy counters, temperatures,
  decoded fault registers with active-fault attributes
- Writable settings: power switch, priority select (Load/Battery/Grid),
  minimum discharge SoC and maximum active power numbers
- Efficient block reads (registers grouped automatically), English and
  German translations, diagnostics download, HACS-ready structure
