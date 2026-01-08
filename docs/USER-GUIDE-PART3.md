# Part 3: Configuration

## 3.1 Configuration System Overview

Weave Node Manager uses a multi-layered configuration system with the following priority (highest to lowest):

1. **Command-line arguments** - Direct flags passed when running `wnm`
2. **Environment variables** - Set in `.env` files or system environment
3. **Config files** - `~/.local/share/wnm/config`, `~/wnm/config`, or `-c/--config`
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

**`--survey_delay`**
- Environment variable: `SURVEY_DELAY`
- Type: Integer (milliseconds)
- Default: `0` (no delay)
- Description: Delay in milliseconds between surveying each node
- Use case: Spreads out the load when surveying many nodes on large servers
- Notes:
  - Applies to both automatic surveys (decision engine) and forced surveys (`--force_action survey`)
  - Delay is inserted BETWEEN nodes, not after the last node
  - Set to 0 to disable (surveys all nodes as fast as possible)
  - Useful values: 100-500ms for servers with 20+ nodes
- Example: `--survey_delay 250` inserts 250ms delay between each node survey

**`--this_survey_delay`**
- Environment variable: `THIS_SURVEY_DELAY`
- Type: Integer (milliseconds)
- Default: None (uses `--survey_delay` value)
- Description: Temporary override for `--survey_delay` for a single execution only
- Use case: Test different delay values without updating the database configuration
- Notes:
  - Takes precedence over `--survey_delay` for the current run only
  - Does not update the database value
  - Useful for one-time adjustments or testing
- Example: `--this_survey_delay 500` uses 500ms delay for this run only

**`--action_delay`**
- Environment variable: `ACTION_DELAY`
- Type: Integer (milliseconds)
- Default: `0` (no delay)
- Description: Delay in milliseconds between node operations (start, stop, upgrade, remove)
- Use case: Rate-limits node operations to prevent overwhelming the system during rapid scaling
- Notes:
  - Applies to all node lifecycle operations
  - Delay is inserted BETWEEN operations, not after the last operation
  - Set to 0 to disable (performs operations as fast as possible)
  - Useful for systems with many concurrent operations enabled
  - Does not apply to surveying (use `--survey_delay` for that)
- Example: `--action_delay 1000` inserts 1 second delay between each node operation

**`--this_action_delay`**
- Environment variable: `THIS_ACTION_DELAY`
- Type: Integer (milliseconds)
- Default: None (uses `--action_delay` value)
- Description: Temporary override for `--action_delay` for a single execution only
- Use case: Test different delay values without updating the database configuration
- Notes:
  - Takes precedence over `--action_delay` for the current run only
  - Does not update the database value
  - Useful for one-time adjustments or testing
- Example: `--this_action_delay 500` uses 500ms delay for this run only

**`--interval`**
- Environment variable: `INTERVAL`
- Type: Integer (milliseconds)
- Default: None (uses `--action_delay` value)
- Description: Alias for `--this_action_delay`, provided for antctl compatibility
- Use case: Same as `--this_action_delay`, compatible with antctl command syntax
- Notes:
  - Takes precedence over both `--this_action_delay` and `--action_delay`
  - Does not update the database value
  - Useful for users familiar with antctl
- Example: `--interval 2000` uses 2 second delay for this run only

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

### UPnP Configuration

**`--no_upnp`**
- Environment variable: `NO_UPNP`
- Type: Boolean flag
- Default: False (UPnP enabled by default)
- Description: Disable UPnP (Universal Plug and Play) port forwarding on nodes
- Use cases:
  - Running nodes behind a firewall with manually configured port forwarding
  - Security-conscious setups where automatic port forwarding is undesirable
  - Network environments where UPnP is disabled or unavailable
- Note: When UPnP is disabled, you must manually configure port forwarding for each node port

**Example:**
```bash
# Initialize with UPnP disabled
wnm --init --rewards_address 0xYourAddress --no_upnp

# Or set in config file
no_upnp=True
```

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

### Antnode Binary Path

**`--antnode_path`**
- Environment variable: `ANTNODE_PATH`
- Type: String (file path)
- Default: `~/.local/bin/antnode`
- Description: Path to the antnode binary executable
- Use cases:
  - Using a custom-built antnode binary
  - Testing different antnode versions
  - Using antnode from a non-standard installation location
- Notes:
  - Path is expanded (tilde `~` and environment variables)
  - Binary must be executable
  - All nodes will use this binary path for cloning
- Example: `--antnode_path /usr/local/bin/antnode`

### Antctl Binary Path

**`--antctl_path`**
- Environment variable: `ANTCTL_PATH`
- Type: String (file path)
- Default: `~/.local/bin/antctl`
- Description: Path to the antctl binary executable (required when using `antctl+user` or `antctl+sudo` process manager)
- Use cases:
  - **macOS cron compatibility**: Children of cron tasks on macOS cannot inherit PATH environment, causing `antctl` command not found errors. Set this to the full path to resolve.
  - Using a custom-built antctl binary
  - Testing different antctl versions
  - Using antctl from a non-standard installation location
- Notes:
  - Path is expanded (tilde `~` and environment variables)
  - Binary must be executable
  - Only used when `--process_manager` is set to `antctl+user` or `antctl+sudo`
  - Critical for macOS cron jobs to work reliably
- Examples:
  - `--antctl_path ~/.local/bin/antctl` (default)
  - `--antctl_path /usr/local/bin/antctl`
  - `--antctl_path /opt/homebrew/bin/antctl` (Homebrew on Apple Silicon)

### Antctl Debug Mode

**`--antctl_debug`**
- Environment variable: `ANTCTL_DEBUG`
- Type: Boolean flag
- Default: `False` (automatically enabled when `--loglevel DEBUG` is set)
- Description: Enable debug output for antctl commands by adding `--debug` flag to all antctl invocations
- Use cases:
  - **Troubleshooting antctl issues**: Get detailed output from antctl operations
  - **Debugging node management problems**: See verbose antctl command execution
  - **Understanding antctl behavior**: View internal antctl decision-making
  - **Development and testing**: Monitor antctl operations in detail
- Notes:
  - Only affects `antctl+user` and `antctl+sudo` process managers
  - Automatically enabled when WNM logging level is set to DEBUG
  - When enabled, all antctl commands run with `--debug` flag (e.g., `antctl --debug start`, `antctl --debug add`)
  - Debug output from antctl appears in WNM logs
  - Can be enabled persistently in database or temporarily via command-line
- Examples:

**Enable debug mode for all antctl operations:**
```bash
# Via command-line flag
wnm --antctl_debug

# Via environment variable
export ANTCTL_DEBUG=1
wnm

# Automatically enabled with DEBUG logging
wnm --loglevel DEBUG
```

**Persistent debug configuration:**
```bash
# Enable for all future runs (updates database)
wnm --force_action update_config --antctl_debug

# Or add to config file
echo "antctl_debug=True" >> ~/.local/share/wnm/config
```

**Temporary debug session:**
```bash
# Debug a specific operation
wnm --antctl_debug --force_action add --count 1
```

**Disable debug mode:**
```bash
# Debug mode stays enabled once set in database
# To disable, you must explicitly turn it off
# Setting the environment varialbe to false should persist
ANTCTL_DEBUG=false
```

### Antctl Version Configuration

**`--antctl_version`**
- Environment variable: `ANTCTL_VERSION`
- Type: String (version number)
- Default: `None` (uses latest version available)
- Description: Specify the antnode version to use when creating or upgrading nodes via antctl
- Use cases:
  - **Pin to specific version**: Lock all nodes to a specific antnode version
  - **Version consistency**: Ensure all nodes run the same version across the cluster
  - **Rollback capability**: Downgrade to a previous version if issues occur
- Notes:
  - Only affects `antctl+zen`, `antctl+user`, and `antctl+sudo` process managers
  - Passes `--version <version>` argument to both `antctl add` and `antctl upgrade` commands
  - When not set (default), antctl uses its latest available version
  - Version format should match antctl's expected format (e.g., `0.4.11`)
  - Changes take effect immediately for new operations (add/upgrade)
- Examples:

**Pin to specific version:**
```bash
# Initialize with specific version
wnm --init --rewards_address 0xYourAddress --antctl_version 0.4.11

# Or update existing cluster to use specific version
wnm --antctl_version 0.4.11

# Via environment variable
export ANTCTL_VERSION=0.4.11
wnm
```

**Persistent version configuration:**
```bash
# Set for all future runs (updates database)
wnm --force_action update_config --antctl_version 0.4.11

# Or add to config file
echo "antctl_version=0.4.11" >> ~/.local/share/wnm/config
```

**Remove version pinning:**
```bash
# Clear version setting to use latest (set to empty string)
wnm --force_action update_config --antctl_version ""
```

**Behavior:**
- **Node creation**: When `--antctl_version` is set, `antctl add --version <version>` is used
- **Node upgrades**: When `--antctl_version` is set, `antctl upgrade --version <version>` is used
- **Without setting**: antctl determines the version automatically (typically latest)

### Antctl Port Allocation Tracking

**`--highest_node_id_used`**
- Environment variable: `HIGHEST_NODE_ID_USED`
- Type: Integer
- Default: `None` (automatically initialized from existing nodes during --init)
- Description: Override the highest node ID used for port allocation tracking in antctl managers
- Use cases:
  - **Initialize with specific starting ID**: Set during --init to start node IDs from a specific number
  - **Fix port tracking desynchronization**: Manually correct the node ID counter if it gets out of sync
  - **Skip problematic port ranges**: Jump past port numbers that are blocked or in use
  - **Recovery from antctl reset**: Manually set tracking after external antctl operations
- Notes:
  - **ONLY works with antctl managers**: `antctl+zen`, `antctl+user`, `antctl+sudo`
  - **After init, requires --force_action update_config**: During normal runs, must use --force_action update_config
  - **Prevents port conflicts**: Antctl doesn't free ports on node removal, so IDs/ports never reuse
  - Port formula remains: `port = port_start * 1000 + node_id`
  - Automatically initialized during --init for antctl managers (if not explicitly set)
  - Automatically reset to 0 during --force_action teardown
  - Used internally to allocate node IDs without filling gaps

**How It Works:**

For antctl process managers, wnm tracks the highest node ID ever used instead of filling gaps when nodes are removed. This prevents port conflicts because antctl processes don't immediately free their ports when removed.

**Port Allocation Examples:**

With `--port_start 55` and sequential node creation:
- Nodes 1, 2, 3 created → highest_node_id_used = 3
- Node 2 removed → highest_node_id_used still 3
- New node added → Node ID 4 (port 55004), NOT reusing ID 2
- Gaps in node IDs (1, 3, 4, 7) → Next node gets ID 8, NOT ID 2, 5, or 6

**Examples:**

**During initialization:**
```bash
# Initialize with specific starting node ID
wnm --init --rewards_address 0xAddr --process_manager antctl+zen --highest_node_id_used 10
# First node created will be ID 11 (port 55011)

# Initialize normally (automatic initialization from existing nodes or 0)
wnm --init --rewards_address 0xAddr --process_manager antctl+zen
# Automatically initialized to max existing node ID or 0
```

**After initialization:**
```bash
# Check current tracking value
wnm --report machine-config | grep highest_node_id_used

# Override tracking (requires --force_action update_config)
wnm --force_action update_config --highest_node_id_used 20
# Next node created will be ID 21 (port 55021)

# Reset tracking after manual cleanup
wnm --force_action update_config --highest_node_id_used 0
# Next node will be ID 1 (port 55001)
```

**When to use this parameter:**

1. **During initialization with existing setup**: Starting a new wnm cluster where antctl nodes already exist at certain IDs
2. **After external antctl operations**: If you ran `antctl` commands outside of wnm and node IDs got out of sync
3. **Port conflict recovery**: If you encounter port conflicts and need to skip past problematic port numbers
4. **Manual cluster reconstruction**: When rebuilding a cluster and want to control node ID assignment

**Validation:**

This parameter has strict validation after initialization to prevent accidental desynchronization:
```bash
# ✅ During --init (no restrictions)
wnm --init --rewards_address 0xAddr --process_manager antctl+zen --highest_node_id_used 10

# ❌ After init - missing --force_action update_config
wnm --highest_node_id_used 10

# ✅ After init - correct usage
wnm --force_action update_config --highest_node_id_used 10
```

**Important:**
- Setting this incorrectly can cause port conflicts or waste port numbers
- Only modify if you understand the port allocation system
- The tracking is automatically managed during normal operations
- After initialization, this is primarily a troubleshooting/recovery parameter

### Process Manager Selection

**`--process_manager`**
- Environment variable: `PROCESS_MANAGER`
- Type: String
- Choices: `systemd+sudo`, `systemd+user`, `setsid+sudo`, `setsid+user`, `launchd+sudo`, `launchd+user`, `antctl+sudo`, `antctl+user`
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
  - `antctl+sudo` uses antctl CLI wrapper with sudo (requires antctl installation)
  - `antctl+user` uses antctl CLI wrapper without sudo (requires antctl installation)

### Logging Configuration

**`--loglevel`**
- Environment variable: `LOGLEVEL`
- Type: String
- Choices: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- Default: `INFO`
- Description: Python logging level for wnm output
- Note: Controls verbosity of wnm's own logging output

**`-v` / `--verbose`**
- Flag only (no environment variable)
- Type: Boolean flag
- Default: False
- Description: Enable verbose output (sets loglevel to DEBUG)
- Note: Shorthand for `--loglevel DEBUG`

**`-q` / `--quiet`**
- Flag only (no environment variable)
- Type: Boolean flag
- Default: False
- Description: Quiet mode - suppresses all output except errors
- Note: Sets loglevel to ERROR, useful for cron jobs and automation

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

These settings control how many nodes can be in transitional states simultaneously, allowing powerful machines to perform multiple operations in parallel for faster scaling.

**`--max_concurrent_upgrades`**
- Environment variable: `MAX_CONCURRENT_UPGRADES`
- Type: Integer
- Default: `1`
- Description: Maximum nodes that can be upgrading simultaneously
- Use case: Set higher on powerful machines to upgrade clusters faster
- Example: `--max_concurrent_upgrades 4`

**`--max_concurrent_starts`**
- Environment variable: `MAX_CONCURRENT_STARTS`
- Type: Integer
- Default: `1`
- Description: Maximum nodes that can be starting/restarting simultaneously
- Use case: Set higher for faster cluster growth on machines with spare resources
- Example: `--max_concurrent_starts 4`

**`--max_concurrent_removals`**
- Environment variable: `MAX_CONCURRENT_REMOVALS`
- Type: Integer
- Default: `1`
- Description: Maximum nodes that can be in removal process simultaneously
- Use case: Set higher to remove nodes faster during resource pressure or teardown
- Example: `--max_concurrent_removals 2`

**`--max_concurrent_operations`**
- Environment variable: `MAX_CONCURRENT_OPERATIONS`
- Type: Integer
- Default: `1`
- Description: Maximum total concurrent operations across all types (global limit)
- Use case: Prevents overwhelming the system with too many simultaneous operations
- Note: Effective limit is MIN(per_operation_limit, remaining_global_capacity)
- Example: `--max_concurrent_operations 8`

### Concurrent Operations Examples

**Conservative (default):**
```bash
wnm --max_concurrent_upgrades 1 \
    --max_concurrent_starts 1 \
    --max_concurrent_operations 1
```
- Adds/upgrades nodes one at a time
- Safest option, prevents system overload
- Recommended for most users

**Aggressive (powerful machine):**
```bash
wnm --max_concurrent_upgrades 4 \
    --max_concurrent_starts 4 \
    --max_concurrent_removals 2 \
    --max_concurrent_operations 8
```
- Adds up to 4 nodes simultaneously
- Upgrades up to 4 nodes in parallel
- Faster cluster growth and upgrades

**Very aggressive (high-end server):**
```bash
wnm --max_concurrent_upgrades 10 \
    --max_concurrent_starts 10 \
    --max_concurrent_removals 5 \
    --max_concurrent_operations 20
```
- Maximize parallelization for rapid scaling
- Can add 10+ nodes per minute
- Best for: Dedicated servers
- Monitor system resources carefully

### How Concurrent Operations Work

WNM will **aggressively scale to capacity** each cycle:
- If upgrade limit is 4 and 2 nodes are upgrading, WNM will start 2 more upgrades immediately
- Operations respect both per-type limits AND global limit
- Dead node removals always take priority and ignore limits
- Each action selects a different node (no duplicate operations on same node)

**Capacity Constraints:**

Operations are limited by actual node availability:
- **Upgrades**: Limited by nodes needing upgrade
- **Starts**: Limited by stopped nodes available
- **Adds**: Limited by node cap - total nodes
- **Removes**: Limited by stopped/running nodes available

Example: If `max_concurrent_starts=4` but only 2 stopped nodes exist, WNM will:
1. Start 2 stopped nodes
2. Add 2 new nodes (if under node cap)

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
- Choices: `add`, `remove`, `upgrade`, `start`, `stop`, `disable`, `teardown`, `survey`, `wnm-db-migration`, `nullop`, `update_config`, `disable_config`
- Description: Force a specific action regardless of resource thresholds
- Use with: `--service_name` to target specific nodes (for node actions)
- Use with: `--count` to affect multiple nodes (for node actions)
- Use with: `--confirm` for destructive operations (`teardown`, `wnm-db-migration`)

#### Lightweight Config Update Actions

**`nullop` / `update_config`**
- Type: Forced action (bypasses decision engine)
- Description: Update configuration settings without running the full decision engine cycle
- Use cases:
  - Quick configuration parameter changes
  - Testing configuration updates with `--dry_run`
  - Updating thresholds without triggering node management
  - Minimal resource usage for config-only operations
- Behavior:
  - Loads minimal resources (config only, no system metrics)
  - Applies any command-line config parameter changes to database
  - Exits immediately without node surveying or decision engine
  - Supports `--dry_run` mode for testing changes
- Notes:
  - Both `nullop` and `update_config` are aliases for the same action
  - Does NOT collect system metrics or node status
  - Does NOT run the decision engine or take any node actions
  - Only updates configuration values in the database

**Examples:**

Update node capacity:
```bash
wnm --force_action nullop --node_cap 30
```

Update CPU thresholds:
```bash
wnm --force_action update_config --cpu_less_than 60 --cpu_remove 80
```

Test configuration change without saving (dry-run):
```bash
wnm --force_action nullop --mem_less_than 70 --dry_run
```

Verify configuration loads correctly (no changes):
```bash
wnm --force_action update_config
```

Update multiple settings at once:
```bash
wnm --force_action nullop --node_cap 40 --delay_start 600 --survey_delay 250
```

**`disable_config`**
- Type: Forced action (bypasses decision engine)
- Description: Disable boolean configuration flags by setting them to False in the database
- Use cases:
  - Disable persistent boolean settings that are difficult to unset
  - Turn off debug mode or other boolean flags
  - Fix stuck boolean settings from config files or environment variables
- Behavior:
  - Works like `nullop` / `update_config` but **inverts** boolean flags
  - When used with `--antctl_debug` or `--no_upnp`, sets them to False
  - Loads minimal resources (config only, no system metrics)
  - Exits immediately without node surveying or decision engine
- Supported flags:
  - `--antctl_debug`: Disable antctl debug mode
  - `--no_upnp`: Re-enable UPnP (sets no_upnp to False)
- Notes:
  - Boolean flags using `action="store_true"` normally can't be disabled once set in the database
  - This action provides a way to explicitly disable these persistent settings
  - Only updates configuration values in the database
  - Does NOT collect system metrics or run the decision engine

**Examples:**

Disable antctl debug mode:
```bash
wnm --force_action disable_config --antctl_debug
```

Re-enable UPnP (disable no_upnp flag):
```bash
wnm --force_action disable_config --no_upnp
```

Disable multiple boolean flags:
```bash
wnm --force_action disable_config --antctl_debug --no_upnp
```

**Why is this needed?**

Some boolean settings use the `store_true` pattern, which means:
- Providing the flag sets it to True
- Not providing the flag defaults to False (but doesn't update the database)

Once a `store_true` flag is set in the database, simply omitting it won't change it back to False. The `disable_config` action solves this by explicitly setting these flags to False when specified.

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
- Choices: `node-status`, `node-status-details`, `influx-resources`, `machine-config`, `machine-metrics`
- Description: Generate a status report instead of managing nodes
- Report types:
  - `node-status`: Tabular summary with service name, peer ID, status, and connected peers
  - `node-status-details`: Detailed information for each node including paths, version, and metrics
  - `influx-resources`: InfluxDB line protocol format for metrics integration
  - `machine-config`: Machine configuration with database path (text, JSON, or env format)
  - `machine-metrics`: Current system metrics (text, JSON, or env format)

**`--report_format`**
- Environment variable: `REPORT_FORMAT`
- Type: String
- Choices: `text`, `json`, `env`, `config`
- Default: `text`
- Description: Output format for reports
- Format details:
  - `text`: Human-readable key: value format
  - `json`: JSON format for programmatic parsing
  - `env`: Environment variable format (UPPER_CASE_KEY=value) - for shell environment variables
  - `config`: Config file format (lower_snake_case_key=value) - for use in config files that are read by configargparse
- Format support:
  - `machine-config` report: Supports all formats (text, json, env, config)
  - `machine-metrics` report: Supports text, json, and env formats
  - `node-status` and `node-status-details` reports: Support text and json formats only
- Note: `influx-resources` report only supports InfluxDB line protocol format (no json/text/env/config option)

**`--json`**
- Type: Boolean flag (shortcut)
- Description: Shortcut for `--report_format json`
- Use case: Convenient way to request JSON output that is compatible with antctl
- Examples:
  - `wnm --report node-status --json` (equivalent to `--report_format json`)
  - `wnm --report machine-config --json`
  - `wnm --report machine-metrics --json`

### Machine Config Report Examples

The `machine-config` report displays your cluster's configuration settings. It supports four output formats.

**Text Format (default):**
```bash
wnm --report machine-config

# Output:
# cpu_count: 8
# node_cap: 50
# cpu_less_than: 70
# rewards_address: 0x00455d78f850b0358E8cea5be24d415E01E107CF
# ...
```

**JSON Format:**
```bash
wnm --report machine-config --report_format json

# Output:
# {
#   "cpu_count": 8,
#   "node_cap": 50,
#   "cpu_less_than": 70,
#   "rewards_address": "0x00455d78f850b0358E8cea5be24d415E01E107CF",
#   ...
# }
```

**Environment Variable Format:**

The `env` format outputs configuration as shell environment variables (unquoted values):

```bash
wnm --report machine-config --report_format env

# Output:
# CPU_COUNT=8
# NODE_CAP=50
# CPU_LESS_THAN=70
# REWARDS_ADDRESS=0x00455d78f850b0358E8cea5be24d415E01E107CF
# ...
```

**Using env format in shell scripts:**

```bash
# Save configuration to file
wnm --report machine-config --report_format env > ~/wnm-config.env

# Source the file to load variables
source ~/wnm-config.env

# Now you can use the variables
echo "Current node capacity: $NODE_CAP"
echo "Rewards address: $REWARDS_ADDRESS"
```

**Inline usage with eval:**

```bash
# Load config directly into current shell
eval $(wnm --report machine-config --report_format env)

# Use the variables immediately
if [ "$NODE_CAP" -lt 50 ]; then
    echo "Node capacity is below 50"
fi
```

**Example script using machine config:**

```bash
#!/bin/bash
# Load WNM configuration
eval $(wnm --report machine-config --report_format env)

# Display current settings
echo "=== WNM Configuration ==="
echo "Node Capacity: $NODE_CAP"
echo "CPU Add Threshold: $CPU_LESS_THAN%"
echo "CPU Remove Threshold: $CPU_REMOVE%"
echo "Memory Add Threshold: $MEM_LESS_THAN%"
echo "Memory Remove Threshold: $MEM_REMOVE%"
echo "Rewards Address: $REWARDS_ADDRESS"
echo "Node Storage: $NODE_STORAGE"
echo "Database: $DBPATH"
```

**Config File Format:**

The `config` format outputs configuration in a format suitable for WNM config files. Unlike the `env` format (which uses UPPER_CASE for shell environment variables), the `config` format uses lower_snake_case parameter names that match command-line arguments.

```bash
wnm --report machine-config --report_format config

# Output:
# cpu_count=8
# node_cap=50
# cpu_less_than=70
# rewards_address=0x00455d78f850b0358E8cea5be24d415E01E107CF
# node_storage="/Users/dawn/Library/Application Support/autonomi/node"
# ...
```

**Using config format to save/load configuration:**

```bash
# Export current configuration to a config file
wnm --report machine-config --report_format config > ~/.local/share/wnm/config

# Now wnm will automatically load these settings from the config file
# You can override individual values via command line:
wnm --node_cap 60  # Uses config file values except node_cap

# Or create a custom config file
wnm --report machine-config --report_format config > ~/my-custom-config
wnm --config ~/my-custom-config
```

**Example: Saving and modifying configuration:**

```bash
# 1. Export current config
wnm --report machine-config --report_format config > /tmp/wnm-backup.config

# 2. Edit the file to adjust settings (edit cpu_less_than, mem_less_than, etc.)
nano /tmp/wnm-backup.config

# 3. Load the modified config
wnm --config /tmp/wnm-backup.config

# The config file will update the database with any changed values
```

### Machine Metrics Report Examples

The `machine-metrics` report displays current system resource usage and node statistics. It supports three output formats.

**Text Format (default):**
```bash
wnm --report machine-metrics

# Output:
# system_start: 1762763731
# total_nodes: 5
# running_nodes: 4
# stopped_nodes: 1
# cpu_percent: 45.3
# mem_percent: 62.1
# ...
```

**JSON Format:**
```bash
wnm --report machine-metrics --report_format json

# Output:
# {
#   "system_start": 1762763731,
#   "total_nodes": 5,
#   "running_nodes": 4,
#   "stopped_nodes": 1,
#   "cpu_percent": 45.3,
#   "mem_percent": 62.1,
#   ...
# }
```

**Environment Variable Format:**

The `env` format outputs metrics as shell environment variables (unquoted values):

```bash
wnm --report machine-metrics --report_format env

# Output:
# SYSTEM_START=1762763731
# TOTAL_NODES=5
# RUNNING_NODES=4
# STOPPED_NODES=1
# CPU_PERCENT=45.3
# MEM_PERCENT=62.1
# ...
```

**Using env format in shell scripts:**

```bash
# Load metrics into current shell environment
eval $(wnm --report machine-metrics --report_format env)

# Now you can use the metrics as variables
echo "Running nodes: $RUNNING_NODES out of $TOTAL_NODES"
echo "CPU usage: $CPU_PERCENT%"
echo "Memory usage: $MEM_PERCENT%"
```

**Example monitoring script:**

```bash
#!/bin/bash
# Load current system metrics
eval $(wnm --report machine-metrics --report_format env)

# Display resource usage
echo "=== System Resource Usage ==="
echo "CPU: ${CPU_PERCENT}%"
echo "Memory: ${MEM_PERCENT}%"
echo "Disk: ${HD_PERCENT}%"
echo "Load Average (1min): ${LOAD_AVERAGE_1}"
echo ""
echo "=== Node Status ==="
echo "Total Nodes: $TOTAL_NODES"
echo "Running: $RUNNING_NODES"
echo "Stopped: $STOPPED_NODES"
echo "Upgrading: $UPGRADING_NODES"
echo "Needs Upgrade: $NODES_TO_UPGRADE"
```

**Conditional actions based on metrics:**

```bash
#!/bin/bash
# Load metrics
eval $(wnm --report machine-metrics --report_format env)

# Check if system is under pressure
if (( $(echo "$CPU_PERCENT > 80" | bc -l) )); then
    echo "WARNING: High CPU usage detected: ${CPU_PERCENT}%"
    # Take action, e.g., alert, scale down, etc.
fi

if (( $(echo "$MEM_PERCENT > 85" | bc -l) )); then
    echo "WARNING: High memory usage detected: ${MEM_PERCENT}%"
fi

# Check node health
if [ "$STOPPED_NODES" -gt 0 ]; then
    echo "Notice: $STOPPED_NODES node(s) are stopped"
fi

if [ "$NODES_TO_UPGRADE" -gt 0 ]; then
    echo "Notice: $NODES_TO_UPGRADE node(s) need upgrade"
fi
```

**Combining config and metrics:**

```bash
#!/bin/bash
# Load both configuration and current metrics
eval $(wnm --report machine-config --report_format env)
eval $(wnm --report machine-metrics --report_format env)

# Compare current usage against thresholds
echo "=== Threshold Analysis ==="
echo "CPU: ${CPU_PERCENT}% (Add < ${CPU_LESS_THAN}%, Remove > ${CPU_REMOVE}%)"
echo "Memory: ${MEM_PERCENT}% (Add < ${MEM_LESS_THAN}%, Remove > ${MEM_REMOVE}%)"
echo "Disk: ${HD_PERCENT}% (Add < ${HD_LESS_THAN}%, Remove > ${HD_REMOVE}%)"
echo ""
echo "Nodes: ${TOTAL_NODES} / ${NODE_CAP} (capacity)"

# Determine if we're in add or remove territory
if (( $(echo "$CPU_PERCENT < $CPU_LESS_THAN" | bc -l) )) && \
   (( $(echo "$MEM_PERCENT < $MEM_LESS_THAN" | bc -l) )) && \
   [ "$TOTAL_NODES" -lt "$NODE_CAP" ]; then
    echo "Status: System can ADD nodes"
elif (( $(echo "$CPU_PERCENT > $CPU_REMOVE" | bc -l) )) || \
     (( $(echo "$MEM_PERCENT > $MEM_REMOVE" | bc -l) )); then
    echo "Status: System may REMOVE nodes"
else
    echo "Status: System is in stable range"
fi
```

### InfluxDB Resources Report Export Examples

The `influx-resources` report generates output in InfluxDB line protocol format, which can be ingested by [NTracking](https://github.com/safenetforum-community/NTracking) using Telegraf.

**Prerequisites:**
- Telegraf installed and configured with `inputs.file` plugin
- Directory for InfluxDB line protocol files (e.g., `/tmp/influx-resources/`)
- Telegraf configuration watching the directory

**Linux (Local Telegraf Installation):**

When Telegraf is running on the same Linux machine as wnm:

```bash
# Export metrics to file for Telegraf ingestion
wnm --report influx-resources --force_action survey -q > /tmp/influx-resources/influx-resources
```

This writes the InfluxDB line protocol directly to a file that Telegraf can read and forward to InfluxDB.

**macOS (Remote Telegraf via SSH):**

When running wnm on macOS and Telegraf is on a remote Linux machine (e.g., a VM):

```bash
# Export metrics and send to remote Telegraf host via SSH
wnm --report influx-resources --force_action survey -q | ssh xdntracking tee /tmp/influx-resources/influx-resources
```

This pipes the output through SSH to write it to the remote machine's Telegraf input directory.

**Automation with Cron:**

Add to crontab to export metrics every minute:

```bash
# Linux (local Telegraf)
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
/5 * * * * . ~/.venv/bin/activate && wnm --report influx-resources --force_action survey -q > /tmp/influx-resources/influx-resources 2>&1

# macOS (remote Telegraf)
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
* * * * * /Users/username/.pyenv/versions/3.14.0/bin/wnm --report influx-resources --force_action survey -q | ssh xdntracking tee /tmp/influx-resources/influx-resources >/dev/null 2>&1
```

**Notes:**
- Use `-q` (quiet mode) to suppress non-metric output
- `--force_action survey` updates all node metrics before generating the report
- Ensure the target directory exists and is writable
- For SSH method, set up SSH key authentication to avoid password prompts

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

---

## 3.7 Database Migrations

### Overview

WNM uses Alembic for database schema migrations. The system automatically detects when your database schema is out of date and requires migration.

### Automatic Detection

On every startup, WNM checks if your database schema matches the current version:
- ✅ **Up to date**: Normal operation continues
- ⚠️ **Out of date**: WNM exits with error and migration instructions

### When Migrations Are Needed

Database migrations are required when:
- Upgrading WNM to a new version with schema changes
- New fields are added to the Machine or Node tables
- Existing fields are modified or removed

### Running Database Migrations

**IMPORTANT: Always backup your database before running migrations!**

**Step 1: Backup your database**
```bash
# macOS user mode
cp ~/Library/Application\ Support/autonomi/colony.db ~/Library/Application\ Support/autonomi/colony.db.backup

# macOS sudo mode
sudo cp /Library/Application\ Support/autonomi/colony.db /Library/Application\ Support/autonomi/colony.db.backup

# Linux user mode
cp ~/.local/share/autonomi/colony.db ~/.local/share/autonomi/colony.db.backup

# Linux sudo mode
sudo cp /var/antctl/colony.db /var/antctl/colony.db.backup
```

**Step 2: Run migrations**
```bash
wnm --force_action wnm-db-migration --confirm
```

**`--force_action wnm-db-migration`**
- Requires: `--confirm` flag
- Description: Run pending database migrations
- Safety: Conservative approach - always warns and requires confirmation
- Output: Shows current revision → target revision
- Exit codes:
  - `0`: Success (migrations completed or already up to date)
  - `1`: Failure (error during migration, restore from backup)

### Migration Process

When you run the migration command:

1. **Validation**: Checks for pending migrations
2. **Warning**: Displays current and target schema versions
3. **Execution**: Runs all pending migrations in order
4. **Confirmation**: Reports success or failure

### Migration Examples

**Check if migrations are needed:**
```bash
# Just try to run WNM normally
wnm

# If migrations are needed, you'll see:
# ======================================================================
# DATABASE MIGRATION REQUIRED
# ======================================================================
#
# Your database schema is out of date:
#   Current revision: abc5afa09a61
#   Required revision: 3249fcc20390
#
# IMPORTANT: Backup your database before proceeding!
#
# To run migrations:
#   wnm --force_action wnm-db-migration --confirm
# ======================================================================
```

**Run migrations:**
```bash
wnm --force_action wnm-db-migration --confirm

# Output:
# ======================================================================
# RUNNING DATABASE MIGRATIONS
# ======================================================================
# Upgrading database from abc5afa09a61 to 3249fcc20390
# Database migration completed successfully!
# ======================================================================
```

**Already up to date:**
```bash
wnm --force_action wnm-db-migration --confirm

# Output:
# Database is already up to date!
# Current revision: 3249fcc20390
```

### New Database Initialization

New databases are automatically stamped with the current schema version:
- No manual migration needed for fresh installations
- First run with `--init` creates database at current version
- Migration system is ready for future updates

### Migration History

WNM tracks schema versions using Alembic revisions. Each migration has:
- **Revision ID**: Unique identifier (e.g., `3249fcc20390`)
- **Description**: Human-readable description (e.g., "add_delay_restart_to_machine")
- **Upgrade function**: Applies schema changes
- **Downgrade function**: Reverts schema changes (if needed)

### Troubleshooting

**Migration fails:**
1. Stop WNM if running: `wnm --remove_lockfile`
2. Restore from backup
3. Report the issue with error details
4. Wait for fix before upgrading

**Database locked error:**
- Ensure no other WNM instances are running
- Remove lock file: `wnm --remove_lockfile`
- Try migration again

**Unknown revision:**
- Your database may be from a different branch or fork
- Backup and start fresh with `--init`

### Best Practices

1. **Always backup before migrating** - Cannot be stressed enough
2. **Read release notes** - Check for breaking changes or special instructions
3. **Keep backups** - Maintain multiple backup copies before major upgrades
4. **Don't skip versions** - Migrate sequentially through versions
5. **Monitor the migration** - Watch for errors during migration process

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