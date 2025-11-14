"""Tests for forced action functionality in ActionExecutor.

These tests verify that forced actions bypass the decision engine and
execute node operations immediately without delays.
"""

import pytest
from unittest.mock import MagicMock, patch

from wnm.executor import ActionExecutor
from wnm.models import Node
from wnm.common import RUNNING, STOPPED, DISABLED, UPGRADING
from wnm.process_managers.base import NodeProcess


class TestNodeNameParsing:
    """Test node name parsing utilities"""

    def test_parse_node_name_valid(self, db_session):
        """Test parsing valid node names"""
        executor = ActionExecutor(lambda: db_session)

        assert executor._parse_node_name("antnode0001") == 1
        assert executor._parse_node_name("antnode0042") == 42
        assert executor._parse_node_name("antnode123") == 123
        assert executor._parse_node_name("antnode9999") == 9999

    def test_parse_node_name_invalid(self, db_session):
        """Test parsing invalid node names returns None"""
        executor = ActionExecutor(lambda: db_session)

        assert executor._parse_node_name("invalid") is None
        assert executor._parse_node_name("node0001") is None
        assert executor._parse_node_name("antnode") is None
        assert executor._parse_node_name("") is None

    def test_get_node_by_name_existing(self, db_session, node):
        """Test getting an existing node by name"""
        executor = ActionExecutor(lambda: db_session)

        # Update the node to have predictable name
        node.id = 1
        node.node_name = "0001"
        db_session.commit()

        result = executor._get_node_by_name("antnode0001")
        assert result is not None
        assert result.id == 1
        assert result.node_name == "0001"

    def test_get_node_by_name_nonexistent(self, db_session):
        """Test getting a non-existent node returns None"""
        executor = ActionExecutor(lambda: db_session)

        result = executor._get_node_by_name("antnode9999")
        assert result is None


class TestForcedAddAction:
    """Test forced add node action"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    def test_force_add_node_success(
        self, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test forced add action creates a new node"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        mock_manager.create_node.return_value = NodeProcess(node_id=1, pid=12345, status="RUNNING")
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        metrics = {
            "antnode_version": "0.4.6",
        }

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False)

        assert result["status"] == "added-node"
        mock_manager.create_node.assert_called_once()

    @patch("wnm.executor.get_process_manager")
    def test_force_add_node_dry_run(
        self, mock_get_manager, db_session, sample_machine_config
    ):
        """Test forced add action in dry-run mode"""
        executor = ActionExecutor(lambda: db_session)

        metrics = {
            "antnode_version": "0.4.6",
        }

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=True)

        assert result["status"] == "add-node"
        mock_get_manager.assert_not_called()


class TestForcedRemoveAction:
    """Test forced remove node action"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_remove_specific_node(
        self, mock_get_manager, db_session, node
    ):
        """Test forced remove of specific node"""
        node.id = 1
        node.node_name = "0001"
        db_session.commit()

        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_remove_node("antnode0001", dry_run=False)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 1
        assert "antnode0001" in result["removed_nodes"]
        mock_manager.remove_node.assert_called_once()

        # Verify node is removed from database
        remaining = db_session.query(Node).filter(Node.id == 1).first()
        assert remaining is None

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_remove_youngest_node_by_age(
        self, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced remove without service_name removes youngest node (highest age)"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_remove_node(None, dry_run=False)

        assert result["status"] == "removed-node"
        # Youngest node (highest age value) should be removed
        assert result["node"] == "0005"
        mock_manager.remove_node.assert_called_once()

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_remove_includes_disabled_nodes(
        self, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced remove can remove disabled nodes"""
        # Mark youngest node as disabled
        youngest = multiple_nodes[-1]
        youngest.status = DISABLED
        db_session.commit()

        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_remove_node(None, dry_run=False)

        # Should still remove 0005 even though it's DISABLED
        assert result["status"] == "removed-node"
        assert result["node"] == "0005"

    def test_force_remove_node_not_found(self, db_session):
        """Test forced remove of non-existent node"""
        executor = ActionExecutor(lambda: db_session)

        result = executor._force_remove_node("antnode9999", dry_run=False)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 0
        assert result["failed_count"] == 1
        assert result["failed_nodes"][0]["service"] == "antnode9999"
        assert "not found" in result["failed_nodes"][0]["error"]


class TestForcedUpgradeAction:
    """Test forced upgrade node action"""

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    def test_force_upgrade_specific_running_node(
        self, mock_upgrade, db_session, node
    ):
        """Test forced upgrade of specific running node"""
        node.id = 1
        node.node_name = "0001"
        node.status = RUNNING
        db_session.commit()

        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 1
        assert "antnode0001" in result["upgraded_nodes"]
        mock_upgrade.assert_called_once()

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    def test_force_upgrade_specific_stopped_node(
        self, mock_upgrade, db_session, node
    ):
        """Test forced upgrade works on stopped nodes"""
        node.id = 1
        node.node_name = "0001"
        node.status = STOPPED
        db_session.commit()

        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 1
        assert "antnode0001" in result["upgraded_nodes"]
        mock_upgrade.assert_called_once()

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    def test_force_upgrade_specific_disabled_node(
        self, mock_upgrade, db_session, node
    ):
        """Test forced upgrade works on disabled nodes"""
        node.id = 1
        node.node_name = "0001"
        node.status = DISABLED
        db_session.commit()

        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 1
        assert "antnode0001" in result["upgraded_nodes"]

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    def test_force_upgrade_oldest_running_node(
        self, mock_upgrade, db_session, multiple_nodes
    ):
        """Test forced upgrade without service_name upgrades oldest running node (lowest age)"""
        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node(None, metrics, dry_run=False)

        assert result["status"] == "upgraded-node"
        # Oldest node (lowest age value) should be upgraded
        assert result["node"] == "0001"

    def test_force_upgrade_no_running_nodes(self, db_session, multiple_nodes):
        """Test forced upgrade without service_name when no running nodes exist"""
        # Stop all nodes
        for node in multiple_nodes:
            node.status = STOPPED
        db_session.commit()

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node(None, metrics, dry_run=False)

        assert result["status"] == "error"
        assert "no running nodes" in result["message"].lower()


class TestForcedStopAction:
    """Test forced stop node action"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_stop_specific_node(self, mock_get_manager, db_session, node):
        """Test forced stop of specific node"""
        node.id = 1
        node.node_name = "0001"
        node.status = RUNNING
        db_session.commit()

        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_stop_node("antnode0001", dry_run=False)

        assert result["status"] == "stopped-nodes"
        assert result["stopped_count"] == 1
        assert "antnode0001" in result["stopped_nodes"]
        mock_manager.stop_node.assert_called_once()

        # Verify node status updated to STOPPED
        updated_node = db_session.query(Node).filter(Node.id == 1).first()
        assert updated_node.status == STOPPED

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_stop_disabled_node(self, mock_get_manager, db_session, node):
        """Test forced stop works on disabled nodes"""
        node.id = 1
        node.node_name = "0001"
        node.status = DISABLED
        db_session.commit()

        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_stop_node("antnode0001", dry_run=False)

        assert result["status"] == "stopped-nodes"
        assert result["stopped_count"] == 1
        assert "antnode0001" in result["stopped_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_stop_youngest_running_node(
        self, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced stop without service_name stops youngest running node (highest age)"""
        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_stop_node(None, dry_run=False)

        assert result["status"] == "stopped-node"
        # Youngest running node (highest age) should be stopped
        assert result["node"] == "0005"


class TestForcedStartAction:
    """Test forced start node action"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    def test_force_start_specific_stopped_node(
        self, mock_version, mock_get_manager, db_session, node
    ):
        """Test forced start of specific stopped node"""
        node.id = 1
        node.node_name = "0001"
        node.status = STOPPED
        node.version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"
        mock_manager = MagicMock()
        mock_manager.start_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 1
        assert "antnode0001" in result["started_nodes"]
        mock_manager.start_node.assert_called_once()

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    def test_force_start_specific_disabled_node(
        self, mock_version, mock_get_manager, db_session, node
    ):
        """Test forced start works on disabled nodes"""
        node.id = 1
        node.node_name = "0001"
        node.status = DISABLED
        node.version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"
        mock_manager = MagicMock()
        mock_manager.start_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 1
        assert "antnode0001" in result["started_nodes"]

    def test_force_start_already_running_node(self, db_session, node):
        """Test forced start of already running node returns error"""
        node.id = 1
        node.node_name = "0001"
        node.status = RUNNING
        db_session.commit()

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 0
        assert result["failed_count"] == 1
        assert result["failed_nodes"][0]["service"] == "antnode0001"
        assert "already running" in result["failed_nodes"][0]["error"]

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    @patch("wnm.executor.get_antnode_version")
    def test_force_start_with_upgrade(
        self, mock_version, mock_upgrade, db_session, node
    ):
        """Test forced start upgrades node if version is old"""
        node.id = 1
        node.node_name = "0001"
        node.status = STOPPED
        node.version = "0.4.5"
        db_session.commit()

        mock_version.return_value = "0.4.5"
        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["upgraded_count"] == 1
        assert "antnode0001" in result["upgraded_nodes"]
        mock_upgrade.assert_called_once()

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    def test_force_start_oldest_stopped_node(
        self, mock_version, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced start without service_name starts oldest stopped node (lowest age)"""
        # Stop some nodes and set their versions to match metrics
        multiple_nodes[0].status = STOPPED  # test001, age=1000000
        multiple_nodes[0].version = "0.4.6"
        multiple_nodes[2].status = STOPPED  # test003, age=1003000
        multiple_nodes[2].version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"
        mock_manager = MagicMock()
        mock_manager.start_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node(None, metrics, dry_run=False)

        assert result["status"] == "started-node"
        # Oldest stopped node (lowest age) should be started
        assert result["node"] == "0001"

    def test_force_start_no_stopped_nodes(self, db_session, multiple_nodes):
        """Test forced start without service_name when no stopped nodes exist"""
        # All nodes running
        for node in multiple_nodes:
            node.status = RUNNING
        db_session.commit()

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node(None, metrics, dry_run=False)

        assert result["status"] == "error"
        assert "no stopped nodes" in result["message"].lower()

    def test_force_start_node_not_found(self, db_session):
        """Test forced start of non-existent node"""
        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode9999", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 0
        assert result["failed_count"] == 1
        assert result["failed_nodes"][0]["service"] == "antnode9999"
        assert "not found" in result["failed_nodes"][0]["error"]

    @patch("wnm.executor.get_antnode_version")
    def test_force_start_dry_run(self, mock_version, db_session, node):
        """Test forced start in dry-run mode"""
        node.id = 1
        node.node_name = "0001"
        node.status = STOPPED
        node.version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001", metrics, dry_run=True)

        assert result["status"] == "start-dryrun"
        assert result["started_count"] == 1
        assert "antnode0001" in result["started_nodes"]


class TestForcedDisableAction:
    """Test forced disable node action"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_disable_running_node(self, mock_get_manager, db_session, node):
        """Test forced disable stops and disables a running node"""
        node.id = 1
        node.node_name = "0001"
        node.status = RUNNING
        db_session.commit()

        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_disable_node("antnode0001", dry_run=False)

        assert result["status"] == "disabled-nodes"
        assert result["disabled_count"] == 1
        assert "antnode0001" in result["disabled_nodes"]
        mock_manager.stop_node.assert_called_once()

        # Verify node status updated to DISABLED
        updated_node = db_session.query(Node).filter(Node.id == 1).first()
        assert updated_node.status == DISABLED

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_disable_stopped_node(self, mock_get_manager, db_session, node):
        """Test forced disable on already stopped node just sets status"""
        node.id = 1
        node.node_name = "0001"
        node.status = STOPPED
        db_session.commit()

        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_disable_node("antnode0001", dry_run=False)

        assert result["status"] == "disabled-nodes"
        assert result["disabled_count"] == 1
        assert "antnode0001" in result["disabled_nodes"]
        # Should not call stop_node since it's already stopped
        mock_manager.stop_node.assert_not_called()

        # Verify node status updated to DISABLED
        updated_node = db_session.query(Node).filter(Node.id == 1).first()
        assert updated_node.status == DISABLED

    def test_force_disable_requires_service_name(self, db_session):
        """Test forced disable requires service_name"""
        executor = ActionExecutor(lambda: db_session)

        result = executor._force_disable_node(None, dry_run=False)

        assert result["status"] == "error"
        assert "service_name required" in result["message"].lower()

    def test_force_disable_node_not_found(self, db_session):
        """Test forced disable of non-existent node"""
        executor = ActionExecutor(lambda: db_session)

        result = executor._force_disable_node("antnode9999", dry_run=False)

        assert result["status"] == "disabled-nodes"
        assert result["disabled_count"] == 0
        assert result["failed_count"] == 1
        assert result["failed_nodes"][0]["service"] == "antnode9999"
        assert "not found" in result["failed_nodes"][0]["error"]


class TestCommaSeparatedActions:
    """Test forced actions with comma-separated node names"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_remove_multiple_nodes(self, mock_get_manager, db_session, multiple_nodes):
        """Test forced remove with comma-separated node names"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_remove_node("antnode0001,antnode0003,antnode0005", dry_run=False)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 3
        assert "antnode0001" in result["removed_nodes"]
        assert "antnode0003" in result["removed_nodes"]
        assert "antnode0005" in result["removed_nodes"]

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    def test_force_upgrade_multiple_nodes(self, mock_upgrade, db_session, multiple_nodes):
        """Test forced upgrade with comma-separated node names"""
        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node("antnode0001,antnode0002", metrics, dry_run=False)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 2
        assert "antnode0001" in result["upgraded_nodes"]
        assert "antnode0002" in result["upgraded_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_stop_multiple_nodes(self, mock_get_manager, db_session, multiple_nodes):
        """Test forced stop with comma-separated node names"""
        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_stop_node("antnode0001,antnode0002", dry_run=False)

        assert result["status"] == "stopped-nodes"
        assert result["stopped_count"] == 2
        assert "antnode0001" in result["stopped_nodes"]
        assert "antnode0002" in result["stopped_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    def test_force_start_multiple_nodes(self, mock_version, mock_get_manager, db_session, multiple_nodes):
        """Test forced start with comma-separated node names"""
        # Stop some nodes first and set their versions
        multiple_nodes[0].status = STOPPED
        multiple_nodes[0].version = "0.4.6"
        multiple_nodes[1].status = STOPPED
        multiple_nodes[1].version = "0.4.6"
        db_session.commit()

        mock_version.return_value = "0.4.6"
        mock_manager = MagicMock()
        mock_manager.start_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node("antnode0001,antnode0002", metrics, dry_run=False)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 2
        assert "antnode0001" in result["started_nodes"]
        assert "antnode0002" in result["started_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_disable_multiple_nodes(self, mock_get_manager, db_session, multiple_nodes):
        """Test forced disable with comma-separated node names"""
        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_disable_node("antnode0001,antnode0002", dry_run=False)

        assert result["status"] == "disabled-nodes"
        assert result["disabled_count"] == 2
        assert "antnode0001" in result["disabled_nodes"]
        assert "antnode0002" in result["disabled_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_comma_separated_with_spaces(self, mock_get_manager, db_session, multiple_nodes):
        """Test comma-separated names with spaces are handled correctly"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        # Test with spaces around commas
        result = executor._force_remove_node("antnode0001 , antnode0003 , antnode0005", dry_run=False)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 3
        assert "antnode0001" in result["removed_nodes"]
        assert "antnode0003" in result["removed_nodes"]
        assert "antnode0005" in result["removed_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_comma_separated_partial_failure(self, mock_get_manager, db_session, multiple_nodes):
        """Test comma-separated actions handle partial failures correctly"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        # Mix of existing and non-existing nodes
        result = executor._force_remove_node("antnode0001,antnode9999,antnode0003", dry_run=False)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 2
        assert "antnode0001" in result["removed_nodes"]
        assert "antnode0003" in result["removed_nodes"]
        assert result["failed_count"] == 1
        assert result["failed_nodes"][0]["service"] == "antnode9999"
        assert "not found" in result["failed_nodes"][0]["error"]


class TestForcedTeardownAction:
    """Test forced teardown cluster action"""

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_teardown_all_nodes(
        self, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced teardown removes all nodes"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_manager.teardown_cluster.return_value = False  # Use default removal
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_teardown_cluster({}, dry_run=False)

        assert result["status"] == "cluster-teardown"
        assert result["method"] == "individual-remove"
        assert result["removed_count"] == 5

        # Verify all nodes removed from database
        remaining = db_session.query(Node).count()
        assert remaining == 0

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_teardown_manager_specific(
        self, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced teardown using manager-specific method"""
        mock_manager = MagicMock()
        mock_manager.teardown_cluster.return_value = True  # Manager handles it
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_teardown_cluster({}, dry_run=False)

        assert result["status"] == "cluster-teardown"
        assert result["method"] == "manager-specific"

        # Verify all nodes removed from database
        remaining = db_session.query(Node).count()
        assert remaining == 0

    def test_force_teardown_no_nodes(self, db_session):
        """Test forced teardown when no nodes exist"""
        executor = ActionExecutor(lambda: db_session)

        result = executor._force_teardown_cluster({}, dry_run=False)

        assert result["status"] == "no-nodes"

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_teardown_handles_partial_failure(
        self, mock_get_manager, db_session, multiple_nodes
    ):
        """Test forced teardown continues despite individual node failures"""
        mock_manager = MagicMock()
        mock_manager.teardown_cluster.return_value = False

        # Make removal fail for node 3
        def remove_side_effect(node):
            if node.id == 3:
                raise Exception("Removal failed")
            return True

        mock_manager.remove_node.side_effect = remove_side_effect
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_teardown_cluster({}, dry_run=False)

        assert result["status"] == "cluster-teardown"
        assert result["method"] == "individual-remove"
        # Should remove 4 out of 5 nodes
        assert result["removed_count"] == 4

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_teardown_dry_run(self, mock_get_manager, db_session, multiple_nodes):
        """Test forced teardown in dry-run mode"""
        mock_manager = MagicMock()
        mock_manager.teardown_cluster.return_value = False
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_teardown_cluster({}, dry_run=True)

        assert result["status"] == "cluster-teardown"
        # Should not actually remove nodes
        remaining = db_session.query(Node).count()
        assert remaining == 5


class TestCountParameter:
    """Test count parameter functionality across actions"""

    @patch("wnm.executor.get_process_manager")
    @patch("wnm.executor.os.path.expanduser")
    def test_force_add_multiple_nodes(
        self, mock_expanduser, mock_get_manager, db_session, sample_machine_config
    ):
        """Test adding multiple nodes with count parameter"""
        mock_expanduser.return_value = "/tmp/antnode"
        mock_manager = MagicMock()
        # Return different NodeProcess objects for each call
        mock_manager.create_node.side_effect = [
            NodeProcess(node_id=i, pid=10000 + i, status="RUNNING") for i in range(1, 4)
        ]
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=3)

        assert result["status"] == "added-nodes"
        assert result["added_count"] == 3
        assert len(result["added_nodes"]) == 3
        # Verify create_node was called 3 times
        assert mock_manager.create_node.call_count == 3

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_remove_multiple_nodes(self, mock_get_manager, db_session, multiple_nodes):
        """Test removing multiple nodes with count parameter"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_remove_node(None, dry_run=False, count=3)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 3
        # Should remove 3 youngest nodes (highest age values)
        assert "antnode0005" in result["removed_nodes"]
        assert "antnode0004" in result["removed_nodes"]
        assert "antnode0003" in result["removed_nodes"]

    @patch("wnm.executor.ActionExecutor._upgrade_node_binary")
    def test_force_upgrade_multiple_nodes(self, mock_upgrade, db_session, multiple_nodes):
        """Test upgrading multiple nodes with count parameter"""
        mock_upgrade.return_value = True

        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.5.0"}

        result = executor._force_upgrade_node(None, metrics, dry_run=False, count=3)

        assert result["status"] == "upgraded-nodes"
        assert result["upgraded_count"] == 3
        # Should upgrade 3 oldest running nodes (lowest age values)
        assert "antnode0001" in result["upgraded_nodes"]
        assert "antnode0002" in result["upgraded_nodes"]
        assert "antnode0003" in result["upgraded_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_force_stop_multiple_nodes(self, mock_get_manager, db_session, multiple_nodes):
        """Test stopping multiple nodes with count parameter"""
        mock_manager = MagicMock()
        mock_manager.stop_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        result = executor._force_stop_node(None, dry_run=False, count=2)

        assert result["status"] == "stopped-nodes"
        assert result["stopped_count"] == 2
        # Should stop 2 youngest running nodes (highest age values)
        assert "antnode0005" in result["stopped_nodes"]
        assert "antnode0004" in result["stopped_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    @patch("wnm.executor.get_antnode_version")
    def test_force_start_multiple_nodes(self, mock_version, mock_get_manager, db_session, multiple_nodes):
        """Test starting multiple nodes with count parameter"""
        # Stop some nodes first
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
        metrics = {"antnode_version": "0.4.6"}

        result = executor._force_start_node(None, metrics, dry_run=False, count=2)

        assert result["status"] == "started-nodes"
        assert result["started_count"] == 2
        # Should start 2 oldest stopped nodes (lowest age values)
        assert "antnode0001" in result["started_nodes"]
        assert "antnode0002" in result["started_nodes"]

    @patch("wnm.executor.ActionExecutor._get_process_manager")
    def test_count_exceeds_available_nodes(self, mock_get_manager, db_session, multiple_nodes):
        """Test count parameter when it exceeds available nodes"""
        mock_manager = MagicMock()
        mock_manager.remove_node.return_value = True
        mock_get_manager.return_value = mock_manager

        executor = ActionExecutor(lambda: db_session)

        # Try to remove 10 nodes when only 5 exist
        result = executor._force_remove_node(None, dry_run=False, count=10)

        assert result["status"] == "removed-nodes"
        assert result["removed_count"] == 5  # Should remove all 5 available nodes
        assert len(result["removed_nodes"]) == 5

    def test_count_parameter_validation(self, db_session, sample_machine_config):
        """Test count parameter validation (must be >= 1)"""
        executor = ActionExecutor(lambda: db_session)
        metrics = {"antnode_version": "0.4.6"}

        # Test with count = 0
        result = executor._force_add_node(sample_machine_config, metrics, dry_run=False, count=0)
        assert result["status"] == "error"
        assert "count must be at least 1" in result["message"]

        # Test with negative count
        result = executor._force_remove_node(None, dry_run=False, count=-1)
        assert result["status"] == "error"
        assert "count must be at least 1" in result["message"]


class TestForcedActionRouter:
    """Test the main execute_forced_action router"""

    @patch("wnm.executor.ActionExecutor._force_add_node")
    def test_route_add_action(self, mock_add, db_session):
        """Test routing to add action"""
        mock_add.return_value = {"status": "added-node"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "add", {}, {}, service_name=None, dry_run=False, count=1
        )

        assert result["status"] == "added-node"
        mock_add.assert_called_once()

    @patch("wnm.executor.ActionExecutor._force_remove_node")
    def test_route_remove_action(self, mock_remove, db_session):
        """Test routing to remove action"""
        mock_remove.return_value = {"status": "removed-node"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "remove", {}, {}, service_name="antnode0001", dry_run=False, count=1
        )

        assert result["status"] == "removed-node"
        mock_remove.assert_called_once_with("antnode0001", False, 1)

    @patch("wnm.executor.ActionExecutor._force_upgrade_node")
    def test_route_upgrade_action(self, mock_upgrade, db_session):
        """Test routing to upgrade action"""
        mock_upgrade.return_value = {"status": "upgraded-node"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "upgrade", {}, {}, service_name="antnode0002", dry_run=False, count=1
        )

        assert result["status"] == "upgraded-node"
        mock_upgrade.assert_called_once_with("antnode0002", {}, False, 1)

    @patch("wnm.executor.ActionExecutor._force_start_node")
    def test_route_start_action(self, mock_start, db_session):
        """Test routing to start action"""
        mock_start.return_value = {"status": "started-node"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "start", {}, {}, service_name="antnode0003", dry_run=False, count=1
        )

        assert result["status"] == "started-node"
        mock_start.assert_called_once_with("antnode0003", {}, False, 1)

    @patch("wnm.executor.ActionExecutor._force_stop_node")
    def test_route_stop_action(self, mock_stop, db_session):
        """Test routing to stop action"""
        mock_stop.return_value = {"status": "stopped-node"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "stop", {}, {}, service_name="antnode0003", dry_run=False, count=1
        )

        assert result["status"] == "stopped-node"
        mock_stop.assert_called_once_with("antnode0003", False, 1)

    @patch("wnm.executor.ActionExecutor._force_disable_node")
    def test_route_disable_action(self, mock_disable, db_session):
        """Test routing to disable action"""
        mock_disable.return_value = {"status": "disabled-node"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "disable", {}, {}, service_name="antnode0004", dry_run=False
        )

        assert result["status"] == "disabled-node"
        mock_disable.assert_called_once_with("antnode0004", False)

    @patch("wnm.executor.ActionExecutor._force_teardown_cluster")
    def test_route_teardown_action(self, mock_teardown, db_session):
        """Test routing to teardown action"""
        mock_teardown.return_value = {"status": "cluster-teardown"}
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "teardown", {}, {}, service_name=None, dry_run=False
        )

        assert result["status"] == "cluster-teardown"
        mock_teardown.assert_called_once()

    def test_route_unknown_action(self, db_session):
        """Test routing unknown action returns error"""
        executor = ActionExecutor(lambda: db_session)

        result = executor.execute_forced_action(
            "invalid", {}, {}, service_name=None, dry_run=False
        )

        assert result["status"] == "error"
        assert "unknown" in result["message"].lower()
