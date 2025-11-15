"""
SystemdManager: Manage nodes via systemd services.

Handles node lifecycle operations using systemd unit files and systemctl commands.
Requires sudo privileges for systemctl and firewall operations.
"""

import logging
import os
import re
import shutil
import subprocess
import time

from wnm.common import DEAD, RESTARTING, RUNNING, STOPPED, UPGRADING
from wnm.config import BOOTSTRAP_CACHE_DIR, IS_ROOT, LOG_DIR
from wnm.models import Node
from wnm.process_managers.base import NodeProcess, ProcessManager
from wnm.utils import (
    get_antnode_version,
    get_node_age,
    read_node_metadata,
    read_node_metrics,
)


class SystemdManager(ProcessManager):
    """Manage nodes as systemd services (system or user mode)"""

    def __init__(self, session_factory=None, firewall_type: str = None, mode: str = None):
        """
        Initialize SystemdManager.

        Args:
            session_factory: SQLAlchemy session factory (optional, for status updates)
            firewall_type: Type of firewall to use (defaults to auto-detect, null for non-root)
            mode: Operation mode - "sudo" for system services with sudo, "user" for user services
        """
        # Determine if we're using system or user services based on mode parameter
        # mode="sudo": Use system services in /etc/systemd/system/ with sudo (production)
        # mode="user": Use user services in ~/.config/systemd/user/ without sudo (default)
        if mode == "sudo":
            self.use_system_services = True
        elif mode == "user":
            self.use_system_services = False
        else:
            # Fallback to IS_ROOT for backward compatibility
            self.use_system_services = IS_ROOT

        # Configure firewall based on mode
        if self.use_system_services:
            # System services mode: use ufw firewall by default (requires sudo)
            if firewall_type is None:
                firewall_type = "ufw"
        else:
            # User services mode: use null firewall by default (no sudo)
            if firewall_type is None:
                firewall_type = "null"

        super().__init__(firewall_type)
        self.S = session_factory

        if self.use_system_services:
            self.service_dir = "/etc/systemd/system"
            self.systemctl_cmd = ["sudo", "systemctl"]
        else:
            self.service_dir = os.path.expanduser("~/.config/systemd/user")
            self.systemctl_cmd = ["systemctl", "--user"]
            # Create user service directory if it doesn't exist
            os.makedirs(self.service_dir, exist_ok=True)

    def create_node(self, node: Node, binary_path: str) -> NodeProcess:
        """
        Create and start a new node as a systemd service.

        Args:
            node: Node database record with configuration
            binary_path: Path to the antnode binary

        Returns:
            NodeProcess with metadata if successful, None if creation failed
        """
        logging.info(f"Creating systemd node {node.id}")

        # Get machine config to check no_upnp setting
        machine_config = None
        if self.S:
            from wnm.config import S
            from wnm.models import Machine
            from sqlalchemy import select

            try:
                with S() as session:
                    result = session.execute(select(Machine)).first()
                    if result:
                        machine_config = result[0]
            except Exception as e:
                logging.warning(f"Failed to get machine config: {e}")

        # Prepare service name
        service_name = f"antnode{node.node_name}.service"
        log_dir = f"{LOG_DIR}/antnode{node.node_name}"

        # Create directories
        if self.use_system_services:
            # Root: use sudo for system paths
            try:
                subprocess.run(
                    ["sudo", "mkdir", "-p", node.root_dir, log_dir],
                    stdout=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                logging.error(f"Failed to create directories: {err}")
                return None
        else:
            # Non-root: create in user paths without sudo
            try:
                os.makedirs(node.root_dir, exist_ok=True)
                os.makedirs(log_dir, exist_ok=True)
            except OSError as err:
                logging.error(f"Failed to create directories: {err}")
                return None

        # Copy binary to node directory
        if self.use_system_services:
            # Root: use sudo to copy
            try:
                subprocess.run(
                    ["sudo", "cp", binary_path, node.root_dir],
                    stdout=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                logging.error(f"Failed to copy binary: {err}")
                return None
        else:
            # Non-root: copy as current user
            try:
                shutil.copy2(binary_path, node.root_dir)
                binary_dest = os.path.join(node.root_dir, "antnode")
                os.chmod(binary_dest, 0o755)
            except (OSError, shutil.Error) as err:
                logging.error(f"Failed to copy binary: {err}")
                return None

        # Change ownership (only when running as root)
        # When running as non-root user, files remain owned by current user
        if self.use_system_services:
            user = getattr(node, "user", "ant")
            try:
                subprocess.run(
                    ["sudo", "chown", "-R", f"{user}:{user}", node.root_dir, log_dir],
                    stdout=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                logging.error(f"Failed to change ownership: {err}")
                return None

        # Build systemd service unit
        env_string = f'Environment="{node.environment}"' if node.environment else ""
        binary_in_node_dir = f"{node.root_dir}/antnode"

        # Determine which user to run as
        # System services (root): use 'ant' user for security
        # User services (non-root): don't specify User= (runs as current user)
        if self.use_system_services:
            user = getattr(node, "user", "ant")
            user_line = f"User={user}"
        else:
            user_line = ""  # User services run as the invoking user

        # Build ExecStart command with conditional --no-upnp
        exec_args = [
            binary_in_node_dir,
            "--bootstrap-cache-dir", BOOTSTRAP_CACHE_DIR,
            "--root-dir", node.root_dir,
            "--port", str(node.port),
            "--enable-metrics-server",
            "--metrics-server-port", str(node.metrics_port),
            "--log-output-dest", log_dir,
            "--max-log-files", "1",
            "--max-archived-log-files", "1",
        ]

        # Add --no-upnp if configured (defaults to True for backwards compatibility)
        if machine_config and getattr(machine_config, 'no_upnp', True):
            exec_args.append("--no-upnp")

        exec_args.extend(["--rewards-address", node.wallet, node.network])
        exec_start = " ".join(exec_args)

        service_content = f"""[Unit]
Description=antnode{node.node_name}
[Service]
{env_string}
{user_line}
ExecStart={exec_start}
Restart=always
#RestartSec=300
"""

        # Write service file
        service_path = f"{self.service_dir}/{service_name}"
        if self.use_system_services:
            # System services: use sudo to write to /etc/systemd/system
            try:
                subprocess.run(
                    ["sudo", "tee", service_path],
                    input=service_content,
                    text=True,
                    stdout=subprocess.PIPE,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                logging.error(f"Failed to write service file: {err}")
                return None
        else:
            # User services: write directly to ~/.config/systemd/user
            try:
                with open(service_path, "w") as f:
                    f.write(service_content)
            except OSError as err:
                logging.error(f"Failed to write service file: {err}")
                return None

        # Reload systemd
        try:
            subprocess.run(
                self.systemctl_cmd + ["daemon-reload"],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to reload systemd: {err}")
            return None

        # Start the node
        if not self.start_node(node):
            return None

        # Return NodeProcess with basic info (systemd doesn't provide external IDs)
        return NodeProcess(
            node_id=node.id,
            status=RESTARTING,  # Node is starting up
        )

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
                self.systemctl_cmd + ["start", node.service],
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
                self.systemctl_cmd + ["stop", node.service],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to stop node: {err}")
            return False

        # Close firewall port
        self.disable_firewall_port(node.port)

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
                self.systemctl_cmd + ["restart", node.service],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to restart node: {err}")
            return False

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
                self.systemctl_cmd
                + ["show", node.service, "--property=MainPID,ActiveState"],
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

            return NodeProcess(
                node_id=node.id, pid=pid if pid > 0 else None, status=status
            )

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
        log_path = f"{LOG_DIR}/{nodename}"

        # Remove data and logs
        if self.use_system_services:
            # System services: use sudo to remove
            try:
                subprocess.run(
                    ["sudo", "rm", "-rf", node.root_dir, log_path],
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                logging.error(f"Failed to remove node data: {err}")
        else:
            # User services: remove as current user
            try:
                if os.path.exists(node.root_dir):
                    shutil.rmtree(node.root_dir)
                if os.path.exists(log_path):
                    shutil.rmtree(log_path)
            except (OSError, shutil.Error) as err:
                logging.error(f"Failed to remove node data: {err}")

        # Remove service file
        service_path = f"{self.service_dir}/{node.service}"
        if self.use_system_services:
            # System services: use sudo to remove
            try:
                subprocess.run(
                    ["sudo", "rm", "-f", service_path],
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                logging.error(f"Failed to remove service file: {err}")
        else:
            # User services: remove as current user
            try:
                if os.path.exists(service_path):
                    os.remove(service_path)
            except OSError as err:
                logging.error(f"Failed to remove service file: {err}")

        # Reload systemd
        try:
            subprocess.run(
                self.systemctl_cmd + ["daemon-reload"],
                stdout=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to reload systemd: {err}")

        return True

    def survey_nodes(self, machine_config) -> list:
        """
        Survey all systemd-managed antnode services.

        Scans systemd service directory (system or user) for antnode*.service files and
        collects their configuration and current status.

        Args:
            machine_config: Machine configuration object

        Returns:
            List of node dictionaries ready for database insertion
        """
        service_names = []

        # Scan for antnode service files in the appropriate directory
        if os.path.exists(self.service_dir):
            try:
                for file in os.listdir(self.service_dir):
                    if re.match(r"antnode[\d]+\.service", file):
                        service_names.append(file)
            except PermissionError as e:
                logging.error(f"Permission denied reading {self.service_dir}: {e}")
                return []
            except Exception as e:
                logging.error(f"Error listing systemd services: {e}")
                return []

        if not service_names:
            logging.info("No systemd antnode services found")
            return []

        logging.info(f"Found {len(service_names)} systemd services to survey")

        details = []
        for service_name in service_names:
            logging.debug(f"{time.strftime('%Y-%m-%d %H:%M')} surveying {service_name}")

            node_id_match = re.findall(r"antnode([\d]+)\.service", service_name)
            if not node_id_match:
                logging.info(f"Can't decode {service_name}")
                continue

            card = {
                "node_name": node_id_match[0],
                "service": service_name,
                "timestamp": int(time.time()),
                "host": machine_config.host or "127.0.0.1",
                "method": "systemd",
                "layout": "1",
            }

            # Read configuration from systemd service file
            config = self._read_service_file(service_name, machine_config)
            card.update(config)

            if not config:
                logging.warning(f"Could not read config from {service_name}")
                continue

            # Check if node is running by querying metrics port
            metadata = read_node_metadata(card["host"], card["metrics_port"])

            if isinstance(metadata, dict) and metadata.get("status") == RUNNING:
                # Node is running - collect metadata and metrics
                card.update(metadata)
                card.update(read_node_metrics(card["host"], card["metrics_port"]))
            else:
                # Node is stopped
                if not os.path.isdir(card.get("root_dir", "")):
                    card["status"] = DEAD
                    card["version"] = ""
                else:
                    card["status"] = STOPPED
                    card["version"] = get_antnode_version(card.get("binary", ""))
                card["peer_id"] = ""
                card["records"] = 0
                card["uptime"] = 0
                card["shunned"] = 0

            card["age"] = get_node_age(card.get("root_dir", ""))
            card["host"] = machine_config.host  # Ensure we use machine config host

            details.append(card)

        return details

    def _read_service_file(self, service_name: str, machine_config) -> dict:
        """
        Read node configuration from a systemd service file.

        Args:
            service_name: Name of the service file (e.g., "antnode0001.service")
            machine_config: Machine configuration object

        Returns:
            Dictionary with node configuration, or empty dict on error
        """
        details = {}
        service_path = f"{self.service_dir}/{service_name}"

        try:
            with open(service_path, "r") as file:
                data = file.read()

            details["id"] = int(re.findall(r"antnode(\d+)", service_name)[0])
            details["binary"] = re.findall(r"ExecStart=([^ ]+)", data)[0]
            # User field may be empty for user services
            user_matches = re.findall(r"User=(\w+)", data)
            details["user"] = user_matches[0] if user_matches else os.getenv("USER", "nobody")
            details["root_dir"] = re.findall(r"--root-dir ([\w\/]+)", data)[0]
            details["port"] = int(re.findall(r"--port (\d+)", data)[0])
            details["metrics_port"] = int(
                re.findall(r"--metrics-server-port (\d+)", data)[0]
            )
            details["wallet"] = re.findall(r"--rewards-address ([^ ]+)", data)[0]
            details["network"] = re.findall(r"--rewards-address [^ ]+ ([\w\-]+)", data)[
                0
            ]

            # Check for IP listen address
            ip_matches = re.findall(r"--ip ([^ ]+)", data)
            if ip_matches:
                ip = ip_matches[0]
                # If wildcard listen address, use default
                details["host"] = machine_config.host if ip == "0.0.0.0" else ip
            else:
                details["host"] = machine_config.host

            # Check for environment variables
            env_matches = re.findall(r'Environment="(.+)"', data)
            details["environment"] = env_matches[0] if env_matches else ""

        except Exception as e:
            logging.debug(f"Error reading service file {service_path}: {e}")

        return details
