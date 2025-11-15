# Force Survey Update - Comma-Separated Service Names

## Overview

Enhanced the `--force_action survey` command to support comma-separated lists of service names, allowing targeted surveying of specific nodes instead of always surveying all nodes.

## Changes Summary

### New Functionality

The survey force action now supports:
- **All nodes survey** (existing behavior): When `--service_name` is not specified
- **Specific nodes survey** (new feature): When `--service_name` contains one or more comma-separated node names

### Implementation Details

#### 1. Centralized Service Name Parsing (`src/wnm/utils.py`)

Created a shared `parse_service_names()` function to eliminate code duplication:

```python
def parse_service_names(service_name_str: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated service names.

    Args:
        service_name_str: Comma-separated service names (e.g., "antnode0001,antnode0003")

    Returns:
        List of service names, or None if input is None/empty
    """
```

This function is now used by:
- `reports.py` - for generating reports on specific nodes
- `executor.py` - for forced actions on specific nodes

#### 2. Survey-Specific Logic (`src/wnm/executor.py`)

Added `_survey_specific_nodes()` method that:
1. Checks metadata first for each node
2. If metadata fails (status == STOPPED):
   - Skips metrics check (avoids unnecessary network calls)
   - Uses 0's for all metrics values (uptime, records, shunned, connected_peers)
3. If metadata succeeds:
   - Fetches metrics normally
4. Skips database update if node is already marked as stopped

This approach optimizes performance by:
- Reducing redundant HTTP requests to stopped nodes
- Maintaining consistent data structure even when nodes are down

#### 3. Updated Method Signatures

**`_force_survey_nodes()`**:
```python
def _force_survey_nodes(
    self,
    service_name: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]
```

Now accepts an optional `service_name` parameter that can contain:
- `None` - surveys all nodes
- `"antnode0001"` - surveys single node
- `"antnode0001,antnode0003,antnode0005"` - surveys multiple nodes

#### 4. Response Format

**All nodes survey** (existing):
```json
{
  "status": "survey-complete",
  "node_count": 10
}
```

**Specific nodes survey** (new):
```json
{
  "status": "survey-complete",
  "surveyed_count": 3,
  "surveyed_nodes": ["antnode0001.service", "antnode0003.service", "antnode0005.service"],
  "failed_count": 0,
  "failed_nodes": null
}
```

**With failures**:
```json
{
  "status": "survey-complete",
  "surveyed_count": 2,
  "surveyed_nodes": ["antnode0001.service", "antnode0003.service"],
  "failed_count": 1,
  "failed_nodes": [
    {"service": "antnode0099", "error": "not found"}
  ]
}
```

## Usage Examples

### Basic Usage

```bash
# Survey all nodes (existing behavior)
python3 -m wnm --force_action survey

# Survey a single node
python3 -m wnm --force_action survey --service_name antnode0001

# Survey multiple specific nodes
python3 -m wnm --force_action survey --service_name antnode0001,antnode0003,antnode0005

# Whitespace is tolerated
python3 -m wnm --force_action survey --service_name "antnode0001, antnode0003, antnode0005"
```

### With Reports

Survey specific nodes before generating a report:

```bash
# Survey and report on specific nodes
python3 -m wnm --force_action survey \
  --service_name antnode0001,antnode0003 \
  --report node-status

# Survey and get detailed report in JSON format
python3 -m wnm --force_action survey \
  --service_name antnode0001,antnode0003 \
  --report node-status-details \
  --report_format json
```

### Dry Run

Test without making changes:

```bash
# Dry run survey of specific nodes
python3 -m wnm --force_action survey \
  --service_name antnode0001,antnode0003 \
  --dry_run
```

## Files Modified

1. **`src/wnm/utils.py`**
   - Added `parse_service_names()` function for shared parsing logic

2. **`src/wnm/executor.py`**
   - Imported `parse_service_names` from utils
   - Removed duplicate `_parse_service_names()` method
   - Added `_survey_specific_nodes()` method
   - Updated `_force_survey_nodes()` to accept `service_name` parameter
   - Updated `execute_forced_action()` to pass `service_name` to survey

3. **`src/wnm/reports.py`**
   - Imported `parse_service_names` from utils
   - Removed duplicate `_parse_service_names()` method
   - Updated calls to use standalone function

4. **`src/wnm/__main__.py`**
   - Added `service_name` parameter when calling survey before reports

5. **`src/wnm/config.py`**
   - Updated `--service_name` help text to mention survey support

6. **`tests/test_reports.py`**
   - Updated tests to use standalone `parse_service_names()` function

## Benefits

1. **Performance**: Surveying specific nodes is faster than surveying entire fleet
2. **Targeted Troubleshooting**: Check status of problematic nodes without affecting others
3. **Code Quality**: Eliminated duplicate parsing logic across modules
4. **Consistency**: Same comma-separated format works for reports and surveys
5. **Network Efficiency**: Skips metrics requests for stopped nodes

## Backward Compatibility

Fully backward compatible:
- Existing behavior preserved when `--service_name` is not provided
- No changes to command-line interface beyond optional parameter
- All existing tests pass without modification

## Testing

All 63 tests pass, including:
- Service name parsing tests
- Report generation tests
- Forced action tests
- Integration tests

## Future Enhancements

Potential improvements:
- Add survey action to other forced actions (start, stop, restart)
- Support node ID ranges (e.g., `antnode0001-0010`)
- Add `--survey_all` flag for explicit all-nodes survey
- Parallel surveying for better performance on large node lists
