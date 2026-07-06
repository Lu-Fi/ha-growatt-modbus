## Growatt SPH Modbus v0.7.0

First public release. Local Modbus integration for Growatt SPH hybrid inverters — no cloud required.

### Highlights
- **Serial RTU & Modbus TCP**, multiple inverters per bus, automatic model detection (1-phase SPH / 3-phase SPH TL3)
- **80+ entities**: PV, grid (per phase on TL3), battery, EPS, energy counters, decoded fault registers, BMS health (SOH, cycles, cell delta)
- **Time-window control** matching Growatt's Setting dialog: Grid First & Battery First rates, stop SoCs, AC charging and 3 schedulable windows each — automate charging on dynamic tariffs
- **Writable settings**: power switch, export limit (zero feed-in), Load First stop SoC, max active power
- **Fault notifications** via any notify entity (DE/EN), warnings separated from real faults
- **Three configurable polling intervals** (live values / energy counters / settings)
- English & German translations, HACS-ready, verified against real hardware (SPH 4600)

See [CHANGELOG.md](CHANGELOG.md) for the full history since 0.2.0.

### Installation
HACS → Custom repositories → `https://github.com/Lu-Fi/ha-growatt-modbus` (Integration)
