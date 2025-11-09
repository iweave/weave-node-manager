# Changelog

## [Unreleased]

## [0.0.15] - 2025-11-09

### Fixed
- **LaunchdManager factory compatibility**: Fixed `LaunchdManager.__init__()` to accept `mode` parameter
  - Resolves `TypeError: LaunchdManager.__init__() got an unexpected keyword argument 'mode'` error
  - Adds infrastructure for future `launchd+sudo` support (system daemons in `/Library/LaunchDaemons/`)
  - Default mode remains user-level (`~/Library/LaunchAgents/`)
  - Maintains compatibility with process manager factory pattern
- **LaunchdManager plist recreation**: Fixed `start_node()` to recreate missing plist files
  - Automatically regenerates plist file if missing when starting a stopped node
  - Resolves "Plist file not found" errors when database and launchd are out of sync
  - Handles cleanup scenarios where plist files were removed but node directories remain

## [0.0.14] - 2025-11-09

### Added
- **`--version` flag**: Display version and exit without database or lock file checks
  - Bypasses all initialization for reliability
  - Useful for quick version verification in scripts and automation
- **`--remove_lockfile` flag**: Remove stale lock file and exit without database checks
  - Bypasses all initialization for reliability
  - Useful for recovery when lock file is stuck (e.g., after crash)

### Changed
- **Terminology consistency**: Renamed `LaunchctlManager` to `LaunchdManager` throughout codebase
  - Factory key changed from `"launchctl"` to `"launchd"`
  - Node survey method field changed from `"launchctl"` to `"launchd"`
  - All documentation and tests updated
  - Naming now consistently reflects the macOS daemon (launchd) rather than the CLI tool (launchctl)
  - Matches naming pattern of other managers (SystemdManager, SetsidManager)

## [0.0.13] - 2025-11-06

### Fixed
- **systemd+sudo path configuration**: Fixed path selection to use system-wide paths (`/var/antctl/`) when using `systemd+sudo` mode instead of user paths
  - Added `_detect_process_manager_mode()` function to detect mode from command line args, environment variables, or existing database
  - Path selection now based on process manager mode (sudo vs user) instead of IS_ROOT check
  - Supports custom database paths via `--dbpath` or `DBPATH` environment variable with proper mode detection
  - Fixed database default path from relative `sqlite:///colony.db` to absolute `DEFAULT_DB_PATH`
- **Node manager_type preservation**: Fixed `executor.py` to use `machine_config["process_manager"]` instead of `get_default_manager_type()` to preserve mode suffix (+sudo, +user)
  - Service files now correctly created in `/etc/systemd/system/` for systemd+sudo mode
  - Nodes inherit correct `manager_type` from machine config in database

### Added
- **Test coverage**: Added comprehensive tests for mode detection, path selection, and manager type preservation in `tests/test_config.py`
- Updated fixtures in `tests/conftest.py` to include `process_manager` field with mode suffix

## [0.0.12] - 2025-11-02

### Added
- **Named wallet support**: `--rewards_address` now accepts named wallets "faucet" and "donate" (case-insensitive)
  - `faucet` always resolves to the Autonomi community faucet address (constant)
  - `donate` resolves to `donate_address` from machine config (user-configurable)
  - Enables easy donation to the project faucet or custom donation addresses
- **Weighted wallet distribution**: Support for comma-separated wallet lists with optional weights
  - Format: `wallet1:weight1,wallet2:weight2,...`
  - Random weighted selection per node creation
  - Mix Ethereum addresses with named wallets
  - Example: `--rewards_address "0xYourAddress:100,faucet:1,donate:10"`
  - Allows flexible reward distribution across multiple wallets
- **New `FAUCET` constant**: Added to `common.py` for the Autonomi community faucet address
- **Wallet validation**: Comprehensive validation of rewards_address during init and updates
- **New `wallets.py` module**: Core wallet resolution and weighted distribution logic
  - `resolve_wallet_name()`: Resolve named wallets to addresses
  - `parse_weighted_wallets()`: Parse comma-separated weighted wallet lists
  - `select_wallet_for_node()`: Random weighted wallet selection
  - `validate_rewards_address()`: Validate wallet string format
- **Comprehensive test suite**: 38 tests for wallet resolution and weighted distribution

### Changed
- **rewards_address configuration**: Now supports single addresses, named wallets, and weighted lists
- **Node creation**: Nodes now randomly select wallet from weighted distribution on creation
- **Documentation**: Updated README.md with wallet configuration examples and usage

### Fixed
- **node_storage path validation**: `get_machine_metrics()` now creates missing node_storage directory before checking disk usage
  - Prevents `FileNotFoundError` crash when node_storage path doesn't exist
  - Logs warning when directory is auto-created to alert misconfiguration
  - Fixes issue where database initialized with wrong platform path causes startup failure

## [0.0.11] - 2025-01-30

### Fixed
- **SystemdManager non-root support**: SystemdManager now properly supports non-root users
  - User services stored in `~/.config/systemd/user/` instead of `/etc/systemd/system/`
  - No sudo required for mkdir, cp, rm, or systemctl operations
  - Uses `systemctl --user` commands for user services
  - Automatically uses null firewall for non-root users (no sudo needed)
  - No chown operations for user services (files owned by current user)
  - User= field omitted in service files for user services (runs as invoking user)

## [0.0.10] - 2025-01-30

### Added
- **`--count` parameter** for batch forced actions (add, remove, start, stop, upgrade)
- Comma-separated service_name support for all force actions (start, stop, upgrade, remove, disable)
- Comma-separated service_name support for survey force action
- `parse_service_names()` utility function for shared parsing logic
- Specific node surveying with detailed success/failure reporting
- Comprehensive test suite for count parameter functionality (7 new tests)
- Comprehensive test suite for comma-separated node operations (7 new tests)

### Changed
- **Batch operations**: Add/remove/start/stop/upgrade multiple nodes at once without delays
- **Smart node selection**: Uses `age` field for intelligent node selection:
  - `add`: Creates new nodes immediately
  - `remove`/`stop`: Selects youngest nodes (highest age values)
  - `start`/`upgrade`: Selects oldest nodes (lowest age values)
- Force action methods now return multi-node format with detailed success/failure reporting
- Start, stop, upgrade, remove, and disable actions now support comma-separated node lists
- Survey action now accepts optional `--service_name` for targeted surveying
- Optimized surveying: checks metadata first, skips metrics for stopped nodes
- Moved `ADD_REPORTS.md` to `docs/` directory
- **Test fixtures**: Updated to use production node naming format (`antnode0001.service`)

### Fixed
- Eliminated duplicate service name parsing code in reports.py and executor.py
- Removed test-specific logic from executor.py for cleaner production code
- Updated all force action tests to match new multi-node return format (56 tests passing)

### Documentation
- Added `docs/FORCE-SURVEY-UPDATE.md` with usage examples and implementation details

## Previous Changes
See git history for earlier changes.
