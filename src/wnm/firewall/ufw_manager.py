"""
UFW (Uncomplicated Firewall) manager implementation.

Manages firewall ports using Ubuntu's ufw command-line tool.
Requires sudo privileges for port operations.
"""

import logging
import shutil
import subprocess

from wnm.firewall.base import FirewallManager


class UFWManager(FirewallManager):
    """
    Firewall manager for Ubuntu's Uncomplicated Firewall (ufw).

    Uses 'sudo ufw' commands to manage port rules.
    """

    def enable_port(
        self, port: int, protocol: str = "udp", comment: str = None
    ) -> bool:
        """
        Open a firewall port using ufw.

        Args:
            port: Port number to open
            protocol: Protocol type (udp/tcp)
            comment: Optional comment for the rule

        Returns:
            True if port was opened successfully
        """
        if not self.is_available():
            logging.warning("UFW is not available on this system")
            return False

        logging.info(f"Opening firewall port {port}/{protocol}")

        try:
            cmd = ["sudo", "ufw", "allow", f"{port}/{protocol}"]
            if comment:
                cmd.extend(["comment", comment])

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            return True

        except (subprocess.CalledProcessError, Exception) as err:
            logging.error(f"Failed to open firewall port: {err}")
            return False

    def disable_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Close a firewall port using ufw.

        Args:
            port: Port number to close
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was closed successfully
        """
        if not self.is_available():
            logging.warning("UFW is not available on this system")
            return False

        logging.info(f"Closing firewall port {port}/{protocol}")

        try:
            subprocess.run(
                ["sudo", "ufw", "delete", "allow", f"{port}/{protocol}"],
                check=True,
                capture_output=True,
                text=True,
            )
            return True

        except (subprocess.CalledProcessError, Exception) as err:
            logging.error(f"Failed to close firewall port: {err}")
            return False

    def is_enabled(self) -> bool:
        """
        Check if UFW is active.

        Returns:
            True if ufw is active, False otherwise
        """
        if not self.is_available():
            return False

        try:
            result = subprocess.run(
                ["sudo", "ufw", "status"],
                check=True,
                capture_output=True,
                text=True,
            )
            return "Status: active" in result.stdout

        except subprocess.CalledProcessError:
            return False

    def is_available(self) -> bool:
        """
        Check if ufw is installed on the system.

        Returns:
            True if ufw command is available
        """
        return shutil.which("ufw") is not None
