# macOS Support Implementation Plan

**Updated:** 2025-10-26
**Goal:** Enable WNM to run natively on macOS for development and testing
**Scope:** User-level node management (no root/sudo required)
**Timeline:** Weeks 7-10 (after REFACTORING-PLAN.md Phase 5 complete)

---

## Background

WNM is currently Linux-only, requiring systemd, ufw firewall, and sudo privileges. To enable development and testing on macOS, we need to replace Linux-specific dependencies with cross-platform alternatives.

**Key Insight:** The codebase already has abstraction layers (ProcessManager and FirewallManager base classes with factory patterns). We need to:
1. Add macOS-specific implementations
2. Make file paths platform-agnostic
3. Fix platform-specific system calls

---

## Platform-Specific Path Strategy

### User-Level Paths (Default for Both Platforms)

| Purpose | Linux User Path | macOS User Path |
|---------|-----------------|-----------------|
| Config/State | `~/.local/share/autonomi/node/` | `~/Library/Application Support/autonomi/node/` |
| Logs | `~/.local/share/autonomi/logs/` | `~/Library/Logs/autonomi/` |
| Database | `~/.local/share/autonomi/node/colony.db` | `~/Library/Application Support/autonomi/node/colony.db` |
| Lock File | `~/.local/share/autonomi/node/wnm_active` | `~/Library/Application Support/autonomi/node/wnm_active` |
| Binary Source | `~/.local/bin/antnode` | `~/.local/bin/antnode` |

### Root-Level Paths (Linux Only, Legacy Support)

| Purpose | Linux Root Path | Used When |
|---------|-----------------|-----------|
| Config/State | `/var/antctl/` | Running as root or migrating from `anm` |
| Logs | `/var/log/antnode/` | Running as root |
| systemd Services | `/etc/systemd/system/` | systemd-managed nodes |

**Design Principle:** Default to user-level paths on both platforms. Linux users can opt into root paths if needed (legacy migration, system-wide deployment).

---

## Architecture Changes

### Current Linux-Specific Dependencies

Based on comprehensive codebase analysis, the following components need macOS alternatives:

1. **Process Management:** systemd → launchd
2. **Firewall:** ufw → null firewall (for testing)
3. **File Paths:** `/var/antctl/`, `/etc/systemd/`, `/var/log/antnode/` → platform-specific user paths
4. **System Metrics:** `uptime --since`, `os.sched_getaffinity()` → platform-specific commands
5. **Legacy Code:** `utils.py` functions that bypass abstraction layers

---

## Phase 1: Create Launchd-Based Process Manager

**Priority:** CRITICAL | **Effort:** High | **Duration:** 1 week

### Goal
Implement `LaunchctlManager` for macOS to replace systemd functionality.

### Implementation

**File to Create:** `src/wnm/process_managers/launchd_manager.py`

**Launchd vs Systemd Comparison:**

| Feature | systemd | launchd |
|---------|---------|---------|
| Unit Files | `/etc/systemd/system/*.service` | `~/Library/LaunchAgents/*.plist` |
| Start Command | `systemctl start <service>` | `launchctl load <plist>` |
| Stop Command | `systemctl stop <service>` | `launchctl unload <plist>` |
| Restart Command | `systemctl restart <service>` | `launchctl kickstart -k <service>` |
| Status Query | `systemctl show <service>` | `launchctl list <service>` |
| Auto-start | `[Install] WantedBy=multi-user.target` | `<key>RunAtLoad</key><true/>` |
| Keep Alive | `Restart=always` | `<key>KeepAlive</key><true/>` |

**Plist Template Example:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.autonomi.antnode-1</string>

    <key>ProgramArguments</key>
    <array>
        <string>~/Library/Application Support/autonomi/node/antnode-1/antnode</string>
        <string>--port</string>
        <string>55001</string>
        <string>--metrics-port</string>
        <string>13001</string>
        <string>--root-dir</string>
        <string>~/Library/Application Support/autonomi/node/antnode-1</string>
        <string>--relay</string>
        <string>--rewards-address</string>
        <string>0x...</string>
        <string>evm-arbitrum-one</string>
    </array>

    <key>WorkingDirectory</key>
    <string>~/Library/Application Support/autonomi/node/antnode-1</string>

    <key>StandardOutPath</key>
    <string>~/Library/Logs/autonomi/antnode-1.log</string>

    <key>StandardErrorPath</key>
    <string>~/Library/Logs/autonomi/antnode-1.log</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

### Key Functions to Implement

Inherit from `ProcessManager` base class (base.py:15-67) and implement:

```python
class LaunchctlManager(ProcessManager):
    def __init__(self, firewall=None):
        super().__init__(firewall)
        self.plist_dir = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(self.plist_dir, exist_ok=True)

    def create_node(self, node: Node) -> bool:
        """
        1. Create node directories (root_dir, logs)
        2. Copy antnode binary from ~/.local/bin/antnode to {root_dir}/antnode
           (Each node gets its own copy for independent upgrades)
        3. Generate .plist file from template
        4. Write plist to ~/Library/LaunchAgents/
        5. Load plist: launchctl load <plist>
        6. Enable firewall port (if firewall manager available)
        """
        pass

    def start_node(self, node: Node) -> bool:
        """
        launchctl load ~/Library/LaunchAgents/com.autonomi.antnode-{id}.plist
        """
        pass

    def stop_node(self, node: Node) -> bool:
        """
        launchctl unload ~/Library/LaunchAgents/com.autonomi.antnode-{id}.plist
        """
        pass

    def restart_node(self, node: Node) -> bool:
        """
        launchctl kickstart -k gui/$(id -u)/com.autonomi.antnode-{id}
        """
        pass

    def get_status(self, node: Node) -> NodeProcess:
        """
        Parse output of: launchctl list com.autonomi.antnode-{id}
        Returns: NodeProcess(node_id, pid, status)
        """
        pass

    def remove_node(self, node: Node) -> bool:
        """
        1. Unload plist: launchctl unload <plist>
        2. Delete plist file
        3. Delete node directories
        4. Disable firewall port
        """
        pass
```

### Binary Management

**Source Binary Location:** `~/.local/bin/antnode`

**Per-Node Binary Location:** `{node.root_dir}/antnode`

**Acquiring/Updating Binary:**
```bash
# Install antup tool
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash

# Download latest antnode binary to ~/.local/bin/antnode
~/.local/bin/antup node
```

**Copy Strategy:**
- When creating a new node, copy `~/.local/bin/antnode` to `{node.root_dir}/antnode`
- Each node has its own binary copy
- Upgrades replace individual node binaries (not the source binary)
- This allows rolling upgrades without affecting running nodes

### Subprocess Commands Reference

| Operation | Command |
|-----------|---------|
| Load service | `launchctl load ~/Library/LaunchAgents/com.autonomi.antnode-1.plist` |
| Unload service | `launchctl unload ~/Library/LaunchAgents/com.autonomi.antnode-1.plist` |
| Kickstart (restart) | `launchctl kickstart -k gui/$(id -u)/com.autonomi.antnode-1` |
| List services | `launchctl list \| grep antnode` |
| Get service info | `launchctl list com.autonomi.antnode-1` |

**Note:** User agents run under `gui/$(id -u)/` domain, not system domain.

### Files to Modify

1. **`src/wnm/process_managers/factory.py:73-75`**
   - Change Darwin detection from "setsid" to "launchctl"
   ```python
   elif system == "Darwin":
       return "launchctl"  # Changed from "setsid"
   ```

### Testing Strategy

1. **Unit Tests:** Mock `subprocess.run()` calls to launchctl
2. **Integration Tests:** Test on macOS with actual plist files
3. **Markers:** Use `@pytest.mark.skipif(platform.system() != "Darwin")`

**Test File:** `tests/test_process_managers.py` (add LaunchctlManager tests)

---

## Phase 2: Use Null Firewall for macOS

**Priority:** CRITICAL | **Effort:** Low | **Duration:** 1 day

### Goal
Configure macOS to use `NullFirewallManager` for initial testing.

### Implementation

**File to Modify:** `src/wnm/firewall/factory.py`

**Current Auto-Detection Logic (lines 39-56):**

```python
def get_default_manager_type() -> str:
    """Auto-detect available firewall manager"""
    system = platform.system()

    if system == "Linux":
        # Check for UFW
        if shutil.which("ufw"):
            return "ufw"
        return "null"  # Fallback

    elif system == "Darwin":
        return "null"  # macOS: use null firewall for now

    else:
        return "null"  # Windows, etc.
```

**No code changes needed!** The factory already returns "null" for Darwin. Just verify it works.

### Alternative: pfctl Manager (Future Phase)

For production macOS deployments, consider implementing `PfctlManager`:

- Use `pfctl` to manage packet filter rules
- Requires editing `/etc/pf.conf` or using anchors
- Commands: `sudo pfctl -f /etc/pf.conf`, `sudo pfctl -e`

**Deferred to later phase** - null firewall sufficient for development/testing.

---

## Phase 3: Make File Paths Platform-Agnostic

**Priority:** HIGH | **Effort:** Medium | **Duration:** 3 days

### Goal
Replace hardcoded Linux paths with platform-specific user-level paths.

### Path Mapping Strategy

Add platform detection and path constants to `config.py`:

```python
import platform
import os

PLATFORM = platform.system()  # 'Linux', 'Darwin', 'Windows'

# User-level paths (default for all platforms)
if PLATFORM == "Darwin":
    BASE_DIR = os.path.expanduser("~/Library/Application Support/autonomi/node")
    LOG_DIR = os.path.expanduser("~/Library/Logs/autonomi")
elif PLATFORM == "Linux":
    # Check if running as root
    if os.geteuid() == 0:
        # Root user: use legacy /var/antctl paths
        BASE_DIR = "/var/antctl"
        LOG_DIR = "/var/log/antnode"
    else:
        # Non-root user: use XDG base directory spec
        BASE_DIR = os.path.expanduser("~/.local/share/autonomi/node")
        LOG_DIR = os.path.expanduser("~/.local/share/autonomi/logs")
else:
    # Windows or other
    BASE_DIR = os.path.expanduser("~/autonomi/node")
    LOG_DIR = os.path.expanduser("~/autonomi/logs")

# Derived paths
LOCK_FILE = os.path.join(BASE_DIR, "wnm_active")
DB_PATH = os.path.join(BASE_DIR, "colony.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config")

# Create directories if they don't exist
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
```

### Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `config.py` | Top of file | Add platform detection and path constants |
| `config.py` | 263, 347, 349, 361 | Replace `/var/antctl/` with `BASE_DIR` |
| `__main__.py` | 89, 95, 172 | Replace `/var/antctl/wnm_active` with `LOCK_FILE` |
| `utils.py` | 286, 571, 657 | Replace `/var/log/antnode/` with `LOG_DIR` |
| `systemd_manager.py` | Various | Use `LOG_DIR` constant for log paths |
| `launchd_manager.py` | New file | Use `BASE_DIR` and `LOG_DIR` constants |

### Migration Considerations

**Linux users upgrading from anm:**
- Migration script already handles `/var/antctl/` paths
- Keep root detection to preserve existing deployments
- Non-root Linux users get new user-level paths

**macOS users (new):**
- Always use user-level paths (no root support needed)
- Follows macOS conventions (Library/Application Support, Library/Logs)

---

## Phase 4: Fix Platform-Specific System Metrics

**Priority:** HIGH | **Effort:** Low | **Duration:** 1 day

### Issues to Fix

#### 4.1 `uptime --since` Command (utils.py:242-246)

**Current Code:**
```python
result = subprocess.run(
    ["uptime", "--since"], capture_output=True, text=True, check=True
)
system_start = int(datetime.fromisoformat(result.stdout.strip()).timestamp())
```

**Problem:** `uptime --since` is Linux-specific. macOS uses different format.

**Solution:**

```python
import platform

if platform.system() == "Darwin":
    # macOS: use sysctl kern.boottime
    result = subprocess.run(
        ["sysctl", "-n", "kern.boottime"],
        capture_output=True, text=True, check=True
    )
    # Parse: { sec = 1234567890, usec = 0 }
    import re
    match = re.search(r"sec = (\d+)", result.stdout)
    if match:
        system_start = int(match.group(1))
    else:
        raise ValueError("Could not parse kern.boottime")
else:
    # Linux: use uptime --since
    result = subprocess.run(
        ["uptime", "--since"], capture_output=True, text=True, check=True
    )
    system_start = int(datetime.fromisoformat(result.stdout.strip()).timestamp())
```

**File to Modify:** `src/wnm/utils.py:242-246`

#### 4.2 `os.sched_getaffinity(0)` (config.py:260, 385)

**Current Code:**
```python
cpu_count = len(os.sched_getaffinity(0))
```

**Problem:** `sched_getaffinity()` is Linux-only.

**Solution:**

```python
import platform

if platform.system() == "Linux":
    # Linux: use sched_getaffinity for accurate count (respects cgroups/taskset)
    cpu_count = len(os.sched_getaffinity(0))
else:
    # macOS/other: use os.cpu_count()
    cpu_count = os.cpu_count() or 1
```

**File to Modify:** `src/wnm/config.py:260, 385`

### Testing

Add platform-specific tests:

```python
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_macos_system_metrics():
    metrics = get_machine_metrics(...)
    assert metrics.system_start > 0
    assert metrics.cpu_count > 0
```

---

## Phase 5: Refactor Legacy utils.py

**Priority:** HIGH | **Effort:** High | **Duration:** 1 week

### Goal
Remove systemd/ufw direct calls from `utils.py` and use abstraction layers.

### Functions to Refactor

| Function | Current Approach | Refactor To |
|----------|------------------|-------------|
| `read_systemd_service()` | Reads `/etc/systemd/system/` directly | Use `ProcessManager.get_status()` or delete if unused |
| `survey_systemd_nodes()` | Lists `/etc/systemd/system/` | Add `ProcessManager.list_nodes()` method |
| `survey_machine()` | Calls `survey_systemd_nodes()` | Use factory-based manager |
| `start_systemd_node()` | Calls `sudo systemctl start` | Use `ProcessManager.start_node()` |
| `stop_systemd_node()` | Calls `sudo systemctl stop` | Use `ProcessManager.stop_node()` |
| `upgrade_node()` | Calls `sudo systemctl restart` | Use `ProcessManager.restart_node()` |
| `remove_node()` | Calls systemd directly | Use `ProcessManager.remove_node()` |
| `create_node()` | Creates systemd service directly | Use `ProcessManager.create_node()` |
| `enable_firewall()` | Calls `sudo ufw allow` directly | Use `FirewallManager.enable_port()` |
| `disable_firewall()` | Calls `sudo ufw delete` directly | Use `FirewallManager.disable_port()` |

### Strategy

1. **Add Process Manager to Function Signatures**
   ```python
   # Before
   def create_node(S, node, metrics):
       ...

   # After
   def create_node(S, node, metrics, manager: ProcessManager = None):
       if manager is None:
           from wnm.process_managers.factory import get_process_manager
           manager = get_process_manager(node.manager_type)

       return manager.create_node(node)
   ```

2. **Update Callers in `__main__.py` and `executor.py`**
   ```python
   # In executor.py
   from wnm.process_managers.factory import get_process_manager

   def execute_add_node(self, action):
       node = self._get_node(action.node_id)
       manager = get_process_manager(node.manager_type)
       success = manager.create_node(node)
   ```

3. **Delete Deprecated Functions** (if no callers remain)
   - `read_systemd_service()`
   - `survey_systemd_nodes()`
   - Direct systemd/ufw wrapper functions

### Files to Modify

- `src/wnm/utils.py` - Refactor all systemd/ufw direct calls
- `src/wnm/__main__.py` - Update function calls
- `src/wnm/executor.py` - Update function calls
- `src/wnm/process_managers/base.py` - Add `list_nodes()` method if needed

---

## Phase 6: Add macOS Testing Infrastructure

**Priority:** MEDIUM | **Effort:** Medium | **Duration:** 3 days

### Goal
Enable testing on both Linux (Docker) and macOS (native).

**Note:** Docker can also be used on macOS. Docker training will be added after these macOS support upgrades are complete.

### 6.1 Platform-Specific Test Fixtures

**File:** `tests/conftest.py`

```python
import platform
import pytest

@pytest.fixture
def process_manager_type():
    """Return appropriate process manager for current platform"""
    if platform.system() == "Darwin":
        return "launchctl"
    elif platform.system() == "Linux":
        return "systemd"
    else:
        return "setsid"

@pytest.fixture
def firewall_manager_type():
    """Return appropriate firewall manager for current platform"""
    if platform.system() == "Darwin":
        return "null"
    elif platform.system() == "Linux":
        return "ufw"
    else:
        return "null"
```

### 6.2 Platform Markers

**File:** `pytest.ini` or `pyproject.toml`

```ini
[tool.pytest.ini_options]
markers = [
    "linux_only: tests that require Linux (systemd, ufw, etc.)",
    "macos_only: tests that require macOS (launchctl, etc.)",
    "requires_docker: tests that require Docker",
    "integration: integration tests (slow)",
]
```

**Usage in Tests:**

```python
@pytest.mark.linux_only
def test_systemd_manager():
    manager = SystemdManager()
    ...

@pytest.mark.macos_only
def test_launchctl_manager():
    manager = LaunchctlManager()
    ...
```

### 6.3 Test Runner Scripts

**File:** `scripts/test-macos.sh`

```bash
#!/bin/bash
# Run tests on macOS (skip Linux-only tests)

set -e

echo "Running macOS tests..."
pytest tests/ -v -m "not linux_only" --cov=src/wnm --cov-report=term-missing

echo ""
echo "macOS test suite complete!"
```

**File:** `scripts/test-linux.sh` (update existing `scripts/test.sh`)

```bash
#!/bin/bash
# Run tests on Linux (skip macOS-only tests)

set -e

echo "Running Linux tests in Docker..."
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

echo ""
echo "Linux test suite complete!"
```

### 6.4 CI/CD: GitHub Actions

**File:** `.github/workflows/test-macos.yml`

```yaml
name: macOS Tests

on: [push, pull_request]

jobs:
  test-macos:
    runs-on: macos-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python3 -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run macOS tests
        run: |
          chmod +x scripts/test-macos.sh
          ./scripts/test-macos.sh
```

**File:** `.github/workflows/test-linux.yml` (update existing)

```yaml
name: Linux Tests

on: [push, pull_request]

jobs:
  test-linux:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Run Linux tests
        run: |
          chmod +x scripts/test.sh
          ./scripts/test.sh
```

### 6.5 Test Coverage Goals

**Target Coverage by Phase:**

- Phase 6 Complete: 50%+ overall coverage
- LaunchctlManager: 70%+ coverage
- Platform-agnostic utils: 60%+ coverage

---

## Phase 7: Update Documentation

**Priority:** LOW | **Effort:** Low | **Duration:** 1 day

### Files to Modify

#### 7.1 README.md

**Remove "Linux-only" statements:**

```diff
- **Important**: This is Linux-only software targeting Python 3.12.3+.
+ **Platforms**: Linux (systemd, ufw) and macOS (launchd, native)
+ Python 3.12.3+ required
```

**Add macOS installation section:**

```markdown
## Installation

### macOS

```bash
# Install antup (manages antnode binary)
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash

# Download antnode binary
~/.local/bin/antup node

# Install WNM from PyPI
pip3 install weave-node-manager

# Or install from source
git clone https://github.com/yourusername/weave-node-manager.git
cd weave-node-manager
pip3 install -e .

# Run (uses launchd for process management)
wnm --init
```

### Linux (systemd)

```bash
# Install from PyPI
pip3 install weave-node-manager

# Or install from source
git clone https://github.com/yourusername/weave-node-manager.git
cd weave-node-manager
pip3 install -e .

# Run as user (uses setsid)
wnm --init

# Run as root (uses systemd)
sudo wnm --init
```
```

#### 7.2 CLAUDE.md

**Update development commands:**

```diff
## Development Environment

- **IMPORTANT: Use Docker for Development and Testing**
+ **Linux Development: Use Docker**

  Since WNM is Linux-only and requires systemd, always use the Docker
  development environment for running and testing the application:
+ Since WNM requires systemd on Linux, use the Docker development
+ environment for Linux testing:

+ **macOS Development: Run Natively**
+
+ On macOS, you can run and test directly:
+
+ ```bash
+ # Run tests natively
+ ./scripts/test-macos.sh
+
+ # Run application in dry-run mode
+ python3 -m wnm --dry_run
+ ```
```

#### 7.3 DOCKER-DEV.md

**Add note about Docker on macOS:**

```markdown
# Docker Development Environment

**Note:** This Docker environment is primarily for Linux-specific testing (systemd, ufw).
macOS users can run tests natively using `./scripts/test-macos.sh`.

Docker can also be used on macOS for containerized node testing. Docker training
will be added after the macOS support upgrades are complete.

This document describes the Docker-based development and testing environment
for WNM on Linux.
```

#### 7.4 New File: PLATFORM-SUPPORT.md

Create comprehensive platform support documentation:

```markdown
# Platform Support Guide

## Supported Platforms

### macOS (User-Level)
- **Process Manager:** launchd (~/Library/LaunchAgents)
- **Firewall:** Null (no firewall management)
- **Base Directory:** ~/Library/Application Support/autonomi/node
- **Log Directory:** ~/Library/Logs/autonomi
- **Binary Source:** ~/.local/bin/antnode (managed by antup)
- **Root Access:** Not required or supported
- **Best For:** Development, testing, single-user deployments

### Linux (User-Level)
- **Process Manager:** setsid (background processes)
- **Firewall:** Null or UFW (if available and enabled)
- **Base Directory:** ~/.local/share/autonomi/node
- **Log Directory:** ~/.local/share/autonomi/logs
- **Root Access:** Not required
- **Best For:** Multi-user systems, non-root deployments

### Linux (Root-Level)
- **Process Manager:** systemd (system services)
- **Firewall:** UFW (Ubuntu/Debian) or Null
- **Base Directory:** /var/antctl
- **Log Directory:** /var/log/antnode
- **Root Access:** Required (sudo)
- **Best For:** Production deployments, anm migration

## Platform Detection

WNM automatically detects the platform and selects appropriate managers:

1. **Process Manager Selection:**
   - macOS → launchctl
   - Linux + systemd → systemd
   - Linux without systemd → setsid

2. **Firewall Manager Selection:**
   - Linux + UFW → ufw
   - macOS → null
   - Other → null

3. **Path Selection:**
   - macOS → ~/Library/Application Support/autonomi/node
   - Linux (root) → /var/antctl
   - Linux (user) → ~/.local/share/autonomi/node

## Binary Management

### Acquiring antnode Binary

```bash
# Install antup tool
curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash

# Download latest antnode binary to ~/.local/bin/antnode
~/.local/bin/antup node
```

### Per-Node Binary Copies

Each node has its own copy of the antnode binary in `{node.root_dir}/antnode`.

**Why?** This allows:
- Rolling upgrades (upgrade one node at a time)
- Version pinning per node
- Rollback to previous binary if upgrade fails
- No disruption to running nodes during upgrades

## Testing by Platform

### macOS
```bash
./scripts/test-macos.sh  # Runs tests with launchctl, null firewall
```

### Linux
```bash
./scripts/test.sh  # Runs tests in Docker with systemd, ufw
```
```

---

## Implementation Order (Recommended)

Based on dependencies and risk:

1. ✅ **Phase 4 (System Metrics)** - COMPLETED 2025-10-26
   - Fixed `uptime --since` command (uses sysctl on macOS)
   - Fixed `os.sched_getaffinity()` call (uses os.cpu_count() on macOS)
   - Fixed CPU metrics parsing (handles missing iowait on macOS)
   - Added platform-specific tests (4/4 passing on macOS natively)
   - **Duration:** 1 day (as estimated)

2. ✅ **Phase 3 (File Paths)** - COMPLETED 2025-10-27
   - Added centralized platform detection (PLATFORM, IS_ROOT constants)
   - Created platform-specific path constants (BASE_DIR, NODE_STORAGE, LOG_DIR, BOOTSTRAP_CACHE_DIR, LOCK_FILE)
   - Updated all hardcoded paths in config.py, __main__.py, utils.py, and all process managers
   - Fixed circular import (removed unused wnm.utils import from config.py)
   - Eliminated duplicate platform detection calls (now single source of truth)
   - macOS: Uses ~/Library/Application Support/autonomi paths
   - Linux (root): Preserves /var/antctl paths for backwards compatibility
   - Linux (user): Uses ~/.local/share/autonomi paths (XDG spec)
   - Tests: 88 passed on macOS, 88 passed on Linux (no regressions)
   - **Duration:** 1 day (faster than 3-day estimate)

3. ✅ **Phase 1 (Launchd Manager)** - COMPLETED 2025-10-27
   - Implemented LaunchctlManager (416 lines)
   - Updated factory to use "launchctl" for Darwin
   - Added 13 comprehensive tests (all passing)
   - Binary management with per-node copies
   - **Duration:** 1 day (faster than 1-week estimate)

4. ✅ **Phase 2 (Null Firewall)** - COMPLETED (already working)
   - Confirmed factory returns "null" for Darwin
   - Tested with NullFirewallManager
   - No firewall errors on macOS
   - **Duration:** Verification only

5. **Phase 5 (Refactor utils.py)** - Cleanup (NEXT)
   - Remove systemd/ufw direct calls
   - Use manager abstractions
   - **Duration:** 1 week

6. **Phase 6 (Testing Infrastructure)** - Quality assurance
   - Add platform-specific fixtures
   - Create test runner scripts
   - Add GitHub Actions
   - **Duration:** 3 days

7. **Phase 7 (Documentation)** - User communication
   - Update README, CLAUDE.md
   - Create PLATFORM-SUPPORT.md
   - **Duration:** 1 day

**Total Estimated Duration:** 3-4 weeks

---

## Success Metrics

### Phase Completion Criteria

**Phase 1: Launchd Manager** ✅ COMPLETED
- [x] LaunchctlManager implements all ProcessManager methods
- [x] Can create/start/stop/restart nodes on macOS
- [x] Plist files generated correctly with --relay flag and evm-arbitrum-one parameter
- [x] Each node has its own antnode binary copy in {root_dir}/antnode
- [x] Unit tests with mocked launchctl commands (70%+ coverage)

**Phase 2: Null Firewall** ✅ COMPLETED
- [x] Factory returns "null" for macOS
- [x] NullFirewall used successfully in integration tests
- [x] No firewall errors on macOS

**Phase 3: Platform-Agnostic Paths** ✅ COMPLETED
- [x] User-level paths work on macOS and Linux
- [x] Root detection works on Linux (IS_ROOT constant)
- [x] Lock file, DB, logs created in correct locations
- [x] All path constants replaced (12 occurrences across 6 files)
- [x] macOS uses ~/Library/Application Support/autonomi
- [x] NODE_STORAGE defaults to platform-appropriate paths (overridable during --init)
- [x] Centralized platform detection (PLATFORM constant, single source of truth)
- [x] No circular imports or duplicate platform.system() calls
- [x] Tests pass on both macOS (88) and Linux (88) with no regressions

**Phase 4: System Metrics** ✅ COMPLETED
- [x] `uptime --since` replacement works on macOS (sysctl kern.boottime)
- [x] CPU count detection works on macOS (os.cpu_count())
- [x] CPU metrics parsing works on macOS (no iowait field)
- [x] System metrics collection succeeds on macOS
- [x] Platform-specific tests pass (4/4 native macOS tests, 88/88 Linux tests)
- [x] No regressions in Linux functionality

**Phase 5: Refactor utils.py**
- [ ] All systemd direct calls removed
- [ ] All ufw direct calls removed
- [ ] Manager abstractions used throughout
- [ ] No regressions in Linux functionality

**Phase 6: Testing Infrastructure**
- [ ] macOS tests run natively via `./scripts/test-macos.sh`
- [ ] Linux tests run in Docker via `./scripts/test.sh`
- [ ] GitHub Actions test both platforms
- [ ] 50%+ overall code coverage

**Phase 7: Documentation**
- [ ] README updated with macOS instructions
- [ ] CLAUDE.md updated for native macOS dev
- [ ] PLATFORM-SUPPORT.md created
- [ ] All "Linux-only" statements removed/updated
- [ ] antup installation documented

### Overall Project Success

- [ ] WNM runs natively on macOS (no Docker required)
- [ ] Tests pass on both Linux and macOS
- [ ] Code coverage 50%+ on both platforms
- [ ] Documentation complete for both platforms
- [ ] No regressions in Linux functionality
- [ ] Developer workflow improved (test on macOS during development)

---

## Risks & Mitigation

### Risk 1: Launchd Complexity
**Risk:** launchd has different semantics than systemd (restart behavior, status codes, etc.)

**Mitigation:**
- Study launchd documentation thoroughly
- Test edge cases (crashes, manual unload, etc.)
- Add comprehensive logging for launchctl commands

### Risk 2: Path Migration
**Risk:** Existing Linux users may have data at `/var/antctl/`

**Mitigation:**
- Keep root detection on Linux
- Only change macOS and Linux user-level paths
- Document migration path for users

### Risk 3: Firewall Differences
**Risk:** Null firewall may expose security issues on macOS

**Mitigation:**
- Document that macOS firewall is disabled
- Add warning if System Preferences firewall is enabled
- Consider implementing PfctlManager in future

### Risk 4: Testing Coverage
**Risk:** Platform-specific code may not be tested on both platforms

**Mitigation:**
- Use GitHub Actions for multi-platform CI
- Require tests to pass on both platforms before merge
- Add platform markers to skip incompatible tests

---

## Future Enhancements (Post-Phase 7)

### macOS Production Features
- [ ] Implement PfctlManager for production firewall management
- [ ] Add LaunchDaemon support (system-level services)
- [ ] Code signing and notarization for macOS binary
- [ ] Homebrew formula for easy installation

### Cross-Platform Improvements
- [ ] Windows support (via WSL or native process management)
- [ ] Unified service management CLI (`wnm service start/stop/status`)
- [ ] Platform-specific performance tuning
- [ ] Multi-platform integration tests

### Docker Training (Post-macOS Support)
- [ ] Docker node management on macOS
- [ ] Container-based node deployment
- [ ] Multi-container orchestration

### Developer Experience
- [ ] Hot-reload for development (watch mode)
- [ ] Better logging for platform-specific operations
- [ ] Performance benchmarks across platforms

---

## Questions / Blockers

1. ~~**Binary Distribution:** Where is the `antnode` binary for macOS?~~
   - **RESOLVED:** Use `antup` tool to download: `curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash && ~/.local/bin/antup node`
   - Binary location: `~/.local/bin/antnode`

2. ~~**Port Requirements:** Does macOS need different port ranges than Linux?~~
   - **RESOLVED:** No, port ranges can be the same.

3. **Performance:** Any known performance differences between launchd and systemd?
   - **UNKNOWN:** Will need to benchmark during testing.

4. ~~**Migration:** Should we support migrating from `anm` on macOS?~~
   - **RESOLVED:** No, `anm` is Linux-only and doesn't run on macOS.

---

## References

- **Refactoring Plan:** `REFACTORING-PLAN.md` (Phases 1-5 complete)
- **Docker Dev Environment:** `DOCKER-DEV.md`
- **Current Architecture:** `src/wnm/process_managers/`, `src/wnm/firewall/`
- **launchd Documentation:** https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html
- **XDG Base Directory Spec:** https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
- **antup Tool:** https://github.com/maidsafe/antup
