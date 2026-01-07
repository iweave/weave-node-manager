"""
Node ID tracking utilities for antctl managers.

Handles initialization and allocation of node IDs to prevent port conflicts
when antctl doesn't free ports after node removal.
"""

import logging
from sqlalchemy import func

from wnm.models import Node


def initialize_node_id_tracking(session, machine_config):
    """
    Initialize highest_node_id_used if it's None.

    Called once on startup before any node operations.

    Args:
        session: SQLAlchemy session
        machine_config: Machine configuration object

    Returns:
        tuple: (needs_update, update_value)
               - needs_update: bool indicating if update is needed
               - update_value: int or None - the value to set
    """
    logger = logging.getLogger(__name__)

    # Check if initialization is needed
    if machine_config.highest_node_id_used is not None:
        # Already initialized
        return False, None

    # Query the maximum node ID from existing nodes
    max_node_id = session.query(func.max(Node.id)).scalar()

    if max_node_id:
        # Found existing nodes, set highest to max ID found
        logger.info(f"Initialized highest_node_id_used to {max_node_id} from existing nodes")
        return True, max_node_id
    else:
        # No existing nodes, initialize to 0 (next node will be ID 1)
        logger.info("Initialized highest_node_id_used to 0 (no existing nodes)")
        return True, 0


def allocate_node_id(machine_config):
    """
    Allocate a new node ID.

    Args:
        machine_config: Machine configuration object

    Returns:
        tuple: (node_id, update_dict)
               - node_id: int - the allocated node ID
               - update_dict: dict - database update for highest_node_id_used
    """
    logger = logging.getLogger(__name__)

    # Allocate new ID by incrementing highest
    if machine_config.highest_node_id_used is None:
        # Should have been initialized, but handle gracefully
        logger.warning("highest_node_id_used not initialized! Using 1")
        new_node_id = 1
    else:
        new_node_id = machine_config.highest_node_id_used + 1

    logger.debug(f"Allocated node ID: {new_node_id}")

    # Return new ID and update for database
    return new_node_id, {"highest_node_id_used": new_node_id}