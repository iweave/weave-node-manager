# RECOVERY DOCUMENT: systemd+sudo Process Manager Fix

## Issue
`systemd+sudo` mode creates service files in wrong location (`~/.config/systemd/user/` instead of `/etc/systemd/system/`)

## Environment
- **Remote server**: `ssh xdwnm` (logs in as user `dawn` on Ubuntu 24.04)
- **Database**: `~/colony.db` (relative path from run directory)
- **Machine config**: `process_manager=systemd+sudo` ✓
- **Cluster status**: Currently torn down (no nodes)
- **Virtual environment**: `~/.venv` (must be sourced before running wnm)
- **Binary location**: `~/.local/bin/` (must be in PATH)

## Database Query Method
```bash
ssh xdwnm "sqlite3 ~/colony.db 'SELECT * FROM machine;'"
ssh xdwnm "sqlite3 ~/colony.db 'SELECT id, node_name, status, manager_type FROM node;'"
```

## Running Commands on Remote Server
Always use this pattern:
```bash
ssh xdwnm "cd ~ && export PATH=~/.local/bin:\$PATH && source ~/.venv/bin/activate && wnm <args>"
```

## Background Context

### Terminology Clarification
- Originally called this mode "root" but it's actually **"systemd+sudo"**
- Runs as non-root user (`dawn`) with **passwordless sudo** access
- Need to identify which specific commands need sudo (not global sudo access)

### Current Issues
1. **Service file location bug**: When using `systemd+sudo` mode, services are being created in `~/.config/systemd/user/` (user services) instead of `/etc/systemd/system/` (system services with sudo)

2. **Database query issue**: RESOLVED - database is at `~/colony.db` due to relative path in config default

## Root Cause Investigation

### Key Code Locations
- `src/wnm/process_managers/factory.py:34-40` - Mode parsing logic (splits "systemd+sudo" into base_type and mode)
- `src/wnm/process_managers/systemd_manager.py:30-48` - SystemdManager.__init__ mode detection
- `src/wnm/process_managers/systemd_manager.py:64-68` - Service directory setting
- `src/wnm/config.py:41` - `IS_ROOT` check (checks if actually root, not if sudo available)

### Logic Flow
1. Factory parses `"systemd+sudo"` → `base_type="systemd"`, `mode="sudo"`
2. Factory passes `mode="sudo"` to `SystemdManager.__init__(mode="sudo")`
3. SystemdManager checks: if `mode == "sudo"`: `self.use_system_services = True`
4. If `use_system_services == True`: `self.service_dir = "/etc/systemd/system"`

### Hypothesis
The mode parameter might not be reaching SystemdManager, or the logic is being overridden by `IS_ROOT` check.

## Test Plan
1. Add a node: `python3 -m wnm --force_action add`
2. Check service file locations:
   - System services: `ls -la /etc/systemd/system/antnode*`
   - User services: `ls -la ~/.config/systemd/user/antnode*`
3. Add debug logging to trace `mode` parameter through initialization

## Fix Applied ✅

### What Was Fixed
Changed `src/wnm/executor.py` line 452 from:
```python
manager_type = get_default_manager_type()
```
to:
```python
manager_type = machine_config.get("process_manager") or get_default_manager_type()
```

### Test Results
✅ Service file now created in `/etc/systemd/system/antnode0001.service` (CORRECT)
✅ Database shows `manager_type=systemd+sudo` (mode preserved)
✅ User services directory remains empty

## Second Fix Applied ✅

### Path Configuration Fixed
Modified `src/wnm/config.py` to detect process manager mode early and select appropriate paths:

1. **Added `_detect_process_manager_mode()` function** that checks (in order):
   - Command line `--process_manager` argument
   - `PROCESS_MANAGER` environment variable
   - Existing databases in both sudo and user paths (auto-detection)
   - Fallback to `IS_ROOT` for backwards compatibility

2. **Path selection based on detected mode**:
   - **Sudo mode** (`systemd+sudo`, `setsid+sudo`, `launchd+sudo`):
     - Linux: `/var/antctl/services`, `/var/log/antnode`, `/var/antctl/bootstrap-cache`
     - macOS: `/Library/Application Support/autonomi/node`, `/Library/Logs/autonomi`
   - **User mode** (`systemd+user`, `setsid+user`, `launchd+user`):
     - Linux: `~/.local/share/autonomi/node`, `~/.local/share/autonomi/logs`
     - macOS: `~/Library/Application Support/autonomi/node`, `~/Library/Logs/autonomi`

3. **Database path fixed**: Changed default from `sqlite:///colony.db` (relative) to `DEFAULT_DB_PATH` (absolute)

4. **Directory creation**: Only creates `BASE_DIR` and `BOOTSTRAP_CACHE_DIR` at import time. `NODE_STORAGE` and `LOG_DIR` are created by ProcessManager when nodes are added.

### Setup Requirements for systemd+sudo Mode
1. Add wnm user to `ant` group: `sudo usermod -aG ant <username>`
2. Set ownership on system directories: `sudo chown -R ant:ant /var/antctl && sudo chmod -R 775 /var/antctl`
3. User must log out/in for group membership to take effect

## Commands Requiring Sudo (systemd+sudo mode)
- `mkdir -p` for system directories
- `cp` binary to system directories
- `chown` to change ownership to ant user
- `tee` to write service files to `/etc/systemd/system/`
- `systemctl daemon-reload`
- `systemctl start/stop/restart` (system services)
- `rm -rf` for system directories
- `ufw` firewall commands

## Final Test Results ✅

Successfully tested on Ubuntu 24.04 remote server:

```bash
# Initialize cluster
wnm --init --process_manager systemd+sudo --rewards_address 0x00455d78f850b0358E8cea5be24d415E01E107CF

# Add nodes WITHOUT --process_manager argument (auto-detection working!)
wnm --force_action add
wnm --force_action add
```

**Verified:**
- ✅ Services created in `/etc/systemd/system/antnode000X.service`
- ✅ Nodes running successfully with correct paths (`/var/antctl/services/antnode000X`)
- ✅ Services run as `ant` user (proper security)
- ✅ Database at `/var/antctl/colony.db` with `process_manager=systemd+sudo`
- ✅ Auto-detection working (no `--process_manager` needed after init)

## Complete Solution Summary

**Files Modified:**
1. `src/wnm/executor.py` line 452: Use `machine_config["process_manager"]` instead of `get_default_manager_type()`
2. `src/wnm/config.py`:
   - Added `_detect_process_manager_mode()` function with database auto-detection
   - Path selection based on detected mode (sudo vs user)
   - Fixed default database path to use `DEFAULT_DB_PATH`
   - Minimal directory creation (only BASE_DIR and BOOTSTRAP_CACHE_DIR)

**systemd+sudo is now fully functional!** 🎉