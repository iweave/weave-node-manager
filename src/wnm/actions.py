"""Action model for representing planned node operations.

This module defines the action types and data structures used by the decision engine
to represent planned operations on nodes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ActionType(Enum):
    """Types of actions that can be performed on nodes."""

    ADD_NODE = "add"
    REMOVE_NODE = "remove"
    UPGRADE_NODE = "upgrade"
    START_NODE = "start"
    STOP_NODE = "stop"
    RESTART_NODE = "restart"
    SURVEY_NODES = "survey"
    RESURVEY_NODES = "resurvey"


@dataclass
class Action:
    """Represents a planned action to be executed.

    Attributes:
        type: The type of action to perform
        node_id: Optional node ID if action is node-specific
        priority: Higher values indicate more urgent actions (default: 0)
        reason: Human-readable explanation of why this action is needed
    """

    type: ActionType
    node_id: Optional[int] = None
    priority: int = 0
    reason: str = ""

    def __repr__(self) -> str:
        """Return a string representation of the action."""
        if self.node_id is not None:
            return f"Action({self.type.value}, node={self.node_id}, reason={self.reason})"
        return f"Action({self.type.value}, reason={self.reason})"
