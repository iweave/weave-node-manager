# Concurrent Operations Design Document

**Feature Branch:** `feature/concurrent-operations`

## Overview

Add support for concurrent node operations to allow powerful machines to perform multiple upgrades, starts, and removals simultaneously instead of being limited to one operation per cycle.

## Current State

### Existing Infrastructure
- Database schema already has per-operation concurrency limits in `Machine` model (models.py:92-95):
  - `max_concurrent_upgrades` (default: 1)
  - `max_concurrent_starts` (default: 2)
  - `max_concurrent_removals` (default: 1)

### Current Problem
- Decision engine (decision_engine.py:218-237) **ignores these limits** and blocks on ANY in-progress operation:
  ```python
  if self.metrics["restarting_nodes"]:
      return [Action(type=ActionType.SURVEY_NODES, ...)]  # Blocks even if only 1 node

  if self.metrics["upgrading_nodes"]:
      return [Action(type=ActionType.SURVEY_NODES, ...)]  # Blocks even if only 1 node
  ```

## Design Decisions

### Chosen Approach: Option 1 - Decision Engine Modification
**Modify decision engine only, leverage existing schema**

### Key Decisions
1. **Scaling Behavior**: **Aggressive** - Jump to capacity immediately
   - If limit is 4 and 2 nodes are upgrading, add 2 more upgrades in one cycle (jump to 4)

2. **Global Limit**: Add `max_concurrent_operations` parameter
   - Limits total concurrent operations across all types
   - Example: `max_concurrent_operations=4` means at most 4 total operations (upgrades + starts + removals) at once
   - Per-operation limits still apply (can't exceed individual limits)

3. **Configuration**: Add command-line flags for all concurrency parameters
   - `--max_concurrent_upgrades`
   - `--max_concurrent_starts`
   - `--max_concurrent_removals`
   - `--max_concurrent_operations`

## Critical Design Constraint: Actual Node Availability

When planning multiple operations, we must respect **actual node counts** to avoid planning actions that cannot be fulfilled:

**Problem Example:**
- `stopped_nodes = 1`, `start_capacity = 4`
- Bad logic: Create 4 START_NODE actions → 3 fail (no nodes to start)

**Solution:**
Plan actions based on MIN(capacity, actual_available_nodes):
- Start actions: Limited by actual stopped nodes
- Add actions: Limited by node cap - total nodes
- Remove actions: Limited by actual stopped/running nodes
- Upgrade actions: Limited by nodes needing upgrade

## Implementation Plan

### Phase 1: Database Schema ✅ (Already exists, needs one addition)
**File**: `src/wnm/models.py`

Add `max_concurrent_operations` field to Machine model (line ~95):
```python
max_concurrent_operations: Mapped[int] = mapped_column(Integer, default=4)
```

Update `__init__()` method to accept `max_concurrent_operations` parameter.

Update `__json__()` method to include `max_concurrent_operations` in output.

### Phase 2: Configuration System
**File**: `src/wnm/config.py`

Add command-line arguments for all concurrency parameters:
```python
parser.add_argument(
    "--max_concurrent_upgrades",
    type=int,
    default=1,
    help="Maximum number of nodes that can be upgrading simultaneously"
)
parser.add_argument(
    "--max_concurrent_starts",
    type=int,
    default=2,
    help="Maximum number of nodes that can be starting/restarting simultaneously"
)
parser.add_argument(
    "--max_concurrent_removals",
    type=int,
    default=1,
    help="Maximum number of nodes that can be in removal state simultaneously"
)
parser.add_argument(
    "--max_concurrent_operations",
    type=int,
    default=4,
    help="Maximum total number of concurrent operations (global limit across all types)"
)
```

Add these to `config_updates` dictionary when provided via CLI.

### Phase 3: Decision Engine Logic
**File**: `src/wnm/decision_engine.py`

#### 3.1 Update `_compute_features()` method
Remove or modify the blocking checks:
- Remove blanket blocking on `upgrading_nodes` or `restarting_nodes`
- Add capacity calculations

#### 3.2 Update `plan_actions()` method
Change from returning single action to returning multiple actions when capacity allows.

**Current blocking logic (lines 218-237):**
```python
if self.metrics["restarting_nodes"]:
    logging.info("Still waiting for RestartDelay")
    return [Action(type=ActionType.SURVEY_NODES, ...)]

if self.metrics["upgrading_nodes"]:
    logging.info("Still waiting for UpgradeDelay")
    return [Action(type=ActionType.SURVEY_NODES, ...)]
```

**New capacity-aware logic:**
```python
# Calculate current total concurrent operations
current_ops = self._get_current_operations()

# Check if at global capacity
if current_ops >= self.config["max_concurrent_operations"]:
    logging.info(f"At global concurrent operations limit ({current_ops}/{self.config['max_concurrent_operations']})")
    return [Action(type=ActionType.SURVEY_NODES, reason="at global capacity")]

# Check individual operation type capacities
if self.metrics["upgrading_nodes"] >= self.config["max_concurrent_upgrades"]:
    logging.debug(f"At upgrade capacity ({self.metrics['upgrading_nodes']}/{self.config['max_concurrent_upgrades']})")

if self.metrics["restarting_nodes"] >= self.config["max_concurrent_starts"]:
    logging.debug(f"At start capacity ({self.metrics['restarting_nodes']}/{self.config['max_concurrent_starts']})")

if self.metrics["removing_nodes"] >= self.config["max_concurrent_removals"]:
    logging.debug(f"At removal capacity ({self.metrics['removing_nodes']}/{self.config['max_concurrent_removals']})")

# Continue with normal action planning (will respect capacities)
```

#### 3.3 Update action planning methods

**`_plan_upgrades()` - Return multiple upgrade actions (FIXED):**
```python
def _plan_upgrades(self) -> List[Action]:
    """Plan node upgrades with aggressive scaling to capacity.

    Returns:
        List of upgrade actions, limited by capacity AND actual upgradeable nodes
    """
    actions = []

    # Calculate available upgrade slots
    current_upgrading = self.metrics.get("upgrading_nodes", 0)
    current_ops = self._get_current_operations()

    # Determine capacity
    upgrade_capacity = min(
        self.config["max_concurrent_upgrades"] - current_upgrading,
        self.config["max_concurrent_operations"] - current_ops
    )

    if upgrade_capacity <= 0:
        return []

    # CRITICAL: Don't plan more upgrades than nodes needing upgrade
    actual_upgrades_needed = self.metrics.get("nodes_to_upgrade", 0)
    upgrades_to_plan = min(upgrade_capacity, actual_upgrades_needed)

    if upgrades_to_plan <= 0:
        return []

    # Plan multiple upgrades up to actual available count
    for i in range(upgrades_to_plan):
        actions.append(
            Action(
                type=ActionType.UPGRADE_NODE,
                node_id=None,  # Executor will query for oldest outdated nodes
                priority=60,
                reason=f"upgrade outdated node ({i+1}/{upgrades_to_plan})",
            )
        )

    return actions
```

**`_plan_node_additions()` - Return multiple start/add actions (FIXED):**
```python
def _plan_node_additions(self) -> List[Action]:
    """Plan adding new nodes or starting stopped nodes with aggressive scaling.

    Returns:
        List of start/add actions, limited by capacity AND actual available nodes
    """
    actions = []

    # Calculate available start slots
    current_starting = self.metrics.get("restarting_nodes", 0)
    current_ops = self._get_current_operations()

    # Determine capacity
    start_capacity = min(
        self.config["max_concurrent_starts"] - current_starting,
        self.config["max_concurrent_operations"] - current_ops
    )

    if start_capacity <= 0:
        return []

    # CRITICAL: Plan starts for stopped nodes (limited by actual stopped nodes)
    stopped_to_start = min(
        self.metrics.get("stopped_nodes", 0),
        start_capacity
    )

    for i in range(stopped_to_start):
        actions.append(
            Action(
                type=ActionType.START_NODE,
                node_id=None,  # Executor will query for oldest stopped nodes
                priority=50,
                reason=f"start stopped node ({i+1}/{stopped_to_start})",
            )
        )

    # CRITICAL: Plan additions for remaining capacity (if under node cap)
    remaining_capacity = start_capacity - stopped_to_start
    nodes_to_add = min(
        remaining_capacity,
        self.config["node_cap"] - self.metrics["total_nodes"]
    )

    for i in range(nodes_to_add):
        actions.append(
            Action(
                type=ActionType.ADD_NODE,
                priority=40,
                reason=f"add new node ({i+1}/{nodes_to_add})",
            )
        )

    return actions
```

**`_plan_resource_removal()` - Return multiple removal actions (FIXED):**
```python
def _plan_resource_removal(self) -> List[Action]:
    """Plan node removals due to resource pressure with aggressive scaling.

    Returns:
        List of removal or stop actions, limited by capacity AND actual available nodes
    """
    actions = []

    # Calculate available removal slots
    current_removing = self.metrics.get("removing_nodes", 0)
    current_ops = self._get_current_operations()

    # Determine capacity
    removal_capacity = min(
        self.config["max_concurrent_removals"] - current_removing,
        self.config["max_concurrent_operations"] - current_ops
    )

    if removal_capacity <= 0:
        return []

    # If under HD pressure, over node cap, or upgrades need resources
    if (
        self.features["remove_hd"]
        or self.metrics["total_nodes"] > self.config["node_cap"]
        or (
            self.metrics["nodes_to_upgrade"] > 0
            and self.metrics["removing_nodes"] == 0
        )
    ):
        # CRITICAL: Remove stopped nodes first (limited by actual stopped nodes)
        stopped_to_remove = min(
            self.metrics.get("stopped_nodes", 0),
            removal_capacity
        )

        for i in range(stopped_to_remove):
            actions.append(
                Action(
                    type=ActionType.REMOVE_NODE,
                    node_id=None,  # Executor will query for youngest stopped
                    priority=80,
                    reason=f"remove stopped node ({i+1}/{stopped_to_remove})",
                )
            )

        # CRITICAL: Remove running nodes for remaining capacity
        remaining_capacity = removal_capacity - stopped_to_remove
        running_to_remove = min(
            self.metrics.get("running_nodes", 0),
            remaining_capacity
        )

        for i in range(running_to_remove):
            actions.append(
                Action(
                    type=ActionType.REMOVE_NODE,
                    node_id=None,  # Executor will query for youngest running
                    priority=75,
                    reason=f"remove running node ({i+1}/{running_to_remove})",
                )
            )
    else:
        # Just stop nodes to reduce resource usage
        if self.metrics["removing_nodes"] > 0:
            logging.info("Still waiting for RemoveDelay")
            return []

        # CRITICAL: Stop youngest running nodes (limited by actual running nodes)
        nodes_to_stop = min(
            self.metrics.get("running_nodes", 0),
            removal_capacity
        )

        for i in range(nodes_to_stop):
            actions.append(
                Action(
                    type=ActionType.STOP_NODE,
                    node_id=None,  # Executor will query for youngest running
                    priority=70,
                    reason=f"stop node ({i+1}/{nodes_to_stop})",
                )
            )

    return actions
```

**Add helper method:**
```python
def _get_current_operations(self) -> int:
    """Get total number of current concurrent operations.

    Returns:
        Count of nodes in transitional states (upgrading, restarting, removing)
    """
    return (
        self.metrics.get("upgrading_nodes", 0)
        + self.metrics.get("restarting_nodes", 0)
        + self.metrics.get("removing_nodes", 0)
    )
```

### Phase 4: Executor Updates
**File**: `src/wnm/executor.py`

The executor's `execute()` method already handles multiple actions. We need to ensure that when executing multiple actions of the same type, each action selects a **different node**.

**Problem:** Current implementation queries for "oldest/youngest" node each time, which could select the same node repeatedly.

**Solution:** Track selected node IDs within a single execution cycle and exclude them from subsequent queries.

**Update `execute()` method:**
```python
def execute(
    self,
    actions: List[Action],
    machine_config: Dict[str, Any],
    metrics: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute a list of actions.

    Args:
        actions: List of Action objects to execute
        machine_config: Machine configuration dictionary
        metrics: Current system metrics
        dry_run: If True, log actions without executing them

    Returns:
        Dictionary with execution status and results
    """
    # Store machine_config for use in _get_process_manager
    self.machine_config = machine_config

    if not actions:
        return {"status": "no-actions", "results": []}

    results = []
    selected_node_ids = []  # Track nodes selected in this cycle

    for action in actions:
        logging.info(
            f"Executing: {action.type.value} (priority={action.priority}, reason={action.reason})"
        )

        try:
            result = self._execute_action(
                action, machine_config, metrics, dry_run, selected_node_ids
            )
            results.append(result)

            # Track selected node ID if available
            if "node_id" in result and result["node_id"]:
                selected_node_ids.append(result["node_id"])

        except Exception as e:
            logging.error(f"Failed to execute {action.type.value}: {e}")
            results.append(
                {"action": action.type.value, "success": False, "error": str(e)}
            )

    # Return status from the first (highest priority) action
    if results:
        return results[0]
    return {"status": "no-results"}
```

**Update `_execute_action()` signature:**
```python
def _execute_action(
    self,
    action: Action,
    machine_config: Dict[str, Any],
    metrics: Dict[str, Any],
    dry_run: bool,
    exclude_node_ids: List[int] = [],
) -> Dict[str, Any]:
```

**Update individual execution methods to accept and use `exclude_node_ids`:**

Example for `_execute_upgrade_node()`:
```python
def _execute_upgrade_node(
    self, metrics: Dict[str, Any], dry_run: bool, exclude_node_ids: List[int] = []
) -> Dict[str, Any]:
    """Execute node upgrade (oldest running node with outdated version).

    Args:
        metrics: Current system metrics
        dry_run: If True, log without executing
        exclude_node_ids: List of node IDs already selected in this cycle
    """
    query = (
        select(Node)
        .where(Node.status == RUNNING)
        .where(Node.version != metrics["antnode_version"])
        .order_by(Node.age.asc())
    )

    # Exclude already-selected nodes
    if exclude_node_ids:
        query = query.where(~Node.id.in_(exclude_node_ids))

    with self.S() as session:
        oldest = session.execute(query).first()

    if oldest:
        node = oldest[0]
        if dry_run:
            logging.warning(f"DRYRUN: Upgrade oldest node {node.id}")
            return {"status": "upgrading-node", "node_id": node.id}
        else:
            # ... rest of upgrade logic
            return {"status": "upgrading-node", "node_id": node.id}
    else:
        return {"status": "no-nodes-to-upgrade"}
```

Similar updates needed for:
- `_execute_start_node()` - exclude already-selected stopped nodes
- `_execute_remove_node()` - exclude already-selected nodes for removal
- `_execute_stop_node()` - exclude already-selected nodes to stop

### Phase 5: Database Migration
**Create new Alembic migration**

```bash
cd src/wnm
alembic revision -m "add_max_concurrent_operations"
```

**Migration file** (`alembic/versions/XXXX_add_max_concurrent_operations.py`):
```python
"""add_max_concurrent_operations

Revision ID: XXXX
Revises: YYYY
Create Date: 2025-XX-XX

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'XXXX'
down_revision = 'YYYY'  # Use the latest revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add max_concurrent_operations column with default value of 4
    op.add_column('machine', sa.Column('max_concurrent_operations', sa.Integer(), nullable=False, server_default='4'))


def downgrade() -> None:
    op.drop_column('machine', 'max_concurrent_operations')
```

### Phase 6: Documentation
**Files to update:**
1. `CLAUDE.md` - Add concurrency configuration section
2. `README.md` - Add examples of concurrent operations configuration

**Example documentation section for CLAUDE.md:**

```markdown
## Concurrent Operations

WNM supports running multiple node operations simultaneously to better utilize powerful hardware.

### Configuration Parameters

**Per-Operation Limits:**
- `--max_concurrent_upgrades` (default: 1): Maximum nodes upgrading simultaneously
- `--max_concurrent_starts` (default: 2): Maximum nodes starting/restarting simultaneously
- `--max_concurrent_removals` (default: 1): Maximum nodes being removed simultaneously

**Global Limit:**
- `--max_concurrent_operations` (default: 4): Total concurrent operations across all types

The effective limit is MIN(per_operation_limit, remaining_global_capacity).

### Examples

**Conservative (default):**
```bash
wnm --max_concurrent_upgrades 1 \
    --max_concurrent_starts 2 \
    --max_concurrent_operations 4
```

**Aggressive (powerful machine with 50+ nodes):**
```bash
wnm --max_concurrent_upgrades 4 \
    --max_concurrent_starts 4 \
    --max_concurrent_removals 2 \
    --max_concurrent_operations 8
```

**Very aggressive (100+ nodes, high-end server):**
```bash
wnm --max_concurrent_upgrades 10 \
    --max_concurrent_starts 10 \
    --max_concurrent_removals 5 \
    --max_concurrent_operations 20
```

**Database configuration (persistent):**
```bash
# Set configuration in database
sqlite3 colony.db "UPDATE machine SET
  max_concurrent_upgrades = 4,
  max_concurrent_starts = 4,
  max_concurrent_removals = 2,
  max_concurrent_operations = 8
  WHERE id = 1;"
```

### Behavior

WNM will **aggressively scale to capacity** each cycle:
- If upgrade limit is 4 and 2 nodes are upgrading, WNM will start 2 more upgrades immediately
- Operations respect both per-type limits AND global limit
- Dead node removals always take priority and ignore limits
- Each action selects a different node (no duplicate operations on same node)

### Capacity Constraints

Operations are limited by actual node availability:
- **Upgrades**: Limited by nodes needing upgrade
- **Starts**: Limited by stopped nodes available
- **Adds**: Limited by node cap - total nodes
- **Removes**: Limited by stopped/running nodes available

Example: If `max_concurrent_starts=4` but only 2 stopped nodes exist, WNM will:
1. Start 2 stopped nodes
2. Add 2 new nodes (if under node cap)
```

### Phase 7: Testing

**Test cases to verify:**

1. **Basic concurrency**: Multiple upgrades execute simultaneously
   - Setup: 10 nodes, all need upgrade, `max_concurrent_upgrades=4`
   - Expected: 4 upgrades start in one cycle

2. **Global limit**: Can't exceed `max_concurrent_operations` total
   - Setup: `max_concurrent_operations=4`, `max_concurrent_upgrades=10`
   - Expected: Only 4 total operations at once

3. **Per-type limits**: Can't exceed individual operation limits
   - Setup: `max_concurrent_upgrades=2`, `max_concurrent_operations=10`
   - Expected: Only 2 upgrades at once (even with global headroom)

4. **Aggressive scaling**: Jumps to capacity in one cycle
   - Setup: 0 operations in progress, capacity for 4
   - Expected: 4 operations start immediately

5. **Mixed operations**: Upgrades + starts respect both limits
   - Setup: `max_concurrent_operations=6`, 2 upgrading, 0 starting, capacity for 4 starts
   - Expected: Can start 4 nodes (6 global - 2 current = 4 available)

6. **Node selection**: Each action selects a different node (no duplicates)
   - Setup: 3 upgrade actions planned
   - Expected: 3 different nodes selected for upgrade

7. **Availability constraint**: Respects actual node counts
   - Setup: 1 stopped node, `max_concurrent_starts=4`
   - Expected: 1 start action, 3 add actions (if under cap)

8. **Backward compatibility**: Default limits (1/2/1/4) behave conservatively
   - Setup: Fresh install with defaults
   - Expected: Max 1 upgrade, 2 starts, 1 removal at a time

**Manual testing commands:**
```bash
# Initialize with high concurrency limits
wnm --init --rewards_address 0x00455d78f850b0358E8cea5be24d415E01E107CF \
    --max_concurrent_upgrades 4 \
    --max_concurrent_starts 4 \
    --max_concurrent_removals 2 \
    --max_concurrent_operations 8

# Force add 10 nodes
wnm --force_action add --count 10

# Wait for nodes to start, then trigger upgrades
# (Mock outdated version by manually setting node.version in DB)
sqlite3 colony.db "UPDATE node SET version = '0.0.1';"

# Run WNM - should upgrade 4 nodes at once
wnm --dry_run --show_decisions

# Check status
wnm --report node-status-details

# Test mixed operations: stop 5 nodes, then run WNM
wnm --force_action stop --count 5
wnm --dry_run --show_decisions  # Should plan to start 4 at once

# Test global limit
sqlite3 colony.db "UPDATE machine SET max_concurrent_operations = 3 WHERE id = 1;"
wnm --dry_run --show_decisions  # Should respect global limit of 3
```

## Implementation Checklist

### Phase 1: Database Schema
- [ ] Update Machine model with `max_concurrent_operations` field (models.py:~95)
- [ ] Add `max_concurrent_operations` parameter to Machine.__init__() (models.py:~163)
- [ ] Add `max_concurrent_operations` to Machine.__json__() (models.py:~271)

### Phase 2: Configuration
- [ ] Add `--max_concurrent_upgrades` flag to config.py
- [ ] Add `--max_concurrent_starts` flag to config.py
- [ ] Add `--max_concurrent_removals` flag to config.py
- [ ] Add `--max_concurrent_operations` flag to config.py
- [ ] Add concurrency params to config_updates dictionary

### Phase 3: Decision Engine
- [ ] Add `_get_current_operations()` helper method
- [ ] Update plan_actions() to check capacity instead of blocking
- [ ] Update _plan_upgrades() to return multiple actions with availability check
- [ ] Update _plan_node_additions() to return multiple actions with availability check
- [ ] Update _plan_resource_removal() to return multiple actions with availability check

### Phase 4: Executor
- [ ] Update execute() to track selected_node_ids
- [ ] Update _execute_action() to accept exclude_node_ids parameter
- [ ] Update _execute_upgrade_node() to accept and use exclude_node_ids
- [ ] Update _execute_start_node() to accept and use exclude_node_ids
- [ ] Update _execute_remove_node() to accept and use exclude_node_ids
- [ ] Update _execute_stop_node() to accept and use exclude_node_ids
- [ ] Update all action executors to return node_id in result dict

### Phase 5: Database Migration
- [ ] Create Alembic migration for max_concurrent_operations
- [ ] Test migration on test database
- [ ] Test downgrade migration

### Phase 6: Documentation
- [ ] Update CLAUDE.md with concurrency configuration section
- [ ] Add examples to CLAUDE.md
- [ ] Update README.md with concurrency examples (if applicable)

### Phase 7: Testing
- [ ] Write unit test for basic concurrency
- [ ] Write unit test for global limit enforcement
- [ ] Write unit test for per-type limit enforcement
- [ ] Write unit test for aggressive scaling
- [ ] Write unit test for mixed operations
- [ ] Write unit test for node selection (no duplicates)
- [ ] Write unit test for availability constraints
- [ ] Write unit test for backward compatibility
- [ ] Manual testing with various concurrency limits
- [ ] Performance testing with high concurrency on real hardware

## Notes

- Executor already supports multiple actions via forced commands (e.g., `--count` parameter)
- Database schema already has per-operation limits; only need to add global limit
- Migration must handle existing databases without breaking them
- Default values maintain backward compatibility (conservative operation)
- **Critical:** Always respect actual node availability to prevent planning impossible actions

## Example Scenarios

### Scenario 1: Aggressive Upgrade
**Config**: `max_concurrent_upgrades=4`, `max_concurrent_operations=8`
**State**: 10 nodes running, 8 need upgrade, 0 currently upgrading
**Result**: Start 4 upgrades in one cycle (jump to capacity)

### Scenario 2: Mixed Operations
**Config**: `max_concurrent_upgrades=4`, `max_concurrent_starts=4`, `max_concurrent_operations=6`
**State**: 2 nodes upgrading, 0 starting, 5 stopped nodes
**Result**: Can start 4 nodes (6 global - 2 current = 4 available, min with start limit 4)

### Scenario 3: At Global Capacity
**Config**: `max_concurrent_operations=4`
**State**: 3 nodes upgrading, 1 node restarting
**Result**: No new operations, wait for existing operations to complete (survey nodes)

### Scenario 4: Availability Constraint (CRITICAL)
**Config**: `max_concurrent_starts=4`, `max_concurrent_operations=8`
**State**: 1 stopped node, 10 total nodes, node_cap=50
**Result**: Start 1 stopped node + Add 3 new nodes = 4 total operations

### Scenario 5: Limited Availability
**Config**: `max_concurrent_upgrades=4`
**State**: Only 2 nodes need upgrade
**Result**: Start 2 upgrades (limited by actual nodes needing upgrade, not capacity)
