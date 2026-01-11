"""Tests for survey preserving transitional states (UPGRADING, RESTARTING, REMOVING)"""

import time
from unittest.mock import patch

import pytest
from sqlalchemy import select

from wnm.common import RESTARTING, RUNNING, STOPPED, UPGRADING, REMOVING
from wnm.models import Node
from wnm.utils import update_node_from_metrics


class TestSurveyTransitionalStates:
    """Test that surveys preserve UPGRADING, RESTARTING, and REMOVING states"""

    @pytest.fixture
    def upgrading_node(self, db_session, sample_machine_config):
        """Create a node in UPGRADING state"""
        node = Node(
            id=1,
            node_name="0001",
            service="antnode0001.service",
            user="ant",
            version="0.1.0",
            root_dir=f"{sample_machine_config['node_storage']}/antnode0001",
            binary=f"{sample_machine_config['node_storage']}/antnode0001/antnode",
            port=55001,
            metrics_port=13001,
            rpc_port=30001,
            network="evm-arbitrum-one",
            wallet="0x1234567890123456789012345678901234567890",
            peer_id="12D3KooWTest",
            status=UPGRADING,
            timestamp=int(time.time()),
            records=100,
            uptime=1000,
            shunned=0,
            age=int(time.time()),
            host="localhost",
            method="systemd",
            layout="1",
        )
        db_session.add(node)
        db_session.commit()
        return node

    @pytest.fixture
    def restarting_node(self, db_session, sample_machine_config):
        """Create a node in RESTARTING state"""
        node = Node(
            id=2,
            node_name="0002",
            service="antnode0002.service",
            user="ant",
            version="0.1.0",
            root_dir=f"{sample_machine_config['node_storage']}/antnode0002",
            binary=f"{sample_machine_config['node_storage']}/antnode0002/antnode",
            port=55002,
            metrics_port=13002,
            rpc_port=30002,
            network="evm-arbitrum-one",
            wallet="0x1234567890123456789012345678901234567890",
            peer_id="12D3KooWTest2",
            status=RESTARTING,
            timestamp=int(time.time()),
            records=50,
            uptime=500,
            shunned=0,
            age=int(time.time()),
            host="localhost",
            method="systemd",
            layout="1",
        )
        db_session.add(node)
        db_session.commit()
        return node

    @pytest.fixture
    def removing_node(self, db_session, sample_machine_config):
        """Create a node in REMOVING state"""
        node = Node(
            id=3,
            node_name="0003",
            service="antnode0003.service",
            user="ant",
            version="0.1.0",
            root_dir=f"{sample_machine_config['node_storage']}/antnode0003",
            binary=f"{sample_machine_config['node_storage']}/antnode0003/antnode",
            port=55003,
            metrics_port=13003,
            rpc_port=30003,
            network="evm-arbitrum-one",
            wallet="0x1234567890123456789012345678901234567890",
            peer_id="12D3KooWTest3",
            status=REMOVING,
            timestamp=int(time.time()),
            records=75,
            uptime=750,
            shunned=0,
            age=int(time.time()),
            host="localhost",
            method="systemd",
            layout="1",
        )
        db_session.add(node)
        db_session.commit()
        return node

    def test_upgrading_node_status_preserved_when_running(
        self, db_session, upgrading_node, session_factory
    ):
        """Test that UPGRADING status is preserved when node responds as RUNNING"""
        # Simulate metrics showing node is running
        metrics = {
            "status": RUNNING,
            "uptime": 2000,
            "records": 200,
            "shunned": 0,
            "connected_peers": 10,
            "gets": 0,
            "puts": 100,
            "mem": 5000,
            "cpu": 300,
            "open_connections": 5,
            "total_peers": 50,
            "bad_peers": 0,
            "rel_records": 150,
            "max_records": 500,
            "rewards": "1000.0",
            "payment_count": 5,
            "live_time": 1500,
            "network_size": 1000,
        }
        metadata = {
            "status": RUNNING,
            "peer_id": "12D3KooWTestUpdated",
            "version": "0.2.0",
        }

        # Update node from metrics
        result = update_node_from_metrics(session_factory, upgrading_node.id, metrics, metadata)
        assert result is True

        # Refresh session to see changes from other transaction
        db_session.expire_all()

        # Verify status is still UPGRADING (not changed to RUNNING)
        stmt = select(Node).where(Node.id == upgrading_node.id)
        updated_node = db_session.execute(stmt).scalar_one()
        assert updated_node.status == UPGRADING, "UPGRADING status should be preserved"

        # Verify other metrics were updated
        assert updated_node.uptime == 2000
        assert updated_node.records == 200
        assert updated_node.connected_peers == 10

    def test_upgrading_node_status_preserved_when_stopped(
        self, db_session, upgrading_node, session_factory
    ):
        """Test that UPGRADING status is preserved when node doesn't respond (STOPPED)"""
        # Simulate metrics showing node is stopped
        metrics = {
            "status": STOPPED,
            "uptime": 0,
            "records": 0,
            "shunned": 0,
            "connected_peers": 0,
        }
        metadata = {
            "status": STOPPED,
            "peer_id": "",
        }

        # Update node from metrics
        result = update_node_from_metrics(session_factory, upgrading_node.id, metrics, metadata)
        assert result is True

        # Refresh session to see changes from other transaction
        db_session.expire_all()

        # Verify status is still UPGRADING (not changed to STOPPED)
        stmt = select(Node).where(Node.id == upgrading_node.id)
        updated_node = db_session.execute(stmt).scalar_one()
        assert updated_node.status == UPGRADING, "UPGRADING status should be preserved even when stopped"

    def test_restarting_node_status_preserved_when_running(
        self, db_session, restarting_node, session_factory
    ):
        """Test that RESTARTING status is preserved when node responds as RUNNING"""
        metrics = {
            "status": RUNNING,
            "uptime": 100,
            "records": 75,
            "shunned": 0,
            "connected_peers": 5,
            "gets": 0,
            "puts": 50,
            "mem": 4000,
            "cpu": 250,
            "open_connections": 3,
            "total_peers": 30,
            "bad_peers": 0,
            "rel_records": 50,
            "max_records": 300,
            "rewards": "500.0",
            "payment_count": 2,
            "live_time": 80,
            "network_size": 800,
        }
        metadata = {
            "status": RUNNING,
            "peer_id": "12D3KooWTest2Updated",
            "version": "0.1.0",
        }

        result = update_node_from_metrics(session_factory, restarting_node.id, metrics, metadata)
        assert result is True

        # Refresh session to see changes from other transaction
        db_session.expire_all()

        stmt = select(Node).where(Node.id == restarting_node.id)
        updated_node = db_session.execute(stmt).scalar_one()
        assert updated_node.status == RESTARTING, "RESTARTING status should be preserved"

    def test_restarting_node_status_preserved_when_stopped(
        self, db_session, restarting_node, session_factory
    ):
        """Test that RESTARTING status is preserved when node doesn't respond"""
        metrics = {
            "status": STOPPED,
            "uptime": 0,
            "records": 0,
            "shunned": 0,
            "connected_peers": 0,
        }
        metadata = {
            "status": STOPPED,
            "peer_id": "",
        }

        result = update_node_from_metrics(session_factory, restarting_node.id, metrics, metadata)
        assert result is True

        # Refresh session to see changes from other transaction
        db_session.expire_all()

        stmt = select(Node).where(Node.id == restarting_node.id)
        updated_node = db_session.execute(stmt).scalar_one()
        assert updated_node.status == RESTARTING, "RESTARTING status should be preserved"

    def test_removing_node_status_preserved(
        self, db_session, removing_node, session_factory
    ):
        """Test that REMOVING status is preserved during survey"""
        metrics = {
            "status": STOPPED,
            "uptime": 0,
            "records": 0,
            "shunned": 0,
            "connected_peers": 0,
        }
        metadata = {
            "status": STOPPED,
            "peer_id": "",
        }

        result = update_node_from_metrics(session_factory, removing_node.id, metrics, metadata)
        assert result is True

        # Refresh session to see changes from other transaction
        db_session.expire_all()

        stmt = select(Node).where(Node.id == removing_node.id)
        updated_node = db_session.execute(stmt).scalar_one()
        assert updated_node.status == REMOVING, "REMOVING status should be preserved"

    def test_normal_node_status_updated(self, db_session, sample_machine_config, session_factory):
        """Test that non-transitional states (RUNNING, STOPPED) are updated normally"""
        # Create a node in STOPPED state
        node = Node(
            id=4,
            node_name="0004",
            service="antnode0004.service",
            user="ant",
            version="0.1.0",
            root_dir=f"{sample_machine_config['node_storage']}/antnode0004",
            binary=f"{sample_machine_config['node_storage']}/antnode0004/antnode",
            port=55004,
            metrics_port=13004,
            rpc_port=30004,
            network="evm-arbitrum-one",
            wallet="0x1234567890123456789012345678901234567890",
            peer_id="",
            status=STOPPED,
            timestamp=int(time.time()),
            records=0,
            uptime=0,
            shunned=0,
            age=int(time.time()),
            host="localhost",
            method="systemd",
            layout="1",
        )
        db_session.add(node)
        db_session.commit()

        # Update with RUNNING metrics
        metrics = {
            "status": RUNNING,
            "uptime": 1000,
            "records": 100,
            "shunned": 0,
            "connected_peers": 10,
            "gets": 0,
            "puts": 50,
            "mem": 3000,
            "cpu": 200,
            "open_connections": 4,
            "total_peers": 40,
            "bad_peers": 0,
            "rel_records": 80,
            "max_records": 400,
            "rewards": "750.0",
            "payment_count": 3,
            "live_time": 900,
            "network_size": 900,
        }
        metadata = {
            "status": RUNNING,
            "peer_id": "12D3KooWTest4",
            "version": "0.1.0",
        }

        result = update_node_from_metrics(session_factory, node.id, metrics, metadata)
        assert result is True

        # Refresh session to see changes from other transaction
        db_session.expire_all()

        # Verify status WAS updated from STOPPED to RUNNING
        stmt = select(Node).where(Node.id == node.id)
        updated_node = db_session.execute(stmt).scalar_one()
        assert updated_node.status == RUNNING, "STOPPED status should be updated to RUNNING"
        assert updated_node.uptime == 1000
        assert updated_node.records == 100

    def test_upgrade_delay_expiration_transitions_status(
        self, db_session, upgrading_node, session_factory
    ):
        """Test that update_counters explicitly transitions status after delay expires"""
        from wnm.utils import update_counters

        # Set the node's timestamp to past (delay already expired)
        old_timestamp = int(time.time()) - 300  # 5 minutes ago
        stmt = select(Node).where(Node.id == upgrading_node.id)
        node = db_session.execute(stmt).scalar_one()
        node.timestamp = old_timestamp
        db_session.commit()

        # Prepare metrics showing node is now RUNNING
        metrics = {
            "upgrading_nodes": 1,
            "restarting_nodes": 0,
            "removing_nodes": 0,
        }
        config = {
            "delay_upgrade": 60,  # 1 minute delay (already expired)
        }

        # Mock read_node_metrics and read_node_metadata to return RUNNING status
        from unittest.mock import patch
        with patch("wnm.utils.read_node_metrics") as mock_metrics, \
             patch("wnm.utils.read_node_metadata") as mock_metadata:
            mock_metrics.return_value = {
                "status": RUNNING,
                "uptime": 500,
                "records": 150,
                "shunned": 0,
                "connected_peers": 8,
                "gets": 0,
                "puts": 75,
                "mem": 4500,
                "cpu": 275,
                "open_connections": 4,
                "total_peers": 45,
                "bad_peers": 0,
                "rel_records": 125,
                "max_records": 450,
                "rewards": "875.0",
                "payment_count": 4,
                "live_time": 1250,
                "network_size": 950,
            }
            mock_metadata.return_value = {
                "status": RUNNING,
                "peer_id": "12D3KooWTestTransitioned",
                "version": "0.2.0",
            }

            # Call update_counters (simulates what __main__.py does)
            updated_metrics = update_counters(session_factory, metrics, config)

        # Refresh and verify node transitioned to RUNNING
        db_session.expire_all()
        stmt = select(Node).where(Node.id == upgrading_node.id)
        updated_node = db_session.execute(stmt).scalar_one()

        assert updated_node.status == RUNNING, "Node should transition to RUNNING after delay expires"
        assert updated_metrics["upgrading_nodes"] == 0, "Should have 0 upgrading nodes after transition"
