"""Tests for node ID tracking utilities for antctl managers"""

import pytest
from unittest.mock import Mock
from sqlalchemy import select

from wnm.models import Machine, Node
from wnm.node_id_tracker import initialize_node_id_tracking, allocate_node_id


class TestInitializeNodeIdTracking:
    """Tests for initialize_node_id_tracking function"""

    def test_initialize_no_nodes(self, db_session, sample_machine_config):
        """Test initialization when no nodes exist"""
        # Create machine without highest_node_id_used set
        machine_config = Machine(**sample_machine_config)
        machine_config.highest_node_id_used = None
        db_session.add(machine_config)
        db_session.commit()

        # Initialize tracking
        needs_update, value = initialize_node_id_tracking(db_session, machine_config)

        assert needs_update is True
        assert value == 0

    def test_initialize_with_existing_nodes(self, db_session, sample_machine_config):
        """Test initialization when nodes exist"""
        # Create machine without highest_node_id_used set
        machine_config = Machine(**sample_machine_config)
        machine_config.highest_node_id_used = None
        db_session.add(machine_config)
        db_session.commit()

        # Add some nodes with IDs 1, 3, 5 (simulating gaps)
        for node_id in [1, 3, 5]:
            node = Node(
                id=node_id,
                node_name=f"{node_id:04}",
                service=f"antnode{node_id:04}.service",
                user="ant",
                version="0.1.0",
                root_dir=f"/tmp/test_nodes/antnode{node_id:04}",
                binary=f"/tmp/test_nodes/antnode{node_id:04}/antnode",
                port=55000 + node_id,
                metrics_port=13000 + node_id,
                rpc_port=30000 + node_id,
                network="evm-arbitrum-one",
                wallet="0x1234567890123456789012345678901234567890",
                peer_id="",
                status="RUNNING",
                timestamp=1234567890,
                records=0,
                uptime=0,
                shunned=0,
                age=1234567890,
                host="127.0.0.1",
                method="antctl+zen",
                layout="1",
                environment="",
                manager_type="antctl+zen",
            )
            db_session.add(node)
        db_session.commit()

        # Initialize tracking
        needs_update, value = initialize_node_id_tracking(db_session, machine_config)

        assert needs_update is True
        assert value == 5  # Should use max node ID

    def test_initialize_already_initialized(self, db_session, sample_machine_config):
        """Test when already initialized"""
        # Create machine with highest_node_id_used already set
        machine_config = Machine(**sample_machine_config)
        machine_config.highest_node_id_used = 10
        db_session.add(machine_config)
        db_session.commit()

        # Initialize tracking
        needs_update, value = initialize_node_id_tracking(db_session, machine_config)

        assert needs_update is False
        assert value is None

    def test_initialize_with_single_node(self, db_session, sample_machine_config):
        """Test initialization with exactly one node"""
        # Create machine without highest_node_id_used set
        machine_config = Machine(**sample_machine_config)
        machine_config.highest_node_id_used = None
        db_session.add(machine_config)
        db_session.commit()

        # Add single node with ID 7
        node = Node(
            id=7,
            node_name="0007",
            service="antnode0007.service",
            user="ant",
            version="0.1.0",
            root_dir="/tmp/test_nodes/antnode0007",
            binary="/tmp/test_nodes/antnode0007/antnode",
            port=55007,
            metrics_port=13007,
            rpc_port=30007,
            network="evm-arbitrum-one",
            wallet="0x1234567890123456789012345678901234567890",
            peer_id="",
            status="RUNNING",
            timestamp=1234567890,
            records=0,
            uptime=0,
            shunned=0,
            age=1234567890,
            host="127.0.0.1",
            method="antctl+zen",
            layout="1",
            environment="",
            manager_type="antctl+zen",
        )
        db_session.add(node)
        db_session.commit()

        # Initialize tracking
        needs_update, value = initialize_node_id_tracking(db_session, machine_config)

        assert needs_update is True
        assert value == 7


class TestAllocateNodeId:
    """Tests for allocate_node_id function"""

    def test_allocate_node_id_normal(self):
        """Test node ID allocation with initialized tracking"""
        machine_config = Mock()
        machine_config.highest_node_id_used = 5

        node_id, updates = allocate_node_id(machine_config)

        assert node_id == 6
        assert updates == {"highest_node_id_used": 6}

    def test_allocate_node_id_from_zero(self):
        """Test allocation when starting from zero"""
        machine_config = Mock()
        machine_config.highest_node_id_used = 0

        node_id, updates = allocate_node_id(machine_config)

        assert node_id == 1
        assert updates == {"highest_node_id_used": 1}

    def test_allocate_node_id_not_initialized(self):
        """Test allocation when not initialized (edge case)"""
        machine_config = Mock()
        machine_config.highest_node_id_used = None

        node_id, updates = allocate_node_id(machine_config)

        # Should default to 1 and warn
        assert node_id == 1
        assert updates == {"highest_node_id_used": 1}

    def test_allocate_node_id_sequential(self):
        """Test sequential allocation"""
        machine_config = Mock()
        machine_config.highest_node_id_used = 10

        # Allocate first ID
        node_id1, updates1 = allocate_node_id(machine_config)
        assert node_id1 == 11
        assert updates1 == {"highest_node_id_used": 11}

        # Update machine_config to simulate database update
        machine_config.highest_node_id_used = 11

        # Allocate second ID
        node_id2, updates2 = allocate_node_id(machine_config)
        assert node_id2 == 12
        assert updates2 == {"highest_node_id_used": 12}

        # Update machine_config again
        machine_config.highest_node_id_used = 12

        # Allocate third ID
        node_id3, updates3 = allocate_node_id(machine_config)
        assert node_id3 == 13
        assert updates3 == {"highest_node_id_used": 13}

    def test_allocate_node_id_large_value(self):
        """Test allocation with large existing value"""
        machine_config = Mock()
        machine_config.highest_node_id_used = 999

        node_id, updates = allocate_node_id(machine_config)

        assert node_id == 1000
        assert updates == {"highest_node_id_used": 1000}


class TestNodeIdTrackingIntegration:
    """Integration tests for node ID tracking workflow"""

    def test_full_workflow_new_cluster(self, db_session, sample_machine_config):
        """Test complete workflow for new cluster initialization"""
        # Create machine for antctl+zen
        sample_machine_config["process_manager"] = "antctl+zen"
        sample_machine_config["highest_node_id_used"] = None
        machine_config = Machine(**sample_machine_config)
        db_session.add(machine_config)
        db_session.commit()

        # Step 1: Initialize tracking (no nodes exist)
        needs_update, initial_value = initialize_node_id_tracking(db_session, machine_config)
        assert needs_update is True
        assert initial_value == 0

        # Update database
        db_session.query(Machine).filter(Machine.id == machine_config.id).update(
            {"highest_node_id_used": initial_value}
        )
        db_session.commit()

        # Reload machine_config
        machine_config = db_session.execute(select(Machine)).scalar_one()
        assert machine_config.highest_node_id_used == 0

        # Step 2: Allocate first node ID
        node_id1, update1 = allocate_node_id(machine_config)
        assert node_id1 == 1

        # Update database
        db_session.query(Machine).filter(Machine.id == machine_config.id).update(update1)
        db_session.commit()

        # Reload and check
        machine_config = db_session.execute(select(Machine)).scalar_one()
        assert machine_config.highest_node_id_used == 1

        # Step 3: Allocate second node ID
        node_id2, update2 = allocate_node_id(machine_config)
        assert node_id2 == 2

        # Update database
        db_session.query(Machine).filter(Machine.id == machine_config.id).update(update2)
        db_session.commit()

        # Final verification
        machine_config = db_session.execute(select(Machine)).scalar_one()
        assert machine_config.highest_node_id_used == 2

    def test_full_workflow_existing_cluster(self, db_session, sample_machine_config):
        """Test complete workflow for existing cluster with nodes"""
        # Create machine for antctl+user
        sample_machine_config["process_manager"] = "antctl+user"
        sample_machine_config["highest_node_id_used"] = None
        machine_config = Machine(**sample_machine_config)
        db_session.add(machine_config)
        db_session.commit()

        # Add existing nodes (IDs 1, 2, 5, 7 - simulating some removals)
        for node_id in [1, 2, 5, 7]:
            node = Node(
                id=node_id,
                node_name=f"{node_id:04}",
                service=f"antnode{node_id:04}.service",
                user="ant",
                version="0.1.0",
                root_dir=f"/tmp/test_nodes/antnode{node_id:04}",
                binary=f"/tmp/test_nodes/antnode{node_id:04}/antnode",
                port=55000 + node_id,
                metrics_port=13000 + node_id,
                rpc_port=30000 + node_id,
                network="evm-arbitrum-one",
                wallet="0x1234567890123456789012345678901234567890",
                peer_id="",
                status="RUNNING",
                timestamp=1234567890,
                records=0,
                uptime=0,
                shunned=0,
                age=1234567890,
                host="127.0.0.1",
                method="antctl+user",
                layout="1",
                environment="",
                manager_type="antctl+user",
            )
            db_session.add(node)
        db_session.commit()

        # Step 1: Initialize tracking (should use max node ID = 7)
        needs_update, initial_value = initialize_node_id_tracking(db_session, machine_config)
        assert needs_update is True
        assert initial_value == 7

        # Update database
        db_session.query(Machine).filter(Machine.id == machine_config.id).update(
            {"highest_node_id_used": initial_value}
        )
        db_session.commit()

        # Reload machine_config
        machine_config = db_session.execute(select(Machine)).scalar_one()
        assert machine_config.highest_node_id_used == 7

        # Step 2: Allocate new node ID (should be 8, NOT 3, 4, or 6 which are gaps)
        node_id_new, update_new = allocate_node_id(machine_config)
        assert node_id_new == 8  # Should NOT fill gaps

        # Update database
        db_session.query(Machine).filter(Machine.id == machine_config.id).update(update_new)
        db_session.commit()

        # Final verification
        machine_config = db_session.execute(select(Machine)).scalar_one()
        assert machine_config.highest_node_id_used == 8

    def test_reset_after_teardown(self, db_session, sample_machine_config):
        """Test resetting highest_node_id_used after cluster teardown"""
        # Create machine with some tracked IDs
        sample_machine_config["process_manager"] = "antctl+sudo"
        sample_machine_config["highest_node_id_used"] = 15
        machine_config = Machine(**sample_machine_config)
        db_session.add(machine_config)
        db_session.commit()

        # Simulate teardown - reset to 0
        db_session.query(Machine).filter(Machine.id == machine_config.id).update(
            {"highest_node_id_used": 0}
        )
        db_session.commit()

        # Reload and verify reset
        machine_config = db_session.execute(select(Machine)).scalar_one()
        assert machine_config.highest_node_id_used == 0

        # Allocate new ID after reset
        node_id, update = allocate_node_id(machine_config)
        assert node_id == 1  # Should start from 1 again after reset