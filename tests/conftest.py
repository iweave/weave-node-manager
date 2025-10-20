"""Pytest fixtures for WNM tests"""

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from wnm.models import Base, Machine, Node


@pytest.fixture(scope="session")
def test_db_path():
    """Create a temporary database file for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_colony.db"
        yield db_path


@pytest.fixture(scope="function")
def db_engine(test_db_path):
    """Create a test database engine"""
    engine = create_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a test database session"""
    Session = scoped_session(sessionmaker(bind=db_engine))
    session = Session()
    yield session
    session.close()
    Session.remove()


@pytest.fixture
def sample_machine_config():
    """Sample machine configuration for testing"""
    return {
        "cpu_count": 8,
        "node_cap": 10,
        "cpu_less_than": 70,
        "cpu_remove": 85,
        "mem_less_than": 70,
        "mem_remove": 85,
        "hd_less_than": 80,
        "hd_remove": 90,
        "delay_start": 300,  # 5 minutes in seconds
        "delay_upgrade": 600,  # 10 minutes in seconds
        "delay_remove": 900,  # 15 minutes in seconds
        "node_storage": "/tmp/test_nodes",
        "rewards_address": "0x1234567890123456789012345678901234567890",
        "donate_address": "0x0987654321098765432109876543210987654321",
        "max_load_average_allowed": 10.0,
        "desired_load_average": 5.0,
        "port_start": 55,
        "hdio_read_less_than": 1000000,
        "hdio_read_remove": 5000000,
        "hdio_write_less_than": 1000000,
        "hdio_write_remove": 5000000,
        "netio_read_less_than": 1000000,
        "netio_read_remove": 5000000,
        "netio_write_less_than": 1000000,
        "netio_write_remove": 5000000,
        "last_stopped_at": 0,
        "host": "test-host",
        "crisis_bytes": 2000000000,
        "metrics_port_start": 13000,
        "environment": None,
        "start_args": None,
        "max_concurrent_upgrades": 1,
        "max_concurrent_starts": 2,
        "max_concurrent_removals": 1,
        "node_removal_strategy": "youngest",
    }


@pytest.fixture
def machine(db_session, sample_machine_config):
    """Create a test Machine in the database"""
    m = Machine(**sample_machine_config)
    db_session.add(m)
    db_session.commit()
    return m


@pytest.fixture
def sample_node_config():
    """Sample node configuration for testing"""
    return {
        "id": 1,
        "node_name": "test001",
        "service": "antnode-test001",
        "user": "testuser",
        "binary": "/usr/local/bin/antnode",
        "version": "0.1.0",
        "root_dir": "/tmp/test_nodes/test001",
        "port": 55001,
        "metrics_port": 13001,
        "network": "evm-arbitrum-one",
        "wallet": "0x1234567890123456789012345678901234567890",
        "peer_id": None,
        "status": "RUNNING",
        "timestamp": 1000000,
        "records": 0,
        "uptime": 0,
        "shunned": 0,
        "age": 1000000,
        "host": "test-host",
        "method": "systemd",
        "layout": "single",
        "environment": None,
        "machine_id": 1,
        "container_id": None,
        "manager_type": "systemd",
    }


@pytest.fixture
def node(db_session, sample_node_config):
    """Create a test Node in the database"""
    n = Node(**sample_node_config)
    db_session.add(n)
    db_session.commit()
    return n


@pytest.fixture
def multiple_nodes(db_session, sample_node_config):
    """Create multiple test nodes in the database"""
    nodes = []
    for i in range(1, 6):
        config = sample_node_config.copy()
        config["id"] = i
        config["node_name"] = f"test{i:03d}"
        config["service"] = f"antnode-test{i:03d}"
        config["root_dir"] = f"/tmp/test_nodes/test{i:03d}"
        config["port"] = 55000 + i
        config["metrics_port"] = 13000 + i
        config["age"] = 1000000 + (i * 1000)
        config["records"] = i * 100
        n = Node(**config)
        db_session.add(n)
        nodes.append(n)
    db_session.commit()
    return nodes
