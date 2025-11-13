"""
Abstract base class for process managers.

Process managers handle node lifecycle operations across different
execution environments (systemd, docker, setsid, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from wnm.firewall.factory import get_firewall_manager
from wnm.models import Node


@dataclass
class NodeProcess:
    """Represents the runtime state of a node process"""

    node_id: int
    pid: Optional[int] = None
    status: str = "UNKNOWN"  # RUNNING, STOPPED, UPGRADING, etc.
    container_id: Optional[str] = None  # For docker-managed nodes
    external_node_id: Optional[str] = None  # For external IDs (e.g., antctl service_name)


class ProcessManager(ABC):
    """
    Abstract interface for node lifecycle management.

    Each implementation handles a specific process management backend:
    - SystemdManager: systemd services (Linux)
    - DockerManager: Docker containers
    - SetsidManager: Background processes via setsid
    - AntctlManager: Wrapper around antctl CLI
    - LaunchdManager: macOS launchd services
    """

    def __init__(self, firewall_type: str = None):
        """
        Initialize process manager with optional firewall manager.

        Args:
            firewall_type: Type of firewall to use ("ufw", "null", etc.)
                          If None, auto-detects best available option
        """
        self.firewall = get_firewall_manager(firewall_type)

    @abstractmethod
    def create_node(self, node: Node, binary_path: str) -> Optional[NodeProcess]:
        """
        Create and start a new node.

        Args:
            node: Node database record with configuration
            binary_path: Path to the node binary to execute

        Returns:
            NodeProcess with metadata (container_id, external_node_id, etc.) if successful
            None if creation failed
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
    def survey_nodes(self, machine_config) -> list:
        """
        Survey all nodes managed by this process manager.

        This is used during database initialization/rebuild to discover
        existing nodes by scanning the manager's configuration directory.
        Each manager handles its own path logic internally.

        The database is the source of truth for regular operations.
        This method is ONLY used for initialization and migration.

        Args:
            machine_config: Machine configuration object

        Returns:
            List of node dictionaries ready for database insertion
        """
        pass

    def enable_firewall_port(
        self, port: int, protocol: str = "udp", comment: str = None
    ) -> bool:
        """
        Open firewall port for node communication.

        Uses the configured firewall manager to open the port.
        Subclasses can override for custom firewall behavior.

        Args:
            port: Port number to open
            protocol: Protocol type (udp/tcp)
            comment: Optional comment for the firewall rule

        Returns:
            True if port was opened successfully
        """
        return self.firewall.enable_port(port, protocol, comment)

    def disable_firewall_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Close firewall port when node is removed.

        Uses the configured firewall manager to close the port.
        Subclasses can override for custom firewall behavior.

        Args:
            port: Port number to close
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was closed successfully
        """
        return self.firewall.disable_port(port, protocol)

    def teardown_cluster(self) -> bool:
        """
        Teardown the entire cluster using manager-specific commands.

        This is an optional method that managers can override to provide
        efficient bulk teardown operations. If not overridden, returns False
        to indicate that individual node removal should be used instead.

        Examples:
            - AntctlManager: Uses 'antctl reset' command
            - Other managers: Return False to use default individual removal

        Returns:
            True if cluster was torn down successfully using manager-specific method,
            False to indicate fallback to individual node removal
        """
        return False
