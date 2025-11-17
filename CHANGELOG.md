# Changelog

## [Unreleased]

## [0.0.31] - 2025-11-17

### Added
- **RPC port configuration**: Added support for configuring RPC server ports to prevent random port assignment
  - Added `RPC_PORT_BASE` constant (default: 30000) for RPC port calculation (`30000 + node_id`)
  - Added `rpc_port_start` field to Machine model (default: 30)
  - Added `rpc_port` field to Node model
  - AntctlManager now passes `--rpc-port` argument to antctl commands
  - Prevents antctl from randomly assigning RPC ports that could conflict with node and metrics port ranges

### Fixed
- **AntctlManager port assignment**: Fixed antctl process manager to properly pass `--node-port` to antctl
  - Added `rpc_port_start` to Machine.__json__() serialization (was missing, causing KeyError)
  - Added `antnode_path` to Machine.__json__() serialization (was missing, causing KeyError)
  - Improved debug logging with proper shell quoting for antctl commands
  - RPC server ports now controlled instead of randomly assigned (e.g., 51430 → 30001)

## [0.0.30] - 2025-11-17

### Fixed
- **AntctlManager binary path handling**: Fixed antctl process manager to properly use configured `antnode_path`
  - `create_node()` now passes `--path` argument with `machine_config.antnode_path` to prevent antctl from downloading binaries on every node add
  - Added `upgrade_node()` method that uses antctl's built-in upgrade command with `--path` argument
  - Unlike other process managers where wnm manually copies binaries, antctl handles stop/replace/restart internally
  - Executor now detects AntctlManager and delegates to its `upgrade_node()` method instead of manual binary copying
  - Prevents redundant binary downloads and ensures consistent binary management across all operations

## [0.0.29] - 2025-11-16

### Added
- **Configurable antnode binary path**: Added `--antnode_path` configuration option
  - Allows customization of source antnode binary location (default: `~/.local/bin/antnode`)
  - Stored in database as machine configuration setting
  - Can be set via command-line argument or `ANTNODE_PATH` environment variable
  - Used by upgrade process and node creation to locate source binary
  - Prevents config value from being clobbered by default value

### Fixed
- **Node upgrade binary replacement**: Fixed upgrade process to stop node before copying new binary
  - Previously tried to copy binary while node was running, causing "Text file busy" errors
  - Node process maintains active file lock on binary, preventing replacement
  - Now follows correct sequence: stop node → copy new binary → start node
  - Applies to SystemdManager, LaunchdManager, and SetsidManager (AntctlManager handles its own upgrades)
  - Added error recovery: attempts to restart with old binary if copy fails

## [0.0.28] - 2025-11-16

### Fixed
- **AntctlManager node startup**: Fixed antctl process manager to start nodes immediately after creation
  - Previously, `create_node()` only called `antctl add` but didn't start the node
  - Nodes remained in "Added" status until picked up by the next management cycle
  - Now calls `start_node()` after creation, matching behavior of SystemdManager and SetsidManager
  - Ensures nodes become active immediately after creation

## [0.0.27] - 2025-11-16

### Fixed
- **Critical: no_upnp config clobbering**: Fixed bug where `no_upnp` setting was reset to False on every wnm run
  - The `--no_upnp` flag uses `action="store_true"` which defaults to False when not provided
  - `merge_config_changes()` was incorrectly treating the False default as an explicit user choice
  - Now only updates database if flag is explicitly provided via `--no_upnp` command line or `NO_UPNP` env var
  - Prevents loss of UPnP configuration between runs
- **AntctlManager network argument**: Fixed network name not being specified correctly

### Changed
- **Restrict process_manager to init-only**: `--process_manager` can now only be set during `--init`
  - Similar to existing restrictions on `--port_start` and `--metrics_port_start`
  - Prevents accidental changes to process manager type on active clusters
  - Exits with error: "Cannot change port_start, metrics_port_start, or process_manager on an active machine"

## [0.0.26] - 2025-11-16

### Changed
- **Logging improvements**: Replaced print statements with proper logging calls throughout application code
  - Converted print() to logging.info(), logging.error(), or logging.debug() in `src/wnm/__main__.py` and `src/wnm/config.py`
  - Improved logging consistency for initialization errors, configuration changes, and action reporting
  - Retained print statements only for CLI output (--version flag, report output) and standalone scripts
  - All application code now uses the centralized logging facility controlled by --loglevel and --quiet flags

## [0.0.25] - 2025-11-16

### Added
- **InfluxDB line protocol reporting**: New `influx-resources` report type for direct InfluxDB integration
  - Outputs InfluxDB line protocol format with per-node metrics, totals, and network size
  - Compatible with NTracking's influx-resources.sh data structure
  - Command: `wnm --report influx-resources [--service_name node1,node2] --quiet`
- **Enhanced metrics collection**: Extended node metrics from Prometheus `/metrics` endpoint
  - Added 13 new database fields: `gets`, `puts`, `mem`, `cpu`, `open_connections`, `total_peers`, `bad_peers`
  - Added storage metrics: `rel_records`, `max_records`
  - Added economic metrics: `rewards` (TEXT for 18-decimal precision), `payment_count`, `live_time`
  - Added network metrics: `network_size`
  - All influx metrics automatically collected during node survey
- **Logging control improvements**:
  - `-q/--quiet` flag to suppress all output except errors (sets loglevel to ERROR)
  - `--loglevel` option now functional (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Logging configuration centralized in config.py based on command-line options
- **Alembic database migrations**: Proper migration system for schema changes
  - Baseline migration (eeec2af7114c) for November 6 schema
  - Migration 62bd2784638c: Add `log_dir` field to Node table (Nov 14)
  - Migration abc5afa09a61: Add `no_upnp` field to Machine table (Nov 15)
  - Migration ade8fcd1fc9a: Add 13 influx metrics fields to Node table (Nov 16)
  - Run with: `alembic upgrade head`

### Changed
- **Metrics collection**: `read_node_metrics()` now parses all InfluxDB-needed metrics from node's Prometheus endpoint
- **Database updates**: `update_node_from_metrics()` saves influx metrics for RUNNING nodes only
- **Node model**: Updated to store high-precision rewards as TEXT instead of Integer
- **Reports**: Added `generate_influx_resources_report()` convenience function

### Migration Instructions
For existing databases, run database migrations:
```bash
# Set your database path (optional, defaults to platform-specific location)
export WNM_DATABASE_URL="sqlite:////path/to/your/colony.db"

# Run migrations
alembic upgrade head
```

Migrations add:
- `log_dir` column to `node` table (nullable)
- `no_upnp` column to `machine` table (default: 1/enabled)
- 13 influx metrics columns to `node` table (all default to 0 or "0")

### Technical Details
- Rewards stored as TEXT to handle 18-decimal precision (e.g., Ethereum wei)
- CPU and memory stored × 100 for precision (e.g., 25.5% stored as 2550)
- Network size computed as average of all running nodes' estimates
- Uses `batch_alter_table` for SQLite compatibility

## [0.0.24] - 2025-11-15

### Added
- **Configurable UPnP control**: Added `--no_upnp` flag for admin-configurable UPnP behavior
  - New `no_upnp` field in Machine model (defaults to True/enabled for backwards compatibility)
  - Command-line argument `--no_upnp` and environment variable `NO_UPNP` support
  - All process managers (LaunchdManager, AntctlManager, SystemdManager, SetsidManager) conditionally add `--no-upnp` based on machine config
  - Replaces hardcoded `--no-upnp` in process managers with deployment-specific setting

### Changed
- **Process managers**: Updated all process managers to use machine config for UPnP setting
  - Previously hardcoded `--no-upnp` in LaunchdManager and AntctlManager
  - Now all managers respect `machine_config.no_upnp` setting with fallback to True for backwards compatibility

## [0.0.21] - 2025-11-14

### Added
- **AntctlManager process manager**: Full integration with antctl CLI for node management
  - Supports both `antctl+user` and `antctl+sudo` modes
  - Wraps all antctl commands: add, start, stop, remove, status, reset
  - Automatic discovery and import of existing antctl nodes via `antctl status --json`
  - Path overrides to maintain WNM's platform-specific conventions
  - Service name extraction and storage in `node.service` field
  - Comprehensive error handling and logging
- **Node schema enhancement**: Added `log_dir` field to Node model
  - Captures antctl's `log_dir_path` during node import
  - Optional field (nullable) for backward compatibility
  - Allows preservation of existing log directory paths when importing
- **CLI support**: Added `--process_manager antctl+user` and `--process_manager antctl+sudo` options
- **Auto-import on init**: When initializing with `antctl+user/antctl+sudo`, automatically discovers and imports existing antctl nodes
- **Documentation**: Comprehensive antctl integration guide in ANTCTL_README.md
  - Installation and setup instructions
  - Configuration examples and usage patterns
  - Multi-container scenario handling
  - Path configuration and overrides
  - Troubleshooting guide

### Changed
- **survey_machine()**: Now respects `machine_config.process_manager` when discovering nodes
  - Previously always used platform auto-detection
  - Now uses configured process manager first, falls back to auto-detection
- **Machine model**: Added default values for Docker-related fields in `__init__`
  - `max_node_per_container=200`
  - `min_container_count=1`
  - `docker_image="iweave/antnode:latest"`

### Fixed
- **Node import during initialization**: Antctl nodes are now properly imported during `--init`
  - Fixed condition to survey nodes when using antctl process manager
  - Ensures existing antctl-managed nodes are discovered on first run

## [0.0.20] - 2025-11-13

### Changed
- **BREAKING**: Removed `--teardown` flag (non-functional stub)
  - Use `--force_action teardown --confirm` instead
  - Eliminates needless duplication between two teardown paths
  - Teardown methods now require `--confirm` flag for safety

### Security
- **Force action teardown now requires confirmation**: `--force_action teardown` must be used with `--confirm` flag
  - Prevents accidental cluster destruction
  - Aligns safety requirements across all teardown methods

## [0.0.19] - 2025-11-13

### Changed
- **Process manager architecture**: Enhanced `create_node()` to return metadata for future manager support
  - Changed `ProcessManager.create_node()` signature from `-> bool` to `-> Optional[NodeProcess]`
  - All process managers now return `NodeProcess` with metadata (container_id, external_node_id, pid, status)
  - Executor automatically persists returned metadata to database (Container records, node service field)
  - Prepares infrastructure for upcoming antctl and s6overlay process managers

### Added
- **Database model enhancements** for s6overlay and antctl support:
  - `NodeProcess.external_node_id` field for storing external identifiers (e.g., antctl service names)
  - `Machine.max_node_per_container`, `Machine.min_container_count`, `Machine.docker_image` fields for s6overlay configuration
  - `Container.port_range_start/end` and `Container.metrics_port_range_start/end` fields for block-based port allocation
- **Executor integration**: Automatic persistence of process manager metadata
  - Docker/s6overlay: Creates Container records and links nodes via foreign key
  - Antctl: Stores external_node_id in node.service field

## [0.0.18] - 2025-11-11

### Added
- **Documentation: User Guide Part 3 - Configuration** (`docs/USER-GUIDE-PART3.md`)
  - Complete reference for all configuration options
  - Configuration system overview with priority layers
  - Detailed resource threshold documentation
  - Wallet configuration including weighted distribution
  - Network settings and port assignment
  - Advanced configuration options
  - Configuration examples and best practices

### Changed
- **Conservative default thresholds**: Updated resource threshold defaults for better stability
  - `--mem_less_than`: 70% → 60% (more conservative memory add threshold)
  - `--mem_remove`: 90% → 75% (earlier memory-based node removal)
  - `--hd_less_than`: 70% → 75% (more conservative disk add threshold)
  - Applied to both `load_anm_config()` and `define_machine()` functions
  - Provides better safety margins for production deployments

## [0.0.17] - 2025-11-09

### Fixed
- **Path expansion for `--dbpath`**: Fixed tilde (`~`) and environment variable expansion in database path
  - `--dbpath ~/colony.db` now correctly expands to full home directory path
  - Works for both command-line `--dbpath` argument and `DBPATH` environment variable
  - Supports both bare paths (`~/colony.db`) and sqlite URLs (`sqlite:///~/colony.db`)
  - Handles both `os.path.expanduser()` for tilde and `os.path.expandvars()` for variables like `$HOME`
  - Applied in three places: mode detection, DBPATH env var, and final options processing

## [0.0.16] - 2025-11-09

### Fixed
- **Test collection failure**: Fixed `config.py` to skip database initialization when `WNM_TEST_MODE` is set
  - Resolves `sqlite3.OperationalError: unable to open database file` during test collection
  - Tests now properly use isolated database fixtures from `conftest.py`
  - Added `WNM_TEST_MODE` check to `_SKIP_DB_INIT` flag alongside `--version` and `--remove_lockfile`
- **Platform detection in tests**: Fixed path selection tests to properly mock `platform.system()`
  - Changed from patching `wnm.config.PLATFORM` to `platform.system()` for module reload compatibility
  - Fixed `test_linux_sudo_paths`, `test_linux_user_paths`, and macOS path tests
  - Platform-specific tests now work correctly on both Linux and macOS
- **Test fixture compatibility**: Fixed executor manager type tests to use proper model fixtures
  - Tests now use `sample_machine_config` and `sample_node_config` fixtures with all required fields
  - Resolves `TypeError` from missing required Machine and Node model fields
- **Platform-specific test assertions**: Fixed `test_node_json` to validate platform-specific manager types
  - Changed from hardcoded "systemd" expectation to dynamic platform-specific validation
  - Now correctly validates `launchd+user` on macOS, `systemd+user` on Linux

### Testing
- **235 tests passing** on both macOS and Linux (11 platform-specific tests skipped on each)
- All test collection and execution issues resolved
- GitHub Actions CI passing on both platforms

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

### Documentation
- **Crontab PATH requirement**: Added prominent documentation about setting PATH in crontab
  - All cron examples now include `PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`
  - Prevents "FileNotFoundError: No such file or directory: 'sysctl'" when running from cron
  - Updated USER-GUIDE-PART1.md with IMPORTANT section and explanation

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
