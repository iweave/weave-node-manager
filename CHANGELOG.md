# Changelog

## [Unreleased]

## [0.6.2] - 2026-02-17

### Changed
- Deferred `config.py` import-time side effects into explicit `initialize()` function

## [0.6.1] - 2026-02-16

### Changed
- Replaced repetitive `merge_config_changes()` if-blocks with data-driven field descriptors

## [0.6.0] - 2026-02-16

### Changed
- Extracted forced actions from `executor.py` into `forced_actions.py` module
- Fixed 4 broken tests

## [0.5.8] - 2026-02-15

### Changed
- Removed outdated archive docs, debug output files, scratch files, and runtime logs from repo; updated `.gitignore`
- Trimmed CHANGELOG and CLAUDE.md to reduce token count

## [0.5.7] - 2026-02-15

### Documentation
- Added `--enable_upgrade` to USER-GUIDE-PART3.md under a new "Automatic Upgrade Control" subsection in section 3.6

## [0.5.6] - 2026-02-14

### Changed
- **Automatic upgrades disabled by default**: Since `antnode` now performs its own self-upgrades, WNM's upgrade decision is skipped unless `--enable_upgrade` is explicitly passed
  - Add `--enable_upgrade` (env: `ENABLE_UPGRADE`) flag to opt back in to WNM-managed upgrades
  - `--force_action upgrade` is unaffected and continues to work regardless of this flag
  - No database schema changes; this is a non-persistent runtime option

## [0.5.5] - 2026-01-11

### Fixed
- Log warning when attempting to disable a named node that does not exist
- Always send a stop signal to the process manager when disabling a service, in case there is a flapping service

## [0.5.4] - 2026-01-11

### Fixed
- **DISABLED nodes no longer block node additions**: DISABLED nodes with outdated versions were causing `nodes_to_upgrade > 0` while no eligible nodes could be found, blocking new node additions indefinitely. Fixed `get_machine_metrics()` to exclude DISABLED nodes from upgrade counting; added `disabled_nodes` metric for visibility

## [0.5.3] - 2026-01-11

### Fixed
- **Force action validation extended to stop/start/upgrade/disable**: Whitespace-only `--service_name` input and all-nodes-failed cases now return a clear error instead of silently affecting unintended nodes

## [0.5.2] - 2026-01-11

### Fixed
- **Force remove node validation**: Invalid or non-existent `--service_name` values now return `status: "error"` instead of removing an unintended node

## [0.5.1] - 2026-01-11

### Fixed
- **Survey transitional state preservation**: Regular node surveys no longer overwrite UPGRADING, RESTARTING, or REMOVING states, preventing loss of delay timer tracking

## [0.5.0] - 2026-01-10

### Changed
- Version bumped to 0.5.0 to avoid confusion with Autonomi tool versions

## [0.4.9] - 2026-01-09

### Fixed
- AntctlZenManager upgrade support: fixed `'dict' object has no attribute 'antnode_path'` error during upgrade; AntctlZenManager now correctly uses antctl's built-in upgrade command

## [0.4.8] - 2026-01-07

### Fixed
- Process manager start node race condition: all managers now check the metadata port before attempting to start, preventing sync loss when a node finishes starting after the manager times out

## [0.4.7] - 2026-01-07

### Added
- `--force_action disable_config`: disables persistent boolean settings (e.g. `--antctl_debug`, `--no_upnp`) by setting them to False in the database

## [0.4.6] - 2026-01-07

### Fixed
- Model serialization: completed missing fields in `__repr__` and `__json__` for Machine, Container, and Node classes

## [0.4.5] - 2026-01-07

### Added
- `--highest_node_id_used`: node ID tracking for antctl managers to prevent port conflicts from ID reuse after node removal; automatically initialized during `--init` and reset during teardown

## [0.4.4] - 2026-01-06

### Added
- `--rust_backtrace`: passes `RUST_BACKTRACE` environment variable to antctl subprocess; accepts `1` or `full`

## [0.4.3] - 2026-01-05

### Added
- `--antctl_version`: pins antnode version for antctl managers; passes `--version` to both `antctl add` and `antctl upgrade`

## [0.4.2] - 2026-01-04

### Fixed
- AntctlZenManager: added `session.refresh(node)` after commit to prevent detached instance error when accessing node attributes

## [0.4.1] - 2025-12-31

### Fixed
- AntctlZenManager: use `session.merge()` instead of `session.add()` for detached node instances during `create_node()`

## [0.4.0] - 2025-12-30

### Added
- `antctl+zen` process manager: uses antctl defaults for paths, maintains explicit port control, parses antctl output to track actual paths

## [0.3.27] - 2025-12-28

### Fixed
- Antctl: extract JSON block from mixed debug/JSON stdout using regex; log stdout/stderr at DEBUG level for all antctl operations

## [0.3.26] - 2025-12-28

### Added
- `--antctl_debug`: adds `--debug` to all antctl commands; auto-enabled when `--loglevel DEBUG` is set

## [0.3.25] - 2025-12-16

### Added
- `--antctl_path`: explicit path to antctl binary; required for macOS cron where PATH is not inherited

## [0.3.23] - 2025-12-15

### Fixed
- Lock file cleanup now guaranteed via `atexit` and signal handlers (SIGTERM, SIGINT)

## [0.3.22] - 2025-12-14

### Fixed
- Node creation: metrics and RPC ports now use configured `metrics_port_start` and `rpc_port_start` instead of hardcoded constants

## [0.3.21] - 2025-12-14

### Added
- Port start settings now accept full port numbers (e.g. 55000) and normalize to thousands digit automatically

## [0.3.20] - 2025-12-14

### Fixed
- Running without `--init` on a missing database now exits with a helpful error instead of creating an empty broken database

## [0.3.19] - 2025-12-14

### Added
- `--report_format config`: outputs machine-config in lower_snake_case suitable for WNM config files

## [0.3.18] - 2025-12-14

### Changed
- `--init` now exits immediately after initialization; decision engine no longer runs during init

## [0.3.17] - 2025-12-14

### Fixed
- False reboot detection on first run after `--init`; `last_stopped_at` now initialized to current system start time

## [0.3.16] - 2025-12-14

### Changed
- `--init` now emits `status: "system-initialized"` instead of `"system-rebooted"`; node survey skipped unless `--import` or `--migrate_anm` is provided

## [0.3.15] - 2025-12-14

### Fixed
- Decision engine tests: added missing concurrent operations config keys and metrics fields

## [0.3.14] - 2025-12-14

### Fixed
- `--report machine-config --report_format env` now quotes paths with spaces or special characters

## [0.3.13] - 2025-12-13

### Fixed
- `--report machine-metrics --report_format env`: `NODES_BY_VERSION` now quoted for shell safety

## [0.3.12] - 2025-12-13

### Added
- `--report machine-metrics --report_format env`: output system metrics as shell environment variables

## [0.3.11] - 2025-12-13

### Changed
- Moved `test_antctl_integration.py` to `scripts/`; merged concurrent ops tests into `test_decision_engine.py`

## [0.3.10] - 2025-12-13

### Added
- `--json` flag as shortcut for `--report_format json`

## [0.3.9] - 2025-12-12

### Changed
- Filled in missing changelog entries for v0.3.0–v0.3.7

## [0.3.8] - 2025-12-12

### Added
- `--this_survey_delay`: non-persistent per-run override for `--survey_delay`

## [0.3.7] - 2025-12-12

### Fixed
- Config file path documentation corrected to match actual configargparse defaults

## [0.3.6] - 2025-12-12

### Fixed
- Immutable settings (`--port_start`, `--metrics_port_start`, `--process_manager`) only error when value differs from database, allowing them in config files

## [0.3.5] - 2025-12-11

### Added
- `--report machine-config --report_format env`: output configuration as shell environment variables

## [0.3.4] - 2025-12-11

### Added
- `--action_delay` / `--this_action_delay` / `--interval`: configurable delay between node operations

### Fixed
- Database migration command now runs before config loading; prevents errors during migration

## [0.3.3] - 2025-12-11

### Fixed
- Critical Alembic migration bugs: database URL override, legacy database auto-stamping, migration detection

## [0.3.2] - 2025-12-11

### Fixed
- Migration error handling when Alembic history has multiple heads

## [0.3.1] - 2025-12-11

### Added
- `--force_action nullop` / `update_config`: lightweight config update that bypasses the decision engine

## [0.3.0] - 2025-12-10

### Added
- Concurrent operations: `--max_concurrent_upgrades`, `--max_concurrent_starts`, `--max_concurrent_removals`, `--max_concurrent_operations`

## [0.2.0] - 2025-11-20

### Fixed
- Alembic migration chain: fixed branched migration tree causing "multiple heads" error

## [0.1.10] - 2025-11-20

### Added
- `--survey_delay`: configurable delay in milliseconds between node surveys

## [0.1.9] - 2025-11-19

### Fixed
- Database migration documentation updated in USER-GUIDE-PART3.md

## [0.1.8] - 2025-11-19

### Added
- InfluxDB resources report export documentation and cron examples

## [0.1.7] - 2025-11-18

### Fixed
- Test fixtures updated with missing required model fields (`delay_restart`, `rpc_port_start`, `rpc_port`, `antnode_path`)

## [0.1.6] - 2025-11-18

### Added
- `--show_machine_config`, `--show_machine_metrics`, `--show_decisions` flags for opt-in verbose logging
- `--report machine-config` and `--report machine-metrics` report types

### Changed
- Machine config, system metrics, and decision features no longer logged by default; require explicit flags or `-v`

## [0.1.5] - 2025-11-18

### Fixed
- Logging system broken by Alembic imports triggering Python's default logging auto-configuration; moved all alembic imports inside functions

## [0.1.4] - 2025-11-17

### Fixed
- Exit code bug: program was always exiting with code 1
- Antctl node import: regex-based node ID extraction from service names
- Antctl RPC port parsing from `rpc_socket_addr` field

## [0.1.3] - 2025-11-17

### Added
- `--import` flag: explicit opt-in to importing existing nodes during `--init`

### Changed
- Node import during init is now opt-in; fresh installs no longer produce import warnings

## [0.1.2] - 2025-11-17

### Added
- Database rebuild from existing systemd/launchd services via `--init --process_manager <type>`

## [0.0.31] - 2025-11-17

### Added
- RPC port configuration: `--rpc_port_start`, `rpc_port` field on Node, `--rpc-port` passed to antctl

## [0.0.30] - 2025-11-17

### Fixed
- AntctlManager: `create_node()` passes `--path` to prevent binary re-download on every add; added `upgrade_node()` using antctl's built-in upgrade

## [0.0.29] - 2025-11-16

### Added
- `--antnode_path`: configurable source binary location (default: `~/.local/bin/antnode`)

### Fixed
- Node upgrade: stop node before copying binary to avoid "Text file busy" error

## [0.0.28] - 2025-11-16

### Fixed
- AntctlManager: `create_node()` now calls `start_node()` after creation so nodes become active immediately

## [0.0.27] - 2025-11-16

### Fixed
- `no_upnp` setting no longer reset to False on every run
- AntctlManager: network argument passed correctly

### Changed
- `--process_manager` restricted to `--init` only

## [0.0.26] - 2025-11-16

### Changed
- Replaced print statements with proper logging calls throughout application code

## [0.0.25] - 2025-11-16

### Added
- `--report influx-resources`: InfluxDB line protocol output for NTracking integration
- Extended node metrics from Prometheus endpoint (13 new fields)
- `-q/--quiet` flag; `--loglevel` now functional; Alembic migration system

## [0.0.24] - 2025-11-15

### Added
- `--no_upnp`: configurable UPnP control across all process managers

## [0.0.21] - 2025-11-14

### Added
- `antctl+user` / `antctl+sudo` process manager with full antctl CLI integration

## [0.0.20] - 2025-11-13

### Changed
- Removed `--teardown` flag; use `--force_action teardown --confirm` instead

## [0.0.19] - 2025-11-13

### Changed
- `ProcessManager.create_node()` returns `NodeProcess` metadata instead of bool

## [0.0.18] - 2025-11-11

### Added
- USER-GUIDE-PART3.md: complete configuration reference

### Changed
- Conservative default thresholds: `mem_less_than` 70→60%, `mem_remove` 90→75%, `hd_less_than` 70→75%

## [0.0.17] - 2025-11-09

### Fixed
- `--dbpath` tilde and environment variable expansion

## [0.0.16] - 2025-11-09

### Fixed
- Test collection failure when database unavailable; platform detection in tests

## [0.0.15] - 2025-11-09

### Fixed
- LaunchdManager: accepts `mode` parameter; `start_node()` recreates missing plist files

## [0.0.14] - 2025-11-09

### Added
- `--version` flag; `--remove_lockfile` flag

### Changed
- Renamed `LaunchctlManager` to `LaunchdManager` throughout

## [0.0.13] - 2025-11-06

### Fixed
- `systemd+sudo` path selection; node `manager_type` preserved from machine config

## [0.0.12] - 2025-11-02

### Added
- Named wallets (`faucet`, `donate`) and weighted wallet distribution for `--rewards_address`

## Previous Changes
See git history for earlier changes.
