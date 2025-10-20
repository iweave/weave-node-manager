"""
Abstract base class for firewall managers.

Firewall managers handle opening/closing ports for node communication
across different firewall implementations.
"""

from abc import ABC, abstractmethod


class FirewallManager(ABC):
    """
    Abstract interface for firewall management.

    Each implementation handles a specific firewall backend:
    - UFWManager: Ubuntu's Uncomplicated Firewall (ufw)
    - FirewalldManager: Firewalld (RHEL/Fedora/CentOS)
    - IptablesManager: Direct iptables manipulation
    - NullFirewall: No-op implementation (firewall disabled)
    """

    @abstractmethod
    def enable_port(
        self, port: int, protocol: str = "udp", comment: str = None
    ) -> bool:
        """
        Open a firewall port for incoming traffic.

        Args:
            port: Port number to open
            protocol: Protocol type (udp/tcp)
            comment: Optional comment/description for the rule

        Returns:
            True if port was opened successfully, False otherwise
        """
        pass

    @abstractmethod
    def disable_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Close a firewall port, blocking incoming traffic.

        Args:
            port: Port number to close
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was closed successfully, False otherwise
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """
        Check if the firewall is enabled and active.

        Returns:
            True if firewall is active, False otherwise
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this firewall implementation is available on the system.

        Returns:
            True if firewall tools are installed, False otherwise
        """
        pass
