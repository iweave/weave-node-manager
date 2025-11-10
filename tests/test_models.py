"""Tests for database models"""

import pytest
from sqlalchemy import select

from wnm.models import Machine, Node


class TestMachine:
    """Tests for Machine model"""

    def test_create_machine(self, db_session, sample_machine_config):
        """Test creating a Machine instance"""
        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        assert machine.id is not None
        assert machine.cpu_count == 8
        assert machine.node_cap == 10
        assert machine.rewards_address == "0x1234567890123456789012345678901234567890"

    def test_machine_repr(self, machine):
        """Test Machine string representation"""
        repr_str = repr(machine)
        assert "Machine(" in repr_str
        assert str(machine.cpu_count) in repr_str
        assert str(machine.node_cap) in repr_str

    def test_machine_json(self, machine):
        """Test Machine JSON serialization"""
        json_data = machine.__json__()
        assert json_data["cpu_count"] == 8
        assert json_data["node_cap"] == 10
        assert json_data["cpu_less_than"] == 70
        assert json_data["cpu_remove"] == 85
        assert (
            json_data["rewards_address"] == "0x1234567890123456789012345678901234567890"
        )

    def test_machine_update(self, db_session, machine):
        """Test updating Machine fields"""
        machine.node_cap = 20
        machine.cpu_less_than = 60
        db_session.commit()

        stmt = select(Machine).where(Machine.id == machine.id)
        updated = db_session.execute(stmt).scalar_one()
        assert updated.node_cap == 20
        assert updated.cpu_less_than == 60

    def test_machine_query(self, db_session, machine):
        """Test querying Machine"""
        stmt = select(Machine).where(Machine.id == 1)
        result = db_session.execute(stmt).scalar_one()
        assert result.id == machine.id
        assert result.cpu_count == machine.cpu_count


class TestNode:
    """Tests for Node model"""

    def test_create_node(self, db_session, sample_node_config):
        """Test creating a Node instance"""
        node = Node(**sample_node_config)
        db_session.add(node)
        db_session.commit()

        assert node.id == 1
        assert node.node_name == "0001"
        assert node.status == "RUNNING"
        assert node.port == 55001
        assert node.metrics_port == 13001

    def test_node_repr(self, node):
        """Test Node string representation"""
        repr_str = repr(node)
        assert "Node(" in repr_str
        assert node.node_name in repr_str

    def test_node_json(self, node):
        """Test Node JSON serialization"""
        json_data = node.__json__()
        assert json_data["id"] == 1
        assert json_data["node_name"] == "0001"
        assert json_data["status"] == "RUNNING"
        assert json_data["port"] == 55001
        # Check that method matches the node's actual method (platform-specific)
        assert json_data["method"] == node.method
        assert json_data["method"] in [
            "systemd+user",
            "systemd+sudo",
            "launchd+user",
            "launchd+sudo",
            "setsid+user",
            "setsid+sudo",
        ]

    def test_node_update_status(self, db_session, node):
        """Test updating Node status"""
        node.status = "STOPPED"
        node.timestamp = 2000000
        db_session.commit()

        stmt = select(Node).where(Node.id == node.id)
        updated = db_session.execute(stmt).scalar_one()
        assert updated.status == "STOPPED"
        assert updated.timestamp == 2000000

    def test_node_update_metrics(self, db_session, node):
        """Test updating Node metrics"""
        node.records = 1000
        node.uptime = 3600
        node.shunned = 5
        db_session.commit()

        stmt = select(Node).where(Node.id == node.id)
        updated = db_session.execute(stmt).scalar_one()
        assert updated.records == 1000
        assert updated.uptime == 3600
        assert updated.shunned == 5

    def test_multiple_nodes(self, db_session, multiple_nodes):
        """Test creating multiple nodes"""
        assert len(multiple_nodes) == 5

        stmt = select(Node)
        all_nodes = db_session.execute(stmt).scalars().all()
        assert len(all_nodes) == 5

        # Check they're ordered by ID
        for i, node in enumerate(all_nodes, 1):
            assert node.id == i
            assert node.node_name == f"{i:04d}"

    def test_query_by_status(self, db_session, multiple_nodes):
        """Test querying nodes by status"""
        # Set different statuses
        multiple_nodes[0].status = "RUNNING"
        multiple_nodes[1].status = "STOPPED"
        multiple_nodes[2].status = "UPGRADING"
        multiple_nodes[3].status = "RUNNING"
        multiple_nodes[4].status = "STOPPED"
        db_session.commit()

        stmt = select(Node).where(Node.status == "RUNNING")
        running = db_session.execute(stmt).scalars().all()
        assert len(running) == 2

        stmt = select(Node).where(Node.status == "STOPPED")
        stopped = db_session.execute(stmt).scalars().all()
        assert len(stopped) == 2

    def test_query_by_records(self, db_session, multiple_nodes):
        """Test querying nodes by record count"""
        stmt = select(Node).where(Node.records > 200)
        high_records = db_session.execute(stmt).scalars().all()
        assert len(high_records) == 3  # nodes 3, 4, 5

    def test_node_optional_fields(self, db_session, sample_node_config):
        """Test Node with optional fields as None"""
        sample_node_config["peer_id"] = None
        sample_node_config["version"] = None
        sample_node_config["environment"] = None

        node = Node(**sample_node_config)
        db_session.add(node)
        db_session.commit()

        assert node.peer_id is None
        assert node.version is None
        assert node.environment is None
