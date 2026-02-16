# Weave Node Manager — Refactoring Plan

## Project Stats (as of 2026-02-15)
- 10,485 lines source (28 files), 6,681 lines tests (15 files)
- Python 3.12.3+, SQLAlchemy, platforming Linux (systemd/setsid) and macOS (launchd)

## Priority 1: Extract forced actions from `executor.py` (1,657 lines)

**Problem**: `_force_*` methods (lines 748-1657, ~900 lines) share nearly identical structure with heavy duplication.

**Shared pattern across `_force_remove_node`, `_force_upgrade_node`, `_force_stop_node`, `_force_start_node`**:
1. Parse service names + validate via `_parse_node_name` / `_get_node_by_name`
2. If service_names provided: loop with delay, process each node
3. Else: count validation + batch processing by age (youngest/oldest)
4. Result aggregation (counts of added/removed/upgraded/stopped)
5. Identical delay logic between operations

**Approach**: Extract to `forced_actions.py` module. Consider a generic `_force_batch_operation()` that accepts: node query function, operation function, delay, and result key. The 4 methods collapse into configuration of this generic.

**Also**: `_execute_add_node` (149 lines) has node construction/ID allocation logic that could become a factory.

---

## Priority 2: Defer `config.py` side effects (1,340 lines)

**Problem**: Lines 1117-1341 execute at import time: database creation, migrations, machine init, filesystem setup. This couples everything to import order and makes testing harder.

**Approach**: Move module-level execution into an explicit `initialize()` function called from `__main__.py`.

---

## Priority 3: Data-driven `merge_config_changes()` (216 lines)

**Problem**: 40+ repetitive if-blocks, each following a nearly identical pattern.

### Field Categories

| Category | Cast/Transform | Truthiness Check | Fields |
|----------|---------------|-----------------|--------|
| **int** | `int()` | truthy | `node_cap`, `cpu_less_than`, `cpu_remove`, `mem_less_than`, `mem_remove`, `hd_less_than`, `hd_remove`, `delay_start`, `delay_restart`, `delay_upgrade`, `delay_remove`, `survey_delay`, `max_concurrent_upgrades`, `max_concurrent_starts`, `max_concurrent_removals`, `max_concurrent_operations`, `hdio_read_less_than`, `hdio_read_remove`, `hdio_write_less_than`, `hdio_write_remove`, `netio_read_less_than`, `netio_read_remove`, `netio_write_less_than`, `netio_write_remove`, `crisis_bytes`, `highest_node_id_used` |
| **int_nullable** | `int()` | `is not None` | `action_delay` (0 is valid) |
| **float** | `float()` | truthy | `max_load_average_allowed`, `desired_load_average` |
| **str** | none | truthy | `node_storage`, `donate_address`, `environment`, `start_args`, `process_manager` |
| **str_path** | none | truthy | `antnode_path`, `antctl_path`, `antctl_version` |
| **port** | `normalize_port_start()` | truthy | `port_start`, `metrics_port_start`, `rpc_port_start` |

### Special cases (keep as explicit code)

1. **`rewards_address`** — calls `validate_rewards_address()`, exits on failure
2. **`no_upnp`, `antctl_debug`** — `bool` fields that check `sys.argv` directly because argparse `store_true` default of `False` is indistinguishable from "not provided"
3. **`disable_config` block** (lines 806-820) — inverts boolean flags when `--force_action disable_config` is used; entirely separate logic

### Proposed implementation

```python
# Field descriptors: (field_name, cast_type)
# cast_type: "int", "int_nullable", "float", "str", "port"
_MERGE_FIELDS = [
    ("node_cap", "int"),
    ("cpu_less_than", "int"),
    ("cpu_remove", "int"),
    # ... all fields from table above ...
    ("rpc_port_start", "port"),
]

def merge_config_changes(options, machine_config):
    cfg = {}

    # Data-driven: handle all standard fields
    for field, cast_type in _MERGE_FIELDS:
        opt_val = getattr(options, field, None)
        db_val = getattr(machine_config, field)

        if cast_type == "int_nullable":
            if opt_val is None:
                continue
            opt_val = int(opt_val)
        elif cast_type == "int":
            if not opt_val:
                continue
            opt_val = int(opt_val)
        elif cast_type == "float":
            if not opt_val:
                continue
            opt_val = float(opt_val)
        elif cast_type == "port":
            if not opt_val:
                continue
            opt_val = normalize_port_start(opt_val)
        else:  # str, str_path
            if not opt_val:
                continue

        if opt_val != db_val:
            cfg[field] = opt_val

    # Special: rewards_address (validation + exit on failure)
    if options.rewards_address and options.rewards_address != machine_config.rewards_address:
        is_valid, error_msg = validate_rewards_address(
            options.rewards_address, machine_config.donate_address
        )
        if not is_valid:
            logging.error(f"Invalid rewards_address: {error_msg}")
            sys.exit(1)
        cfg["rewards_address"] = options.rewards_address

    # Special: bool flags checked via sys.argv (store_true default is indistinguishable)
    if "--no_upnp" in sys.argv or "--no-upnp" in sys.argv or os.getenv("NO_UPNP"):
        if bool(options.no_upnp) != bool(machine_config.no_upnp):
            cfg["no_upnp"] = bool(options.no_upnp)

    if "--antctl_debug" in sys.argv or "--antctl-debug" in sys.argv or os.getenv("ANTCTL_DEBUG"):
        if bool(options.antctl_debug) != bool(machine_config.antctl_debug):
            cfg["antctl_debug"] = bool(options.antctl_debug)

    # Special: disable_config inversion
    if hasattr(options, "force_action") and options.force_action == "disable_config":
        if "--antctl_debug" in sys.argv or "--antctl-debug" in sys.argv:
            if machine_config.antctl_debug != False:
                cfg["antctl_debug"] = False
                logging.info("disable_config: Setting antctl_debug to False")
        if "--no_upnp" in sys.argv or "--no-upnp" in sys.argv:
            if machine_config.no_upnp != False:
                cfg["no_upnp"] = False
                logging.info("disable_config: Setting no_upnp to False (enabling UPnP)")

    return cfg
```

**Result**: ~216 lines → ~60 lines. The 3 special cases remain explicit and readable. Standard fields are fully described by the `_MERGE_FIELDS` list — adding a new int config field is one line.

---

## Priority 4: Split `main()` into phases (284 lines)

**Problem**: `main()` in `__main__.py` handles version checks, lock files, migration, node discovery/import, port configuration, metrics, reporting, and forced actions.

**Approach**: Extract into named functions for each phase:
- `check_prerequisites()` — version, lock file
- `handle_migration()` — DB migration logic
- `handle_initialization()` — node discovery, import, port config
- `run_decision_cycle()` — metrics, decision engine, execution
- `generate_reports()` — reporting phase

---

## Files reference (largest first)
- `executor.py` — 1,657 lines (Priority 1)
- `config.py` — 1,340 lines (Priority 2, 3)
- `models.py` — 658 lines (fine)
- `process_managers/antctl_zen_manager.py` — 676 lines (fine, platform-specific)
- `process_managers/launchd_manager.py` — 649 lines (fine)
- `process_managers/antctl_manager.py` — 602 lines (fine)
- `process_managers/systemd_manager.py` — 593 lines (fine)
- `utils.py` — 542 lines (fine)
- `reports.py` — 521 lines (fine)
- `decision_engine.py` — 518 lines (fine, well-organized)
- `__main__.py` — 436 lines (Priority 4)