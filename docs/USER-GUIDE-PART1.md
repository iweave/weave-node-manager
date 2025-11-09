# Weave Node Manager - User Guide
# Part 1: Getting Started

---

## 1.1 Introduction

### What is Weave Node Manager?

Weave Node Manager (wnm) is a Python-based tool that automatically manages Autonomi network nodes on your computer. It monitors your system resources (CPU, memory, disk, network I/O, and load average) and continuously adds or removes nodes to keep your system running smoothly while maximizing your participation in the Autonomi network.

Think of it as an autopilot for your Autonomi nodes - you set resource thresholds, and wnm handles the rest: creating nodes when you have spare capacity, removing them when resources get tight, upgrading to new versions, and restarting nodes that encounter problems.

### Key Features and Capabilities

- **Automatic Resource Management**: Monitors CPU, memory, disk, I/O, and load average to decide when to add or remove nodes
- **Smart Node Lifecycle**: Creates, starts, stops, upgrades, and removes nodes automatically
- **Platform-Native Process Management**:
  - macOS: Uses launchd for reliable node management
  - Linux (root): Uses systemd system services
  - Linux (user): Uses systemd user services
- **Independent Node Upgrades**: Each node has its own binary copy, allowing gradual rollouts
- **Flexible Wallet Support**: Route rewards to a single address or distribute across multiple wallets with weighted randomization
- **Conservative Operation**: Makes only one decision per execution cycle to avoid cascading changes
- **SQLite Database**: Tracks all configuration and node state locally

### When to Use wnm vs anm

**Use Weave Node Manager (wnm) if you:**
- Want a modern Python-based tool with active development
- Need macOS support (wnm is fully supported on macOS)
- Prefer user-level node management (no sudo required)
- Want flexible wallet distribution options
- Are starting fresh with Autonomi nodes

**Use Autonomi Node Manager (anm) if you:**
- Already have a working anm installation on Linux
- Prefer the mature, battle-tested shell script approach
- Are comfortable with the current anm feature set

**Note:** wnm can migrate from existing anm installations on Linux, so you're not locked in.

### Platform Support Overview

#### macOS (Fully Supported)
- **Process Manager**: launchd (user agents in `~/Library/LaunchAgents/`)
- **Firewall**: None required currently (nodes use --relay mode)
- **Data Location**: `~/Library/Application Support/autonomi/`
- **Logs**: `~/Library/Logs/autonomi/`
- **Privileges**: No sudo required - runs entirely in user space
- **Status**: Ready for personal and development use

#### Linux (Fully Supported)

**Option A: User-Level (Recommended)**
- **Process Manager**: systemd user services
- **Firewall**: Optional (no UFW integration in user mode)
- **Data Location**: `~/.local/share/autonomi/`
- **Privileges**: No sudo required
- **Status**: Ready, recommended for most users

**Option B: Root-Level (Advanced)**
- **Process Manager**: systemd services
- **Firewall**: UFW (optional)
- **Data Location**: `/var/antctl/`
- **Privileges**: Requires sudo
- **Status**: Ready, compatible with anm migration
- **Use Case**: Multi-user systems, server deployments

### Alpha Software Disclaimer

Weave Node Manager is **Alpha software**. While it has been tested and is in active use, you should be aware that:

- **Breaking changes may occur** between versions
- **Database schema may change** without automatic migration (you may need to reinitialize)
- **Bugs and edge cases** are still being discovered and fixed
- **Documentation may lag** behind the latest features
- **Backup your configuration** (especially your `colony.db` database) before upgrading
- **ANM cluster migration is one-way** you have to reset if you want to go back to anm

That said, wnm is designed to be safe:
- It operates conservatively by default (one action per cycle)
- Dry-run mode lets you test before making changes


**Recommended for**: Development, testing, personal node running, and enthusiasts who want to help test and improve the tool.

**Not recommended for**: Mission-critical production deployments where stability is paramount over new features.

---

## 1.2 Prerequisites

### Python Version Requirements

Weave Node Manager requires **Python 3.12.3 or higher**.

**Check your Python version:**
```bash
python3 --version
```

You should see output like `Python 3.12.3` or higher.

**macOS Installation:**
```bash
# Install via Homebrew
brew install python@3.12

# Or download from python.org
# https://www.python.org/downloads/macos/
```

**Linux Installation:**
```bash
# Ubuntu/Debian 24.04+
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip

```

### System Requirements

Autonomi nodes are not resource-intensive. Your system should have:

**Minimum (1-10 nodes):**
- **CPU**: 2 cores
- **RAM**: 4 GB
- **Disk**: 35 GB free space per node
- **Network**: Stable broadband connection (10 Mbps+)

**Recommended (50+ nodes):**
- **CPU**: 4+ cores
- **RAM**: 16 GB+
- **Disk**: 1 TB+ free space
- **Network**: High-speed connection (100 Mbps+)

**Storage Considerations:**
- Each node can consume 5-35 GB of disk space depending on network capacity
- Nodes store encrypted data chunks from the Autonomi network
- Monitor disk space carefully - wnm will remove nodes if disk usage exceeds thresholds

### Platform-Specific Prerequisites

#### macOS

**Required:**
- macOS 10.15 (Catalina) or later
- launchd (built into macOS, no installation needed)
- Write access to `~/Library/Application Support/` and `~/Library/LaunchAgents/`

**Network Setup:**
- No firewall configuration needed currently
- Nodes run with `--relay` flag (until pf firewall solved)
- Nodes run with `--no-upnp` flag (no port forwarding required)
- Ensure your firewall (if enabled) allows bi-directional connections

**Optional:**
- Homebrew package manager (recommended for installing Python and dependencies)

#### Linux

**User-Level Mode (Recommended):**
- systemd-based distribution (most modern Linux distros)
- Write access to `~/.local/share/` (standard XDG directories)
- No sudo required
- No firewall configuration supported

**Root-Level Mode (Advanced):**
- systemd-based distribution (most modern Linux distros)
- sudo/root access
- Optional: UFW for firewall management
- If migrating from anm: existing `/var/antctl/` directory

### Autonomi Network Basics

Before running nodes, you should understand a few key concepts:

**What is an Autonomi Node?**
- A program (`antnode`) that stores encrypted data chunks for the Autonomi network
- Earns rewards in ANT tokens for providing storage and serving data
- Contributes to a decentralized, secure, and private data storage network

**Rewards Address (Ethereum Address):**
- You need an Ethereum-compatible wallet address (starts with `0x`)
- Rewards are paid to this address
- You can use any Ethereum wallet: MetaMask, hardware wallet, etc.
- wnm supports distributing rewards across multiple addresses

**Node Lifecycle:**
- Nodes join the network and build reputation over time
- Nodes that go offline frequently may be penalized
- Regular upgrades keep nodes compatible with network changes and earnings

**Network Participation:**
- Nodes communicate with other nodes to store and retrieve data
- Network uses UDP for communication
- Current setup requires port forwarding (UPnP disabled)
- Stable internet connection is important

**Getting a Rewards Address:**
If you don't have one:
1. Install MetaMask browser extension (https://metamask.io)
2. Create a new wallet and securely store your seed phrase
3. Copy your Ethereum address (click on account name to copy)
4. That's it - you can use this address with wnm

**Security Note:** Your rewards address is public information (it's written to node logs and config files). Never share your wallet's private key or seed phrase.

---

## 1.3 Quick Start Guide

This section provides step-by-step installation instructions for three different scenarios. Choose the one that matches your platform and use case.

### Option A: macOS

This guide covers installation on macOS for both development and production use.

#### Step 1: Install antup (Autonomi Binary Manager)

antup is the official tool for downloading and managing Autonomi binaries.

```bash
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash
```

This installs antup to `~/.local/bin/antup`.

**Verify installation:**
```bash
~/.local/bin/antup --version
```

#### Step 2: Download the antnode Binary

```bash
~/.local/bin/antup node
```

This downloads the latest `antnode` binary to `~/.local/bin/antnode`.

**Verify the binary:**
```bash
~/.local/bin/antnode --version
```

You should see version information for the Autonomi node software.

#### Step 3: Install Weave Node Manager

**From PyPI (Recommended):**
```bash
pip3 install wnm
```

**Or from source (for development):**
```bash
git clone https://github.com/ambled/weave-node-manager.git
cd weave-node-manager
pip3 install -e .
```

**Verify installation:**
```bash
wnm --version
```

#### Step 4: Initialize WNM with Your Rewards Address

Replace `0xYourEthereumAddress` with your actual Ethereum wallet address:

```bash
wnm --init --rewards_address 0xYourEthereumAddress
```

This creates:
- Database: `~/Library/Application Support/autonomi/colony.db`
- Log directory: `~/Library/Logs/autonomi/`
- Node storage: `~/Library/Application Support/autonomi/node/`

**What happens during initialization:**
- Creates the SQLite database with default configuration
- Sets your rewards address
- Configures platform-specific paths for macOS
- Sets resource thresholds to safe defaults (70% add, 80% remove)
- Sets node cap to 50 (maximum nodes)

#### Step 5: Test with Dry-Run Mode

Before letting wnm make changes, test it in dry-run mode:

```bash
wnm --dry_run
```

**What to look for:**
- No errors during execution
- Output shows current system metrics (CPU, memory, disk, etc.)
- Shows what action wnm *would* take (but doesn't actually do it)
- Example: "Would add node (dry run)" or "Idle: all thresholds OK"

**Run it a few times** to see how wnm responds to your current system state.

#### Step 6: Run Normally to Start Managing Nodes

When you're ready, run wnm without dry-run:

```bash
wnm
```

**First run will typically:**
- Create your first node (antnode-1) if resources are below add thresholds
- Create the launchd plist file in `~/Library/LaunchAgents/com.autonomi.antnode-1.plist`
- Start the node using `launchctl bootstrap`
- Wait about 30 seconds for the node to start
- Display the action taken and system metrics

**Check node status:**
```bash
# List all launchd services for Autonomi nodes
launchctl list | grep autonomi

# View logs
tail -f ~/Library/Logs/autonomi/antnode-1.log
```

#### Step 7: Set Up Cron for Automated Management (Optional)

For wnm to continuously manage your nodes, add it to your crontab:

```bash
crontab -e
```

Add this line (adjust path to your Python installation):

```cron
*/1 * * * * /Users/username/.pyenv/versions/3.14.0/bin/python3 -m wnm >> ~/Library/Logs/autonomi/wnm-cron.log 2>&1
```

**Note:** Replace `/Users/username/.pyenv/versions/3.14.0` with your actual pyenv Python path. Find it with:
```bash
which python3
```

**This will:**
- Run wnm every minute
- Make one decision per minute (add node, remove node, upgrade, etc.)
- Log all output to `~/Library/Logs/autonomi/wnm-cron.log`

**Monitor the cron log:**
```bash
tail -f ~/Library/Logs/autonomi/wnm-cron.log
```

---

### Option B: Linux User-Level (Recommended)

This is the recommended approach for most Linux users without a firewall - no sudo required.

#### Step 1: Install Python 3.12.3+

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip

```

Verify:
```bash
python3 --version
```

#### Step 2: Install antup

```bash
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash
```

Add `~/.local/bin` to your PATH if not already there:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### Step 3: Download antnode Binary

```bash
antup node
```

Verify:
```bash
antnode --version
```

#### Step 4: Install Weave Node Manager

**From PyPI:**
```bash
pip3 install wnm
```

**Or from source:**
```bash
git clone https://github.com/ambled/weave-node-manager.git
cd weave-node-manager
pip3 install -e .
```

Ensure `~/.local/bin` is in your PATH:
```bash
which wnm
```

#### Step 5: Initialize WNM

```bash
wnm --init --rewards_address 0xYourEthereumAddress
```

This creates:
- Database: `~/.local/share/autonomi/colony.db`
- Log directory: `~/.local/share/autonomi/logs/`
- Node storage: `~/.local/share/autonomi/node/`

#### Step 6: Test in Dry-Run Mode

```bash
wnm --dry_run
```

Run multiple times to observe wnm's decision-making based on your system resources.

#### Step 7: Run Normally

```bash
wnm
```

The first run will typically create and start your first node.

**Check node processes:**
```bash
ps aux | grep antnode
```

**View logs:**
```bash
tail -f ~/.local/share/autonomi/logs/antnode-1.log
```

#### Step 8: Set Up Cron

```bash
crontab -e
```

Add:
```cron
*/1 * * * * . ~/.venv/bin/activate && wnm >> ~/.local/share/autonomi/logs/wnm-cron.log 2>&1
```

**Note:** Adjust `~/.venv` to match your virtual environment path if different.

**Monitor:**
```bash
tail -f ~/.local/share/autonomi/logs/wnm-cron.log
```

---

### Option C: Linux Root-Level (Production)

This approach uses systemd for process management and is compatible with anm migrations.

**⚠️ Warning:** This requires root/sudo access and modifies system-level directories.

#### Step 1: Install System Dependencies

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

#### Step 2: Install antup and antnode with sudo

```bash
# Install antup for your user
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash

# Download antnode
~/.local/bin/antup node

# Copy to system location if not running as the 'ant' user
sudo cp ~/.local/bin/antnode /usr/local/bin/
sudo chmod +x /usr/local/bin/antnode

# Verify
antnode --version
```

#### Step 3: Install WNM System-Wide

```bash
sudo pip3 install wnm
```

Verify:
```bash
which wnm
# Should show /usr/local/bin/wnm
```

#### Step 4: Initialize

**If migrating from anm:**
```bash
wnm --init --migrate_anm
```

This will:
- Disable anm by removing `/etc/cron.d/anm`
- Read configuration from `/var/antctl/config`
- Import existing nodes from systemd services
- Take over management from anm

**If starting fresh:**
```bash
wnm --init --rewards_address 0xYourEthereumAddress --process_manager systemd+sudo
```

This creates:
- Database: `/var/antctl/colony.db`
- Log directory: `/var/log/antnode/`
- Node storage: `/var/antctl/services/`

#### Step 5: Test in Dry-Run Mode

```bash
sudo wnm --dry_run
```

If you migrated from anm, you should see your existing nodes in the output.

#### Step 6: Run Normally

```bash
sudo wnm
```

**Check systemd services:**
```bash
systemctl list-units | grep antnode
```

**View logs:**
```bash
journalctl -u antnode-1 -f
# Or
tail -f /var/log/antnode/antnode-1.log
```

#### Step 7: Set Up Root Cron

```bash
sudo crontab -e
```

Add (adjust Python path as needed):
```cron
*/1 * * * * /usr/bin/python3 -m wnm >> /var/antctl/wnm-cron.log 2>&1
```

**Note:** If you installed wnm in a virtual environment, activate it first:
```cron
*/1 * * * * . /opt/venv/bin/activate && wnm >> /var/antctl/wnm-cron.log 2>&1
```

**Monitor:**
```bash
sudo tail -f /var/antctl/wnm-cron.log
```

---

## 1.4 First Run Tutorial

This section walks you through what happens during wnm's first few runs and explains how to monitor and understand its behavior.

### Understanding the Initialization Process

When you run `wnm --init --rewards_address 0xYourAddress`, several things happen:

1. **Database Creation**
   - Creates `colony.db` SQLite database at the platform-specific location
   - Initializes the `machine` table with one row (id=1) containing configuration
   - Creates the `node` table (initially empty)

2. **Default Configuration Applied**
   - Resource thresholds: 70% add, 80% remove for CPU, memory, disk
   - Node cap: 50 maximum nodes
   - Delay timings: 2 minute for starts, 15 minutes for upgrades, 5 minutes for restarts
   - Port ranges: 55001-55051 for nodes, 13001-13051 for metrics
   - Network: `evm-arbitrum-one` (current Autonomi network)

3. **Platform Detection**
   - Detects macOS vs Linux
   - Selects appropriate process manager (launchd or systemd)
   - Sets platform-specific paths

4. **Directory Creation**
   - Creates node storage directory
   - Creates log directory
   - Sets appropriate permissions

**View the configuration:**
```bash
# macOS (shows column names and values in line format)
sqlite3 -line ~/Library/Application\ Support/autonomi/colony.db "SELECT * FROM machine;"

# Linux (user)
sqlite3 -line ~/.local/share/autonomi/colony.db "SELECT * FROM machine;"

# Linux (root)
sudo sqlite3 -line /var/antctl/colony.db "SELECT * FROM machine;"
```

The `-line` flag displays each column name with its corresponding value on a separate line, making the configuration easy to read.

### Setting Up Your Rewards Address

Your rewards address is stored in the `machine` table and is used for all new nodes.

**Single Address:**
```bash
wnm --init --rewards_address 0x1234567890abcdef1234567890abcdef12345678
```

**Multiple Addresses with Weighted Distribution:**
```bash
wnm --init --rewards_address "0xYourAddress:100,faucet:1,donate:10"
```

This means:
- 100/111 (~90%) of nodes use your address
- 1/111 (~1%) use the Autonomi faucet address
- 10/111 (~9%) use the donate address (if configured, also the Autonomi faucet if not)

**Named Wallets:**
- `faucet` - The Autonomi community faucet address (built-in)
- `donate` - Your custom donation address (set via `--donate_address` if desired)

**Changing Rewards Address Later:**

You can update the rewards address at any time:
```bash
wnm --rewards_address "0xNewAddress:1"
```

**Note:** This only affects *new* nodes. Existing nodes keep their current address. To change existing nodes, you would need to remove and recreate them (wnm will do this automatically over time as it cycles nodes).

### Dry-Run Mode Walkthrough

Dry-run mode lets you see what wnm would do without actually making changes.

**Run dry-run:**
```bash
wnm --dry_run
```

**Example output:**
```
=== Weave Node Manager v0.0.12 ===
Platform: Darwin (macOS)
Process Manager: launchd+user
Database: ~/Library/Application Support/autonomi/colony.db

=== System Metrics ===
CPU: 15.3%
Memory: 45.2%
Disk: 32.1%
Load Average: 2.34 (cores: 10)
Network I/O: 1.2 MB/s

=== Thresholds ===
CPU: add <70%, remove >80%
Memory: add <70%, remove >80%
Disk: add <70%, remove >80%
Load: desired 8.00, max 10.00

=== Current Nodes: 0 ===
(No nodes yet)

=== Decision ===
Action: ADD_NODE
Reason: No nodes running, resources below add thresholds
[DRY RUN] Would create node: antnode-1
[DRY RUN] Would assign port: 55001, metrics port: 13001
[DRY RUN] Would use rewards address: 0xYourAddress
```

**Key things to observe:**
- **System Metrics**: Current resource usage on your machine
- **Thresholds**: The decision boundaries wnm uses
- **Current Nodes**: List of existing nodes (empty on first run)
- **Decision**: What action wnm wants to take and why
- **[DRY RUN] markers**: These actions are NOT executed in dry-run mode

**Try it under different conditions:**
- Run while doing heavy work (compile code, run tests) to see higher CPU
- Run with many browser tabs open to see higher memory
- Watch how wnm's decision changes based on resource usage

### Monitoring Your First Node

After running `wnm` (without `--dry_run`) for the first time, your first node should be created.

**Check if the node is running:**

*macOS:*
```bash
launchctl list | grep autonomi
# Should show: com.autonomi.antnode-1

# Check status
launchctl print gui/$UID/com.autonomi.antnode-1
```

*Linux (user):*
```bash
systemctl --user status antnode-1
```

*Linux (sudo):*
```bash
systemctl status antnode-1
```

**View node logs:**

*macOS:*
```bash
tail -f ~/Library/Logs/autonomi/antnode-1.log
```

*Linux (user):*
```bash
tail -f ~/.local/share/autonomi/logs/antnode-1.log
```

*Linux (sudo):*
```bash
tail -f /var/log/antnode/antnode-1.log
# or
journalctl -u antnode-1 -f
```

**What to look for in logs:**
- Node startup messages
- Connecting to bootstrap peers
- Joining the network
- Storing and retrieving data chunks
- Reward events (when your node earns ANT)

**Check node metrics (after node has started):**

Nodes expose metrics on port 13000 + node_id. For node 1:
```bash
curl http://localhost:13001/metrics
```

You should see JSON output with:
- `connected_peers`: Number of other nodes connected to yours
- `store_cost`: Current cost to store data (indicates network participation)
- Various performance metrics

**Query the database:**

*macOS:*
```bash
sqlite3 ~/Library/Application\ Support/autonomi/colony.db "SELECT id, node_name, status, port, wallet FROM node;"
```

*Linux (user):*
```bash
sqlite3 ~/.local/share/autonomi/colony.db "SELECT id, node_name, status, port, wallet FROM node;"
```

*Linux (sudo):*
```bash
sudo sqlite3 /var/antctl/colony.db "SELECT id, node_name, status, port, wallet FROM node;"
```

**Expected output:**
```
1|antnode-1|RUNNING|55000|0xYourAddress
```

**Status meanings:**
- `RUNNING` - Node is responding to metrics port
- `STOPPED` - Node is not responding (may be starting up or crashed)
- `UPGRADING` - Node is in upgrade delay period
- `RESTARTING` - Node is in restart delay period
- `REMOVING` - Node is scheduled for removal

### Setting Up Cron for Automated Management

For wnm to work as designed, it should run every minute via cron.

#### Why Every Minute?

- **Responsive**: Quickly adapts to resource changes
- **Conservative**: Only makes one decision per run, avoiding chaos
- **Simple**: Cron is available on all Unix-like systems
- **Reliable**: If one run fails, the next one runs in 60 seconds

#### Setting Up Cron

**Edit your crontab:**
```bash
crontab -e
```

**IMPORTANT: Add PATH at the top of your crontab**

Cron runs with a minimal environment that doesn't include standard system paths. Add this line at the top of your crontab to ensure wnm can find system utilities like `sysctl`:

```cron
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
```

**Then add one of these lines based on your platform:**

*macOS (with pyenv):*
```cron
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
*/1 * * * * /Users/username/.pyenv/versions/3.14.0/bin/wnm >> ~/Library/Logs/autonomi/wnm-cron.log 2>&1
```

*macOS (system Python):*
```cron
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
*/1 * * * * /usr/local/bin/python3 -m wnm >> ~/Library/Logs/autonomi/wnm-cron.log 2>&1
```

*Linux (user with venv):*
```cron
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
*/1 * * * * . ~/.venv/bin/activate && wnm >> ~/.local/share/autonomi/logs/wnm-cron.log 2>&1
```

*Linux (root with system Python):*
```cron
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
*/1 * * * * /usr/bin/python3 -m wnm >> /var/antctl/wnm-cron.log 2>&1
```

*Linux (root with venv):*
```cron
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
*/1 * * * * . /opt/venv/bin/activate && wnm >> /var/antctl/wnm-cron.log 2>&1
```

**Explanation:**
- `PATH=...` - Sets the search path for system commands (required for wnm to find `sysctl`, `uptime`, etc.)
- `*/1 * * * *` - Run every 1 minute
- `/path/to/python3 -m wnm` - Run wnm as a Python module when using full path to Python
- `. /path/to/venv/bin/activate && wnm` - Activate venv first, then use short `wnm` command
- `>>` - Append output to log file
- `2>&1` - Redirect stderr to stdout (captures all output)

#### Verify Cron is Running

**List your cron jobs:**
```bash
crontab -l
```

**Watch the log file:**
```bash
# macOS
tail -f ~/Library/Logs/autonomi/wnm-cron.log

# Linux (user)
tail -f ~/.local/share/autonomi/logs/wnm-cron.log

# Linux (root)
sudo tail -f /var/antctl/wnm-cron.log
```

**You should see output every minute** showing wnm's execution.

#### What to Expect from Automated Management

Once cron is set up, wnm will run every minute and make decisions:

**Initial Growth Phase** (first hour):
- Adds nodes one at a time every few minutes
- Stops when resource thresholds are hit OR node cap is reached
- Each node takes ~1 minute to start and begin responding

**Steady State** (ongoing):
- Monitors all nodes and system resources
- Most runs will be "idle" (no action needed)
- Removes nodes if resources exceed removal thresholds
- Adds nodes back when resources drop below add thresholds
- Upgrades nodes when new antnode versions are released
- Restarts nodes that become unresponsive

**Example Timeline:**
```
Minute 0:  wnm runs, creates antnode-1
Minute 1:  wnm runs, antnode-1 still starting, idle
Minute 2:  wnm runs, antnode-1 RUNNING, creates antnode-2
Minute 3:  wnm runs, antnode-2 still starting, idle
Minute 4:  wnm runs, antnode-2 RUNNING, creates antnode-3
...
Minute 30: wnm runs, 15 nodes RUNNING, CPU at 72%, idle (under add threshold but above 70%)
Minute 31: wnm runs, CPU at 68%, creates antnode-16
...
Minute 60: CPU spikes to 82% (you started compiling code)
Minute 61: wnm runs, removes youngest node (antnode-16)
Minute 62: CPU drops to 78%, idle (above add threshold)
...
```

#### Troubleshooting Cron

**Cron not running?**
```bash
# Check cron service is running
# macOS: cron runs automatically
# Linux:
sudo systemctl status cron
```

**Check for errors:**
```bash
# macOS system log
log show --predicate 'process == "cron"' --last 10m

# Linux
grep CRON /var/log/syslog
```

**Path issues?**
If wnm can't be found, use the full path:
```bash
which wnm
# Use the full path in your crontab
```

**Environment differences:**
Cron runs with a minimal environment. If wnm works in your shell but not in cron, you may need to set environment variables:

```cron
PATH=/usr/local/bin:/usr/bin:/bin
*/1 * * * * /usr/local/bin/wnm >> ~/Library/Logs/autonomi/wnm-cron.log 2>&1
```

---

**End of Part 1: Getting Started**

You now have wnm installed, configured, and running your first nodes. Continue to Part 2: Core Concepts to understand how wnm makes decisions and manages node lifecycle.