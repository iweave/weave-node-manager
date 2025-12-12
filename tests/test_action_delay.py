"""Tests for action delay functionality.

These tests verify the action_delay feature that controls delays between
individual node operations when processing multiple nodes.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from wnm.executor import ActionExecutor
from wnm.models import Machine, Node
from wnm.common import RUNNING, STOPPED
from wnm.process_managers.base import NodeProcess


class TestMachineActionDelayField:
    """Test action_delay field in Machine model"""

    def test_machine_has_action_delay_field(self, db_session, sample_machine_config):
        """Test Machine model has action_delay field"""
        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        assert hasattr(machine, "action_delay")

    def test_action_delay_default_value(self, db_session, sample_machine_config):
        """Test action_delay defaults to 0"""
        # Don't specify action_delay in config
        sample_machine_config.pop("action_delay", None)

        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        assert machine.action_delay == 0

    def test_action_delay_custom_value(self, db_session, sample_machine_config):
        """Test action_delay can be set to custom value"""
        sample_machine_config["action_delay"] = 1500

        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        assert machine.action_delay == 1500

    def test_action_delay_in_json_serialization(self, db_session, sample_machine_config):
        """Test action_delay appears in JSON serialization"""
        sample_machine_config["action_delay"] = 2000

        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        json_data = machine.__json__()
        assert "action_delay" in json_data
        assert json_data["action_delay"] == 2000

    def test_action_delay_update(self, db_session, sample_machine_config):
        """Test updating action_delay value"""
        sample_machine_config["action_delay"] = 1000

        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        # Update the value
        machine.action_delay = 3000
        db_session.commit()

        # Verify it persisted
        db_session.refresh(machine)
        assert machine.action_delay == 3000


class TestActionDelayHelperMethod:
    """Test _get_action_delay_ms() helper method"""

    def test_get_action_delay_default(self, db_session):
        """Test getting default action delay (0ms)"""
        executor = ActionExecutor(lambda: db_session)

        machine_config = {"action_delay": 0}
        delay = executor._get_action_delay_ms(machine_config)

        assert delay == 0

    def test_get_action_delay_persistent(self, db_session):
        """Test getting persistent action_delay setting"""
        executor = ActionExecutor(lambda: db_session)

        machine_config = {"action_delay": 1500}
        delay = executor._get_action_delay_ms(machine_config)

        assert delay == 1500

    def test_get_action_delay_transient_override(self, db_session):
        """Test transient override takes precedence over persistent"""
        executor = ActionExecutor(lambda: db_session)

        machine_config = {
            "action_delay": 1000,
            "this_action_delay": 500
        }
        delay = executor._get_action_delay_ms(machine_config)

        assert delay == 500

    def test_get_action_delay_transient_none(self, db_session):
        """Test that None transient override falls back to persistent"""
        executor = ActionExecutor(lambda: db_session)

        machine_config = {
            "action_delay": 1000,
            "this_action_delay": None
        }
        delay = executor._get_action_delay_ms(machine_config)

        assert delay == 1000

    def test_get_action_delay_missing_keys(self, db_session):
        """Test getting delay when keys are missing"""
        executor = ActionExecutor(lambda: db_session)

        machine_config = {}
        delay = executor._get_action_delay_ms(machine_config)

        assert delay == 0


class TestActionDelayInForceAdd:
    """Test action delay in _force_add_node()"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_add_multiple_nodes_with_delay(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test adding multiple nodes with delay between operations"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 4)
        ]
        mock_get_manager.return_value = mock_manager

        # Set action delay to 1000ms (1 second)
        sample_machine_config["action_delay"] = 1000

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=3)

        assert result["status"] == "added-nodes"
        assert result["added_count"] == 3

        # Should sleep twice (between nodes 1-2 and 2-3, not before node 1)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.0)  # 1000ms = 1.0s

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_add_single_node_no_delay(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test adding single node doesn't sleep (no delay needed)"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.return_value = NodeProcess(node_id=1, pid=12345, status="RUNNING")
        mock_get_manager.return_value = mock_manager

        sample_machine_config["action_delay"] = 1000

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=1)

        assert result["status"] == "added-node"
        # No sleep for single node
        mock_sleep.assert_not_called()

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_add_nodes_zero_delay(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test adding multiple nodes with zero delay (no sleep)"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 4)
        ]
        mock_get_manager.return_value = mock_manager

        sample_machine_config["action_delay"] = 0

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=3)

        assert result["status"] == "added-nodes"
        assert result["added_count"] == 3
        # No sleep when delay is 0
        mock_sleep.assert_not_called()


class TestActionDelayInForceRemove:
    """Test action delay in _force_remove_node()"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("time.sleep")
    def test_remove_multiple_specific_nodes_with_delay(
        self, mock_sleep, mock_get_manager, db_session, multiple_nodes
    ):
        """Test removing multiple specific nodes with delay"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        # Set machine_config with delay
        executor.machine_config = {"action_delay": 2000}

        result = executor._force_remove_node("antnode0001,antnode0002,antnode0003", dry_run=False)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 3

        # Should sleep twice (between 3 nodes)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2.0)  # 2000ms = 2.0s

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("time.sleep")
    def test_remove_youngest_nodes_with_delay(
        self, mock_sleep, mock_get_manager, db_session, multiple_nodes
    ):
        """Test removing youngest nodes with delay (count parameter)"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 1500}

        result = executor._force_remove_node(None, dry_run=False, count=4)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 4

        # Should sleep 3 times (between 4 nodes)
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(1.5)  # 1500ms = 1.5s


class TestActionDelayInForceUpgrade:
    """Test action delay in _force_upgrade_node()"""

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    @patch("time.sleep")
    def test_upgrade_multiple_specific_nodes_with_delay(
        self, mock_sleep, mock_upgrade, db_session, multiple_nodes
    ):
        """Test upgrading multiple specific nodes with delay"""
        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 3000}
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node("antnode0001,antnode0002,antnode0003", metrics, dry_run=False)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 3

        # Should sleep twice (between 3 nodes)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(3.0)  # 3000ms = 3.0s

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    @patch("time.sleep")
    def test_upgrade_oldest_nodes_with_delay(
        self, mock_sleep, mock_upgrade, db_session, multiple_nodes
    ):
        """Test upgrading oldest nodes with delay (count parameter)"""
        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 500}
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node(None, metrics, dry_run=False, count=3)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 3

        # Should sleep 2 times (between 3 nodes)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.5)  # 500ms = 0.5s


class TestActionDelayInForceStop:
    """Test action delay in _force_stop_node()"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("time.sleep")
    def test_stop_multiple_specific_nodes_with_delay(
        self, mock_sleep, mock_get_manager, db_session, multiple_nodes
    ):
        """Test stopping multiple specific nodes with delay"""
        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 800}

        result = executor._force_stop_node("antnode0001,antnode0002", dry_run=False)

        assert result["status"] == "stopped-nodes"
        assert result["stopped_count"] == 2

        # Should sleep once (between 2 nodes)
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(0.8)  # 800ms = 0.8s

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("time.sleep")
    def test_stop_youngest_nodes_with_delay(
        self, mock_sleep, mock_get_manager, db_session, multiple_nodes
    ):
        """Test stopping youngest nodes with delay (count parameter)"""
        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 1200}

        result = executor._force_stop_node(None, dry_run=False, count=3)

        assert result["status"] == "stopped-nodes"
        assert result["stopped_count"] == 3

        # Should sleep 2 times (between 3 nodes)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.2)  # 1200ms = 1.2s


class TestActionDelayInForceStart:
    """Test action delay in _force_start_node()"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    @patch("time.sleep")
    def test_start_multiple_specific_nodes_with_delay(
        self, mock_sleep, mock_version, mock_get_manager, db_session, multiple_nodes
    ):
        """Test starting multiple specific nodes with delay"""
        # Stop nodes first
        multiple_nodes[0].status = STOPPED
        multiple_nodes[0].version = "0.4.6"
        multiple_nodes[1].status = STOPPED
        multiple_nodes[1].version = "0.4.6"
        multiple_nodes[2].status = STOPPED
        multiple_nodes[2].version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"
        mock_manager = MagicMock()
        mock_manager.start_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 2500}
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001,antnode0002,antnode0003", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 3

        # Should sleep twice (between 3 nodes)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2.5)  # 2500ms = 2.5s

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    @patch("time.sleep")
    def test_start_oldest_stopped_nodes_with_delay(
        self, mock_sleep, mock_version, mock_get_manager, db_session, multiple_nodes
    ):
        """Test starting oldest stopped nodes with delay (count parameter)"""
        # Stop some nodes
        for i in range(4):
            multiple_nodes[i].status = STOPPED
            multiple_nodes[i].version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"
        mock_manager = MagicMock()
        mock_manager.start_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 750}
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node(None, metrics, dry_run=False, count=3)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 3

        # Should sleep 2 times (between 3 nodes)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.75)  # 750ms = 0.75s


class TestTransientActionDelayOverride:
    """Test transient this_action_delay override"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_transient_override_takes_precedence(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test that this_action_delay overrides action_delay"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 3)
        ]
        mock_get_manager.return_value = mock_manager

        # Set both persistent and transient delays
        sample_machine_config["action_delay"] = 2000
        sample_machine_config["this_action_delay"] = 500  # This should be used

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=2)

        assert result["status"] == "added-nodes"
        assert result["added_count"] == 2

        # Should use transient delay of 500ms, not persistent 2000ms
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(0.5)  # 500ms = 0.5s

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_transient_none_uses_persistent(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test that None transient override falls back to persistent"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 3)
        ]
        mock_get_manager.return_value = mock_manager

        sample_machine_config["action_delay"] = 1500
        sample_machine_config["this_action_delay"] = None  # Falls back to persistent

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=2)

        assert result["status"] == "added-nodes"
        assert result["added_count"] == 2

        # Should use persistent delay of 1500ms
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(1.5)  # 1500ms = 1.5s


class TestActionDelayTimingAccuracy:
    """Test that delays are actually applied with correct timing"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    def test_actual_delay_timing(
        self, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test that delays are actually applied (integration-style test)"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 4)
        ]
        mock_get_manager.return_value = mock_manager

        # Set delay to 100ms (short for testing)
        sample_machine_config["action_delay"] = 100

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        start_time = time.time()
        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=3)
        elapsed_time = time.time() - start_time

        assert result["status"] == "added-nodes"
        assert result["added_count"] == 3

        # Should take at least 200ms (2 delays of 100ms each)
        # Allow some tolerance for test execution time
        assert elapsed_time >= 0.2, f"Expected at least 0.2s, got {elapsed_time}s"


class TestActionDelayLoggingMessages:
    """Test that action delays log appropriate messages"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    @patch("wnm.executor.logging")
    def test_delay_logs_message(
        self, mock_logging, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test that delay operations log informative messages"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 3)
        ]
        mock_get_manager.return_value = mock_manager

        sample_machine_config["action_delay"] = 1000

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=2)

        assert result["status"] == "added-nodes"

        # Verify logging was called with delay message
        # Check that info was called with a message containing delay information
        log_calls = [str(call) for call in mock_logging.info.call_args_list]
        delay_logs = [call for call in log_calls if "Action delay" in call or "waiting" in call]
        assert len(delay_logs) > 0, "Expected delay logging messages"


class TestActionDelayEdgeCases:
    """Test edge cases for action delay"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_very_small_delay(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test very small delay (1ms)"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 3)
        ]
        mock_get_manager.return_value = mock_manager

        sample_machine_config["action_delay"] = 1  # 1 millisecond

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=2)

        assert result["status"] == "added-nodes"
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(0.001)  # 1ms = 0.001s

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    @patch("time.sleep")
    def test_large_delay(
        self, mock_sleep, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test large delay (10 seconds)"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 3)
        ]
        mock_get_manager.return_value = mock_manager

        sample_machine_config["action_delay"] = 10000  # 10 seconds

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=2)

        assert result["status"] == "added-nodes"
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(10.0)  # 10000ms = 10.0s

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("time.sleep")
    def test_delay_with_failure_continues(
        self, mock_sleep, mock_get_manager, db_session, multiple_nodes
    ):
        """Test that delays continue even if some operations fail"""
        mock_manager = MagicMock()
        # First node succeeds, second fails, third succeeds
        mock_manager.remove_node.side_effect = [True, Exception("Test failure"), True]
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        executor.machine_config = {"action_delay": 500}

        # Try to remove 3 specific nodes
        result = executor._force_remove_node("antnode0001,antnode0002,antnode0003", dry_run=False)

        # Should still process all nodes even with failure
        assert result["removed_count"] == 2
        assert result["failed_count"] == 1

        # Should still sleep between operations
        assert mock_sleep.call_count == 2