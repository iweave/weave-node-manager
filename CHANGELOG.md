# Changelog

## [Unreleased]

## [0.3.14] - 2025-12-14

### Fixed
- **Env format quoting (as easy as pie!)**: Added proper quoting for paths and arguments with special characters in env format outputs
  - Machine-config report now quotes: `NODE_STORAGE`, `ENVIRONMENT`, `START_ARGS`, `ANTNODE_PATH`, `DBPATH`
  - Machine-metrics report now quotes: `ANTNODE` binary path
  - Ensures shell-safe parsing of paths with spaces or special characters
  - Examples:
    - `NODE_STORAGE="/path/with spaces/node/"` (properly quoted)
    - `ANTNODE="/usr/local/bin/antnode"` (properly quoted)
  - Fixes issues when sourcing env output: `eval $(wnm --report machine-config --report_format env)`
  - Added comprehensive test coverage for quoted fields and paths with spaces

## [0.3.13] - 2025-12-13

### Fixed
- **Machine-metrics env format**: Fixed `NODES_BY_VERSION` value to be env-safe by quoting dictionary values
  - Dictionary values like `NODES_BY_VERSION` are now properly quoted: `NODES_BY_VERSION="{'0.4.7': 3}"`
  - Numeric values remain unquoted for proper type handling: `CPU=45.2`, `NODES_RUNNING=5`
  - Ensures compatibility with `eval $(wnm --report machine-metrics --report_format env)` in shell scripts

## [0.3.12] - 2025-12-13

### Added
- **Environment variable format for machine-metrics report**: Added `env` output format support for `--report machine-metrics`
  - New format option: `--report machine-metrics --report_format env`
  - Outputs system metrics as shell environment variables in `UPPER_CASE_KEY=value` format
  - Enables using metrics in shell scripts with `eval $(wnm --report machine-metrics --report_format env)`
  - Provides access to all metrics as shell variables: `$CPU_PERCENT`, `$MEM_PERCENT`, `$TOTAL_NODES`, etc.
  - Consistent with existing `env` format support for `machine-config` report
  - Documentation includes comprehensive examples:
    - Loading metrics into current shell environment
    - Building monitoring scripts with threshold checks
    - Conditional actions based on system metrics
    - Combining config and metrics for intelligent decision-making

## [0.3.11] - 2025-12-13

### Changed
- **Test organization**: Reorganized test files for better structure
  - Moved `test_antctl_integration.py` from root to `scripts/` directory (manual integration test)
  - Converted `test_concurrent_ops.py` to pytest format and merged into `tests/test_decision_engine.py`
  - Added new `TestDecisionEngineConcurrency` test class with comprehensive concurrent operations tests
  - All concurrent operations functionality now has proper automated test coverage

## [0.3.10] - 2025-12-13

### Added
- **JSON output shortcut**: Added `--json` flag as a convenient shortcut for `--report_format json`
  - New `--json` command-line flag for requesting JSON output format
  - Equivalent to `--report_format json` but shorter and easier to type
  - Compatible with antctl command syntax for users familiar with that tool
  - Works with all report types: `node-status`, `node-status-details`, `machine-config`, `machine-metrics`
  - Examples:
    - `wnm --report node-status --json`
    - `wnm --report machine-config --json`
    - `wnm --report machine-metrics --json`

## [0.3.9] - 2025-12-12

### Changed
- **Changelog documentation**: Filled in missing release notes for versions 0.3.0 through 0.3.7
  - Added v0.3.7: Configuration documentation corrections
  - Added v0.3.5: Environment variable format for machine config report
  - Added v0.3.4: Action delay feature and migration fixes
  - Added v0.3.3: Critical database migration bug fixes
  - Added v0.3.2: Migration error handling improvements
  - Added v0.3.1: Lightweight config update action (nullop/update_config)
  - Added v0.3.0: Concurrent operations support (major feature)
  - Complete changelog coverage from v0.2.0 through v0.3.9

## [0.3.8] - 2025-12-12

### Added
- **Non-persistent survey delay override**: Added `--this_survey_delay` parameter for temporary survey delay adjustments
  - New `--this_survey_delay` command-line flag accepting milliseconds (no default)
  - Environment variable: `THIS_SURVEY_DELAY`
  - Temporary override for `--survey_delay` that applies only to current execution
  - Does not update database value (non-persistent)
  - Takes precedence over `--survey_delay` when specified

## [0.3.7] - 2025-12-12

### Fixed
- **Configuration documentation**: Corrected config file paths in documentation to reflect actual defaults
  - Updated README.md and USER-GUIDE-PART3.md with accurate config file locations
  - Changed from platform-specific paths to actual configargparse defaults
  - Config files: `~/.local/share/wnm/config`, `~/wnm/config`, or `-c/--config`

## [0.3.6] - 2025-12-12

### Fixed
- **Immutable settings validation**: Changed validation logic to only error when values are different
  - `--port_start`, `--metrics_port_start`, and `--process_manager` can now be safely included in config files
  - Error only raised when provided values differ from database (not just when present)
  - Improved error messages showing old and new values: "port_start (trying to change from 55 to 56)"
  - More explicit and maintainable validation code
  - Allows users to document complete cluster configuration in config files

## [0.3.5] - 2025-12-11

### Added
- **Environment variable format for machine config**: New `env` output format for `--report machine-config`
  - Outputs configuration in shell environment variable format (`UPPER_CASE_KEY=value`)
  - Suitable for sourcing in shell scripts: `eval $(wnm --report machine-config --report_format env)`
  - Can be saved to file: `wnm --report machine-config --report_format env > config.env`
  - Added to `--report_format` parameter choices alongside `text` and `json`

## [0.3.4] - 2025-12-11

### Added
- **Action delay feature**: Added configurable delays between node operations to reduce system load
  - New `--action_delay` parameter (milliseconds between operations, default: 0)
  - Environment variable: `ACTION_DELAY`
  - New `--this_action_delay` for temporary override (non-persistent)
  - New `--interval` alias for antctl compatibility
  - Implemented delay enforcement in ActionExecutor for all node operations
  - Database migration: `67fe02809d26_add_action_delay.py`

### Fixed
- **Database migration handling**: Fixed critical issues preventing proper migration execution
  - Migration command now runs before config loading
  - Skip machine_config loading when running `wnm-db-migration`
  - Prevents "unable to open database file" errors during migration

## [0.3.3] - 2025-12-11

### Fixed
- **Critical database migration bugs**: Fixed three critical issues preventing proper migration handling
  - **Database URL override**: `alembic/env.py` now checks if URL is already configured before setting default
  - **Legacy database auto-stamping**: Now correctly detects legacy databases (with data but no alembic_version)
  - **Migration detection**: `has_pending_migrations()` now correctly returns True for legacy databases
  - **Error messaging**: Added specific instructions for stamping legacy databases with clear guidance

## [0.3.2] - 2025-12-11

### Fixed
- **Migration error handling**: Improved handling when Alembic migration history has multiple heads
  - Catches `CommandError` when multiple heads are detected
  - Returns all heads as list from `get_head_revision()`
  - Provides clear user-friendly error message explaining the issue
  - Shows which heads are present and directs users to update installation
  - Prevents crash when running with branched migration history

## [0.3.1] - 2025-12-11

### Added
- **Lightweight config update action**: New `nullop`/`update_config` force action for quick config changes
  - Addressable as either `--force_action nullop` or `--force_action update_config`
  - Bypasses decision engine and metrics collection for minimal resource usage
  - Only loads configuration and applies parameter changes to database
  - Supports dry-run mode for testing config changes
  - Example: `wnm --force_action nullop --node_cap 30`
  - Example: `wnm --force_action update_config --cpu_less_than 60 --dry_run`
  - Documentation added to USER-GUIDE-PART3.md

## [0.3.0] - 2025-12-10

### Added
- **Concurrent operations support**: Aggressive concurrent operations for powerful machines
  - New global limit: `--max_concurrent_operations` (default: 1)
  - Per-operation limits: `--max_concurrent_upgrades`, `--max_concurrent_starts`, `--max_concurrent_removals` (default: 1 each)
  - Aggressive scaling: jumps to capacity immediately each cycle
  - Respects both per-type and global concurrency limits
  - Honors actual node availability (no impossible actions)
  - Each action selects different node (no duplicates)
  - Backward compatible: defaults to 1 (conservative behavior)
  - Database migration: `00dd80bcd645_add_max_concurrent_operations.py`
  - Example: `wnm --max_concurrent_upgrades 4 --max_concurrent_starts 4 --max_concurrent_operations 8`

### Changed
- **Documentation updates**: Updated README.md, CLAUDE.md, and USER-GUIDE for concurrent operations
  - Added conservative, aggressive, and very aggressive configuration examples
  - Clarified default single-operation behavior

## [0.2.0] - 2025-11-20

### Fixed
- **Alembic migration chain**: Fixed branched migration tree by updating `survey_delay` migration parent
  - Migration `fa0ca0abff5c` (add_survey_delay_to_machine) now correctly revises `3249fcc20390` instead of `44f23f078686`
  - Resolves "multiple heads" error in Alembic migration history
  - Creates proper linear migration chain from baseline through all schema changes
  - Ensures `alembic upgrade head` runs correctly without branch conflicts

## [0.1.10] - 2025-11-20

### Added
- **Survey delay feature for load distribution**: Added `--survey_delay` parameter to spread out load when surveying nodes
  - New `--survey_delay` command-line flag accepting milliseconds (default: 0, no delay)
  - Environment variable: `SURVEY_DELAY`
  - Inserts configurable delay between each node survey to reduce server load spikes
  - Applies to both automatic surveys (decision engine) and forced surveys (`--force_action survey`)
  - Delay inserted BETWEEN nodes, not after the last node (optimized)
  - Recommended values: 100-500ms for servers with 20+ nodes
  - Added `survey_delay` field to Machine model (Integer, default: 0)
  - Database migration: `fa0ca0abff5c_add_survey_delay_to_machine.py`
  - Documentation added to `docs/USER-GUIDE-PART3.md` section 3.3
  - Example usage: `wnm --survey_delay 250` for 250ms delay between node surveys

## [0.1.9] - 2025-11-19

### Fixed
- **Database migration documentation**: Updated `docs/USER-GUIDE-PART3.md` section 3.7 with comprehensive database migration guide
  - Added step-by-step migration process (backup → run migration → verify)
  - Added examples of migration output for all scenarios (needed, successful, already up-to-date)
  - Added troubleshooting section for common migration issues
  - Added best practices for safe database migrations
  - Documented automatic detection and new database initialization behavior

## [0.1.8] - 2025-11-19

### Added
- **InfluxDB Resources Report Export Examples**: Added comprehensive documentation for exporting `influx-resources` report to NTracking
  - Added new section "InfluxDB Resources Report Export Examples" in `docs/USER-GUIDE-PART3.md`
  - Linux example for local Telegraf installations writing to `/tmp/influx-resources/`
  - macOS example for remote Telegraf via SSH to VM (e.g., `ssh xdntracking tee /tmp/influx-resources/influx-resources`)
  - Cron automation examples for both Linux and macOS scenarios with proper PATH configuration
  - Documentation of integration with NTracking technology stack
  - Notes on using `-q` flag, `--force_action survey`, and SSH key authentication

## [0.1.7] - 2025-11-18

### Fixed
- **Test fixtures missing required model parameters**: Fixed test failures caused by fixtures not including new required fields
  - Added `delay_restart` and `rpc_port_start` to `sample_machine_config` in `conftest.py`
  - Added `rpc_port` to `sample_node_config` in `conftest.py`
  - Added `antnode_path` to `sample_machine_config` in `conftest.py`
  - Fixed `test_reports.py` local fixtures to include `delay_restart`, `rpc_port_start`, and `rpc_port` fields
  - All 246 tests now pass (was 7 failed, 64 errors)

## [0.1.6] - 2025-11-18

### Added
- **Verbose output control flags**: Added granular control over INFO-level logging
  - `--show_machine_config`: Log machine configuration on each run (default: disabled)
  - `--show_machine_metrics`: Log system metrics on each run (default: disabled)
  - `--show_decisions`: Log decision engine features on each run (default: disabled)
  - All three flags also enabled when `-v` (verbose) flag is set
- **New report types**: Added two new report options for on-demand data access
  - `--report machine-config`: Output machine configuration with database path (text, JSON, or env format)
  - `--report machine-metrics`: Output current system metrics (text or JSON)

### Changed
- **Reduced default logging verbosity**: Machine config, system metrics, and decision engine features no longer logged by default
  - Previously these were always logged at INFO level on every run
  - Now requires explicit `--show_*` flags or `-v` to display
  - Cleaner output for production cron jobs and scripts
  - Data still accessible via new report types when needed

## [0.1.5] - 2025-11-18

### Fixed
- **Critical: Logging system completely broken**: Fixed logging not outputting INFO/DEBUG messages
  - Root cause: Alembic imports at module level triggered Python's default logging auto-configuration with WARNING level
  - Moved all alembic imports inside their respective functions to prevent premature logging configuration
  - Added try/finally block to always restore logging level even if exceptions occur during database stamping
  - Disabled SQLAlchemy's `echo=True` which was interfering with logging configuration
  - Logging now properly respects `--loglevel` setting (info, debug, warning, error)
  - Output format now shows full level name ("INFO" instead of truncated "WARNI")

## [0.1.4] - 2025-11-17

### Fixed
- **Critical: Exit code bug**: Fixed program always exiting with code 1 (failure) even on success
  - Changed `sys.exit(1)` to `sys.exit(0)` at end of main() function
  - Now properly returns 0 on successful execution
- **Antctl node import**: Fixed antctl node import to correctly extract node IDs from service names
  - Added regex-based `_extract_node_id()` helper that handles "antnode1", "antnode0001", etc.
  - Previously failed to detect port ranges because it couldn't parse "antnode1" as node ID 1
  - Now successfully imports antctl nodes with proper port configuration detection
- **Antctl RPC port parsing**: Added RPC port extraction from antctl status JSON
  - Parses `rpc_socket_addr` field (e.g., "127.0.0.1:30001" → 30001)
  - Ensures imported nodes have complete port information

### Changed
- **Reduced logging noise**: Changed several warnings to debug-level messages
  - Port detection warnings now debug-level (only visible with `--loglevel DEBUG`)
  - Database stamping failures now debug-level
  - Cleaner output during initialization for users
- **Import feedback**: Added explicit success message showing number of imported nodes
  - Now logs "Successfully imported N node(s)" at INFO level
  - Better visibility of import operation results

## [0.1.3] - 2025-11-17

### Added
- **`--import` flag for explicit node import**: Added new `--import` flag to explicitly request importing existing nodes during initialization
  - Used with `--init` to import existing nodes from process manager (systemd, launchd, antctl)
  - Example: `wnm --init --import --rewards_address <addr> --process_manager launchd+user`
  - Prevents confusing warnings on fresh installations that don't have existing nodes

### Changed
- **Node import now opt-in during initialization**: Changed initialization behavior to only import existing nodes when explicitly requested
  - Previously, `--init` would automatically survey for existing nodes with any process manager, producing warnings on fresh installs
  - Now only surveys when `--migrate_anm` or `--import` flags are provided
  - Fresh installations with `--init` (no import flags) now cleanly initialize without warnings
  - Existing behavior with `--migrate_anm` unchanged

## [0.1.2] - 2025-11-17

### Added
- **Database rebuild capability for systemd and launchd process managers**: Added ability to rebuild database from existing system configuration
  - Extended survey trigger to support `systemd`, `systemd+user`, `systemd+sudo`, `launchd`, `launchd+user`, and `launchd+sudo` process managers
  - Users can now run `wnm --init --process_manager <type> --rewards_address <addr>` to rebuild database from existing nodes
  - Automatically detects port configuration from discovered nodes (reverse-engineers `port_start` from node 1's port)
  - Preserves node IDs from service names (e.g., `antnode0003.service` → node ID 3)
  - Handles non-sequential node IDs gracefully (gaps in numbering are normal)
  - Added `detect_port_ranges_from_nodes()` function in migration module to calculate port configuration
  - Automatically updates machine config database with detected port ranges
  - Useful for disaster recovery scenarios where database is lost but systemd/launchd services remain

### Fixed
- **Migration documentation clarity**: Updated USER-GUIDE to distinguish between:
  - `--migrate_anm` flag: Only for actual anm installations (checks for `/var/antctl/system`)
  - Plain `--init` with process manager: For rebuilding wnm clusters or importing existing systemd/launchd nodes

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
