# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.10.1b1] - 2026-10-20

### Added (beta)

- **Support services for register problems** (first used for [#2](https://github.com/Lu-Fi/ha-growatt-modbus/issues/2): Battery First times revert to 00:00 on an SPH 10000TL3 BH-UP).
  - `growatt_modbus_lufi.dump_registers` reads the holding registers 0-124 and 1000-1124 raw (optionally the input registers too), falls back to single registers where a block is rejected, masks the serial number, and saves the result as `growatt_modbus_lufi_dump_<time>.json` in the Home Assistant config folder. Read-only.
  - `growatt_modbus_lufi.battery_first_write_test` **writes to the inverter**: it temporarily changes one Battery First window with single-register writes (function 6) and/or one block write of start, stop and enable (function 16), reads the values back immediately, after 5 s and after 60 s, then restores the original values. It does nothing unless the user switches on the `confirm` field, and the service description carries the warning. Report saved as `growatt_modbus_lufi_write_test_<time>.json`.
- `tests/test_diag_tools.py`: both tools against a simulated inverter, no Home Assistant needed (`python3 -m unittest discover -s tests`).

## [0.10.0] - 2026-09-05

### Fixed

- **A switch register holding any value other than 1 was shown as off.** `is_on` compared the raw register against `command_on`, so a setting that is tri-state on other Growatt series — the export limitation is documented as 0 = off, 1 = via RS485 meter, 2 = via CT — read as off while it was actually active, and the next "turn on" would have overwritten the working mode with 1. The switch state is now "anything that is not the off value"; what turn on/off write is unchanged.
- **A truncated Modbus response silently froze every register behind the truncation point.** pymodbus decodes whatever byte count the response frame announces and does not raise on a well formed but short reply, and each poll cycle starts from the previous cycle's values — so a gateway that returned fewer registers than requested left the rest on stale values forever, without the entities ever going unavailable. Block reads now compare the returned register count against the requested one and fail the poll if it differs.
- **Auto detection silently fell back to the SPH profile when it could not read the inverter type.** A failed read of holding registers 43/44 only logged a warning, so a device whose type was never established still got the SPH register map — including its write addresses. Detection failure and an implausible tracker/phase register now surface as a config-flow error asking the user to pick the series manually.
- **Any Growatt series that answered on the bus was set up with the SPH register map.** Setup now additionally probes input register 1000 (storage inverter mode, read on every poll of a real SPH) and refuses devices that do not provide the SPH storage register range, instead of exposing SPH write addresses on a series where those addresses mean something else.
- **Adding a second inverter probed the bus with its own extra connection.** Connection validation opened a fresh client even when another entry already held one for that serial port or TCP endpoint; many RS485-Ethernet gateways accept only one client, so validating the second inverter could fail or drop the first one's live connection. The flow now reuses the running client for that bus (and leaves it open).
- **A second entry on an already used serial port with a different baud rate failed forever after setup.** Entries on one port share a client opened at the first entry's baud rate, so the newcomer validated fine with its own client and then never reached its inverter. The config flow now rejects the mismatch with a clear error.
- The shared bus client's reference count leaked when platform setup raised, so it was never closed on the final unload.

### Changed

- Diagnostics now dump the real `polling_plan()` (per group: fast / energy / settings) instead of the unused `read_blocks()`, which had drifted from what is actually read. The dead `required_registers()`/`read_blocks()` pair was removed.
- The power factor sensor declares `device_class: power_factor`. Its decode (`raw / 10000`) is unchanged — the leading/lagging encoding of Growatt's 0-20000 range is not documented well enough to touch without hardware verification.
- The coordinator passes `config_entry` to `DataUpdateCoordinator` instead of relying on the deprecated ContextVar fallback.

## [0.9.1] - 2026-08-30

### Fixed

- Screenshot images on the HACS repository page were broken (`<img src="docs/...png">` relative paths, which github.com rewrites against the repo root but HACS's own README renderer does not). Switched to absolute `raw.githubusercontent.com` URLs.

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
