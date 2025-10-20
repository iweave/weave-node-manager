# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Weave Node Manager (wnm) is a Python application for managing Autonomi nodes on Linux systems. It's an Alpha-stage Python port of the `anm` (autonomic node manager) tool. The system automatically manages node lifecycle: creating, starting, stopping, upgrading, and removing nodes based on system resource thresholds (CPU, memory, disk, network I/O, load average).

**Important**: This is Linux-only software targeting Python 3.12.3+. It requires systemd, ufw firewall, and sudo privileges.

## Development Environment

**IMPORTANT: Use Docker for Development and Testing**

Since WNM is Linux-only and requires systemd, always use the Docker development environment for running and testing the application:

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

**Do NOT run tests directly on macOS** - the application currently requires Linux-specific features (systemd, ufw, /proc filesystem) that are not available on macOS.

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

1. **Locking**: Creates `/var/antctl/wnm_active` lock file to prevent concurrent runs
2. **Configuration**: Loads machine config from SQLite database or initializes from `anm` migration
3. **Metrics Collection**: Gathers system metrics (CPU, memory, disk, I/O, load average) and node statuses
4. **Decision Engine**: `choose_action()` determines what action to take based on thresholds
5. **Action Execution**: Performs one action per cycle (add/remove/upgrade/restart node, or idle)
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

### Node Management (`utils.py`)
Key functions for node lifecycle:

- **Survey**: `survey_machine()` - Scans systemd services to discover nodes
- **Metrics**: `read_node_metrics()`, `read_node_metadata()` - Polls node HTTP endpoints
- **Create**: `create_node()` - Generates systemd service, directories, starts node
- **Upgrade**: `upgrade_node()` - Copies new binary, restarts service, sets UPGRADING status
- **Remove**: `remove_node()` - Stops node, deletes data/logs/service files
- **Start/Stop**: `start_systemd_node()`, `stop_systemd_node()` - Controls systemd services and UFW firewall

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

Resource thresholds control when nodes are added/removed:
- `CpuLessThan/CpuRemove`: CPU percentage thresholds for add/remove decisions
- `MemLessThan/MemRemove`: Memory percentage thresholds
- `HDLessThan/HDRemove`: Disk usage percentage thresholds
- `DesiredLoadAverage/MaxLoadAverageAllowed`: Load average thresholds
- `NodeCap`: Maximum number of nodes allowed
- `DelayStart/DelayRestart/DelayUpgrade/DelayRemove`: Minutes to wait in transitional states
- `NodeStorage`: Root directory for node data (default: `/var/antctl/services`)
- `RewardsAddress`: Ethereum address for node rewards (required)

## Important Constraints

- Only ONE action per execution cycle (conservative approach)
- Nodes are added/removed based on the "youngest" (most recent `age` timestamp)
- Upgrades only proceed when no removals are pending
- Database has single Machine row (id=1); updates apply to entire cluster
- Requires sudo access for systemd, ufw, file operations
- Lock file prevents concurrent execution