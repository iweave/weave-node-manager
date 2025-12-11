# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Weave Node Manager (wnm) is a Python application for managing Autonomi nodes on Linux and macOS systems. It's an Alpha-stage Python port of the `anm` (autonomic node manager) tool. The system automatically manages node lifecycle: creating, starting, stopping, upgrading, and removing nodes based on system resource thresholds (CPU, memory, disk, network I/O, load average).

**Platforms**:
- **Linux**: systemd or setsid for process management, UFW for firewall (root or user-level)
- **macOS**: launchd for process management, no firewall management (user-level only)
- **Python 3.12.3+** required

## Development Environment

### macOS Development (Native)

**On macOS, you can run and test natively** using launchd for process management:

```bash
# Run tests natively on macOS
./scripts/test-macos.sh

# Or run tests directly
pytest tests/ -v -m "not linux_only"

# Run application in dry-run mode
python3 -m wnm --dry_run

# Initialize with rewards address
python3 -m wnm --init --rewards_address 0xYourEthereumAddress
```

**macOS Notes**:
- Uses `~/Library/Application Support/autonomi/` for data
- Uses `~/Library/Logs/autonomi/` for logs
- Nodes managed via launchd (`~/Library/LaunchAgents/`)
- No root/sudo required
- Some tests marked `@pytest.mark.linux_only` will be skipped

### Linux Development (Docker)

**On Linux, use Docker for systemd/UFW testing**:

```bash
# Run tests in Docker container
./scripts/test.sh

# Interactive development shell in Docker
./scripts/dev.sh

# Inside the container, you can run:
pytest tests/ -v                    # Run all tests
python3 -m wnm --dry_run           # Run application in dry-run mode
```

See `DOCKER-DEV.md` for complete Docker development environment documentation.

## Development Commands

### Setup Development Environment
```bash
# Create virtual environment
python3 -m venv .venv
. .venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt

# Install development dependencies
pip3 install -r requirements-dev.txt
```

### Code Formatting
```bash
# Format code with black
black src/

# Sort imports with isort
isort src/
```

### Build and Package
```bash
# Build the package
python3 -m build

# Upload to TestPyPi (maintainers only)
twine upload --verbose --repository testpypi dist/*
# Upload to PyPI (maintainers only)
twine upload dist/*
```

### Running the Application
```bash
# Run directly from source
python3 -m wnm

# With command-line options
python3 -m wnm --dry_run --init --migrate_anm

# Entry point after installation
wnm
```

## Architecture

### Core Flow (`__main__.py`)
The application runs as a single-execution cycle (typically invoked via cron every minute):

1. **Locking**: Creates platform-specific lock file to prevent concurrent runs
   - macOS: `~/Library/Application Support/autonomi/wnm_active`
   - Linux (root): `/var/antctl/wnm_active`
   - Linux (user): `~/.local/share/autonomi/wnm_active`
2. **Configuration**: Loads machine config from SQLite database or initializes from `anm` migration
3. **Metrics Collection**: Gathers system metrics (CPU, memory, disk, I/O, load average) and node statuses
4. **Decision Engine**: `choose_action()` determines what action to take based on thresholds
5. **Action Execution**: Performs one action per cycle (add/remove/upgrade/restart node, or idle) via ProcessManager
6. **Cleanup**: Removes lock file and exits

### Database Models (`models.py`)
Two SQLAlchemy ORM models backed by SQLite (`colony.db`):

- **Machine**: Single row (id=1) storing cluster configuration (thresholds, ports, paths, addresses)
- **Node**: One row per Autonomi node with status, version, ports, metrics, timestamps

### Configuration System (`config.py`)
Multi-layer configuration priority (highest to lowest):
1. Command-line arguments (via `configargparse`)
2. Environment variables from `.env` or `/var/antctl/config`
3. Config files (`~/.local/share/wnm/config`, `~/wnm/config`)
4. Database-stored machine config
5. Defaults

Configuration loading happens at module import, creating global `options`, `machine_config`, and database session factory `S`.

### Process Management (`process_managers/`)
Platform-specific process managers handle node lifecycle via factory pattern:

- **SystemdManager** (`systemd_manager.py`): Linux root-level, uses systemd services
- **LaunchdManager** (`launchd_manager.py`): macOS, uses launchd agents
- **SetsidManager** (`setsid_manager.py`): Linux user-level, background processes

All managers implement the `ProcessManager` base class with these methods:
- `create_node()`: Creates directories, copies binary, starts node
- `start_node()`, `stop_node()`, `restart_node()`: Controls node lifecycle
- `get_status()`: Returns node process status
- `remove_node()`: Stops node and cleans up files
- `survey_nodes()`: Discovers existing nodes

### Firewall Management (`firewall/`)
Platform-specific firewall managers:

- **UfwManager** (`ufw_manager.py`): Linux, manages UFW firewall rules
- **NullFirewallManager** (`null_manager.py`): macOS and fallback, no-op implementation

### Node Management (`utils.py`)
Legacy helper functions (being phased out in favor of ProcessManager abstraction):

- **Metrics**: `read_node_metrics()`, `read_node_metadata()` - Polls node HTTP endpoints
- **Binary**: `get_latest_binary_version()` - Checks for new antnode versions

### Node States (`common.py`)
Nodes transition through states tracked in the database:
- `RUNNING`: Node responding to metrics port
- `STOPPED`: Node not responding
- `UPGRADING`: In upgrade delay period
- `RESTARTING`: In restart delay period
- `REMOVING`: In removal delay period before deletion
- `DEAD`: Node with missing root directory, marked for immediate removal
- `DISABLED`: Excluded from management

### Decision Engine Logic
The `choose_action()` function implements a priority-based decision tree:

1. **System Reboot Detection**: If system start time changed, resurvey all nodes
2. **Dead Node Cleanup**: Remove nodes with missing directories immediately
3. **Version Updates**: Update version field for nodes missing it
4. **Delay Expiration**: Wait for in-progress operations (RESTARTING, UPGRADING)
5. **Resource Pressure Removal**: Remove youngest nodes if CPU/Mem/HD/IO/Load exceed removal thresholds
6. **Upgrades**: Upgrade oldest running nodes with outdated versions (only when not removing)
7. **Node Addition**: Start stopped nodes or create new nodes when under capacity and resource thresholds allow
8. **Idle Survey**: Update all node metrics when no action needed

## Migration from anm

When `--init --migrate_anm` flags are used:
1. Disables anm by removing `/etc/cron.d/anm`
2. Reads `/var/antctl/config` and `/usr/bin/anms.sh` for configuration
3. Scans `/etc/systemd/system/antnode*.service` files
4. Imports discovered nodes into SQLite database
5. Takes over management from anm

## Port Assignment Scheme

- **Node Ports**: `{PortStart} * 1000 + {node_id}` (default: 55000 + id)
- **Metrics Ports**: `13000 + {node_id}`

Port ranges cannot be changed after initialization.

## Key Configuration Parameters

Resource thresholds control when nodes are added/removed (use snake_case on command line):
- `--cpu_less_than` / `--cpu_remove`: CPU percentage thresholds for add/remove decisions (default: 70% / 80%)
- `--mem_less_than` / `--mem_remove`: Memory percentage thresholds (default: 70% / 80%)
- `--hd_less_than` / `--hd_remove`: Disk usage percentage thresholds (default: 70% / 80%)
- `--desired_load_average` / `--max_load_average_allowed`: Load average thresholds
- `--node_cap`: Maximum number of nodes allowed (default: 50)
- `--delay_start` / `--delay_restart` / `--delay_upgrade` / `--delay_remove`: Minutes to wait in transitional states
- `--node_storage`: Root directory for node data (platform-specific defaults)
- `--rewards_address`: Ethereum address for node rewards (required)

**Platform-Specific Default Paths**:
- macOS: `~/Library/Application Support/autonomi/node/`
- Linux (root): `/var/antctl/services/`
- Linux (user): `~/.local/share/autonomi/node/`

## Concurrent Operations

WNM supports running multiple node operations simultaneously to better utilize powerful hardware. This feature allows aggressive scaling on machines with high capacity.

### Configuration Parameters

**Per-Operation Limits:**
- `--max_concurrent_upgrades` (default: 1): Maximum nodes upgrading simultaneously
- `--max_concurrent_starts` (default: 1): Maximum nodes starting/restarting simultaneously
- `--max_concurrent_removals` (default: 1): Maximum nodes being removed simultaneously

**Global Limit:**
- `--max_concurrent_operations` (default: 1): Total concurrent operations across all types

The effective limit is MIN(per_operation_limit, remaining_global_capacity).

### Examples

**Conservative (default):**
```bash
wnm --max_concurrent_upgrades 1 \
    --max_concurrent_starts 1 \
    --max_concurrent_operations 1
```

**Aggressive (powerful machine):**
```bash
wnm --max_concurrent_upgrades 4 \
    --max_concurrent_starts 4 \
    --max_concurrent_removals 2 \
    --max_concurrent_operations 8
```

**Very aggressive (high-end server):**
```bash
wnm --max_concurrent_upgrades 10 \
    --max_concurrent_starts 10 \
    --max_concurrent_removals 5 \
    --max_concurrent_operations 20
```

### Behavior

WNM will **aggressively scale to capacity** each cycle:
- If upgrade limit is 4 and 2 nodes are upgrading, WNM will start 2 more upgrades immediately
- Operations respect both per-type limits AND global limit
- Dead node removals always take priority and ignore limits
- Each action selects a different node (no duplicate operations on same node)

### Capacity Constraints

Operations are limited by actual node availability:
- **Upgrades**: Limited by nodes needing upgrade
- **Starts**: Limited by stopped nodes available
- **Adds**: Limited by node cap - total nodes
- **Removes**: Limited by stopped/running nodes available

Example: If `max_concurrent_starts=4` but only 2 stopped nodes exist, WNM will:
1. Start 2 stopped nodes
2. Add 2 new nodes (if under node cap)

## Important Constraints

- Concurrent operations respect configured limits (default: 1 action per cycle for backward compatibility)
- Nodes are added/removed based on the "youngest" (most recent `age` timestamp)
- Upgrades only proceed when no removals are pending
- Database has single Machine row (id=1); updates apply to entire cluster
- Lock file prevents concurrent execution
- **Platform-specific requirements**:
  - Linux (root): Requires sudo for systemd and ufw
  - Linux (user): No sudo required, uses setsid
  - macOS: No sudo required, uses launchd

## Platform Support

See `MACOS-SUPPORT-PLAN.md` for detailed macOS implementation roadmap.
See `PLATFORM-SUPPORT.md` for platform-specific details on:
- Process management (systemd, launchd, setsid)
- Firewall management (UFW, null)
- Path conventions
- Binary management and upgrades