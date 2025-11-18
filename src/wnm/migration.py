"""
Migration and node discovery utilities.

This module handles surveying existing nodes from process managers for
database initialization and migration from anm (Autonomi Node Manager).

These functions are only used during initialization, not regular operation.
The database is the source of truth for node management.
"""

import logging

from wnm.common import METRICS_PORT_BASE, PORT_MULTIPLIER
from wnm.process_managers.factory import get_default_manager_type, get_process_manager


def detect_port_ranges_from_nodes(nodes: list) -> dict:
    """
    Detect port_start and metrics_port_start from discovered nodes.

    This function looks for node 1 in the discovered nodes and reverse-engineers
    the port configuration from its port assignments. If node 1 is not found,
    it attempts to calculate from the lowest-numbered node.

    Port formulas:
        node_port = port_start * 1000 + node_id
        metrics_port = 13000 + node_id

    Args:
        nodes: List of node dictionaries from survey_nodes()

    Returns:
        Dictionary with 'port_start' and 'metrics_port_start' keys, or empty dict if cannot detect
    """
    if not nodes:
        logging.debug("No nodes to detect port ranges from")
        return {}

    def _extract_node_id(node_dict):
        """Extract numeric node ID from node dictionary."""
        # Try direct 'id' field first
        node_id = node_dict.get("id")
        if node_id is not None:
            return node_id

        # Try extracting from 'node_name'
        if "node_name" in node_dict:
            node_name = node_dict["node_name"]
            # Handle formats like "antnode1", "antnode0001", or just "0001"
            import re
            match = re.search(r'\d+', str(node_name))
            if match:
                try:
                    return int(match.group())
                except (ValueError, TypeError):
                    pass
        return None

    # Try to find node 1 first (most reliable for port detection)
    node_1 = None
    for node in nodes:
        node_id = _extract_node_id(node)
        if node_id == 1:
            node_1 = node
            break

    # If node 1 not found, use the lowest-numbered node
    if node_1 is None:
        min_node_id = float("inf")
        for node in nodes:
            node_id = _extract_node_id(node)
            if node_id and node_id < min_node_id:
                min_node_id = node_id
                node_1 = node

    if node_1 is None:
        logging.debug("Could not find any node with valid ID for port detection (using defaults)")
        return {}

    # Extract node_id, port, and metrics_port
    node_id = _extract_node_id(node_1)
    if node_id is None:
        logging.warning("Could not extract node_id from node")
        return {}

    node_port = node_1.get("port")
    metrics_port = node_1.get("metrics_port")

    if not node_port or not metrics_port:
        logging.warning(
            f"Node {node_id} missing port information (port={node_port}, metrics_port={metrics_port})"
        )
        return {}

    # Reverse-engineer port_start from: node_port = port_start * 1000 + node_id
    # So: port_start = (node_port - node_id) / 1000
    calculated_port_start = (node_port - node_id) / PORT_MULTIPLIER

    # Validate it's a whole number
    if calculated_port_start != int(calculated_port_start):
        logging.warning(
            f"Calculated port_start {calculated_port_start} is not a whole number. "
            f"Node {node_id} has unusual port configuration (port={node_port})"
        )
        return {}

    port_start = int(calculated_port_start)

    # Verify metrics_port follows expected formula: 13000 + node_id
    expected_metrics_base = metrics_port - node_id
    if expected_metrics_base != METRICS_PORT_BASE:
        logging.warning(
            f"Node {node_id} has non-standard metrics port {metrics_port}. "
            f"Expected base {METRICS_PORT_BASE}, got {expected_metrics_base}"
        )
        # Use the detected value anyway
        metrics_port_start = expected_metrics_base
    else:
        metrics_port_start = METRICS_PORT_BASE

    logging.info(
        f"Detected port configuration from node {node_id}: "
        f"port_start={port_start}, metrics_port_start={metrics_port_start}"
    )

    return {
        "port_start": port_start,
        "metrics_port_start": metrics_port_start // 1000,  # Convert 13000 -> 13
    }


def survey_machine(machine_config, manager_type: str = None) -> list:
    """
    Survey all nodes managed by the process manager.

    This is used during database initialization/rebuild to discover
    existing nodes. The specific process manager handles its own path
    logic internally.

    Args:
        machine_config: Machine configuration object
        manager_type: Type of process manager ("systemd", "launchd", etc.)
                     If None, auto-detects from platform

    Returns:
        List of node dictionaries ready for database insertion
    """
    if manager_type is None:
        # Try to use manager type from machine config first
        if hasattr(machine_config, 'process_manager') and machine_config.process_manager:
            manager_type = machine_config.process_manager
        else:
            # Auto-detect manager type from platform
            manager_type = get_default_manager_type()

    logging.info(f"Surveying machine with {manager_type} manager")

    # Get the appropriate process manager
    manager = get_process_manager(manager_type)

    # Use the manager's survey_nodes() method
    return manager.survey_nodes(machine_config)
