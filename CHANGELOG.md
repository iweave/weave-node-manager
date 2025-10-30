# Changelog

## [Unreleased]

### Added
- Comma-separated service_name support for all force actions (start, stop, upgrade, remove, disable)
- Comma-separated service_name support for survey force action
- `parse_service_names()` utility function for shared parsing logic
- Specific node surveying with detailed success/failure reporting
- Comprehensive test suite for comma-separated node operations (7 new tests)

### Changed
- Force action methods now return multi-node format with detailed success/failure reporting
- Start, stop, upgrade, remove, and disable actions now support comma-separated node lists
- Survey action now accepts optional `--service_name` for targeted surveying
- Optimized surveying: checks metadata first, skips metrics for stopped nodes
- Moved `ADD_REPORTS.md` to `docs/` directory

### Fixed
- Eliminated duplicate service name parsing code in reports.py and executor.py
- Updated all force action tests to match new multi-node return format (49 tests passing)

### Documentation
- Added `docs/FORCE-SURVEY-UPDATE.md` with usage examples and implementation details

## Previous Changes
See git history for earlier changes.
