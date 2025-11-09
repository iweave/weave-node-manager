"""
Migration and node discovery utilities.

This module handles surveying existing nodes from process managers for
database initialization and migration from anm (Autonomi Node Manager).

These functions are only used during initialization, not regular operation.
The database is the source of truth for node management.
"""

import logging

from wnm.process_managers.factory import get_default_manager_type, get_process_manager


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
        # Auto-detect manager type from platform
        manager_type = get_default_manager_type()

    logging.info(f"Surveying machine with {manager_type} manager")

    # Get the appropriate process manager
    manager = get_process_manager(manager_type)

    # Use the manager's survey_nodes() method
    return manager.survey_nodes(machine_config)
