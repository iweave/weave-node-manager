# Changelog

## [Unreleased]

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
