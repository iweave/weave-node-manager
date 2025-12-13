# Weave Node Manager

## Overview
Weave Node Manager (wnm) is a Python application designed to manage Autonomi nodes on Linux and macOS systems.

**Platforms**:
- **Linux**: systemd or setsid for process management, UFW for firewall
- **macOS**: launchd for process management (native support)
- **Python 3.12.3+** required

## Features
- Automatic node lifecycle management (create, start, stop, upgrade, remove)
- Resource-based decision engine (CPU, memory, disk, I/O, load average thresholds)
- Platform-specific process management (systemd on Linux, launchd on macOS)
- Per-node binary copies for independent upgrades
- SQLite database for configuration and state tracking
- Support for configuration via environment variables, config files, or command-line parameters

## Warning - Alpha Software

This code is Alpha. On Linux, it can migrate from an existing [anm](https://github.com/safenetforum-community/NTracking/tree/main/anm) installation. On macOS, it provides native development and testing support using launchd.

## Installation

### macOS (Development & Testing)

macOS support uses launchd for process management and is ideal for development and testing.

#### 1. Install antup (Autonomi binary manager)
```bash
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash
```

#### 2. Download antnode binary
```bash
~/.local/bin/antup node
```

#### 3. Install WNM from PyPI
```bash
pip3 install wnm
```

#### 4. Or install from source
```bash
git clone https://github.com/iweave/weave-node-manager.git
cd weave-node-manager
pip3 install -e .
```

#### 5. Initialize and configure
```bash
# Initialize with your rewards address
wnm --init --rewards_address 0xYourEthereumAddress

# Run in dry-run mode to test
wnm --dry_run

# Or run normally to start managing nodes
wnm
```

#### 6. Optional: Add to cron for automatic management
```bash
# Add to crontab (runs every minute)
crontab -e

# Add this line:
*/1 * * * * /usr/local/bin/wnm >> ~/Library/Logs/autonomi/wnm-cron.log 2>&1
```

**macOS Notes:**
- Uses `~/Library/Application Support/autonomi/node/` for data
- Uses `~/Library/Logs/autonomi/` for logs
- Nodes managed via launchd (`~/Library/LaunchAgents/`)
- No root/sudo access required

### Linux (User-Level, Recommended)

Non-root installation using setsid for process management.

#### 1. Install antup (Autonomi binary manager)
```bash
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash
```

#### 2. Download antnode binary
```bash
~/.local/bin/antup node
```

#### 3. Install WNM from PyPI
```bash
pip3 install wnm
```

#### 4. Or install from source
```bash
git clone https://github.com/iweave/weave-node-manager.git
cd weave-node-manager
pip3 install -e .
```

#### 5. Initialize and configure
```bash
# Initialize with your rewards address
wnm --init --rewards_address 0xYourEthereumAddress

# Run in dry-run mode to test
wnm --dry_run

# Or run normally
wnm
```

#### 6. Optional: Add to cron
```bash
crontab -e

# Add this line:
*/1 * * * * ~/.local/bin/wnm >> ~/.local/share/autonomi/logs/wnm-cron.log 2>&1
```

**Linux User-Level Notes:**
- Uses `~/.local/share/autonomi/node/` for data (XDG spec)
- Uses `~/.local/share/autonomi/logs/` for logs
- Nodes run as background processes (setsid)
- No root/sudo required

### Linux (Root-Level, Production)

Root installation using systemd for process management.

#### 1. Install system dependencies
```bash
sudo apt install -y python3.12-venv python3-pip
```

#### 2. Install antup and antnode
```bash
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash
~/.local/bin/antup node
sudo cp ~/.local/bin/antnode /usr/local/bin/
```

#### 3. Install WNM
```bash
sudo pip3 install wnm
```

#### 4. Initialize as root
```bash
# Migrate from existing anm installation
sudo wnm --init --migrate_anm

# Or initialize fresh
sudo wnm --init --rewards_address 0xYourEthereumAddress
```

#### 5. Add to cron
```bash
sudo crontab -e

# Add this line:
*/1 * * * * /usr/local/bin/wnm >> /var/log/antnode/wnm-cron.log 2>&1
```

**Linux Root-Level Notes:**
- Uses `/var/antctl/` for data (legacy anm compatibility)
- Uses `/var/log/antnode/` for logs
- Nodes managed via systemd (`/etc/systemd/system/`)
- Requires root/sudo access
- Supports migration from anm

## Configuration

Configuration follows a multi-layer priority system (highest to lowest):

1. **Command-line arguments**: `wnm --cpu_less_than 70 --node_cap 50`
2. **Environment variables**: Set in `.env` file or shell environment
3. **Config files**: `~/.local/share/wnm/config`, `~/wnm/config`, or `-c/--config`
4. **Database-stored config**: Persisted in `colony.db` after initialization
5. **Default values**: Built-in defaults

### Key Configuration Parameters

Resource thresholds control when nodes are added or removed:

- `--cpu_less_than` / `--cpu_remove`: CPU percentage thresholds (default: 70% / 80%)
- `--mem_less_than` / `--mem_remove`: Memory percentage thresholds (default: 70% / 80%)
- `--hd_less_than` / `--hd_remove`: Disk usage percentage thresholds (default: 70% / 80%)
- `--desired_load_average` / `--max_load_average_allowed`: Load average thresholds
- `--node_cap`: Maximum number of nodes (default: 50)
- `--rewards_address`: Wallet address(es) for node rewards (required) - see Wallet Configuration below
- `--node_storage`: Root directory for node data (auto-detected per platform)

### Wallet Configuration

The `--rewards_address` parameter supports multiple formats for flexible reward distribution:

#### Single Wallet
Use a single Ethereum address or named wallet:
```bash
# Ethereum address
wnm --init --rewards_address 0xYourEthereumAddress

# Named wallet: "donate" (uses your custom donate_address or the community foucet if not deefined)
wnm --init --rewards_address donate

# Named wallet: "faucet" (always uses the autonomi community faucet address)
wnm --init --rewards_address faucet
```

#### Weighted Distribution
Distribute rewards across multiple wallets using weighted random selection:
```bash
# Format: wallet1:weight1,wallet2:weight2,...
wnm --init --rewards_address "0xYourAddress:100,faucet:1,donate:10"
```

In this example:
- Your address receives ~90% of nodes (100 out of 111 weight)
- Faucet receives ~1% of nodes (1 out of 111 weight)
- Donate address receives ~9% of nodes (10 out of 111 weight)

**Key Features:**
- **Random per node**: Each new node randomly selects a wallet based on weights
- **Named wallets**: Use `faucet` (project faucet) or `donate` (your custom donation address)
- **Case-insensitive**: `faucet`, `FAUCET`, and `Faucet` all work
- **Mix addresses and names**: Combine Ethereum addresses with named wallets
- **Changeable**: Update `--rewards_address` anytime to change distribution for new nodes

**Examples:**
```bash
# 50/50 split between your address and faucet
wnm --rewards_address "0xYourAddress:1,faucet:1"

# Your address only
wnm --rewards_address 0xYourAddress

# Mostly yours, small donation to faucet
wnm --rewards_address "0xYourAddress:99,faucet:1"

# Multiple addresses with custom weights
wnm --rewards_address "0xAddress1:100,0xAddress2:50,faucet:10"
```

### anm Migration (Linux Only)

Upon finding an existing [anm](https://github.com/safenetforum-community/NTracking/tree/main/anm) installation, wnm will:
1. Disable anm by removing `/etc/cron.d/anm`
2. Import configuration from `/var/antctl/config`
3. Discover and import existing nodes from systemd
4. Take over management of the cluster

Use `wnm --init --migrate_anm` to trigger migration.

## Usage

### Run Once
```bash
# macOS or Linux
wnm

# With dry-run (no actual changes)
wnm --dry_run

# Initialize first time
wnm --init --rewards_address 0xYourEthereumAddress
```

### Run via Cron (Recommended)

WNM is designed to run every minute via cron. By default it performs one operation per cycle, but can be configured for concurrent operations on powerful machines:

**macOS:**
```bash
crontab -e
# Add: */1 * * * * /usr/local/bin/wnm >> ~/Library/Logs/autonomi/wnm-cron.log 2>&1
```

**Linux (user):**
```bash
crontab -e
# Add: */1 * * * * ~/.local/bin/wnm >> ~/.local/share/autonomi/logs/wnm-cron.log 2>&1
```

**Linux (root):**
```bash
sudo crontab -e
# Add: */1 * * * * /usr/local/bin/wnm >> /var/log/antnode/wnm-cron.log 2>&1
```

### Development Mode

For development with live code reloading:

**macOS (native):**
```bash
python3 -m wnm --dry_run
```

**Linux (Docker):**
```bash
./scripts/dev.sh
# Inside container:
python3 -m wnm --dry_run
```

See `DOCKER-DEV.md` for comprehensive Docker development workflow.

## Platform Support

See `PLATFORM-SUPPORT.md` for detailed information about:
- Platform-specific process managers (systemd, launchd, setsid)
- Firewall management (UFW, null)
- Path conventions per platform
- Binary management and upgrades
- Testing strategies

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.
