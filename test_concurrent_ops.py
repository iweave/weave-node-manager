#!/usr/bin/env python3
"""Quick test of concurrent operations functionality."""

from wnm.decision_engine import DecisionEngine
from wnm.actions import ActionType


def test_concurrent_upgrades():
    """Test that decision engine returns multiple upgrade actions."""
    # Mock machine config with high concurrency limits
    config = {
        "cpu_less_than": 70,
        "mem_less_than": 70,
        "hd_less_than": 70,
        "cpu_remove": 80,
        "mem_remove": 80,
        "hd_remove": 80,
        "netio_read_less_than": 0,
        "netio_read_remove": 0,
        "netio_write_less_than": 0,
        "netio_write_remove": 0,
        "hdio_read_less_than": 0,
        "hdio_read_remove": 0,
        "hdio_write_less_than": 0,
        "hdio_write_remove": 0,
        "desired_load_average": 10,
        "max_load_average_allowed": 20,
        "node_cap": 50,
        "last_stopped_at": 0,
        "max_concurrent_upgrades": 4,
        "max_concurrent_starts": 4,
        "max_concurrent_removals": 2,
        "max_concurrent_operations": 8,
    }

    # Mock metrics with nodes needing upgrade
    metrics = {
        "system_start": 0,
        "dead_nodes": 0,
        "upgrading_nodes": 0,  # No current upgrades
        "restarting_nodes": 0,
        "removing_nodes": 0,
        "migrating_nodes": 0,
        "running_nodes": 10,
        "stopped_nodes": 0,
        "total_nodes": 10,
        "nodes_to_upgrade": 8,  # 8 nodes need upgrade
        "antnode_version": "1.0.0",
        "queen_node_version": "1.0.0",
        "used_cpu_percent": 50,
        "used_mem_percent": 50,
        "used_hd_percent": 50,
        "load_average_1": 5,
        "load_average_5": 5,
        "load_average_15": 5,
        "netio_read_bytes": 0,
        "netio_write_bytes": 0,
        "hdio_read_bytes": 0,
        "hdio_write_bytes": 0,
    }

    engine = DecisionEngine(config, metrics)
    actions = engine.plan_actions()

    print(f"✓ DecisionEngine created successfully")
    print(f"✓ Planned {len(actions)} actions")

    # Should plan 4 upgrade actions (limited by max_concurrent_upgrades)
    assert len(actions) == 4, f"Expected 4 actions, got {len(actions)}"
    assert all(a.type == ActionType.UPGRADE_NODE for a in actions), "All actions should be upgrades"

    print(f"✓ Correctly planned 4 concurrent upgrades (limited by max_concurrent_upgrades=4)")

    for i, action in enumerate(actions):
        print(f"  Action {i+1}: {action.type.value} - {action.reason}")


def test_concurrent_starts():
    """Test that decision engine returns multiple start actions."""
    config = {
        "cpu_less_than": 70,
        "mem_less_than": 70,
        "hd_less_than": 70,
        "cpu_remove": 80,
        "mem_remove": 80,
        "hd_remove": 80,
        "netio_read_less_than": 0,
        "netio_read_remove": 0,
        "netio_write_less_than": 0,
        "netio_write_remove": 0,
        "hdio_read_less_than": 0,
        "hdio_read_remove": 0,
        "hdio_write_less_than": 0,
        "hdio_write_remove": 0,
        "desired_load_average": 10,
        "max_load_average_allowed": 20,
        "node_cap": 50,
        "last_stopped_at": 0,
        "max_concurrent_upgrades": 4,
        "max_concurrent_starts": 4,
        "max_concurrent_removals": 2,
        "max_concurrent_operations": 8,
    }

    # Mock metrics with stopped nodes
    metrics = {
        "system_start": 0,
        "dead_nodes": 0,
        "upgrading_nodes": 0,
        "restarting_nodes": 0,
        "removing_nodes": 0,
        "migrating_nodes": 0,
        "running_nodes": 5,
        "stopped_nodes": 3,  # 3 stopped nodes
        "total_nodes": 8,
        "nodes_to_upgrade": 0,
        "antnode_version": "1.0.0",
        "queen_node_version": "1.0.0",
        "used_cpu_percent": 50,
        "used_mem_percent": 50,
        "used_hd_percent": 50,
        "load_average_1": 5,
        "load_average_5": 5,
        "load_average_15": 5,
        "netio_read_bytes": 0,
        "netio_write_bytes": 0,
        "hdio_read_bytes": 0,
        "hdio_write_bytes": 0,
    }

    engine = DecisionEngine(config, metrics)
    actions = engine.plan_actions()

    print(f"\n✓ Planned {len(actions)} actions for starts")

    # Should plan 3 start actions (limited by stopped_nodes=3) + 1 add action
    assert len(actions) == 4, f"Expected 4 actions (3 starts + 1 add), got {len(actions)}"

    start_actions = [a for a in actions if a.type == ActionType.START_NODE]
    add_actions = [a for a in actions if a.type == ActionType.ADD_NODE]

    assert len(start_actions) == 3, f"Expected 3 start actions, got {len(start_actions)}"
    assert len(add_actions) == 1, f"Expected 1 add action, got {len(add_actions)}"

    print(f"✓ Correctly planned 3 starts + 1 add (respecting availability)")

    for i, action in enumerate(actions):
        print(f"  Action {i+1}: {action.type.value} - {action.reason}")


def test_global_capacity_limit():
    """Test that global capacity limit is respected."""
    config = {
        "cpu_less_than": 70,
        "mem_less_than": 70,
        "hd_less_than": 70,
        "cpu_remove": 80,
        "mem_remove": 80,
        "hd_remove": 80,
        "netio_read_less_than": 0,
        "netio_read_remove": 0,
        "netio_write_less_than": 0,
        "netio_write_remove": 0,
        "hdio_read_less_than": 0,
        "hdio_read_remove": 0,
        "hdio_write_less_than": 0,
        "hdio_write_remove": 0,
        "desired_load_average": 10,
        "max_load_average_allowed": 20,
        "node_cap": 50,
        "last_stopped_at": 0,
        "max_concurrent_upgrades": 10,  # High per-type limit
        "max_concurrent_starts": 10,
        "max_concurrent_removals": 10,
        "max_concurrent_operations": 3,  # Low global limit
    }

    # Mock metrics at global capacity
    metrics = {
        "system_start": 0,
        "dead_nodes": 0,
        "upgrading_nodes": 2,  # Already 2 upgrading
        "restarting_nodes": 1,  # Already 1 starting
        "removing_nodes": 0,
        "migrating_nodes": 0,
        "running_nodes": 10,
        "stopped_nodes": 5,
        "total_nodes": 15,
        "nodes_to_upgrade": 8,
        "antnode_version": "1.0.0",
        "queen_node_version": "1.0.0",
        "used_cpu_percent": 50,
        "used_mem_percent": 50,
        "used_hd_percent": 50,
        "load_average_1": 5,
        "load_average_5": 5,
        "load_average_15": 5,
        "netio_read_bytes": 0,
        "netio_write_bytes": 0,
        "hdio_read_bytes": 0,
        "hdio_write_bytes": 0,
    }

    engine = DecisionEngine(config, metrics)
    actions = engine.plan_actions()

    print(f"\n✓ Planned {len(actions)} actions with global limit")

    # Should return SURVEY_NODES because at global capacity (2+1=3, limit=3)
    assert len(actions) == 1, f"Expected 1 action, got {len(actions)}"
    assert actions[0].type == ActionType.SURVEY_NODES, f"Expected SURVEY_NODES, got {actions[0].type}"
    assert "global capacity" in actions[0].reason, f"Reason should mention global capacity"

    print(f"✓ Correctly blocked at global capacity (3/3 operations)")
    print(f"  Action: {actions[0].type.value} - {actions[0].reason}")


if __name__ == "__main__":
    print("Testing concurrent operations functionality...\n")
    test_concurrent_upgrades()
    test_concurrent_starts()
    test_global_capacity_limit()
    print("\n✅ All tests passed!")