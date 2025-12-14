"""Tests for DecisionEngine and ActionExecutor classes.

These tests verify the new decision engine's ability to plan actions
and the executor's ability to carry them out.
"""

import pytest
from unittest.mock import MagicMock, patch

from wnm.actions import Action, ActionType
from wnm.decision_engine import DecisionEngine


class TestDecisionEngineFeatures:
    """Test feature computation in DecisionEngine"""

    def test_compute_features_allow_cpu(self):
        """Test that CPU threshold feature is computed correctly"""
        config = {"cpu_less_than": 70, "cpu_remove": 85}
        metrics = {
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
            "total_nodes": 5,
        }
        # Add required config keys
        config.update({
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        })

        engine = DecisionEngine(config, metrics)
        features = engine.get_features()

        assert features["allow_cpu"] is True
        assert features["remove_cpu"] is False

    def test_compute_features_remove_cpu(self):
        """Test that CPU removal feature triggers correctly"""
        config = {
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "used_cpu_percent": 90,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        features = engine.get_features()

        assert features["allow_cpu"] is False
        assert features["remove_cpu"] is True
        assert features["remove"] is True

    def test_compute_features_load_allow(self):
        """Test load average allow feature"""
        config = {
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        features = engine.get_features()

        assert features["load_allow"] is True
        assert features["load_not_allow"] is False

    def test_compute_features_add_new_node(self):
        """Test add_new_node feature computation"""
        config = {
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
            "upgrading_nodes": 0,
            "restarting_nodes": 0,
            "migrating_nodes": 0,
            "removing_nodes": 0,
        }

        engine = DecisionEngine(config, metrics)
        features = engine.get_features()

        assert features["add_new_node"] is True


class TestDecisionEnginePlanning:
    """Test action planning in DecisionEngine"""

    def test_plan_resurvey_on_reboot(self):
        """Test that system reboot triggers resurvey"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "system_start": 2000,  # System rebooted after last_stopped_at
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
            "dead_nodes": 0,
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.RESURVEY_NODES
        assert actions[0].priority == 100
        assert "rebooted" in actions[0].reason.lower()

    def test_plan_resurvey_on_init_with_import(self):
        """Test that system init with import triggers resurvey"""
        config = {
            "last_stopped_at": 0,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "system_start": 2000,  # System start > last_stopped_at
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 0,
            "total_nodes": 0,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
            "dead_nodes": 0,
        }

        # Test with --init and --import (should survey)
        engine = DecisionEngine(config, metrics, is_init=True, should_survey_init=True)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.RESURVEY_NODES
        assert actions[0].priority == 100
        assert "initialized" in actions[0].reason.lower()

    def test_plan_survey_on_init_without_import(self):
        """Test that system init without import returns survey action"""
        config = {
            "last_stopped_at": 0,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "system_start": 2000,  # System start > last_stopped_at
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 0,
            "total_nodes": 0,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
            "dead_nodes": 0,
        }

        # Test with --init but no import (should NOT resurvey, just idle survey)
        engine = DecisionEngine(config, metrics, is_init=True, should_survey_init=False)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.SURVEY_NODES
        assert actions[0].priority == 0
        assert "initialized" in actions[0].reason.lower()

    def test_plan_dead_node_removal(self):
        """Test that dead nodes are planned for removal"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
        }
        metrics = {
            "system_start": 500,  # No reboot
            "dead_nodes": 2,
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.REMOVE_NODE
        assert actions[0].priority == 90
        assert "dead" in actions[0].reason.lower()

    def test_plan_wait_for_restarting(self):
        """Test that restarting nodes cause wait"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
            "max_concurrent_upgrades": 1,
            "max_concurrent_starts": 1,
            "max_concurrent_removals": 1,
            "max_concurrent_operations": 1,
        }
        metrics = {
            "system_start": 500,
            "dead_nodes": 0,
            "restarting_nodes": 1,
            "upgrading_nodes": 0,
            "removing_nodes": 0,
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.SURVEY_NODES
        # With 1 restarting node and max_concurrent_operations=1, engine correctly reports at capacity
        assert "capacity" in actions[0].reason.lower()

    def test_plan_remove_node_on_resource_pressure(self):
        """Test node removal/stop under resource pressure"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
            "max_concurrent_upgrades": 1,
            "max_concurrent_starts": 1,
            "max_concurrent_removals": 1,
            "max_concurrent_operations": 1,
        }
        metrics = {
            "system_start": 500,
            "dead_nodes": 0,
            "restarting_nodes": 0,
            "upgrading_nodes": 0,
            "used_cpu_percent": 95,  # Over cpu_remove threshold
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "stopped_nodes": 0,
            "removing_nodes": 0,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        # When resource pressure exists but not critical (no HD pressure, under cap),
        # the engine chooses to STOP a node rather than REMOVE it
        assert actions[0].type in [ActionType.REMOVE_NODE, ActionType.STOP_NODE]
        assert actions[0].priority >= 70

    def test_plan_upgrade_node(self):
        """Test upgrade planning when conditions are right"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
            "max_concurrent_upgrades": 1,
            "max_concurrent_starts": 1,
            "max_concurrent_removals": 1,
            "max_concurrent_operations": 1,
        }
        metrics = {
            "system_start": 500,
            "dead_nodes": 0,
            "restarting_nodes": 0,
            "upgrading_nodes": 0,
            "removing_nodes": 0,
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 2,
            "antnode_version": "1.2.0",
            "queen_node_version": "1.1.0",  # Current version is newer
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.UPGRADE_NODE
        assert actions[0].priority == 60

    def test_plan_add_node(self):
        """Test add node planning when resources allow"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
            "max_concurrent_upgrades": 1,
            "max_concurrent_starts": 1,
            "max_concurrent_removals": 1,
            "max_concurrent_operations": 1,
        }
        metrics = {
            "system_start": 500,
            "dead_nodes": 0,
            "restarting_nodes": 0,
            "upgrading_nodes": 0,
            "migrating_nodes": 0,
            "removing_nodes": 0,
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 5,
            "total_nodes": 5,
            "stopped_nodes": 0,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.ADD_NODE
        assert actions[0].priority == 40

    def test_plan_idle_survey(self):
        """Test idle survey when no actions needed"""
        config = {
            "last_stopped_at": 1000,
            "cpu_less_than": 70,
            "cpu_remove": 85,
            "mem_less_than": 70,
            "mem_remove": 85,
            "hd_less_than": 80,
            "hd_remove": 90,
            "node_cap": 10,
            "netio_read_less_than": 0,
            "netio_read_remove": 0,
            "netio_write_less_than": 0,
            "netio_write_remove": 0,
            "hdio_read_less_than": 0,
            "hdio_read_remove": 0,
            "hdio_write_less_than": 0,
            "hdio_write_remove": 0,
            "desired_load_average": 5.0,
            "max_load_average_allowed": 10.0,
            "max_concurrent_upgrades": 1,
            "max_concurrent_starts": 1,
            "max_concurrent_removals": 1,
            "max_concurrent_operations": 1,
        }
        metrics = {
            "system_start": 500,
            "dead_nodes": 0,
            "restarting_nodes": 0,
            "upgrading_nodes": 0,
            "migrating_nodes": 0,
            "removing_nodes": 0,
            "used_cpu_percent": 60,
            "used_mem_percent": 60,
            "used_hd_percent": 70,
            "running_nodes": 10,  # At capacity
            "total_nodes": 10,
            "load_average_1": 3.0,
            "load_average_5": 3.5,
            "load_average_15": 4.0,
            "nodes_to_upgrade": 0,
        }

        engine = DecisionEngine(config, metrics)
        actions = engine.plan_actions()

        assert len(actions) == 1
        assert actions[0].type == ActionType.SURVEY_NODES
        assert "idle" in actions[0].reason.lower()


class TestDecisionEngineConcurrency:
    """Test concurrent operations in DecisionEngine"""

    def test_concurrent_upgrades(self):
        """Test that decision engine returns multiple upgrade actions"""
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

        metrics = {
            "system_start": 0,
            "dead_nodes": 0,
            "upgrading_nodes": 0,
            "restarting_nodes": 0,
            "removing_nodes": 0,
            "migrating_nodes": 0,
            "running_nodes": 10,
            "stopped_nodes": 0,
            "total_nodes": 10,
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

        # Should plan 4 upgrade actions (limited by max_concurrent_upgrades)
        assert len(actions) == 4
        assert all(a.type == ActionType.UPGRADE_NODE for a in actions)

    def test_concurrent_starts(self):
        """Test that decision engine returns multiple start actions"""
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

        metrics = {
            "system_start": 0,
            "dead_nodes": 0,
            "upgrading_nodes": 0,
            "restarting_nodes": 0,
            "removing_nodes": 0,
            "migrating_nodes": 0,
            "running_nodes": 5,
            "stopped_nodes": 3,
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

        # Should plan 3 start actions (limited by stopped_nodes=3) + 1 add action
        assert len(actions) == 4

        start_actions = [a for a in actions if a.type == ActionType.START_NODE]
        add_actions = [a for a in actions if a.type == ActionType.ADD_NODE]

        assert len(start_actions) == 3
        assert len(add_actions) == 1

    def test_global_capacity_limit(self):
        """Test that global capacity limit is respected"""
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
            "max_concurrent_upgrades": 10,
            "max_concurrent_starts": 10,
            "max_concurrent_removals": 10,
            "max_concurrent_operations": 3,
        }

        metrics = {
            "system_start": 0,
            "dead_nodes": 0,
            "upgrading_nodes": 2,
            "restarting_nodes": 1,
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

        # Should return SURVEY_NODES because at global capacity (2+1=3, limit=3)
        assert len(actions) == 1
        assert actions[0].type == ActionType.SURVEY_NODES
        assert "global capacity" in actions[0].reason or "capacity" in actions[0].reason


class TestActionExecutor:
    """Test ActionExecutor execution logic"""

    @patch("wnm.executor.update_nodes")
    def test_execute_resurvey_reboot(self, mock_update_nodes):
        """Test executing resurvey action for system reboot"""
        from wnm.executor import ActionExecutor

        S = MagicMock()
        executor = ActionExecutor(S)

        actions = [Action(type=ActionType.RESURVEY_NODES, priority=100, reason="system rebooted")]
        config = {"last_stopped_at": 1000}
        metrics = {"system_start": 2000}

        result = executor.execute(actions, config, metrics, dry_run=False)

        mock_update_nodes.assert_called_once()
        assert result["status"] == "system-rebooted"

    @patch("wnm.executor.update_nodes")
    def test_execute_resurvey_init(self, mock_update_nodes):
        """Test executing resurvey action for system initialization"""
        from wnm.executor import ActionExecutor

        S = MagicMock()
        executor = ActionExecutor(S)

        actions = [Action(type=ActionType.RESURVEY_NODES, priority=100, reason="system initialized")]
        config = {"last_stopped_at": 0}
        metrics = {"system_start": 2000}

        result = executor.execute(actions, config, metrics, dry_run=False)

        mock_update_nodes.assert_called_once()
        assert result["status"] == "system-initialized"

    def test_execute_dry_run(self):
        """Test that dry_run prevents actual execution"""
        from wnm.executor import ActionExecutor

        S = MagicMock()
        executor = ActionExecutor(S)

        actions = [Action(type=ActionType.ADD_NODE, priority=40, reason="test")]
        config = {}
        metrics = {}

        # Should not raise any errors in dry_run mode
        result = executor.execute(actions, config, metrics, dry_run=True)
        assert result is not None

    def test_execute_empty_actions(self):
        """Test executing empty action list"""
        from wnm.executor import ActionExecutor

        S = MagicMock()
        executor = ActionExecutor(S)

        result = executor.execute([], {}, {}, dry_run=False)

        assert result["status"] == "no-actions"
        assert result["results"] == []
