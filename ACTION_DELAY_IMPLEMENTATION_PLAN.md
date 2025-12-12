# Implementation Plan: Action Delay Feature (Node Operations)

## Overview
Add `--action_delay` (persistent) and `--this_action_delay` (transient) parameters to control delays **between individual node operations** when multiple nodes are being processed. `--this_action_delay` needs an alias called `--interval` which is the parameters name from antctl

**Requirements:**
- `--action_delay`: Persistent setting stored in Machine model, default 0 milliseconds
- `--this_action_delay`: One-time override for current execution, doesn't update machine_config
- `--interval`: One-time override for the current execution, doesn't update machine_config. this is an alias of this_action_delay.
- Delay inserted **between node operations** (when processing multiple nodes)
- Units: milliseconds (consistent with existing `survey_delay`)

## Use Cases

When this feature is used:
1. `wnm --force_action add --count 4 --action_delay 2000` - Adds 4 nodes with 2-second delays between each add
2. `wnm --force_action upgrade --count 10 --this_action_delay 500` - Upgrades 10 nodes with 500ms delays
3. `wnm --force_action remove antnode0001,antnode0002,antnode0003 --action_delay 1000` - Removes 3 specific nodes with 1-second delays

## Critical Files to Modify

1. **`src/wnm/models.py`** - Add database field for `action_delay`
2. **`src/wnm/config.py`** - Add configuration parameters and merge logic
3. **`src/wnm/executor.py`** - Implement delay logic in all multi-node operation loops

## Implementation Steps

### 1. Database Model Changes (`src/wnm/models.py`)

**Field declaration (after line 71):**
```python
action_delay: Mapped[int] = mapped_column(Integer, default=0)  # milliseconds
```

**Constructor parameter (after line 175, after survey_delay):**
```python
action_delay=0,
```

**Constructor assignment (after line 189):**
```python
self.action_delay = action_delay
```

**JSON serialization in `__json__()` (after line 252):**
```python
"action_delay": self.action_delay,
```

**Pattern to follow:** Identical to existing `survey_delay` field (line 71, 175, 189, 252)

---

### 2. Configuration System Changes (`src/wnm/config.py`)

#### A. Add command-line arguments (after line 302)

**Persistent setting:**
```python
c.add(
    "--action_delay",
    env_var="ACTION_DELAY",
    help="Delay between node operations in milliseconds (default: 0)",
    type=int,
)
```

**Transient setting:**
```python
c.add(
    "--this_action_delay",
    env_var="THIS_ACTION_DELAY",
    help="Override action_delay for this execution only (milliseconds)",
    type=int,
)
```
```python
c.add(
    "--interval",
    env_var="INTERVAL",
    help="Override action_delay for this execution only (milliseconds), compatible with antctl",
    type=int,
)
```

#### B. Add merge logic in `merge_config_changes()` (after line 540)

```python
if options.action_delay is not None and int(options.action_delay) != machine_config.action_delay:
    cfg["action_delay"] = int(options.action_delay)
    changes.append(f"action_delay: {machine_config.action_delay} -> {options.action_delay}")
```

**Note:** Do NOT add merge logic for `this_action_delay` (it's transient)

#### C. Add initialization in `load_anm_config()` (after line 726)

```python
anm_config["action_delay"] = int(_get_option(options, "action_delay") or 0)
```

---

### 3. Executor Changes (`src/wnm/executor.py`)

This is where the bulk of the work happens. We need to add delays in all loops that process multiple nodes.

#### Pattern to Follow

Similar to survey_delay in `_survey_specific_nodes()` (lines 1336-1338):
```python
# Insert delay between nodes (but not after the last node)
if survey_delay_ms > 0 and idx < len(service_names) - 1:
    time.sleep(survey_delay_ms / 1000.0)
```

**Our pattern:**
```python
# Determine delay to use
delay_ms = options.this_action_delay if options.this_action_delay is not None else machine_config.get("action_delay", 0)

# In each loop, before the next iteration (but not after the last):
if delay_ms > 0 and <not_last_iteration>:
    delay_seconds = delay_ms / 1000.0
    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node operations")
    time.sleep(delay_seconds)
```

#### Challenge: Accessing `options.this_action_delay` in executor

The executor doesn't currently have access to `options`. We have two approaches:

**Approach A (Recommended):** Pass `this_action_delay` through machine_config
- Modify `choose_action()` in `__main__.py` to inject `this_action_delay` into `machine_config` dict
- Executor reads from `machine_config["action_delay"]` (persistent) or `machine_config.get("this_action_delay")` (transient override)

**Approach B:** Add parameter to all force methods
- Add `action_delay_override=None` parameter to each `_force_*` method
- Pass through from `_execute_action()` caller

**Chosen approach: A** (cleaner, less invasive). Is it possible to pass this_action_delay into machine_config without adding a field in the database?

---

### 4. Specific Code Changes in `executor.py`

#### Helper Method (add to ActionExecutor class, around line 175)

```python
def _get_action_delay_ms(self, machine_config: Dict[str, Any]) -> int:
    """Get the effective action delay in milliseconds.

    Checks for transient override first, then falls back to persistent setting.

    Args:
        machine_config: Machine configuration dict

    Returns:
        Delay in milliseconds
    """
    # Check for transient override (this_action_delay)
    if "this_action_delay" in machine_config and machine_config["this_action_delay"] is not None:
        return int(machine_config["this_action_delay"])

    # Fall back to persistent setting
    return machine_config.get("action_delay", 0)
```

#### Changes to `_force_add_node()` (lines 693-708)

**Current loop:**
```python
for i in range(count):
    result = self._execute_add_node(machine_config, metrics, dry_run)
    # ... process result ...
```

**New loop:**
```python
delay_ms = self._get_action_delay_ms(machine_config)

for i in range(count):
    # Insert delay between operations (skip before first)
    if i > 0 and delay_ms > 0:
        delay_seconds = delay_ms / 1000.0
        logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node additions")
        time.sleep(delay_seconds)

    result = self._execute_add_node(machine_config, metrics, dry_run)
    # ... existing code ...
```

#### Changes to `_force_remove_node()` (lines 742-763)

**Current loop (specific nodes):**
```python
for name in service_names:
    node = self._get_node_by_name(name)
    # ... remove logic ...
```

**New loop:**
```python
delay_ms = self._get_action_delay_ms(machine_config)

for idx, name in enumerate(service_names):
    # Insert delay between operations (skip before first)
    if idx > 0 and delay_ms > 0:
        delay_seconds = delay_ms / 1000.0
        logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node removals")
        time.sleep(delay_seconds)

    node = self._get_node_by_name(name)
    # ... existing remove logic ...
```

**Similar changes needed for the "youngest nodes" loop** (need to find this section)

#### Changes to `_force_upgrade_node()` (lines 848-866 and 900-913)

**Current loop 1 (specific nodes, line 848):**
```python
for name in service_names:
    # ... upgrade logic ...
```

**New loop 1:**
```python
delay_ms = self._get_action_delay_ms(machine_config)

for idx, name in enumerate(service_names):
    # Insert delay between operations (skip before first)
    if idx > 0 and delay_ms > 0:
        delay_seconds = delay_ms / 1000.0
        logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node upgrades")
        time.sleep(delay_seconds)

    # ... existing upgrade logic ...
```

**Current loop 2 (oldest nodes, line 900):**
```python
for row in oldest_nodes:
    node = row[0]
    # ... upgrade logic ...
```

**New loop 2:**
```python
delay_ms = self._get_action_delay_ms(machine_config)

for idx, row in enumerate(oldest_nodes):
    # Insert delay between operations (skip before first)
    if idx > 0 and delay_ms > 0:
        delay_seconds = delay_ms / 1000.0
        logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node upgrades")
        time.sleep(delay_seconds)

    node = row[0]
    # ... existing upgrade logic ...
```

#### Changes to `_force_stop_node()` (line 950 and beyond)

**Current loop (specific nodes, line 950):**
```python
for name in service_names:
    # ... stop logic ...
```

**New loop:**
```python
delay_ms = self._get_action_delay_ms(machine_config)

for idx, name in enumerate(service_names):
    # Insert delay between operations (skip before first)
    if idx > 0 and delay_ms > 0:
        delay_seconds = delay_ms / 1000.0
        logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node stops")
        time.sleep(delay_seconds)

    # ... existing stop logic ...
```

**Similar changes needed for "youngest running nodes" loop**

#### Changes to `_force_start_node()` (line 1054 and beyond)

**Current loop (specific nodes, line 1054):**
```python
for name in service_names:
    # ... start logic ...
```

**New loop:**
```python
delay_ms = self._get_action_delay_ms(machine_config)

for idx, name in enumerate(service_names):
    # Insert delay between operations (skip before first)
    if idx > 0 and delay_ms > 0:
        delay_seconds = delay_ms / 1000.0
        logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node starts")
        time.sleep(delay_seconds)

    # ... existing start logic ...
```

**Similar changes needed for "oldest stopped nodes" loop**

---

### 5. Main Entry Point Changes (`src/wnm/__main__.py`)

**Location:** `choose_action()` function, before line 91

**Insert before executor call:**
```python
# Inject transient action delay override into machine_config if provided
if options.this_action_delay is not None:
    machine_config["this_action_delay"] = options.this_action_delay
# Inject alias Interval as this_action_delay
if options.interval is not None:
    machine_config["this_action_delay"] = options.interval

executor = ActionExecutor(S)
result = executor.execute(actions, machine_config, metrics, dry_run)
```

This makes `this_action_delay` available to the executor through `machine_config`.

---

## Complete List of Loops to Modify

Search for these patterns in `executor.py` and add delays:

1. ✅ `_force_add_node()` line 693: `for i in range(count)`
2. ✅ `_force_remove_node()` line 742: `for name in service_names`
3. ⚠️ `_force_remove_node()` (youngest nodes loop - need to locate)
4. ✅ `_force_upgrade_node()` line 848: `for name in service_names`
5. ✅ `_force_upgrade_node()` line 900: `for row in oldest_nodes`
6. ✅ `_force_stop_node()` line 950: `for name in service_names`
7. ⚠️ `_force_stop_node()` (youngest running nodes loop - need to locate)
8. ✅ `_force_start_node()` line 1054: `for name in service_names`
9. ⚠️ `_force_start_node()` (oldest stopped nodes loop - need to locate)

**Action:** Use `Grep` to find all loops in these methods to ensure complete coverage.

---

## Database Migration Strategy

The codebase has built-in migration detection in `config.py`:

1. **Auto-detection:** When a new field is added to the Machine model, `check_migration_status()` will detect the schema mismatch
2. **Auto-stamping:** If enabled, the system will automatically create and apply the migration
3. **Manual migration:** If auto-stamping is disabled, users will need to run:
   ```bash
   alembic revision --autogenerate -m "Add action_delay field"
   alembic upgrade head
   ```

**Default value:** By adding `default=0` to the column definition, existing databases will get `0` (no delay) when migrated, preserving current behavior.

---

## Testing Plan

1. **Test persistent setting:**
   ```bash
   python3 -m wnm --init --action_delay 1000
   # Check that action_delay=1000 is stored in database
   ```

2. **Test transient override:**
   ```bash
   python3 -m wnm --this_action_delay 500 --force_action add --count 3
   # Should use 500ms delay for this execution only
   # Database should NOT be updated
   ```
      ```bash
   python3 -m wnm --interval 500 --force_action add --count 3
   # Should use 500ms delay for this execution only
   # Database should NOT be updated
   ```

3. **Test multiple node additions:**
   ```bash
   python3 -m wnm --force_action add --count 4 --this_action_delay 2000
   # Should add 4 nodes with 2-second delays between each
   # Verify logs show "Action delay: waiting 2000ms (2.00s) between node additions"
   ```

4. **Test multiple node upgrades:**
   ```bash
   python3 -m wnm --force_action upgrade --count 5 --this_action_delay 1500
   # Should upgrade 5 oldest nodes with 1.5-second delays between each
   # Verify logs show timing between operations
   ```

5. **Test specific node operations:**
   ```bash
   python3 -m wnm --force_action remove antnode0001,antnode0002,antnode0003 --action_delay 1000
   # Should remove 3 nodes with 1-second delays
   ```

6. **Test default (no delay):**
   ```bash
   python3 -m wnm --force_action add --count 3
   # Should execute with no delays (action_delay defaults to 0)
   ```

---

## Edge Cases & Considerations

1. **Single operation:** When only one node is processed, no delay occurs (idx > 0 check)
2. **Zero delay:** When action_delay=0 or this_action_delay=0, no sleep occurs
3. **Precedence:** this_action_delay overrides action_delay for current execution
4. **Units:** Milliseconds (like survey_delay), not seconds (like delay_start/restart)
5. **Dry-run mode:** Delay still applies in dry-run mode (logs delays being applied)
6. **Migration compatibility:** Default value ensures existing installations continue with 0ms delay
7. **Import:** `time` module is already imported in executor.py (line 11)

---

## Summary

This implementation adds fine-grained control over node operation timing, allowing users to throttle WNM when processing multiple nodes. Delays occur **between individual node operations**, not between different types of actions.

**Files changed:** 3 (models.py, config.py, executor.py, __main__.py = 4 total)
**Lines added:** ~60-80 (helper method + 8-9 loop modifications)
**Migration required:** Yes (auto-detected)
**Breaking changes:** None (default 0ms preserves current behavior)

---

## Next Steps

1. Read all `_force_*` methods completely to find all loops
2. Implement database model changes
3. Implement configuration system changes
4. Add `_get_action_delay_ms()` helper method
5. Modify all loops in force methods
6. Test with various scenarios
7. Create database migration if needed