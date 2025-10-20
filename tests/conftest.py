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
        "CpuCount": 8,
        "NodeCap": 10,
        "CpuLessThan": 70,
        "CpuRemove": 85,
        "MemLessThan": 70,
        "MemRemove": 85,
        "HDLessThan": 80,
        "HDRemove": 90,
        "DelayStart": 5,
        "DelayUpgrade": 10,
        "DelayRemove": 15,
        "NodeStorage": "/tmp/test_nodes",
        "RewardsAddress": "0x1234567890123456789012345678901234567890",
        "DonateAddress": "0x0987654321098765432109876543210987654321",
        "MaxLoadAverageAllowed": 10.0,
        "DesiredLoadAverage": 5.0,
        "PortStart": 55,
        "HDIOReadLessThan": 1000000,
        "HDIOReadRemove": 5000000,
        "HDIOWriteLessThan": 1000000,
        "HDIOWriteRemove": 5000000,
        "NetIOReadLessThan": 1000000,
        "NetIOReadRemove": 5000000,
        "NetIOWriteLessThan": 1000000,
        "NetIOWriteRemove": 5000000,
        "LastStoppedAt": 0,
        "Host": "test-host",
        "CrisisBytes": 2000000000,
        "MetricsPortStart": 13000,
        "Environment": None,
        "StartArgs": None,
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
        "nodename": "test001",
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
        config["nodename"] = f"test{i:03d}"
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
