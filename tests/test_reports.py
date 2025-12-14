"""
Tests for the reports module.
"""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from wnm.models import Base, Machine, Node
from wnm.common import RUNNING, STOPPED, DISABLED
from wnm.reports import NodeReporter, generate_node_status_report, generate_node_status_details_report


@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    S = scoped_session(session_factory)

    # Create a machine config
    with S() as session:
        machine = Machine(
            cpu_count=4,
            node_cap=50,
            cpu_less_than=70,
            cpu_remove=80,
            mem_less_than=70,
            mem_remove=80,
            hd_less_than=70,
            hd_remove=80,
            delay_start=300,
            delay_restart=300,
            delay_upgrade=600,
            delay_remove=900,
            node_storage="/tmp/test",
            rewards_address="0x00455d78f850b0358E8cea5be24d415E01E107CF",
            donate_address="0x00455d78f850b0358E8cea5be24d415E01E107CF",
            max_load_average_allowed=10.0,
            desired_load_average=5.0,
            port_start=55,
            hdio_read_less_than=1000000,
            hdio_read_remove=5000000,
            hdio_write_less_than=1000000,
            hdio_write_remove=5000000,
            netio_read_less_than=1000000,
            netio_read_remove=5000000,
            netio_write_less_than=1000000,
            netio_write_remove=5000000,
            last_stopped_at=0,
            host="localhost",
            crisis_bytes=2000000000,
            metrics_port_start=13000,
            rpc_port_start=30,
            environment=None,
            start_args=None,
            max_concurrent_upgrades=1,
            max_concurrent_starts=2,
            max_concurrent_removals=1,
            node_removal_strategy="youngest",
        )
        session.add(machine)
        session.commit()

    yield S

    # Cleanup
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_nodes(db_session):
    """Create sample nodes for testing."""
    with db_session() as session:
        nodes = [
            Node(
                id=1,
                node_name="0001",
                service="antnode0001",
                user="test",
                binary="antnode",
                version="0.4.6",
                root_dir="/tmp/test/antnode0001",
                port=55001,
                metrics_port=13001,
                rpc_port=30001,
                network="mainnet",
                wallet="0x00455d78f850b0358E8cea5be24d415E01E107CF",
                peer_id="12D3KooWAgR9UqQ4MeYq5kfyEG29HktnnM6QRKdbWbYdghqxQj6s",
                status=RUNNING,
                timestamp=1234567890,
                records=100,
                uptime=3600,
                shunned=0,
                connected_peers=4,
                age=1234560000,
                host="localhost",
                method="launchd",
                layout="standard",
                environment=None,
            ),
            Node(
                id=2,
                node_name="0002",
                service="antnode0002",
                user="test",
                binary="antnode",
                version="0.4.6",
                root_dir="/tmp/test/antnode0002",
                port=55002,
                metrics_port=13002,
                rpc_port=30002,
                network="mainnet",
                wallet="0x00455d78f850b0358E8cea5be24d415E01E107CF",
                peer_id="12D3KooWXyZ123456789012345678901234567890123456789012",
                status=STOPPED,
                timestamp=1234567890,
                records=50,
                uptime=0,
                shunned=1,
                connected_peers=0,
                age=1234560000,
                host="localhost",
                method="launchd",
                layout="standard",
                environment=None,
            ),
            Node(
                id=3,
                node_name="0003",
                service="antnode0003",
                user="test",
                binary="antnode",
                version="0.4.5",
                root_dir="/tmp/test/antnode0003",
                port=55003,
                metrics_port=13003,
                rpc_port=30003,
                network="mainnet",
                wallet="0x11111111111111111111111111111111111111111",
                peer_id=None,  # No peer ID yet
                status=RUNNING,
                timestamp=1234567890,
                records=200,
                uptime=7200,
                shunned=0,
                connected_peers=8,
                age=1234560000,
                host="localhost",
                method="launchd",
                layout="standard",
                environment=None,
            ),
        ]
        for node in nodes:
            session.add(node)
        session.commit()

    return nodes


class TestNodeReporter:
    """Test the NodeReporter class."""

    def test_parse_service_names_single(self):
        """Test parsing a single service name."""
        from wnm.utils import parse_service_names
        result = parse_service_names("antnode0001")
        assert result == ["antnode0001"]

    def test_parse_service_names_multiple(self):
        """Test parsing comma-separated service names."""
        from wnm.utils import parse_service_names
        result = parse_service_names("antnode0001,antnode0002,antnode0003")
        assert result == ["antnode0001", "antnode0002", "antnode0003"]

    def test_parse_service_names_with_spaces(self):
        """Test parsing service names with whitespace."""
        from wnm.utils import parse_service_names
        result = parse_service_names("antnode0001 , antnode0002 , antnode0003")
        assert result == ["antnode0001", "antnode0002", "antnode0003"]

    def test_parse_service_names_none(self):
        """Test parsing None input."""
        from wnm.utils import parse_service_names
        result = parse_service_names(None)
        assert result is None

    def test_parse_service_names_empty(self):
        """Test parsing empty string."""
        from wnm.utils import parse_service_names
        result = parse_service_names("")
        assert result is None

    def test_get_nodes_all(self, db_session, sample_nodes):
        """Test retrieving all nodes."""
        reporter = NodeReporter(db_session)
        nodes = reporter._get_nodes()
        assert len(nodes) == 3
        # Should be ordered by ID
        assert nodes[0].id == 1
        assert nodes[1].id == 2
        assert nodes[2].id == 3

    def test_get_nodes_specific(self, db_session, sample_nodes):
        """Test retrieving specific nodes in order."""
        reporter = NodeReporter(db_session)
        nodes = reporter._get_nodes(["antnode0003", "antnode0001"])
        assert len(nodes) == 2
        # Should be in requested order
        assert nodes[0].service == "antnode0003"
        assert nodes[1].service == "antnode0001"

    def test_get_nodes_nonexistent(self, db_session, sample_nodes):
        """Test retrieving nonexistent node."""
        reporter = NodeReporter(db_session)
        nodes = reporter._get_nodes(["antnode9999"])
        assert len(nodes) == 0

    def test_node_status_report_all(self, db_session, sample_nodes):
        """Test node-status report with all nodes."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_report()

        # Check that report contains expected data
        assert "Service Name" in report
        assert "Peer ID" in report
        assert "Status" in report
        assert "Connected Peers" in report

        assert "antnode0001" in report
        assert "antnode0002" in report
        assert "antnode0003" in report

        assert "12D3KooWAgR9UqQ4MeYq5kfyEG29HktnnM6QRKdbWbYdghqxQj6s" in report
        assert "RUNNING" in report
        assert "STOPPED" in report

        # Check connected peers column
        lines = report.split("\n")
        assert len(lines) >= 4  # Header + 3 nodes

    def test_node_status_report_specific(self, db_session, sample_nodes):
        """Test node-status report with specific nodes."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_report("antnode0001,antnode0003")

        assert "antnode0001" in report
        assert "antnode0003" in report
        assert "antnode0002" not in report

        # Check order is preserved
        lines = report.split("\n")
        antnode1_line = next(i for i, line in enumerate(lines) if "antnode0001" in line)
        antnode3_line = next(i for i, line in enumerate(lines) if "antnode0003" in line)
        assert antnode1_line < antnode3_line

    def test_node_status_report_no_nodes(self, db_session):
        """Test node-status report with no nodes."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_report()
        assert report == "No nodes found."

    def test_node_status_report_json(self, db_session, sample_nodes):
        """Test node-status report in JSON format."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_report(report_format="json")

        # Parse JSON
        data = json.loads(report)

        # Should be a list of nodes
        assert isinstance(data, list)
        assert len(data) == 3

        # Check first node structure
        node1 = data[0]
        assert node1["service_name"] == "antnode0001"
        assert node1["peer_id"] == "12D3KooWAgR9UqQ4MeYq5kfyEG29HktnnM6QRKdbWbYdghqxQj6s"
        assert node1["status"] == "RUNNING"
        assert node1["connected_peers"] == 4

        # Check that it only has the expected fields
        assert set(node1.keys()) == {"service_name", "peer_id", "status", "connected_peers"}

    def test_node_status_report_json_single_node(self, db_session, sample_nodes):
        """Test node-status report in JSON format for single node."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_report(
            service_name="antnode0001", report_format="json"
        )

        # Parse JSON
        data = json.loads(report)

        # Should be a single object (not array)
        assert isinstance(data, dict)
        assert data["service_name"] == "antnode0001"
        assert data["connected_peers"] == 4
        assert set(data.keys()) == {"service_name", "peer_id", "status", "connected_peers"}

    def test_node_status_report_json_no_nodes(self, db_session):
        """Test node-status report JSON with no nodes."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_report(report_format="json")
        data = json.loads(report)
        assert data == {"error": "No nodes found"}

    def test_node_status_details_text(self, db_session, sample_nodes):
        """Test node-status-details report in text format."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_details_report(report_format="text")

        # Check for expected fields
        assert "Service Name:" in report
        assert "Version:" in report
        assert "Port:" in report
        assert "Metrics Port:" in report
        assert "Data path:" in report
        assert "Log path:" in report
        assert "Bin Path:" in report
        assert "Connected peers:" in report
        assert "Rewards address:" in report
        assert "Age:" in report
        assert "Peer ID:" in report
        assert "Status:" in report

        # Check for node data
        assert "antnode0001" in report
        assert "0.4.6" in report
        assert "55001" in report
        assert "13001" in report
        assert "/tmp/test/antnode0001" in report
        assert "0x00455d78f850b0358E8cea5be24d415E01E107CF" in report

    def test_node_status_details_json(self, db_session, sample_nodes):
        """Test node-status-details report in JSON format."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_details_report(report_format="json")

        # Parse JSON
        data = json.loads(report)

        # Should be a list of nodes
        assert isinstance(data, list)
        assert len(data) == 3

        # Check first node structure
        node1 = data[0]
        assert node1["service"] == "antnode0001"
        assert node1["version"] == "0.4.6"
        assert node1["port"] == 55001
        assert node1["metrics_port"] == 13001
        assert node1["connected_peers"] == 4
        assert node1["wallet"] == "0x00455d78f850b0358E8cea5be24d415E01E107CF"
        assert node1["status"] == "RUNNING"

    def test_node_status_details_json_single_node(self, db_session, sample_nodes):
        """Test node-status-details report in JSON format for single node."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_details_report(
            service_name="antnode0001", report_format="json"
        )

        # Parse JSON
        data = json.loads(report)

        # Should be a single object (not array)
        assert isinstance(data, dict)
        assert data["service"] == "antnode0001"

    def test_node_status_details_no_nodes(self, db_session):
        """Test node-status-details with no nodes."""
        reporter = NodeReporter(db_session)
        report = reporter.node_status_details_report(report_format="text")
        assert report == "No nodes found."

        report_json = reporter.node_status_details_report(report_format="json")
        data = json.loads(report_json)
        assert data == {"error": "No nodes found"}


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_generate_node_status_report(self, db_session, sample_nodes):
        """Test generate_node_status_report function."""
        report = generate_node_status_report(db_session)
        assert "antnode0001" in report
        assert "Service Name" in report

    def test_generate_node_status_details_report(self, db_session, sample_nodes):
        """Test generate_node_status_details_report function."""
        report = generate_node_status_details_report(db_session)
        assert "Service Name:" in report
        assert "antnode0001" in report

    def test_generate_node_status_details_report_json(self, db_session, sample_nodes):
        """Test generate_node_status_details_report with JSON format."""
        report = generate_node_status_details_report(db_session, report_format="json")
        data = json.loads(report)
        assert isinstance(data, list)
        assert len(data) == 3


class TestMachineConfigReport:
    """Test machine config report generation."""

    def test_generate_machine_config_report_text(self, db_session):
        """Test machine-config report in text format."""
        from wnm.reports import generate_machine_config_report

        report = generate_machine_config_report(db_session, "/tmp/test.db", "text")
        assert "cpu_count: 4" in report
        assert "node_cap: 50" in report
        assert "cpu_less_than: 70" in report
        assert "rewards_address: 0x00455d78f850b0358E8cea5be24d415E01E107CF" in report
        assert "dbpath: /tmp/test.db" in report

    def test_generate_machine_config_report_json(self, db_session):
        """Test machine-config report in JSON format."""
        from wnm.reports import generate_machine_config_report

        report = generate_machine_config_report(db_session, "/tmp/test.db", "json")
        data = json.loads(report)
        assert isinstance(data, dict)
        assert data["cpu_count"] == 4
        assert data["node_cap"] == 50
        assert data["cpu_less_than"] == 70
        assert data["rewards_address"] == "0x00455d78f850b0358E8cea5be24d415E01E107CF"
        assert data["dbpath"] == "/tmp/test.db"

    def test_generate_machine_config_report_env(self, db_session):
        """Test machine-config report in env format."""
        from wnm.reports import generate_machine_config_report

        report = generate_machine_config_report(db_session, "/tmp/test.db", "env")

        # Check that variables are uppercase
        assert 'CPU_COUNT=4' in report
        assert 'NODE_CAP=50' in report
        assert 'CPU_LESS_THAN=70' in report
        assert 'CPU_REMOVE=80' in report
        assert 'MEM_LESS_THAN=70' in report
        assert 'MEM_REMOVE=80' in report
        assert 'REWARDS_ADDRESS=0x00455d78f850b0358E8cea5be24d415E01E107CF' in report

        # Check that path fields are quoted
        assert 'DBPATH="/tmp/test.db"' in report
        assert 'NODE_STORAGE="/tmp/test"' in report
        # ANTNODE_PATH should be quoted (has default value)
        assert 'ANTNODE_PATH="' in report
        # ENVIRONMENT and START_ARGS should be quoted even if None
        assert 'ENVIRONMENT="None"' in report
        assert 'START_ARGS="None"' in report


class TestMachineMetricsReport:
    """Test machine metrics report generation."""

    def test_generate_machine_metrics_report_text(self):
        """Test machine-metrics report in text format."""
        from collections import Counter
        from wnm.reports import generate_machine_metrics_report

        metrics = {
            "cpu": 45.2,
            "mem": 62.8,
            "nodes_running": 5,
            "nodes_stopped": 2,
            "nodes_by_version": Counter({"0.4.7": 3, "0.4.8": 2}),
        }

        report = generate_machine_metrics_report(metrics, "text")
        assert "cpu: 45.2" in report
        assert "mem: 62.8" in report
        assert "nodes_running: 5" in report
        assert "nodes_stopped: 2" in report

    def test_generate_machine_metrics_report_json(self):
        """Test machine-metrics report in JSON format."""
        from collections import Counter
        from wnm.reports import generate_machine_metrics_report

        metrics = {
            "cpu": 45.2,
            "mem": 62.8,
            "nodes_running": 5,
            "nodes_stopped": 2,
            "nodes_by_version": Counter({"0.4.7": 3, "0.4.8": 2}),
        }

        report = generate_machine_metrics_report(metrics, "json")
        data = json.loads(report)
        assert data["cpu"] == 45.2
        assert data["mem"] == 62.8
        assert data["nodes_running"] == 5
        assert data["nodes_stopped"] == 2
        assert isinstance(data["nodes_by_version"], dict)
        assert data["nodes_by_version"]["0.4.7"] == 3
        assert data["nodes_by_version"]["0.4.8"] == 2

    def test_generate_machine_metrics_report_env(self):
        """Test machine-metrics report in env format."""
        from collections import Counter
        from wnm.reports import generate_machine_metrics_report

        metrics = {
            "cpu": 45.2,
            "mem": 62.8,
            "nodes_running": 5,
            "nodes_stopped": 2,
            "nodes_by_version": Counter({"0.4.7": 3, "0.4.8": 2}),
        }

        report = generate_machine_metrics_report(metrics, "env")

        # Check that variables are uppercase
        assert 'CPU=45.2' in report
        assert 'MEM=62.8' in report
        assert 'NODES_RUNNING=5' in report
        assert 'NODES_STOPPED=2' in report

        # Check that dictionary values are quoted for env-safety
        assert 'NODES_BY_VERSION="' in report
        # The dict should be quoted
        lines = report.split('\n')
        nodes_by_version_line = next(line for line in lines if line.startswith('NODES_BY_VERSION='))
        # Should start with quote after =
        assert nodes_by_version_line.startswith('NODES_BY_VERSION="')
        # Should end with quote
        assert nodes_by_version_line.endswith('"')

    def test_generate_machine_metrics_report_env_no_quotes_on_numbers(self):
        """Test that env format doesn't quote numeric values."""
        from wnm.reports import generate_machine_metrics_report

        metrics = {
            "cpu": 45.2,
            "mem": 62.8,
            "nodes_running": 5,
        }

        report = generate_machine_metrics_report(metrics, "env")

        # Numeric values should NOT have quotes
        assert 'CPU=45.2' in report
        assert 'CPU="45.2"' not in report
        assert 'MEM=62.8' in report
        assert 'MEM="62.8"' not in report
        assert 'NODES_RUNNING=5' in report
        assert 'NODES_RUNNING="5"' not in report

    def test_generate_machine_metrics_report_env_antnode_quoted(self):
        """Test that env format quotes the ANTNODE path field."""
        from wnm.reports import generate_machine_metrics_report

        metrics = {
            "cpu": 45.2,
            "antnode": "/usr/local/bin/antnode",
        }

        report = generate_machine_metrics_report(metrics, "env")

        # ANTNODE path should be quoted
        assert 'ANTNODE="/usr/local/bin/antnode"' in report

    def test_generate_machine_metrics_report_env_antnode_with_spaces(self):
        """Test that env format quotes ANTNODE path with spaces."""
        from wnm.reports import generate_machine_metrics_report

        metrics = {
            "cpu": 45.2,
            "antnode": "/path/with spaces/antnode",
        }

        report = generate_machine_metrics_report(metrics, "env")

        # ANTNODE path with spaces should be quoted
        assert 'ANTNODE="/path/with spaces/antnode"' in report

