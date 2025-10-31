"""
Reports module for weave-node-manager (wnm).

Provides formatted reporting capabilities for node status and details.
"""

import json
import logging
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
