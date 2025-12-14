"""
Reports module for weave-node-manager (wnm).

Provides formatted reporting capabilities for node status and details.
"""

import json
import logging
import time
from typing import List, Optional

from sqlalchemy import select

from wnm.models import Node
from wnm.common import RUNNING, STOPPED, UPGRADING, RESTARTING, REMOVING, DISABLED, DEAD
from wnm.utils import parse_service_names


class NodeReporter:
    """
    Reporter class for generating node status reports.

    Supports two report types:
    - node-status: Tabular summary of nodes
    - node-status-details: Detailed node information
    """

    def __init__(self, session_factory):
        """
        Initialize reporter with database session factory.

        Args:
            session_factory: SQLAlchemy scoped_session factory
        """
        self.S = session_factory
        self.logger = logging.getLogger(__name__)

    def _get_nodes(self, service_names: Optional[List[str]] = None) -> List[Node]:
        """
        Retrieve nodes from database.

        Args:
            service_names: Optional list of specific service names to retrieve

        Returns:
            List of Node objects, ordered appropriately
        """
        with self.S() as session:
            if service_names:
                # Get specific nodes in the order requested
                nodes = []
                for service_name in service_names:
                    result = session.execute(
                        select(Node).where(Node.service == service_name)
                    ).first()
                    if result:
                        nodes.append(result[0])
                    else:
                        self.logger.warning(f"Node {service_name} not found in database")
                return nodes
            else:
                # Get all nodes ordered by ID (numerical order)
                results = session.execute(
                    select(Node).order_by(Node.id)
                ).all()
                return [row[0] for row in results]

    def node_status_report(
        self,
        service_name: Optional[str] = None,
        report_format: str = "text"
    ) -> str:
        """
        Generate tabular node status report.

        Format (text):
            Service Name    Peer ID       Status      Connected Peers
            antnode0001     12D3Koo...    RUNNING     4

        Format (json):
            [{"service_name": "antnode0001", "peer_id": "12D3Koo...",
              "status": "RUNNING", "connected_peers": 4}]

        Args:
            service_name: Optional comma-separated list of service names
            report_format: Output format ("text" or "json")

        Returns:
            Formatted string report
        """
        service_names = parse_service_names(service_name)
        nodes = self._get_nodes(service_names)

        if not nodes:
            if report_format == "json":
                return json.dumps({"error": "No nodes found"}, indent=2)
            return "No nodes found."

        if report_format == "json":
            # Build JSON output with only the specified fields
            node_dicts = []
            for node in nodes:
                node_dict = {
                    "service_name": node.service,
                    "peer_id": node.peer_id or "-",
                    "status": node.status,
                    "connected_peers": node.connected_peers if node.connected_peers is not None else 0,
                }
                node_dicts.append(node_dict)

            # If single node, return object; if multiple, return array
            if len(node_dicts) == 1:
                return json.dumps(node_dicts[0], indent=2)
            else:
                return json.dumps(node_dicts, indent=2)

        # Build text report
        lines = []

        # Header
        header = f"{'Service Name':<20}{'Peer ID':<55}{'Status':<15}{'Connected Peers':>15}"
        lines.append(header)

        # Node rows
        for node in nodes:
            service_col = f"{node.service:<20}"
            peer_id_col = f"{(node.peer_id or '-'):<55}"
            status_col = f"{node.status:<15}"
            # Connected peers from connected_peers field
            peers = node.connected_peers if node.connected_peers is not None else 0
            peers_col = f"{peers:>15}"

            lines.append(f"{service_col}{peer_id_col}{status_col}{peers_col}")

        return "\n".join(lines)

    def node_status_details_report(
        self,
        service_name: Optional[str] = None,
        report_format: str = "text"
    ) -> str:
        """
        Generate detailed node status report.

        Supports two formats:
        - text: key: value format
        - json: JSON format with snake_case keys

        Args:
            service_name: Optional comma-separated list of service names
            report_format: Output format ("text" or "json")

        Returns:
            Formatted string report
        """
        service_names = parse_service_names(service_name)
        nodes = self._get_nodes(service_names)

        if not nodes:
            if report_format == "json":
                return json.dumps({"error": "No nodes found"}, indent=2)
            return "No nodes found."

        if report_format == "json":
            return self._format_details_json(nodes)
        else:
            return self._format_details_text(nodes)

    def _format_details_text(self, nodes: List[Node]) -> str:
        """
        Format node details as text (key: value format).

        Args:
            nodes: List of Node objects

        Returns:
            Formatted text string
        """
        sections = []

        for node in nodes:
            lines = []

            # Service Name
            lines.append(f"Service Name: {node.service}")

            # Version
            lines.append(f"Version: {node.version or 'unknown'}")

            # Port
            lines.append(f"Port: {node.port}")

            # Metrics Port
            lines.append(f"Metrics Port: {node.metrics_port}")

            # Data path (root_dir)
            lines.append(f"Data path: {node.root_dir}")

            # Log path - construct from root_dir
            log_path = f"{node.root_dir}/logs" if node.root_dir else "unknown"
            lines.append(f"Log path: {log_path}")

            # Bin path - construct from root_dir and binary name
            bin_path = f"{node.root_dir}/{node.binary}" if node.root_dir and node.binary else "unknown"
            lines.append(f"Bin Path: {bin_path}")

            # Connected peers from connected_peers field
            connected_peers = node.connected_peers if node.connected_peers is not None else 0
            lines.append(f"Connected peers: {connected_peers}")

            # Rewards address from node's wallet field
            rewards_address = node.wallet or "unknown"
            lines.append(f"Rewards address: {rewards_address}")

            # Age in seconds
            age_seconds = node.age if node.age is not None else 0
            lines.append(f"Age: {age_seconds}")

            # Peer ID
            lines.append(f"Peer ID: {node.peer_id or '-'}")

            # Status
            lines.append(f"Status: {node.status}")

            sections.append("\n".join(lines))

        # Separate multiple nodes with blank line
        return "\n\n".join(sections)

    def _format_details_json(self, nodes: List[Node]) -> str:
        """
        Format node details as JSON using snake_case field names from model.

        Args:
            nodes: List of Node objects

        Returns:
            JSON formatted string
        """
        # Use the __json__ method from the Node model
        node_dicts = [node.__json__() for node in nodes]

        # If single node, return object; if multiple, return array
        if len(node_dicts) == 1:
            return json.dumps(node_dicts[0], indent=2)
        else:
            return json.dumps(node_dicts, indent=2)

    def influx_resources_report(
        self,
        service_name: Optional[str] = None,
    ) -> str:
        """
        Generate InfluxDB line protocol report for node metrics.

        Format (InfluxDB line protocol):
            nodes,id=1 PeerId="12D3...",status="RUNNING",version="0.4.7",gets=0i,puts=1i,... <timestamp>
            nodes_totals rewards="12345",nodes_running=5i,nodes_killed=2i <timestamp>
            nodes_network size=2064384i <timestamp>

        Args:
            service_name: Optional comma-separated list of service names

        Returns:
            InfluxDB line protocol formatted string
        """
        service_names = parse_service_names(service_name)
        nodes = self._get_nodes(service_names)

        if not nodes:
            return "# No nodes found"

        lines = []
        timestamp_ns = int(time.time() * 1_000_000_000)  # Current time in nanoseconds

        # Per-node metrics
        total_rewards = 0
        running_count = 0
        killed_count = 0
        total_network_size = 0
        network_size_count = 0

        for node in nodes:
            # Convert CPU and MEM back to decimals (they're stored * 100)
            cpu_val = node.cpu / 100.0 if node.cpu else 0.0
            mem_val = node.mem / 100.0 if node.mem else 0.0

            # Build tags (id only)
            tags = f"id={node.id}"

            # Build fields (all metrics)
            fields = []
            fields.append(f'PeerId="{node.peer_id or ""}"')
            fields.append(f'status="{node.status}"')
            fields.append(f'version="{node.version or ""}"')
            fields.append(f"gets={node.gets}i")
            fields.append(f"puts={node.puts}i")
            fields.append(f"up_time={node.uptime}i")
            fields.append(f'rewards="{node.rewards or "0"}"')  # String for precision
            fields.append(f"records={node.records}i")
            fields.append(f"connected_peers={node.connected_peers}i")
            fields.append(f"network_size={node.network_size}i")
            fields.append(f"open_connections={node.open_connections}i")
            fields.append(f"total_peers={node.total_peers}i")
            fields.append(f"shunned_count={node.shunned}i")
            fields.append(f"bad_peers={node.bad_peers}i")
            fields.append(f"mem={mem_val}")
            fields.append(f"cpu={cpu_val}")
            fields.append(f"rel_records={node.rel_records}i")
            fields.append(f"max_records={node.max_records}i")
            fields.append(f"payment_count={node.payment_count}i")
            fields.append(f"live_time={node.live_time}i")

            # Assemble line: measurement,tags fields timestamp
            line = f"nodes,{tags} {','.join(fields)} {timestamp_ns}"
            lines.append(line)

            # Accumulate totals
            try:
                total_rewards += float(node.rewards or "0")
            except ValueError:
                pass  # Skip non-numeric rewards

            if node.status == RUNNING:
                running_count += 1
            elif node.status in (STOPPED, DEAD):
                killed_count += 1

            # For network size, only count running nodes with non-zero estimates
            if node.status == RUNNING and node.network_size > 0:
                total_network_size += node.network_size
                network_size_count += 1

        # Totals line
        total_fields = []
        total_fields.append(f'rewards="{total_rewards}"')  # String for precision
        total_fields.append(f"nodes_running={running_count}i")
        total_fields.append(f"nodes_killed={killed_count}i")
        totals_line = f"nodes_totals {','.join(total_fields)} {timestamp_ns}"
        lines.append(totals_line)

        # Network size line (average of running nodes' estimates)
        if network_size_count > 0:
            avg_network_size = total_network_size // network_size_count
        else:
            avg_network_size = 0
        network_line = f"nodes_network size={avg_network_size}i {timestamp_ns}"
        lines.append(network_line)

        return "\n".join(lines)


def generate_node_status_report(
    session_factory,
    service_name: Optional[str] = None,
    report_format: str = "text"
) -> str:
    """
    Convenience function to generate node status report.

    Args:
        session_factory: SQLAlchemy scoped_session factory
        service_name: Optional comma-separated list of service names
        report_format: Output format ("text" or "json")

    Returns:
        Formatted report string
    """
    reporter = NodeReporter(session_factory)
    return reporter.node_status_report(service_name, report_format)


def generate_node_status_details_report(
    session_factory,
    service_name: Optional[str] = None,
    report_format: str = "text"
) -> str:
    """
    Convenience function to generate node status details report.

    Args:
        session_factory: SQLAlchemy scoped_session factory
        service_name: Optional comma-separated list of service names
        report_format: Output format ("text" or "json")

    Returns:
        Formatted report string
    """
    reporter = NodeReporter(session_factory)
    return reporter.node_status_details_report(service_name, report_format)


def generate_influx_resources_report(
    session_factory,
    service_name: Optional[str] = None,
) -> str:
    """
    Convenience function to generate InfluxDB line protocol report.

    Args:
        session_factory: SQLAlchemy scoped_session factory
        service_name: Optional comma-separated list of service names

    Returns:
        InfluxDB line protocol formatted string
    """
    reporter = NodeReporter(session_factory)
    return reporter.influx_resources_report(service_name)


def generate_machine_config_report(
    session_factory,
    dbpath: str,
    report_format: str = "text"
) -> str:
    """
    Generate a report of the machine configuration.

    Args:
        session_factory: SQLAlchemy scoped_session factory
        dbpath: Path to the database
        report_format: Output format ("text", "json", or "env")

    Returns:
        Formatted report string
    """
    from sqlalchemy import select
    from wnm.models import Machine

    with session_factory() as session:
        result = session.execute(select(Machine)).first()
        if not result:
            return "No machine configuration found"

        machine = result[0]
        config_dict = machine.__json__()

        # Add dbpath to the config
        config_dict["dbpath"] = dbpath

        # Fields that need quoting (paths and args with special characters)
        quoted_fields = {'node_storage', 'environment', 'start_args', 'antnode_path', 'dbpath'}

        if report_format == "json":
            return json.dumps(config_dict, indent=2)
        elif report_format == "env":
            # Environment variable format: UPPER_CASE_KEY="value"
            lines = []
            for key, value in config_dict.items():
                upper_key = key.upper()
                # Quote fields that may contain spaces or special characters
                if key in quoted_fields:
                    lines.append(f'{upper_key}="{value}"')
                else:
                    lines.append(f'{upper_key}={value}')
            return "\n".join(lines)
        elif report_format == "config":
            # Config file format: lower_snake_case_key="value"
            lines = []
            for key, value in config_dict.items():
                # Quote fields that may contain spaces or special characters
                if key in quoted_fields:
                    lines.append(f'{key}="{value}"')
                else:
                    lines.append(f'{key}={value}')
            return "\n".join(lines)
        else:
            # Text format: one entry per line
            lines = []
            for key, value in config_dict.items():
                lines.append(f"{key}: {value}")
            return "\n".join(lines)


def generate_machine_metrics_report(
    metrics: dict,
    report_format: str = "text"
) -> str:
    """
    Generate a report of the current system metrics.

    Args:
        metrics: Dictionary of system metrics from get_machine_metrics()
        report_format: Output format ("text", "json", or "env")

    Returns:
        Formatted report string
    """
    if not metrics:
        if report_format == "json":
            return json.dumps({"error": "No metrics available"}, indent=2)
        return "No metrics available"

    # Create a copy to avoid modifying the original
    metrics_output = dict(metrics)

    # Convert Counter object to regular dict for JSON serialization
    if "nodes_by_version" in metrics_output:
        metrics_output["nodes_by_version"] = dict(metrics_output["nodes_by_version"])

    if report_format == "json":
        return json.dumps(metrics_output, indent=2)
    elif report_format == "env":
        # Environment variable format: UPPER_CASE_KEY=value (quote dicts/complex values)
        # Fields that need quoting (paths with special characters)
        quoted_fields = {'antnode'}
        lines = []
        for key, value in metrics_output.items():
            upper_key = key.upper()
            # Quote dictionary values and path fields to make them env-safe
            if isinstance(value, dict) or key in quoted_fields:
                lines.append(f'{upper_key}="{value}"')
            else:
                lines.append(f'{upper_key}={value}')
        return "\n".join(lines)
    else:
        # Text format: one entry per line
        lines = []
        for key, value in metrics_output.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
