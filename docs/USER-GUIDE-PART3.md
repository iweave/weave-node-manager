# Part 3: Configuration

## 3.1 Configuration System Overview

Weave Node Manager uses a multi-layered configuration system with the following priority (highest to lowest):

1. **Command-line arguments** - Direct flags passed when running `wnm`
2. **Environment variables** - Set in `.env` files or system environment
3. **Configuration files** - Read from default locations
4. **Database-stored values** - Persisted in the SQLite database
5. **Built-in defaults** - Hardcoded fallback values

### Configuration Priority

When the same setting is specified in multiple locations, the highest priority source wins. For example, if `--node_cap` is set on the command line AND in the database, the command-line value takes precedence for that run and updates the database.

### Configuration File Locations

Default config file locations (checked in order):
- `~/.local/share/wnm/config`
- `~/wnm/config`

You can specify a custom config file with:
```bash
wnm --config /path/to/custom/config
```

### Environment Variable Files

Environment variables can be loaded from:
- `.env` file in `~/.local/share/wnm/.env` (user mode)
- `/var/antctl/config` (sudo mode, for anm migration compatibility)

### Configuration Updates

Most configuration values can be changed after initialization by:
1. Passing the new value via command-line flag
2. Setting the environment variable
3. Adding to a config file

The database will be automatically updated with the new values.

**Exceptions** (cannot be changed after `--init`):
- `--port_start`
- `--metrics_port_start`
- `--process_manager`

### Platform-Specific Defaults

Base directories vary by platform and process manager mode:

**macOS (launchd+user)** - Default:
- Base: `~/Library/Application Support/autonomi`
- Node storage: `~/Library/Application Support/autonomi/node`
- Logs: `~/Library/Logs/autonomi`
- Bootstrap cache: `~/Library/Caches/autonomi/bootstrap-cache`

**macOS (launchd+sudo)** - System-wide:
- Base: `/Library/Application Support/autonomi`
- Node storage: `/Library/Application Support/autonomi/node`
- Logs: `/Library/Logs/autonomi`
- Bootstrap cache: `/Library/Caches/autonomi/bootstrap-cache`

**Linux (systemd+user or setsid+user)** - Default:
- Base: `~/.local/share/autonomi`
- Node storage: `~/.local/share/autonomi/node`
- Logs: `~/.local/share/autonomi/logs`
- Bootstrap cache: `~/.local/share/autonomi/bootstrap-cache`

**Linux (systemd+sudo or setsid+sudo)** - System-wide:
- Base: `/var/antctl`
- Node storage: `/var/antctl/services`
- Logs: `/var/log/antnode`
- Bootstrap cache: `/var/antctl/bootstrap-cache`

---

## 3.2 Resource Thresholds

Resource thresholds control when wnm automatically adds or removes nodes. The system monitors CPU, memory, disk space, disk I/O, network I/O, and load average.

### How Thresholds Work

Each resource type has two thresholds:
- **Add threshold** (`_less_than`) - Nodes will be added when resource usage is BELOW this level
- **Remove threshold** (`_remove`) - Nodes will be removed when resource usage is ABOVE this level

The remove threshold should always be higher than the add threshold to prevent oscillation.

### CPU Thresholds

**`--cpu_less_than`**
- Environment variable: `CPU_LESS_THAN`
- Type: Integer (percentage)
- Default: `50`
- Description: Add nodes when CPU usage is below this percentage
- Valid range: 0-100

**`--cpu_remove`**
- Environment variable: `CPU_REMOVE`
- Type: Integer (percentage)
- Default: `70`
- Description: Remove nodes when CPU usage exceeds this percentage
- Valid range: 0-100

### Memory Thresholds

**`--mem_less_than`**
- Environment variable: `MEM_LESS_THAN`
- Type: Integer (percentage)
- Default: `60`
- Description: Add nodes when memory usage is below this percentage
- Valid range: 0-100

**`--mem_remove`**
- Environment variable: `MEM_REMOVE`
- Type: Integer (percentage)
- Default: `75`
- Description: Remove nodes when memory usage exceeds this percentage
- Valid range: 0-100

### Disk Space Thresholds

**`--hd_less_than`**
- Environment variable: `HD_LESS_THAN`
- Type: Integer (percentage)
- Default: `75`
- Description: Add nodes when disk usage is below this percentage
- Valid range: 0-100

**`--hd_remove`**
- Environment variable: `HD_REMOVE`
- Type: Integer (percentage)
- Default: `90`
- Description: Remove nodes when disk usage exceeds this percentage
- Valid range: 0-100

### Disk I/O Thresholds

**`--hdio_read_less_than`**
- Environment variable: `HDIO_READ_LESS_THAN`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Add nodes when disk read I/O is below this rate
- Note: Set to 0 to disable this check

**`--hdio_read_remove`**
- Environment variable: `HDIO_READ_REMOVE`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Remove nodes when disk read I/O exceeds this rate
- Note: Set to 0 to disable this check

**`--hdio_write_less_than`**
- Environment variable: `HDIO_WRITE_LESS_THAN`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Add nodes when disk write I/O is below this rate
- Note: Set to 0 to disable this check

**`--hdio_write_remove`**
- Environment variable: `HDIO_WRITE_REMOVE`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Remove nodes when disk write I/O exceeds this rate
- Note: Set to 0 to disable this check

### Network I/O Thresholds

**`--netio_read_less_than`**
- Environment variable: `NETIO_READ_LESS_THAN`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Add nodes when network read I/O is below this rate
- Note: Set to 0 to disable this check

**`--netio_read_remove`**
- Environment variable: `NETIO_READ_REMOVE`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Remove nodes when network read I/O exceeds this rate
- Note: Set to 0 to disable this check

**`--netio_write_less_than`**
- Environment variable: `NETIO_WRITE_LESS_THAN`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Add nodes when network write I/O is below this rate
- Note: Set to 0 to disable this check

**`--netio_write_remove`**
- Environment variable: `NETIO_WRITE_REMOVE`
- Type: Integer (bytes/second)
- Default: `0` (disabled)
- Description: Remove nodes when network write I/O exceeds this rate
- Note: Set to 0 to disable this check

### Load Average Thresholds

**`--desired_load_average`**
- Environment variable: `DESIRED_LOAD_AVERAGE`
- Type: Float
- Default: `cpu_count * 0.6`
- Description: Add nodes when load average is below this value
- Platform note: Calculated based on available CPU count

**`--max_load_average_allowed`**
- Environment variable: `MAX_LOAD_AVERAGE_ALLOWED`
- Type: Float
- Default: `cpu_count`
- Description: Remove nodes when load average exceeds this value
- Platform note: Calculated based on available CPU count

### CPU Count Detection

The system automatically detects available CPUs:
- **Linux**: Uses `os.sched_getaffinity(0)` which respects cgroups and taskset restrictions
- **macOS**: Uses `os.cpu_count()`

This affects default values for load average thresholds.

---

## 3.3 Node Management Settings

### Node Capacity

**`--node_cap`**
- Environment variable: `NODE_CAP`
- Type: Integer
- Default: `20`
- Description: Maximum number of nodes allowed on this machine
- Note: Setting this lower than current node count will trigger node removal

### Node Storage

**`--node_storage`**
- Environment variable: `NODE_STORAGE`
- Type: String (file path)
- Default: Platform-specific (see 3.1)
- Description: Root directory where node data is stored
- Platform defaults:
  - macOS user: `~/Library/Application Support/autonomi/node`
  - macOS sudo: `/Library/Application Support/autonomi/node`
  - Linux user: `~/.local/share/autonomi/node`
  - Linux sudo: `/var/antctl/services`
- Note: Each node creates a subdirectory in this location

### Delay Settings

All delay values are in **seconds** (not minutes).

**`--delay_start`**
- Environment variable: `DELAY_START`
- Type: Integer (seconds)
- Default: `300` (5 minutes)
- Description: How long to wait after creating a new node before taking another action
- Use case: Allows new nodes time to initialize

**`--delay_restart`**
- Environment variable: `DELAY_RESTART`
- Type: Integer (seconds)
- Default: `300` (5 minutes)
- Description: How long to wait after restarting a node before taking another action
- Use case: Gives restarted nodes time to stabilize
- Note: No default `delay_restart` in models.py, but referenced in anm migration

**`--delay_upgrade`**
- Environment variable: `DELAY_UPGRADE`
- Type: Integer (seconds)
- Default: `300` (5 minutes)
- Description: How long to wait after upgrading a node before taking another action
- Use case: Allows upgraded nodes to restart and stabilize

**`--delay_remove`**
- Environment variable: `DELAY_REMOVE`
- Type: Integer (seconds)
- Default: `300` (5 minutes)
- Description: How long to wait in REMOVING state before actually removing a node
- Use case: Provides a grace period before permanent removal

### Crisis Bytes Threshold

**`--crisis_bytes`**
- Environment variable: `CRISIS_BYTES`
- Type: Integer (bytes)
- Default: `2000000000` (2 GB)
- Description: Disk space threshold for capacity per node
- Note: Doesn't affect anything, this is a forecast for the capacity per node that causes a large operator to drop out or churn nodes.

---

## 3.4 Wallet Configuration

Wallet configuration determines which Ethereum addresses receive node rewards.

### Single Wallet Setup

The simplest configuration uses a single rewards address:

```bash
wnm --init --rewards_address 0xYourEthereumAddress
```

All nodes will use this address for rewards.

### Rewards Address

**`--rewards_address`**
- Environment variable: `REWARDS_ADDRESS`
- Type: String
- Required: Yes (must be set during `--init`)
- Format: Ethereum address (0x + 40 hex characters) or weighted wallet list
- Description: Ethereum address(es) for node rewards

### Named Wallets

Two special wallet names are supported:

**`faucet`**
- Resolves to: `0x00455d78f850b0358E8cea5be24d415E01E107CF`
- Description: Autonomi faucet address (hardcoded, cannot be changed)
- Use case: Donate rewards to the Autonomi community faucet

**`donate`**
- Resolves to: Value of `--donate_address` (or default faucet address)
- Description: Configurable donation address
- Use case: Allows users to set a custom donation address

### Donate Address

**`--donate_address`**
- Environment variable: `DONATE_ADDRESS`
- Type: String (Ethereum address)
- Default: `0x00455d78f850b0358E8cea5be24d415E01E107CF` (same as faucet)
- Description: Address used when `donate` name is specified in rewards
- Format: Ethereum address (0x + 40 hex characters)

### Weighted Distribution Across Multiple Wallets

You can distribute rewards across multiple addresses using weighted random selection:

```bash
--rewards_address "0xYourAddress:100,faucet:1,donate:10"
```

Format: `wallet1:weight1,wallet2:weight2,...`

**How it works:**
- Each time a node is created, wnm randomly selects one wallet based on weights
- Higher weights = higher probability of selection
- Weights are relative (100:1 means 100 times more likely, not 100%)

**Examples:**

1. **90/10 split between your address and faucet:**
   ```bash
   --rewards_address "0xYourAddress:9,faucet:1"
   ```
   Result: ~90% of nodes use your address, ~10% use faucet

2. **Equal distribution across three addresses:**
      ```bash
   --rewards_address "0xAddr1,0xAddr2,0xAddr3"
   ```

    or
      ```bash
   --rewards_address "0xAddr1:1,0xAddr2:1,0xAddr3:1"
   ```
   Result: Each address gets ~33% of nodes

3. **Mostly yours, small donations:**
   ```bash
   --rewards_address "0xYourAddress:95,faucet:3,donate:2"
   ```
   Result: ~95% yours, ~3% faucet, ~2% donate address

4. **Using named wallets:**
   ```bash
   --rewards_address "0xYourAddress:100,faucet:5"
   ```
   Result: ~95% yours, ~5% to Autonomi faucet

### Changing Wallet Configuration

You can change wallet configuration at any time:

```bash
wnm --rewards_address "0xNewAddress:80,faucet:20"
```

**Important:**
- Only affects NEW nodes created after the change
- Existing nodes keep their assigned wallet addresses
- To change wallet for existing nodes, you must remove and recreate them

### Validation

Wallet addresses are validated:
- Must be Ethereum format: `0x` + 40 hexadecimal characters
- Named wallets (`faucet`, `donate`) are case-insensitive
- Weighted lists must have valid format: `wallet:weight,wallet:weight`
- Weights must be positive integers
- Invalid addresses will prevent initialization or updates

---

## 3.5 Network Settings

### Port Configuration

Port assignment cannot be changed after initialization.

**`--port_start`**
- Environment variable: `PORT_START`
- Type: Integer
- Default: `55`
- Description: Starting multiplier for node port assignment
- Port calculation: `port_start * 1000 + node_id`
- Example: With default 55, node 1 gets port 55001, node 2 gets 55002, etc.
- **Cannot be changed after `--init`**

**`--metrics_port_start`**
- Environment variable: `METRICS_PORT_START`
- Type: Integer
- Default: `13`
- Description: Starting multiplier for metrics port assignment
- Port calculation: `metrics_port_start * 1000 + node_id`
- Example: With default 13, node 1 gets metrics port 13001, node 2 gets 13002, etc.
- **Cannot be changed after `--init`**

### Port Assignment Examples

With defaults (`--port_start 55` and `--metrics_port_start 13`):

| Node ID | Node Name    | Node Port | Metrics Port |
|---------|--------------|-----------|--------------|
| 1       | antnode0001  | 55001     | 13001        |
| 2       | antnode0002  | 55002     | 13002        |
| 10      | antnode0010  | 55010     | 13010        |
| 50      | antnode0050  | 55050     | 13050        |

### Host Configuration

**`--host`**
- Environment variable: `HOST`
- Type: String (IP address or hostname)
- Default: `127.0.0.1`
- Description: Hostname or IP address for node configuration
- Note: Used for internal tracking and metrics collection

### Bootstrap Peers

Bootstrap peers are currently managed by the antnode binary itself, not by wnm. Future versions may add configuration support.

### Bootstrap Cache Management

Bootstrap cache directory is automatically managed:
- macOS user: `~/Library/Caches/autonomi/bootstrap-cache`
- macOS sudo: `/Library/Caches/autonomi/bootstrap-cache`
- Linux user: `~/.local/share/autonomi/bootstrap-cache`
- Linux sudo: `/var/antctl/bootstrap-cache`

No user configuration is currently needed.

---

## 3.6 Advanced Configuration

### Database Path

**`--dbpath`**
- Environment variable: `DBPATH`
- Type: String (SQLite connection URI)
- Default: Platform-specific
  - macOS user: `sqlite:///~/Library/Application Support/autonomi/colony.db`
  - macOS sudo: `sqlite:////Library/Application Support/autonomi/colony.db`
  - Linux user: `sqlite:///~/.local/share/autonomi/colony.db`
  - Linux sudo: `sqlite:////var/antctl/colony.db`
- Description: Path to SQLite database file
- Format: `sqlite:///absolute/path/to/file.db`
- Note: Tilde (`~`) and environment variables are expanded

### Process Manager Selection

**`--process_manager`**
- Environment variable: `PROCESS_MANAGER`
- Type: String
- Choices: `systemd+sudo`, `systemd+user`, `setsid+sudo`, `setsid+user`, `launchd+sudo`, `launchd+user`
- Platform defaults:
  - macOS: `launchd+user`
  - Linux: `systemd+user`
- Description: Process manager to use for node lifecycle management
- Notes:
  - `systemd+sudo` requires root privileges and systemd
  - `systemd+user` uses user-level systemd services
  - `setsid+sudo` uses background processes with sudo
  - `setsid+user` uses background processes without sudo
  - `launchd+sudo` requires root privileges on macOS
  - `launchd+user` uses user-level LaunchAgents on macOS

### Logging Configuration

**`--loglevel`**
- Environment variable: `LOGLEVEL`
- Type: String
- Choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- Default: Not set (INFO level)
- Description: Python logging level for wnm output

**`-v` / `--verbose`**
- Flag only (no environment variable)
- Type: Boolean flag
- Default: False
- Description: Enable verbose output (sets loglevel to DEBUG)

### Dry-Run Mode

**`--dry_run`**
- Environment variable: `DRY_RUN`
- Type: Boolean flag
- Default: False
- Description: Run without making changes to the system
- Use cases:
  - Testing configuration changes
  - Previewing what actions would be taken
  - Debugging decision engine logic
- Note: Changes are NOT saved to database in dry-run mode
- Note: NOT compatible with `--init`

### Environment Variables for Antnode

**`--environment`**
- Environment variable: `ENVIRONMENT`
- Type: String
- Default: Empty string
- Description: Environment variables to pass to antnode processes
- Format: Space-separated `KEY=value` pairs
- Example: `--environment "RUST_LOG=debug RUST_BACKTRACE=1"`

### Start Arguments for Antnode

**`--start_args`**
- Environment variable: `START_ARGS`
- Type: String
- Default: Empty string
- Description: Additional command-line arguments to pass to antnode
- Example: `--start_args "--log-output-dest /custom/log/path"`

### Concurrency Limits (Advanced)

These settings control how many nodes can be in transitional states simultaneously:

**`max_concurrent_upgrades`**
- Database only (no CLI flag yet)
- Type: Integer
- Default: `1`
- Description: Maximum nodes that can be upgrading at once
- Note: Set in database directly, not exposed via CLI

**`max_concurrent_starts`**
- Database only (no CLI flag yet)
- Type: Integer
- Default: `2`
- Description: Maximum nodes that can be starting at once
- Note: Set in database directly, not exposed via CLI

**`max_concurrent_removals`**
- Database only (no CLI flag yet)
- Type: Integer
- Default: `1`
- Description: Maximum nodes that can be in removal process at once
- Note: Set in database directly, not exposed via CLI

### Node Removal Strategy (Advanced)

**`node_removal_strategy`**
- Database only (no CLI flag yet)
- Type: String
- Default: `youngest`
- Choices: `youngest` (only option currently implemented)
- Description: Strategy for selecting which nodes to remove when resources are constrained
- Note: Future versions may support other strategies (oldest, least records, etc.)

### Forced Actions

**`--force_action`**
- Environment variable: `FORCE_ACTION`
- Type: String
- Choices: `add`, `remove`, `upgrade`, `start`, `stop`, `disable`, `teardown`, `survey`
- Description: Force a specific action regardless of resource thresholds
- Use with: `--service_name` to target specific nodes
- Use with: `--count` to affect multiple nodes

**`--service_name`**
- Environment variable: `SERVICE_NAME`
- Type: String
- Description: Node name for targeted operations (e.g., `antnode0001`)
- Format for reports: Comma-separated list (e.g., `antnode0001,antnode0003`)

**`--count`**
- Environment variable: `COUNT`
- Type: Integer
- Default: `1`
- Description: Number of nodes to affect when using `--force_action`
- Works with: `add`, `remove`, `start`, `stop`, `upgrade` actions

### Reports

**`--report`**
- Environment variable: `REPORT`
- Type: String
- Choices: `node-status`, `node-status-details`
- Description: Generate a status report instead of managing nodes

**`--report_format`**
- Environment variable: `REPORT_FORMAT`
- Type: String
- Choices: `text`, `json`
- Default: `text`
- Description: Output format for reports

### Special Flags

**`--init`**
- Flag only
- Description: Initialize a new wnm cluster
- Required on first run
- Requires: `--rewards_address`
- Not compatible with: `--dry_run`

**`--migrate_anm`**
- Flag only
- Description: Migrate configuration and nodes from existing anm installation
- Use with: `--init`
- Linux only (reads from `/var/antctl/config` and `/etc/systemd/system/`)

**`--confirm`**
- Flag only
- Description: Confirm destructive operations (required for `--force_action teardown`)

**`--remove_lockfile`**
- Flag only
- Description: Remove the lock file and exit
- Use case: Cleanup after crashes or interrupted runs

**`--version`**
- Flag only
- Description: Display wnm version and exit

### Last Stopped Timestamp (Internal)

**`--last_stopped_at`**
- Environment variable: `LAST_STOPPED_AT`
- Type: Integer (Unix timestamp)
- Default: `0`
- Description: Internal timestamp tracking
- Note: Primarily for internal use, not user-configurable

---

## Configuration Examples

### Minimal Configuration File

```
# ~/.local/share/wnm/config
rewards_address=0xYourEthereumAddress
node_cap=30
```

### Production Configuration

```
# Production settings for a dedicated server
rewards_address=0xYourEthereumAddress:95,faucet:5
node_cap=50

# Conservative thresholds
cpu_less_than=50
cpu_remove=70
mem_less_than=60
mem_remove=75
hd_less_than=75
hd_remove=90

# Longer delays for stability
delay_start=600
delay_upgrade=600
delay_remove=600
```

### Development/Testing Configuration

```
# Development settings with dry-run
dry_run=True
loglevel=DEBUG
node_cap=5

# Aggressive thresholds for testing
cpu_less_than=80
cpu_remove=90
```

### Multi-Wallet Configuration

```
# Distribute rewards: 85% yours, 10% faucet, 5% custom donate
rewards_address=0xYourMainAddress:85,faucet:10,donate:5
donate_address=0xYourDonationAddress
node_cap=40
```

### Environment Variable Configuration

```bash
# .env file or shell exports
export REWARDS_ADDRESS="0xYourAddress"
export NODE_CAP=25
export CPU_LESS_THAN=65
export CPU_REMOVE=85
export NODE_STORAGE="/mnt/large-disk/autonomi/nodes"
```

---

## Configuration Best Practices

1. **Set conservative thresholds initially** - You can always adjust based on observed performance
2. **Leave margin between add and remove thresholds** - Prevents rapid add/remove cycles
3. **Monitor disk space closely** - `hd_remove` may want to be at 70% on ssd drives
4. **Enable logging during initial setup** - Use `--loglevel DEBUG` to understand behavior
5. **Test with dry-run first** - Always test configuration changes with `--dry_run`
6. **Document your configuration** - Keep notes on why you chose specific threshold values
7. **Back up your database** - Save `colony.db` before making major configuration changes