# Code Style Analysis: Weave Node Manager (wnm)

**Date:** 2025-10-18
**Version Analyzed:** 0.0.9
**Total Lines of Code:** 2,131 Python lines

## Overall Assessment: Mixed/Inconsistent

The codebase shows characteristics of early-stage development with functional priorities over strict style consistency.

## ⚠️ IMPORTANT: Proof of Concept Status

**This is a functional proof-of-concept** migrated from bash (`anm`) to Python. Based on `upgrade-considerations.md`, a major architectural rewrite is planned:

### Planned Architectural Changes:
1. **Dual-mode operation**:
   - **Single-shot mode** (cron-based) - **default**, supports multi-action if thresholds allow
   - **Daemon mode** (opt-in) - long-running with REST API/dashboard
2. **Single-machine scope**: Each wnm instance manages ONE physical machine
   - Nodes on bare host OS (systemd, setsid, antctl, launchctl)
   - Nodes IN Docker containers on same machine (HIGH PRIORITY)
   - Dashboard aggregates data from multiple wnm instances (separate concern)
3. **Multiple process managers** (HIGH PRIORITY: non-sudo support)
   - Import patterns from: anm, antctl, formacio, Dimitar's docker methods
   - Only takeover anm clusters (others don't auto-manage)
4. **Optional/modular firewall** (vs. hardcoded ufw)
5. **Concurrent actions with thresholds** (both modes)
   - Config: `max_concurrent_upgrades`, `max_concurrent_starts`, etc.
6. **Pluggable node selection strategies** (youngest/records/bans/CPU)
7. **Docker support** - run and monitor nodes inside containers
8. **Database breaking changes OK** - no migration needed, no current users

### Impact on Refactoring Priorities:

**Evolutionary enhancement** - core logic stays and improves:
- ✅ Refactor `choose_action()` - evolves to multi-action planner
- ✅ Modularize process managers - critical for docker/non-sudo
- ✅ Snake_case migration - no migration burden, go for it
- ✅ Fix error handling, add tests - foundation for reliability
- ✅ Timeline: Daily bursts (weeks) → sporadic (months)

---

## Strengths

### 1. Formatting Tools Configured
- **Black** (line-length: 88) and **isort** (profile: black) are configured in `pyproject.toml:42-46`
- This suggests intent to maintain consistent formatting

### 2. Clear Module Organization
- Well-separated concerns: `models.py`, `config.py`, `utils.py`, `common.py`, `__main__.py`
- Logical file size distribution (largest file: `utils.py` at 760 lines)

### 3. Type Hints (Partial)
- Modern SQLAlchemy 2.0 style with `Mapped[]` types in `models.py`
- Type hints in ORM models (`models.py:34-66`, `models.py:192-234`)

### 4. Documentation
- Docstrings present in module init (`__init__.py:1`)
- Inline comments explain decision logic (`__main__.py:159-180`)
- Comprehensive CLAUDE.md project documentation

---

## Issues & Inconsistencies

### 1. Naming Conventions (MAJOR ISSUE)

**Inconsistent variable casing:**
- **UpperCamelCase** used for configuration parameters throughout:
  ```python
  machine_config["CpuLessThan"]  # Should be cpu_less_than
  machine_config["NodeCap"]      # Should be node_cap
  ```
  - Seen in: `__main__.py:53-59`, `config.py:148-247`, `models.py:35-66`

**Python PEP 8 violation:** Variables and attributes should use `snake_case`, not `UpperCamelCase`. UpperCamelCase is reserved for class names.

**Function naming is correct:**
- `choose_action()`, `get_machine_metrics()`, `read_node_metadata()` ✓

### 2. Error Handling (CRITICAL ISSUE)

**Bare except clauses:**
```python
except:  # config.py:374, utils.py:58, utils.py:83, utils.py:542
    pass  # Silently swallows all errors
```
- Found in: `config.py:374`, `utils.py:58-59`, `utils.py:83-84`, multiple locations
- **Risk:** Catches `KeyboardInterrupt`, `SystemExit`, masking critical failures

**Better patterns found elsewhere:**
```python
except Exception as error:  # utils.py:74, utils.py:124
    template = "..."
    logging.info(message)
```

### 3. Magic Numbers

**Hardcoded constants without explanation:**
```python
if metrics["DeadNodes"] > 1:  # __main__.py:183 - Why 1 not 0?
if metrics["NodesNoVersion"] > 1:  # __main__.py:200
card["port"] = config["PortStart"] * 1000 + card["id"]  # utils.py:634
```

### 4. Function Length & Complexity

**Overly long functions:**
- `choose_action()`: ~337 lines (`__main__.py:50-386`)
- `create_node()`: ~114 lines (`utils.py:606-719`)
- `get_machine_metrics()`: ~106 lines (`utils.py:231-336`)

**Cyclomatic complexity:** `choose_action()` has deeply nested conditionals (10+ levels)

### 5. Code Duplication

**Repeated patterns:**
```python
# __main__.py:175-179 and __main__.py:295-299
with S() as session:
    session.query(Machine).filter(Machine.id == 1).update(...)
    session.commit()
```

**Config merging:**
- 30+ nearly identical if-blocks in `config.py:148-247`
- Could use a loop with a config schema

### 6. Commented-Out Code

```python
# utils.py:223-224
# if len(antnodes)>=5:
#   break

# utils.py:690
#RestartSec=300
```
Should be removed or converted to TODO comments

### 7. Inconsistent Return Types

```python
def start_systemd_node(S, node):
    # ...
    return True  # utils.py:496

def stop_systemd_node(S, node):
    # ...
    return True  # utils.py:512 - Always returns True even on errors
```

### 8. Type Hints Missing

- Function signatures lack type hints: `config.py:35-141`, `utils.py` (all functions)
- Only ORM models use modern typing

### 9. Logging Inconsistency

**Mixed logging levels:**
```python
logging.info(message)    # For errors: utils.py:77, utils.py:127
logging.warning(...)     # config.py:299
logging.error("... ERROR:", err)  # utils.py:473
logging.debug(...)       # utils.py:72
```

**Inconsistent error message format:**
- `"RN1 ERROR:"`, `"CN4 ERROR:"`, `"SSN2 ERROR:"` (utils.py)

### 10. SQL and Security

**SQL injection risk (mitigated by using `text()`):**
```python
sql = text("select n1.id + 1 as id from node n1 ...")  # utils.py:611-616
```
- Using `text()` prevents injection, but raw SQL could be replaced with ORM queries

---

## Specific Style Violations

| Issue | Location | PEP 8 Rule |
|-------|----------|-----------|
| Variables in UpperCamelCase | Throughout | PEP 8: Variable names lowercase_with_underscores |
| Bare `except:` | `utils.py:58`, `config.py:374` | PEP 8: Catch specific exceptions |
| Line too long (>88) | `config.py:350`, `models.py:137` | Black config: 88 chars |
| Unused imports | None found ✓ | - |
| Missing docstrings | All functions | PEP 257 |

---

## Refactoring Recommendations

**See `REFACTORING-PLAN.md` for detailed implementation roadmap.**

### Phase 1: Foundation (Week 1-2) - IMMEDIATE

1. **Replace bare `except:` clauses** ⚡ CRITICAL
   - Files: `utils.py:58, 83, 542`, `config.py:374`
   - Use `except Exception as e:` with proper logging
   - **Why:** Safety, debugging, doesn't hide KeyboardInterrupt

2. **Extract magic numbers to constants** ⚡
   - Add to `common.py`: `MIN_NODES_THRESHOLD`, `PORT_MULTIPLIER`, etc.
   - **Why:** Documents intent, easier to modify

3. **Remove commented-out code** ⚡
   - `utils.py:223-224, 690`
   - **Why:** Reduces confusion, git history preserves it

4. **Run Black + isort** ⚡
   - Already configured in `pyproject.toml`
   - **Why:** Establishes baseline, reduces diff noise

5. **Set up pytest + test infrastructure** 🧪
   - Create `tests/` directory
   - Docker test environment
   - **Why:** Foundation for safe refactoring

### Phase 2: Database Schema (Week 2) - HIGH PRIORITY

6. **Migrate to snake_case columns**
   - `NodeCap` → `node_cap`, etc.
   - **No migration needed** - breaking changes OK
   - **Why:** PEP 8 compliance, cleaner code

7. **Add Container table**
   - Support nodes in Docker containers
   - `Node.container_id` foreign key
   - **Why:** HIGH PRIORITY - docker support critical

8. **Add concurrency config**
   - `max_concurrent_upgrades`, `max_concurrent_starts`
   - **Why:** Enables multi-action support

### Phase 3: Process Manager Abstraction (Week 3-4) - CRITICAL

9. **Create ProcessManager interface** 🏗️
   - Abstract base class
   - Implementations: SystemdManager, DockerManager, SetsidManager
   - **Why:** HIGH PRIORITY - non-sudo + docker support

10. **Implement DockerManager** 🐳
    - Research formacio/Dimitar patterns
    - Single + multiple nodes per container
    - **Why:** HIGH PRIORITY requirement

11. **Modular firewall support**
    - Optional/pluggable (ufw, firewalld, none)
    - **Why:** Not all systems use ufw

### Phase 4: Decision Engine (Week 5-6) - ARCHITECTURE

12. **Refactor `choose_action()` → DecisionEngine**
    - Extract to `decision_engine.py`
    - Returns `List[Action]` instead of single action
    - **Why:** Enables multi-action with thresholds

13. **Create ActionExecutor**
    - Executes actions respecting concurrency limits
    - Sequential (single-shot) or async (daemon)
    - **Why:** Core of multi-action support

14. **Pluggable node selection strategies**
    - Strategy pattern: youngest, least_records, most_banned
    - **Why:** Different removal strategies for different use cases

### Phase 5: Daemon Mode (Month 2+) - FUTURE

15. **Add daemon mode**
    - Long-running event loop
    - FastAPI REST server
    - **Why:** Opt-in API for dashboard

16. **Add type hints (ongoing)**
    - Add as you refactor each module
    - Use mypy for checking
    - **Why:** Catch bugs, better IDE support

17. **Add docstrings (ongoing)**
    - Document complex logic
    - API endpoints need docs
    - **Why:** Maintainability, API documentation

---

## Positive Notes

- ✓ Uses modern Python 3.12+ features
- ✓ SQLAlchemy 2.0 declarative syntax
- ✓ Reasonable separation of concerns
- ✓ Functional code (working software > perfect style)
- ✓ Good project documentation in CLAUDE.md

---

## Summary

This is functional code with **moderate technical debt** primarily around naming conventions, error handling, and function complexity. It would benefit significantly from a refactoring pass focused on PEP 8 compliance and breaking down large functions.

## Action Items Checklist

- [ ] Fix all bare `except:` clauses
- [ ] Plan database migration for snake_case column names
- [ ] Add type hints to all function signatures
- [ ] Break down `choose_action()` into smaller functions
- [ ] Remove commented-out code
- [ ] Add docstrings to public functions
- [ ] Standardize logging format
- [ ] Extract magic numbers to constants in `common.py`
- [ ] Run black and isort formatters
- [ ] Set up pre-commit hooks with black, isort, mypy, ruff

## Files Analyzed

```
3 src/wnm/__init__.py
483 src/wnm/__main__.py
14 src/wnm/common.py
554 src/wnm/config.py
317 src/wnm/models.py
760 src/wnm/utils.py
2131 total
```
