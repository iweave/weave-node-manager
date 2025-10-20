"""
SystemdManager: Manage nodes via systemd services.

Handles node lifecycle operations using systemd unit files and systemctl commands.
Requires sudo privileges for systemctl and firewall operations.
"""

import logging
import os
import re
import subprocess
import time

from wnm.common import DEAD, RESTARTING, RUNNING, STOPPED, UPGRADING
from wnm.models import Node
from wnm.process_managers.base import NodeProcess, ProcessManager


class SystemdManager(ProcessManager):
    """Manage nodes as systemd services"""

    def __init__(self, session_factory=None):
        """
        Initialize SystemdManager.

        Args:
            session_factory: SQLAlchemy session factory (optional, for status updates)
        """
        self.S = session_factory

    def create_node(self, node: Node, binary_path: str) -> bool:
        """
        Create and start a new node as a systemd service.

        Args:
            node: Node database record with configuration
            binary_path: Path to the antnode binary

        Returns:
            True if node was created successfully
        """
        logging.info(f"Creating systemd node {node.id}")

        # Prepare service name
        service_name = f"antnode{node.node_name}.service"
        log_dir = f"/var/log/antnode/antnode{node.node_name}"

        # Create directories
        try:
            subprocess.run(
                ["sudo", "mkdir", "-p", node.root_dir, log_dir],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to create directories: {err}")
            return False

        # Copy binary to node directory
        try:
            subprocess.run(
                ["sudo", "cp", binary_path, node.root_dir],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to copy binary: {err}")
            return False

        # Change ownership
        user = getattr(node, "user", "ant")
        try:
            subprocess.run(
                ["sudo", "chown", "-R", f"{user}:{user}", node.root_dir, log_dir],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to change ownership: {err}")
            return False

        # Build systemd service unit
        env_string = (
            f'Environment="{node.environment}"' if node.environment else ""
        )
        binary_in_node_dir = f"{node.root_dir}/antnode"

        service_content = f"""[Unit]
Description=antnode{node.node_name}
[Service]
{env_string}
User={user}
ExecStart={binary_in_node_dir} --bootstrap-cache-dir /var/antctl/bootstrap-cache --root-dir {node.root_dir} --port {node.port} --enable-metrics-server --metrics-server-port {node.metrics_port} --log-output-dest {log_dir} --max-log-files 1 --max-archived-log-files 1 --rewards-address {node.wallet} {node.network}
Restart=always
#RestartSec=300
"""

        # Write service file
        try:
            subprocess.run(
                ["sudo", "tee", f"/etc/systemd/system/{service_name}"],
                input=service_content,
                text=True,
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to write service file: {err}")
            return False

        # Reload systemd
        try:
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to reload systemd: {err}")
            return False

        # Start the node
        return self.start_node(node)

    def start_node(self, node: Node) -> bool:
        """
        Start a systemd node.

        Args:
            node: Node database record

        Returns:
            True if node started successfully
        """
        logging.info(f"Starting systemd node {node.id}")

        # Start service
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "start", node.service],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if "Failed to start" in result.stdout:
                logging.error(f"Failed to start node: {result.stdout}")
                return False
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to start node: {err}")
            return False

        # Open firewall port
        self.enable_firewall_port(node.port)

        # Update status if we have a session factory
        if self.S:
            self._set_node_status(node.id, RESTARTING)

        return True

    def stop_node(self, node: Node) -> bool:
        """
        Stop a systemd node.

        Args:
            node: Node database record

        Returns:
            True if node stopped successfully
        """
        logging.info(f"Stopping systemd node {node.id}")

        # Stop service
        try:
            subprocess.run(
                ["sudo", "systemctl", "stop", node.service],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to stop node: {err}")
            return False

        # Close firewall port
        self.disable_firewall_port(node.port)

        # Update status
        if self.S:
            self._set_node_status(node.id, STOPPED)

        return True

    def restart_node(self, node: Node) -> bool:
        """
        Restart a systemd node.

        Args:
            node: Node database record

        Returns:
            True if node restarted successfully
        """
        logging.info(f"Restarting systemd node {node.id}")

        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", node.service],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to restart node: {err}")
            return False

        # Update status
        if self.S:
            self._set_node_status(node.id, RESTARTING)

        return True

    def get_status(self, node: Node) -> NodeProcess:
        """
        Get current status of a systemd node.

        Args:
            node: Node database record

        Returns:
            NodeProcess with current status
        """
        try:
            result = subprocess.run(
                ["systemctl", "show", node.service, "--property=MainPID,ActiveState"],
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            )

            # Parse output
            lines = result.stdout.strip().split("\n")
            state_info = dict(line.split("=", 1) for line in lines if "=" in line)

            pid = int(state_info.get("MainPID", 0))
            active_state = state_info.get("ActiveState", "unknown")

            # Map systemd state to our status
            if active_state == "active":
                status = RUNNING
            elif active_state == "inactive" or active_state == "failed":
                status = STOPPED
            else:
                status = "UNKNOWN"

            # Check if root directory exists
            if not os.path.isdir(node.root_dir):
                status = DEAD

            return NodeProcess(node_id=node.id, pid=pid if pid > 0 else None, status=status)

        except (subprocess.CalledProcessError, ValueError, KeyError) as err:
            logging.error(f"Failed to get node status: {err}")
            return NodeProcess(node_id=node.id, pid=None, status="UNKNOWN")

    def remove_node(self, node: Node) -> bool:
        """
        Stop and remove a systemd node.

        Args:
            node: Node database record

        Returns:
            True if node was removed successfully
        """
        logging.info(f"Removing systemd node {node.id}")

        # Stop the node first
        self.stop_node(node)

        nodename = f"antnode{node.node_name}"

        # Remove data and logs
        try:
            subprocess.run(
                ["sudo", "rm", "-rf", node.root_dir, f"/var/log/antnode/{nodename}"],
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to remove node data: {err}")

        # Remove service file
        try:
            subprocess.run(
                ["sudo", "rm", "-f", f"/etc/systemd/system/{node.service}"],
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to remove service file: {err}")

        # Reload systemd
        try:
            subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to reload systemd: {err}")

        return True

    def enable_firewall_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Open firewall port using ufw.

        Args:
            port: Port number to open
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was opened successfully
        """
        logging.info(f"Opening firewall port {port}/{protocol}")

        try:
            subprocess.run(
                ["sudo", "ufw", "allow", f"{port}/{protocol}"],
                stdout=subprocess.PIPE,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to open firewall port: {err}")
            return False

    def disable_firewall_port(self, port: int, protocol: str = "udp") -> bool:
        """
        Close firewall port using ufw.

        Args:
            port: Port number to close
            protocol: Protocol type (udp/tcp)

        Returns:
            True if port was closed successfully
        """
        logging.info(f"Closing firewall port {port}/{protocol}")

        try:
            subprocess.run(
                ["sudo", "ufw", "delete", "allow", f"{port}/{protocol}"],
                stdout=subprocess.PIPE,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to close firewall port: {err}")
            return False

    def _set_node_status(self, node_id: int, status: str):
        """Helper to update node status in database"""
        if not self.S:
            return

        try:
            with self.S() as session:
                session.query(Node).filter(Node.id == node_id).update(
                    {"status": status, "timestamp": int(time.time())}
                )
                session.commit()
        except Exception as e:
            logging.error(f"Failed to set node status for {node_id}: {e}")
