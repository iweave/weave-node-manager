# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Weave Node Manager (wnm) is a Python application for managing Autonomi nodes on Linux and macOS systems. The system automatically manages node lifecycle: creating, starting, stopping, upgrading, and removing nodes based on system resource thresholds (CPU, memory, disk, network I/O, load average).

**Platforms**:
- **Linux**: systemd or setsid for process management, UFW for firewall (root or user-level)
- **macOS**: launchd for process management, no firewall management (user-level only)
- **Python 3.12.3+** required

## Development Environment

### macOS (Native)

```bash
./scripts/test-macos.sh
# or
pytest tests/ -v -m "not linux_only"
python3 -m wnm --dry_run
```

- Data: `~/Library/Application Support/autonomi/`
- Logs: `~/Library/Logs/autonomi/`
- Nodes: `~/Library/LaunchAgents/`
- Some tests marked `@pytest.mark.linux_only` will be skipped

### Linux (Docker)

```bash
./scripts/test.sh    # run tests
./scripts/dev.sh     # interactive shell
```

## Development Commands

```bash
# Setup
python3 -m venv .venv && . .venv/bin/activate
pip3 install -r requirements.txt -r requirements-dev.txt

# Format
black src/ && isort src/

# Build
python3 -m build
twine upload dist/*
```

## Architecture

### Core Flow (`__main__.py`)
Single-execution cycle, invoked via cron each minute:

1. **Locking**: Platform-specific lock file prevents concurrent runs
2. **Configuration**: Loads machine config from SQLite (`colony.db`)
3. **Metrics Collection**: CPU, memory, disk, I/O, load average + node statuses
4. **Decision Engine**: Plans actions based on thresholds and concurrency limits
5. **Action Execution**: Performs operations via ProcessManager
6. **Cleanup**: Removes lock file and exits

### Key Modules
- **`models.py`**: SQLAlchemy ORM — `Machine` (single row, cluster config) and `Node` (one row per node)
- **`config.py`**: Multi-layer config — CLI args → env vars → config files → DB → defaults; global `options`, `machine_config`, session factory `S` created at import
- **`decision_engine.py`**: `DecisionEngine` class; `_compute_features()` + `plan_actions()`
- **`executor.py`**: `ActionExecutor` class; executes planned actions and all `--force_action` variants
- **`utils.py`**: Metrics polling (`read_node_metrics()`, `read_node_metadata()`), counter/state updates
- **`process_managers/`**: Factory pattern — `SystemdManager`, `LaunchdManager`, `SetsidManager`, `AntctlManager`, `AntctlZenManager`, `DockerManager` all implement `ProcessManager` base
- **`firewall/`**: `UfwManager` (Linux) and `NullFirewallManager` (macOS/fallback)

### Node States (`common.py`)
`RUNNING` → `STOPPED` → `RESTARTING` → `UPGRADING` → `REMOVING` → deleted; `DEAD` (missing dir, immediate removal); `DISABLED` (excluded from management)

### Decision Engine Priority
1. Reboot detection → resurvey all nodes
2. Dead node cleanup (immediate)
3. Version field updates
4. Delay expiration for transitional states
5. Resource pressure removal (CPU/Mem/HD/IO/Load)
6. Upgrades (only when `--enable_upgrade` passed; blocked during removals)
7. Node addition (stopped nodes first, then create new)
8. Idle survey

### Port Assignment
- Node ports: `port_start * 1000 + node_id` (default: 55000+)
- Metrics ports: `metrics_port_start * 1000 + node_id` (default: 13000+)
- Cannot be changed after `--init`

### Concurrent Operations
Per-type limits (`--max_concurrent_upgrades/starts/removals`, default 1) combined with a global cap (`--max_concurrent_operations`, default 1). Effective limit = MIN(per-type, remaining global). See `docs/USER-GUIDE-PART3.md` for configuration examples.

## Important Constraints
- Single `Machine` row (id=1); all config updates apply cluster-wide
- Nodes selected for removal by "youngest" (`age` timestamp)
- Upgrades skipped unless `--enable_upgrade` is passed (antnode self-upgrades by default)
- Linux root mode requires sudo for systemd and UFW
- `--port_start`, `--metrics_port_start`, and `--process_manager` are immutable after `--init`