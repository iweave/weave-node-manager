"""
Abstract base class for process managers.

Process managers handle node lifecycle operations across different
execution environments (systemd, docker, setsid, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from wnm.models import Node


@dataclass
class NodeProcess:
    """Represents the runtime state of a node process"""

    node_id: int
    pid: Optional[int] = None
    status: str = "UNKNOWN"  # RUNNING, STOPPED, UPGRADING, etc.
    container_id: Optional[str] = None  # For docker-managed nodes


class ProcessManager(ABC):
    """
    Abstract interface for node lifecycle management.

    Each implementation handles a specific process management backend:
    - SystemdManager: systemd services (Linux)
    - DockerManager: Docker containers
    - SetsidManager: Background processes via setsid
    - AntctlManager: Wrapper around antctl CLI
    - LaunchctlManager: macOS launchd services
    """

    @abstractmethod
    def create_node(self, node: Node, binary_path: str) -> bool:
        """
        Create and start a new node.

        Args:
            node: Node database record with configuration
            binary_path: Path to the node binary to execute

        Returns:
            True if node was created successfully
        """
        pass

    @abstractmethod
    def start_node(self, node: Node) -> bool:
        """
        Start a stopped node.

        Args:
            node: Node database record

        Returns:
            True if node started successfully
        """
        pass

    @abstractmethod
    def stop_node(self, node: Node) -> bool:
        """
        Stop a running node.

        Args:
            node: Node database record

        Returns:
            True if node stopped successfully
        """
        pass

    @abstractmethod
    def restart_node(self, node: Node) -> bool:
        """
        Restart a node.

        Args:
            node: Node database record

        Returns:
            True if node restarted successfully
        """
        pass

    @abstractmethod
    def get_status(self, node: Node) -> NodeProcess:
        """
        Get current runtime status of a node.

        Args:
            node: Node database record

        Returns:
            NodeProcess with current status and PID
        """
        pass

    @abstractmethod
    def remove_node(self, node: Node) -> bool:
        """
        Stop and remove all traces of a node.

        This should:
        1. Stop the node process
        2. Remove service/container definitions
        3. Optionally clean up data directories (controlled by node.keep_data)

        Args:
            node: Node database record

        Returns:
            True if node was removed successfully
        """
        pass

    @abstractmethod
    def enable_firewall_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Open firewall port for node communication.

        Args:
            port: Port number to open
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was opened successfully
        """
        pass

    @abstractmethod
    def disable_firewall_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Close firewall port when node is removed.

        Args:
            port: Port number to close
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was closed successfully
        """
        pass
