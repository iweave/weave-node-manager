# Refactoring Plan: WNM v0.0.9 → v1.0

**Updated:** 2025-10-18
**Timeline:** Daily bursts (next few weeks) → sporadic work (months)
**Scope:** Single physical machine per wnm instance, manage nodes on host + in containers

---

## Revised Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ Physical Machine (ONE per wnm instance)                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐       ┌─────────────────────┐    │
│  │ Host OS Nodes    │       │ Container Nodes     │    │
│  ├──────────────────┤       ├─────────────────────┤    │
│  │ • systemd        │       │ Docker Container 1  │    │
│  │ • setsid         │       │  ├─ Node 1          │    │
│  │ • antctl         │       │  └─ Node 2          │    │
│  │ • launchctl(mac) │       │                     │    │
│  └──────────────────┘       │ Docker Container 2  │    │
│                             │  └─ Node 3          │    │
│                             └─────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ WNM (Single-shot or Daemon)                      │  │
│  │ ├─ DecisionEngine  → Plan actions                │  │
│  │ ├─ ActionExecutor  → Execute with thresholds     │  │
│  │ ├─ ProcessManagers → systemd/docker/setsid/...   │  │
│  │ └─ API (daemon)    → Dashboard queries           │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

      │
      │ (Dashboard aggregates multiple wnm instances)
      ▼
┌─────────────────────┐
│ Central Dashboard   │
│ (queries N machines)│
└─────────────────────┘
```

---

## Phase 1: Foundation (Week 1-2) - "Make it Safe"

**Goal:** Fix critical issues, establish testing, enable daily development

**STATUS: ✅ COMPLETED (2025-10-19)**

### 1.1 Critical Safety Fixes ✅ COMPLETED
- [x] Replace all bare `except:` with `except Exception as e:`
  - Files: `utils.py:58, 83, 542`, `config.py:374`
  - Log exceptions properly
  - **Completed:** 2025-10-18, commit 549768a

- [x] Extract magic numbers to `common.py`
  ```python
  # common.py additions
  MIN_NODES_THRESHOLD = 0  # Why checking > 1 instead of > 0?
  PORT_MULTIPLIER = 1000
  METRICS_PORT_BASE = 13000
  DEFAULT_CRISIS_BYTES = 2 * 10**9
  ```
  - **Completed:** 2025-10-18, commit 549768a

- [x] Remove commented code
  - `utils.py:223-224, 690`
  - **Completed:** 2025-10-18, commit 549768a

### 1.2 Testing Infrastructure ✅ COMPLETED
- [x] Add pytest + dependencies to `requirements-dev.txt`
  - pytest 8.0+, pytest-cov, pytest-asyncio, pytest-mock, pytest-docker
  - **Completed:** 2025-10-19, commit 4bd60d1

- [x] Create `tests/` directory structure:
  ```
  tests/
  ├── __init__.py
  ├── conftest.py           # Fixtures, test DB setup ✅
  ├── test_models.py        # ORM tests (14 tests) ✅
  ├── test_decision_engine.py # Decision logic (19 tests) ✅
  ├── test_process_managers.py # Stubs (29 tests for Phase 3)
  ├── integration/
  │   └── __init__.py
  └── docker/
      ├── Dockerfile.test   # Debian + systemd ✅
      └── docker-compose.test.yml ✅
  ```
  - **Completed:** 2025-10-19, commit 4bd60d1

- [x] Add Docker test environment
  - Debian Bookworm with Python 3.11, systemd, ufw
  - User 'ant' with sudo privileges
  - Two services: wnm-test (CI) and wnm-dev (interactive)
  - Helper scripts: scripts/test.sh, scripts/dev.sh
  - Documentation: DOCKER-DEV.md
  - **Test Results:** 33 passed, 29 skipped, 12% coverage
  - **Completed:** 2025-10-19, commit 4bd60d1

### 1.3 Code Formatting ✅ COMPLETED
- [x] Run `black src/` and `isort src/`
  - Reformatted 3 files: __main__.py, config.py, utils.py
  - **Completed:** 2025-10-19

- [x] Verify pyproject.toml settings
  - black: line-length = 88 ✅
  - isort: profile = "black" ✅
  - **Completed:** 2025-10-19

- [ ] Add pre-commit hooks (optional - deferred to later)

---

## Phase 2: Database Migration (Week 2) - "Clean Schema"

**Goal:** Snake_case, add Container support, no backward compatibility needed

**STATUS: ✅ COMPLETED (2025-10-19)**

### 2.1 New Schema Design ✅ COMPLETED
```python
# models.py (new version)

class Machine(Base):
    """One row per wnm instance (single physical machine)"""
    __tablename__ = "machine"
    id: Mapped[int] = mapped_column(primary_key=True)

    # Resource thresholds
    cpu_less_than: Mapped[int]
    cpu_remove: Mapped[int]
    mem_less_than: Mapped[int]
    # ... all snake_case

    # NEW: Concurrency limits
    max_concurrent_upgrades: Mapped[int] = mapped_column(default=1)
    max_concurrent_starts: Mapped[int] = mapped_column(default=2)
    max_concurrent_removals: Mapped[int] = mapped_column(default=1)

    # NEW: Node selection strategy
    node_removal_strategy: Mapped[str] = mapped_column(default="youngest")


class Container(Base):
    """Optional: Docker containers hosting nodes"""
    __tablename__ = "container"
    id: Mapped[int] = mapped_column(primary_key=True)
    container_id: Mapped[str]  # Docker container ID
    name: Mapped[str]
    image: Mapped[str]
    status: Mapped[str]  # running, stopped, etc.
    created_at: Mapped[int]


class Node(Base):
    """Nodes on host OS or in containers"""
    __tablename__ = "node"
    id: Mapped[int] = mapped_column(primary_key=True)

    # NEW: Optional container reference
    container_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("container.id"), nullable=True
    )

    # Process manager type
    manager_type: Mapped[str]  # "systemd", "docker", "setsid", "antctl", "launchctl"

    # All snake_case
    node_name: Mapped[str]
    root_dir: Mapped[str]
    # ...
```

### 2.2 Migration Script ✅ COMPLETED
- [x] Create `scripts/migrate_v0_to_v1.py`
  - Reads old `colony.db`
  - Creates new schema
  - Migrates data (UpperCamelCase → snake_case)
  - Converts delay timers from minutes to seconds
  - **Completed:** 2025-10-19, commit 3484412

### 2.3 Update All Code ✅ COMPLETED
- [x] Update `config.py` - snake_case everywhere, timer defaults to seconds
- [x] Update `utils.py` - snake_case, removed * 60 conversions
- [x] Update `__main__.py` - snake_case, removed * 60 conversions
- [x] Update `common.py` - already snake_case (no changes needed)
- [x] Update all tests - snake_case throughout
- [x] Update `CLAUDE.md` - added Docker testing requirements
- **Completed:** 2025-10-19, commit 3484412

---

## Phase 3: Process Manager Abstraction (Week 3-4) - "Modularize"

**Goal:** Support systemd, docker, setsid, antctl, launchctl

### 3.1 Abstract Base Class
```python
# src/wnm/process_managers/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class NodeProcess:
    """Represents a running node process"""
    node_id: int
    pid: Optional[int]
    status: str  # RUNNING, STOPPED, etc.

class ProcessManager(ABC):
    """Abstract interface for node lifecycle management"""

    @abstractmethod
    def create_node(self, node: Node) -> bool:
        """Create and start a node"""
        pass

    @abstractmethod
    def start_node(self, node: Node) -> bool:
        """Start a stopped node"""
        pass

    @abstractmethod
    def stop_node(self, node: Node) -> bool:
        """Stop a running node"""
        pass

    @abstractmethod
    def get_status(self, node: Node) -> NodeProcess:
        """Get current node status"""
        pass

    @abstractmethod
    def remove_node(self, node: Node) -> bool:
        """Stop and remove node"""
        pass
```

### 3.2 Implementations (Priority Order)

**HIGH PRIORITY:**

1. **SystemdManager** (Week 3)
   - [ ] Extract current `utils.py` systemd code
   - [ ] Support both system and user systemd
   - [ ] Tests with mocked `systemctl` calls

2. **DockerManager** (Week 3-4) - **CRITICAL**
   - [ ] Research formacio, Dimitar's docker patterns
   - [ ] Implement `docker run`, `docker exec`, `docker stop`
   - [ ] Monitor via `docker stats` or metrics ports
   - [ ] Handle single node per container
   - [ ] Handle multiple nodes per container
   - [ ] Update `Container` table on operations

**MEDIUM PRIORITY:**

3. **SetsidManager** (Week 4)
   - [ ] Non-sudo process launching
   - [ ] PID file management
   - [ ] Process monitoring via psutil

4. **AntctlManager** (Week 4)
   - [ ] Wrapper around `antctl` commands
   - [ ] Parse `antctl` output

**LOW PRIORITY (Later):**

5. **LaunchctlManager** (Month 2+)
   - [ ] macOS support via launchctl

### 3.3 Factory Pattern
```python
# src/wnm/process_managers/factory.py

def get_process_manager(manager_type: str) -> ProcessManager:
    managers = {
        "systemd": SystemdManager,
        "docker": DockerManager,
        "setsid": SetsidManager,
        "antctl": AntctlManager,
        "launchctl": LaunchctlManager,
    }
    return managers[manager_type]()
```

### 3.4 Update Node Creation
```python
# utils.py (refactored)

def create_node(config, metrics, manager_type="systemd"):
    # ... build node dict ...
    node.manager_type = manager_type

    manager = get_process_manager(manager_type)
    return manager.create_node(node)
```

---

## Phase 4: Firewall Abstraction (Week 4) - "Optional Firewalls"

### 4.1 Firewall Manager Interface
```python
# src/wnm/firewall/base.py

class FirewallManager(ABC):
    @abstractmethod
    def enable_port(self, port: int, protocol: str = "udp") -> bool:
        pass

    @abstractmethod
    def disable_port(self, port: int, protocol: str = "udp") -> bool:
        pass

# Implementations
class UFWManager(FirewallManager): ...
class FirewalldManager(FirewallManager): ...
class NullFirewall(FirewallManager):  # No-op for disabled firewall
    def enable_port(self, port, protocol): return True
    def disable_port(self, port, protocol): return True
```

### 4.2 Make Firewall Optional
- [ ] Config option: `firewall_enabled=true`, `firewall_type="ufw"`
- [ ] Default to `NullFirewall` if disabled

---

## Phase 5: Decision Engine Refactor (Week 5-6) - "Multi-Action"

**Goal:** Extract logic from `choose_action()`, enable concurrent actions

### 5.1 Action Model
```python
# src/wnm/actions.py

from enum import Enum
from dataclasses import dataclass

class ActionType(Enum):
    ADD_NODE = "add"
    REMOVE_NODE = "remove"
    UPGRADE_NODE = "upgrade"
    START_NODE = "start"
    STOP_NODE = "stop"
    SURVEY_NODES = "survey"

@dataclass
class Action:
    type: ActionType
    node_id: Optional[int] = None
    priority: int = 0  # Higher = more urgent
    reason: str = ""   # Why this action (for logging)
```

### 5.2 Decision Engine
```python
# src/wnm/decision_engine.py

class DecisionEngine:
    def __init__(self, machine_config, metrics):
        self.config = machine_config
        self.metrics = metrics

    def plan_actions(self) -> list[Action]:
        """
        Returns prioritized list of actions to take.
        Respects concurrency thresholds.
        """
        actions = []

        # Check for dead nodes (highest priority)
        if self.metrics.dead_nodes > 0:
            actions.extend(self._plan_dead_node_removals())

        # Check if we need to remove nodes
        if self._should_remove_nodes():
            actions.extend(self._plan_node_removals())

        # Check for upgrades (if not removing)
        elif self.metrics.nodes_to_upgrade > 0:
            actions.extend(self._plan_upgrades())

        # Check if we can add nodes
        if self._can_add_nodes():
            actions.extend(self._plan_node_additions())

        # Default: survey nodes
        if not actions:
            actions.append(Action(ActionType.SURVEY_NODES, reason="idle"))

        return self._apply_thresholds(actions)

    def _apply_thresholds(self, actions: list[Action]) -> list[Action]:
        """Filter actions based on concurrency limits"""
        # Count current in-flight actions
        upgrading = self.metrics.upgrading_nodes
        starting = self.metrics.restarting_nodes
        removing = self.metrics.removing_nodes

        # Filter based on limits
        result = []
        for action in actions:
            if action.type == ActionType.UPGRADE_NODE:
                if upgrading < self.config.max_concurrent_upgrades:
                    result.append(action)
                    upgrading += 1
            # ... similar for other types

        return result
```

### 5.3 Action Executor
```python
# src/wnm/executor.py

class ActionExecutor:
    def __init__(self, session_factory):
        self.S = session_factory

    def execute(self, actions: list[Action]) -> dict:
        """Execute actions sequentially (single-shot) or async (daemon)"""
        results = {}

        for action in actions:
            logging.info(f"Executing: {action.type.value} - {action.reason}")

            if action.type == ActionType.UPGRADE_NODE:
                node = self._get_node(action.node_id)
                success = upgrade_node(self.S, node, metrics)
                results[action.node_id] = success
            # ... handle other action types

        return results
```

### 5.4 Update Main Loop
```python
# __main__.py (refactored choose_action)

def main():
    # ... existing setup ...

    metrics = get_machine_metrics(...)

    # NEW: Use decision engine
    engine = DecisionEngine(local_config, metrics)
    actions = engine.plan_actions()

    # NEW: Execute actions
    executor = ActionExecutor(S)
    results = executor.execute(actions)

    logging.info(f"Executed {len(results)} actions")
```

---

## Phase 6: Node Selection Strategies (Week 6) - "Smart Selection"

### 6.1 Strategy Interface
```python
# src/wnm/selectors.py

class NodeSelector(ABC):
    @abstractmethod
    def select_for_removal(self, nodes: list[Node], count: int) -> list[Node]:
        """Select which nodes to remove"""
        pass

class YoungestSelector(NodeSelector):
    def select_for_removal(self, nodes, count):
        return sorted(nodes, key=lambda n: n.age, reverse=True)[:count]

class LeastRecordsSelector(NodeSelector):
    def select_for_removal(self, nodes, count):
        return sorted(nodes, key=lambda n: n.records)[:count]

class MostBannedSelector(NodeSelector):
    def select_for_removal(self, nodes, count):
        return sorted(nodes, key=lambda n: n.shunned, reverse=True)[:count]
```

### 6.2 Use in Decision Engine
```python
# decision_engine.py

def _plan_node_removals(self):
    strategy_name = self.config.node_removal_strategy
    selector = get_selector(strategy_name)

    nodes_to_remove = selector.select_for_removal(
        self._get_removable_nodes(),
        count=self._calculate_removal_count()
    )

    return [Action(ActionType.REMOVE_NODE, node.id) for node in nodes_to_remove]
```

---

## Phase 7: Daemon Mode Scaffold (Month 2) - "Optional API"

### 7.1 Mode Detection
```python
# __main__.py

def main():
    if options.daemon:
        run_daemon_mode()
    else:
        run_single_shot()

def run_single_shot():
    """Current behavior: run once, exit"""
    # ... existing logic ...

def run_daemon_mode():
    """NEW: Long-running event loop"""
    import asyncio
    asyncio.run(daemon_loop())

async def daemon_loop():
    """Run decision engine every N seconds"""
    api_task = asyncio.create_task(start_api_server())

    while True:
        await asyncio.sleep(60)  # Run every minute
        # ... decision engine logic ...
```

### 7.2 API Server (FastAPI)
```python
# src/wnm/api/server.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="WNM API")

@app.get("/nodes")
def get_nodes():
    """List all nodes on this machine"""
    with S() as session:
        nodes = session.query(Node).all()
    return [node.__json__() for node in nodes]

@app.get("/metrics")
def get_metrics():
    """Current machine metrics"""
    return get_machine_metrics(...)

@app.post("/actions/add-node")
def trigger_add_node():
    """Manually trigger node addition"""
    # ... validation, then create_node()
```

---

## Testing Strategy

### Unit Tests
```python
# tests/test_decision_engine.py

def test_plan_dead_node_removals():
    metrics = MockMetrics(dead_nodes=2)
    config = MockConfig()
    engine = DecisionEngine(config, metrics)

    actions = engine.plan_actions()

    assert len(actions) == 2
    assert all(a.type == ActionType.REMOVE_NODE for a in actions)

def test_respect_upgrade_threshold():
    metrics = MockMetrics(
        upgrading_nodes=1,
        nodes_to_upgrade=5
    )
    config = MockConfig(max_concurrent_upgrades=2)
    engine = DecisionEngine(config, metrics)

    actions = engine.plan_actions()
    upgrade_actions = [a for a in actions if a.type == ActionType.UPGRADE_NODE]

    assert len(upgrade_actions) <= 1  # Only 1 more allowed
```

### Integration Tests (Docker)
```python
# tests/integration/test_docker_nodes.py

@pytest.mark.docker
def test_create_docker_node():
    manager = DockerManager()
    node = create_test_node(manager_type="docker")

    success = manager.create_node(node)
    assert success

    # Verify container exists
    containers = docker_client.containers.list()
    assert any(c.name == f"antnode{node.id}" for c in containers)
```

---

## Immediate Next Steps

**Phase 1 ✅ COMPLETE** - Foundation established
**Phase 2 ✅ COMPLETE** - Schema migrated to snake_case

### Next: Phase 3 - Process Manager Abstraction
1. Create abstract base class for process managers
2. Extract SystemdManager from existing utils.py code
3. Implement DockerManager (high priority)
4. Implement SetsidManager (medium priority)
5. Create factory pattern for manager selection
6. Update tests with mocked manager implementations

---

## Success Metrics

**Phase 1 Metrics:**
- [x] All bare `except:` fixed ✅
- [x] Testing infrastructure established ✅
- [x] 12% code coverage with pytest (100% models.py) ✅
- [x] Docker development environment working ✅
- [x] Code formatting with black/isort ✅

**Phase 2 Metrics:**
- [x] Snake_case migration complete (all files) ✅
- [x] Timer resolution: minutes → seconds ✅
- [x] Container table added ✅
- [x] New Machine/Node fields added ✅
- [x] Migration script created ✅
- [x] All 33 tests passing ✅
- [x] 15% code coverage (95% on models.py) ✅

**Overall Project Metrics (In Progress):**
- [ ] 50%+ code coverage with pytest (currently 15%)
- [x] Snake_case migration complete ✅
- [ ] At least 2 process managers working (systemd, docker)
- [ ] Multi-action support with thresholds
- [ ] Non-sudo operation supported
- [ ] Docker nodes create/start/stop/monitor
- [ ] API scaffold ready for dashboard integration

---

## Questions / Blockers

1. **Docker patterns:** Need examples from formacio/Dimitar - where to find?
2. **Antctl integration:** Is `antctl` CLI documented? Any examples?
3. **Testing in Docker:** Preference for test runner setup?
4. **Dashboard API contract:** Any existing API spec or should we design fresh?

---

## References

- Original POC: `upgrade-considerations.md`
- Style analysis: `code-style-analysis.md`
- Current code: `src/wnm/*.py`
