"""
Null firewall manager implementation.

A no-op firewall manager for systems where firewall management is
disabled, not needed, or handled externally (e.g., Docker networking).
"""

import logging

from wnm.firewall.base import FirewallManager


class NullFirewall(FirewallManager):
    """
    No-op firewall manager that performs no actual firewall operations.

    This is used when:
    - Firewall management is disabled in configuration
    - Running in Docker where port mapping handles exposure
    - Firewall is managed externally
    - Development/testing environments without firewall
    """

    def enable_port(
        self, port: int, protocol: str = "udp", comment: str = None
    ) -> bool:
        """
        No-op port enable operation.

        Args:
            port: Port number (ignored)
            protocol: Protocol type (ignored)
            comment: Comment (ignored)

        Returns:
            Always True
        """
        logging.debug(f"NullFirewall: Skipping enable for port {port}/{protocol}")
        return True

    def disable_port(self, port: int, protocol: str = "udp") -> bool:
        """
        No-op port disable operation.

        Args:
            port: Port number (ignored)
            protocol: Protocol type (ignored)

        Returns:
            Always True
        """
        logging.debug(f"NullFirewall: Skipping disable for port {port}/{protocol}")
        return True

    def is_enabled(self) -> bool:
        """
        Check if firewall is enabled.

        Returns:
            Always False (null firewall is never "enabled")
        """
        return False

    def is_available(self) -> bool:
        """
        Check if firewall is available.

        Returns:
            Always True (null firewall is always "available")
        """
        return True
