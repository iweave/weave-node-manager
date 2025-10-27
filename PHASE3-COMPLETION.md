# Phase 3 Completion: Platform-Agnostic File Paths

**Completed:** 2025-10-27
**Duration:** 1 day (estimated 3 days)
**Status:** ✅ All success criteria met

---

## Overview

Successfully implemented platform-specific file paths for macOS, Linux (root), and Linux (user) environments. This enables WNM to run natively on macOS while maintaining backwards compatibility with existing Linux deployments.

---

## What Was Implemented

### 1. Centralized Platform Detection (config.py:34-79)

**Added global constants:**
```python
PLATFORM = platform.system()  # 'Linux', 'Darwin', 'Windows'
IS_ROOT = PLATFORM == "Linux" and os.geteuid() == 0
```

**Benefits:**
- Single source of truth for platform detection
- No duplicate `platform.system()` calls throughout codebase
- Root user detection centralized

### 2. Platform-Specific Path Constants

| Constant | macOS | Linux (root) | Linux (user) |
|----------|-------|--------------|--------------|
| **BASE_DIR** | `~/Library/Application Support/autonomi` | `/var/antctl` | `~/.local/share/autonomi` |
| **NODE_STORAGE** | `~/Library/Application Support/autonomi/node` | `/var/antctl/services` | `~/.local/share/autonomi/node` |
| **LOG_DIR** | `~/Library/Logs/autonomi` | `/var/log/antnode` | `~/.local/share/autonomi/logs` |
| **BOOTSTRAP_CACHE_DIR** | `~/Library/Caches/autonomi/bootstrap-cache` | `/var/antctl/bootstrap-cache` | `~/.local/share/autonomi/bootstrap-cache` |
| **LOCK_FILE** | `{BASE_DIR}/wnm_active` | `/var/antctl/wnm_active` | `{BASE_DIR}/wnm_active` |
| **DEFAULT_DB_PATH** | `sqlite:///{BASE_DIR}/colony.db` | `sqlite:///colony.db` | `sqlite:///{BASE_DIR}/colony.db` |

**Design Decisions:**
- macOS follows Apple HIG (Human Interface Guidelines) for app data storage
- Linux (root) preserves `/var/antctl` for backwards compatibility with `anm` migration
- Linux (user) follows XDG Base Directory specification
- NODE_STORAGE can be overridden via env var/CLI option (only during `--init`)
- Test mode (`WNM_TEST_MODE=1`) skips directory creation

### 3. Updated Files

**Total:** 6 files modified, 12 hardcoded path occurrences replaced

| File | Changes | Lines Modified |
|------|---------|----------------|
| `config.py` | Added path constants, updated 2 NODE_STORAGE defaults, eliminated duplicate platform checks | 34-79, 307, 341, 437, 458 |
| `__main__.py` | Imported LOCK_FILE constant, replaced 3 hardcoded `/var/antctl/wnm_active` | 10, 96, 102, 179 |
| `utils.py` | Imported constants, replaced 4 log/bootstrap-cache paths, removed duplicate platform checks | 31, 244, 316, 596, 682 (×2), 718, 772 |
| `systemd_manager.py` | Imported constants, replaced 3 paths | 15, 49, 96, 287 |
| `docker_manager.py` | Imported constant, replaced 1 bootstrap-cache path | 16, 104 |
| `setsid_manager.py` | Imported constant, replaced 1 bootstrap-cache path | 19, 127 |

### 4. Eliminated Duplicate Platform Detection

**Before (5 duplicate calls):**
- config.py: `platform.system()` called 3 times (lines 36, 307, 437)
- utils.py: `platform.system()` called 2 times (lines 244, 316)

**After (1 canonical definition):**
- config.py: `PLATFORM = platform.system()` defined once
- All other modules import and use `PLATFORM` constant

**Benefits:**
- Consistent behavior across entire codebase
- Faster (no repeated system calls)
- Easier to mock for testing
- Single import statement

### 5. Fixed Circular Import

**Issue:** config.py imported `wnm.utils`, but utils.py needed to import from config.py

**Solution:** Removed unused `import wnm.utils` from config.py (line 31)

**Impact:** Clean module dependencies, faster imports, no circular dependency issues

---

## Test Results

### macOS Native Tests
```bash
WNM_TEST_MODE=1 PYTHONPATH=src python3 -m pytest tests/test_macos_native.py -v
```
**Result:** ✅ 4 passed, 3 skipped

### Full macOS Test Suite
```bash
WNM_TEST_MODE=1 PYTHONPATH=src python3 -m pytest tests/ -v
```
**Result:** ✅ 88 passed, 10 skipped

### Linux Docker Tests
```bash
./scripts/test.sh
```
**Result:** ✅ 88 passed, 11 skipped

### Coverage
- Overall: 47% (maintained, no regression)
- config.py: 33%
- utils.py: 21%

---

## Files Modified Summary

### Core Changes
1. **src/wnm/config.py** (45 lines added, 3 lines modified)
   - Added platform detection section (34-79)
   - Updated `load_anm_config()` to use PLATFORM constant (307)
   - Updated `define_machine()` to use PLATFORM constant (437)
   - Updated NODE_STORAGE defaults (341, 458)
   - Removed circular import (31)

2. **src/wnm/__main__.py** (3 occurrences)
   - Imported LOCK_FILE constant (10)
   - Replaced hardcoded lock file paths (96, 102, 179)

3. **src/wnm/utils.py** (8 occurrences)
   - Imported constants and removed platform import (31)
   - Updated system start detection to use PLATFORM (244)
   - Updated CPU metrics parsing to use PLATFORM (316)
   - Replaced LOG_DIR paths (596, 682 ×2)
   - Replaced BOOTSTRAP_CACHE_DIR paths (718, 772)

### Process Managers
4. **src/wnm/process_managers/systemd_manager.py** (3 occurrences)
   - Imported constants (15)
   - Replaced LOG_DIR path (49)
   - Replaced BOOTSTRAP_CACHE_DIR path (96)
   - Replaced LOG_DIR in remove operation (287)

5. **src/wnm/process_managers/docker_manager.py** (1 occurrence)
   - Imported constant (16)
   - Replaced BOOTSTRAP_CACHE_DIR volume mount (104)

6. **src/wnm/process_managers/setsid_manager.py** (1 occurrence)
   - Imported constant (19)
   - Replaced BOOTSTRAP_CACHE_DIR argument (127)

### Tests
7. **tests/test_macos_native.py** (1 update)
   - Updated test to verify PLATFORM constant instead of platform module (75-91)

---

## Verification Checklist

✅ **Platform Detection**
- [x] PLATFORM constant defined once in config.py
- [x] IS_ROOT properly detects Linux root user
- [x] No duplicate platform.system() calls
- [x] utils.py imports PLATFORM from config

✅ **Path Constants**
- [x] BASE_DIR platform-specific
- [x] NODE_STORAGE platform-specific
- [x] LOG_DIR platform-specific
- [x] BOOTSTRAP_CACHE_DIR platform-specific
- [x] LOCK_FILE derived from BASE_DIR
- [x] DEFAULT_DB_PATH derived from BASE_DIR

✅ **Code Updates**
- [x] config.py: All hardcoded paths replaced
- [x] __main__.py: Lock file paths use constant
- [x] utils.py: Log and bootstrap paths use constants
- [x] systemd_manager.py: Paths use constants
- [x] docker_manager.py: Bootstrap cache uses constant
- [x] setsid_manager.py: Bootstrap cache uses constant

✅ **Import Cleanup**
- [x] Removed circular import (wnm.utils from config.py)
- [x] Removed unused platform import from utils.py
- [x] Clean import statements

✅ **Testing**
- [x] macOS tests pass (88 passed)
- [x] Linux tests pass (88 passed)
- [x] No regressions
- [x] Test coverage maintained at 47%

✅ **Backwards Compatibility**
- [x] Linux root still uses /var/antctl
- [x] anm migration still works
- [x] Existing deployments unaffected

---

## Known Limitations

1. **Admin Override:** NODE_STORAGE can only be overridden during `--init`, not after cluster is created
2. **Windows Support:** Paths defined but untested (requires future work)
3. **Path Migration:** No automatic migration for users moving from one platform to another

---

## Next Steps

**Recommended:** Proceed to Phase 1 (Launchd Manager)

**Alternative Options:**
1. Phase 2 (Null Firewall) - Verify existing firewall abstraction works on macOS
2. Additional testing - Increase code coverage on path-related functions
3. Documentation - Update CLAUDE.md and README.md with platform-specific setup

---

## Git Diff Summary

```
 MACOS-SUPPORT-PLAN.md                         |  19 +++++-
 PHASE3-COMPLETION.md                          | 244 +++++++++++++++++++++
 src/wnm/__main__.py                           |   8 +-
 src/wnm/config.py                             |  49 ++++-
 src/wnm/process_managers/docker_manager.py    |   3 +-
 src/wnm/process_managers/setsid_manager.py    |   3 +-
 src/wnm/process_managers/systemd_manager.py   |   7 +-
 src/wnm/utils.py                              |  14 +-
 tests/test_macos_native.py                    |  12 +-
 9 files changed, 326 insertions(+), 33 deletions(-)
```

---

## Performance Impact

- **Startup:** Negligible (one-time platform detection at import)
- **Runtime:** Faster (no repeated platform.system() calls)
- **Memory:** Minimal (6 additional module-level constants)
- **Disk:** Directory creation only occurs once (unless test mode)

---

## Success Metrics Achieved

✅ All Phase 3 success criteria from MACOS-SUPPORT-PLAN.md met:
- User-level paths work on macOS and Linux
- Root detection works on Linux
- Lock file, DB, logs created in correct locations
- All path constants replaced (12 occurrences)
- macOS uses ~/Library/Application Support/autonomi
- NODE_STORAGE defaults to platform-appropriate paths
- Centralized platform detection implemented
- No circular imports or duplicate calls
- Tests pass on both platforms with no regressions

---

**Phase 3 Status:** ✅ COMPLETE
**Ready for:** Phase 1 (Launchd Manager) or commit
