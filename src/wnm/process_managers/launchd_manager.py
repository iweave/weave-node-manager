"""
LaunchdManager: Manage nodes via macOS launchd services.

Handles node lifecycle operations using launchd plist files and launchctl commands.
Designed for user-level node management (no sudo required).
"""

import logging
import os
import plistlib
import re
import shutil
import subprocess
import time
from typing import Optional

from wnm.common import DEAD, RESTARTING, RUNNING, STOPPED, UPGRADING
from wnm.config import BOOTSTRAP_CACHE_DIR, LOG_DIR
from wnm.models import Node
from wnm.process_managers.base import NodeProcess, ProcessManager
from wnm.utils import (
    get_antnode_version,
    get_node_age,
    read_node_metadata,
    read_node_metrics,
)


class LaunchdManager(ProcessManager):
    """Manage nodes as launchd user agents on macOS"""

    def __init__(self, session_factory=None, firewall_type: str = None, mode: str = None):
        """
        Initialize LaunchdManager.

        Args:
            session_factory: SQLAlchemy session factory (optional, for status updates)
            firewall_type: Type of firewall to use (defaults to "null" on macOS)
            mode: Operation mode - "sudo" for system daemons with sudo, "user" for user agents (default)
        """
        super().__init__(firewall_type)
        self.S = session_factory

        # Determine if we're using system daemons or user agents based on mode parameter
        # mode="sudo": Use system daemons in /Library/LaunchDaemons/ with sudo (future)
        # mode="user" or None: Use user agents in ~/Library/LaunchAgents/ without sudo (default)
        if mode == "sudo":
            self.use_system_daemons = True
            self.plist_dir = "/Library/LaunchDaemons"
        else:
            self.use_system_daemons = False
            self.plist_dir = os.path.expanduser("~/Library/LaunchAgents")

        # Ensure plist directory exists
        os.makedirs(self.plist_dir, exist_ok=True)

    def _get_plist_path(self, node: Node) -> str:
        """Get the path to the plist file for a node."""
        label = self._get_service_label(node)
        return os.path.join(self.plist_dir, f"{label}.plist")

    def _get_service_label(self, node: Node) -> str:
        """Get the launchd service label for a node."""
        return f"com.autonomi.antnode-{node.id}"

    def _get_service_domain(self) -> str:
        """Get the launchd domain for user agents."""
        # User agents run under gui/<uid>/ domain
        uid = os.getuid()
        return f"gui/{uid}"

    def _generate_plist_content(self, node: Node, binary_path: str, machine_config=None) -> str:
        """
        Generate the plist XML content for a node.

        Args:
            node: Node database record
            binary_path: Path to the node binary in the node's directory
            machine_config: Machine configuration (optional, will query if not provided)

        Returns:
            XML string for the plist file
        """
        # Get machine config if not provided
        if machine_config is None and self.S:
            from wnm.config import S
            from wnm.models import Machine
            from sqlalchemy import select

            with S() as session:
                result = session.execute(select(Machine)).first()
                if result:
                    machine_config = result[0]

        label = self._get_service_label(node)
        log_file = os.path.join(LOG_DIR, f"antnode{node.node_name}.log")

        # Build program arguments array
        args = [binary_path]

        # Add --no-upnp if configured (defaults to True for backwards compatibility)
        if machine_config and getattr(machine_config, 'no_upnp', True):
            args.append("--no-upnp")

        args.extend([
            "--bootstrap-cache-dir",
            BOOTSTRAP_CACHE_DIR,
            "--root-dir",
            node.root_dir,
            "--port",
            str(node.port),
            "--metrics-server-port",
            str(node.metrics_port),
            "--log-output-dest",
            LOG_DIR,
            "--max-log-files",
            "1",
            "--max-archived-log-files",
            "1",
            "--rewards-address",
            node.wallet,
            node.network,
        ])

        # Build ProgramArguments XML
        args_xml = "\n".join(f"        <string>{arg}</string>" for arg in args)

        # Build environment variables if needed
        env_xml = ""
        if node.environment:
            # Parse environment variables from node.environment string
            # Expected format: "KEY1=value1 KEY2=value2"
            env_vars = {}
            for pair in node.environment.split():
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    env_vars[key] = value

            if env_vars:
                env_xml = "    <key>EnvironmentVariables</key>\n    <dict>\n"
                for key, value in env_vars.items():
                    env_xml += f"        <key>{key}</key>\n"
                    env_xml += f"        <string>{value}</string>\n"
                env_xml += "    </dict>\n"

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>

    <key>WorkingDirectory</key>
    <string>{node.root_dir}</string>

    <key>StandardOutPath</key>
    <string>{log_file}</string>

    <key>StandardErrorPath</key>
    <string>{log_file}</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

{env_xml}</dict>
</plist>
"""
        return plist_content

    def create_node(self, node: Node, binary_path: str) -> NodeProcess:
        """
        Create and start a new node as a launchd user agent.

        Args:
            node: Node database record with configuration
            binary_path: Path to the antnode binary (typically ~/.local/bin/antnode)

        Returns:
            NodeProcess with metadata if successful, None if creation failed
        """
        logging.info(f"Creating launchd node {node.id}")

        # Create node directories
        log_dir = os.path.join(LOG_DIR, f"antnode{node.node_name}")
        try:
            os.makedirs(node.root_dir, exist_ok=True)
            os.makedirs(log_dir, exist_ok=True)
        except OSError as err:
            logging.error(f"Failed to create directories: {err}")
            return None

        # Copy binary to node directory (each node gets its own copy)
        node_binary_path = os.path.join(node.root_dir, "antnode")
        try:
            if not os.path.exists(binary_path):
                logging.error(f"Source binary not found: {binary_path}")
                return None
            shutil.copy2(binary_path, node_binary_path)
            # Make it executable
            os.chmod(node_binary_path, 0o755)
        except (OSError, shutil.Error) as err:
            logging.error(f"Failed to copy binary: {err}")
            return None

        # Generate plist file
        plist_path = self._get_plist_path(node)
        plist_content = self._generate_plist_content(node, node_binary_path)

        try:
            with open(plist_path, "w") as f:
                f.write(plist_content)
        except OSError as err:
            logging.error(f"Failed to write plist file: {err}")
            return None

        # Load the service with launchctl
        try:
            result = subprocess.run(
                ["launchctl", "load", plist_path],
                capture_output=True,
                text=True,
                check=True,
            )
            logging.info(f"Loaded launchd service: {self._get_service_label(node)}")
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to load service: {err.stderr}")
            return None

        # Enable firewall port
        if not self.enable_firewall_port(
            node.port, protocol="udp", comment=f"antnode{node.node_name}"
        ):
            logging.warning(f"Failed to enable firewall for port {node.port}")

        # Return NodeProcess with basic info (launchd doesn't provide external IDs)
        return NodeProcess(
            node_id=node.id,
            status=RESTARTING,  # Node is starting up
        )

    def start_node(self, node: Node) -> bool:
        """
        Start a stopped node.

        Args:
            node: Node database record

        Returns:
            True if node started successfully
        """
        logging.info(f"Starting launchd node {node.id}")

        plist_path = self._get_plist_path(node)

        # If plist doesn't exist, recreate it (node directory should exist)
        if not os.path.exists(plist_path):
            logging.info(f"Plist file not found, recreating: {plist_path}")

            # Get the binary path from the node's root directory
            node_binary_path = os.path.join(node.root_dir, "antnode")

            if not os.path.exists(node_binary_path):
                logging.error(f"Node binary not found: {node_binary_path}")
                return False

            # Generate and write the plist file
            plist_content = self._generate_plist_content(node, node_binary_path)
            try:
                with open(plist_path, "w") as f:
                    f.write(plist_content)
                logging.info(f"Recreated plist file: {plist_path}")
            except OSError as err:
                logging.error(f"Failed to write plist file: {err}")
                return False

        try:
            subprocess.run(
                ["launchctl", "load", plist_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to start node: {err.stderr}")
            return False

    def stop_node(self, node: Node) -> bool:
        """
        Stop a running node.

        Args:
            node: Node database record

        Returns:
            True if node stopped successfully
        """
        logging.info(f"Stopping launchd node {node.id}")

        plist_path = self._get_plist_path(node)
        if not os.path.exists(plist_path):
            logging.warning(f"Plist file not found: {plist_path}")
            # If plist doesn't exist, consider it already stopped
            return True

        try:
            subprocess.run(
                ["launchctl", "unload", plist_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as err:
            # It's possible the service is already unloaded
            if "Could not find specified service" in err.stderr:
                logging.info(
                    f"Service already unloaded: {self._get_service_label(node)}"
                )
                return True
            logging.error(f"Failed to stop node: {err.stderr}")
            return False

    def restart_node(self, node: Node) -> bool:
        """
        Restart a node using launchctl kickstart.

        Args:
            node: Node database record

        Returns:
            True if node restarted successfully
        """
        logging.info(f"Restarting launchd node {node.id}")

        label = self._get_service_label(node)
        domain = self._get_service_domain()
        service_target = f"{domain}/{label}"

        try:
            # Use kickstart -k to kill and restart
            subprocess.run(
                ["launchctl", "kickstart", "-k", service_target],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to restart node: {err.stderr}")
            # Fallback: try unload/load
            if self.stop_node(node):
                return self.start_node(node)
            return False

    def get_status(self, node: Node) -> NodeProcess:
        """
        Get current runtime status of a node.

        Args:
            node: Node database record

        Returns:
            NodeProcess with current status and PID
        """
        label = self._get_service_label(node)

        try:
            result = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True,
                text=True,
                check=False,  # Don't raise exception - service might not exist
            )

            if result.returncode != 0:
                # Service not found
                return NodeProcess(node_id=node.id, pid=None, status=STOPPED)

            # Parse launchctl list output
            # Format:
            # {
            #     "Label" = "com.autonomi.antnode-1";
            #     "LimitLoadToSessionType" = "Aqua";
            #     "OnDemand" = false;
            #     "LastExitStatus" = 0;
            #     "PID" = 12345;
            #     "Program" = "/path/to/binary";
            # };

            pid = None
            last_exit_status = None

            for line in result.stdout.split("\n"):
                if '"PID"' in line:
                    match = re.search(r'"PID"\s*=\s*(\d+)', line)
                    if match:
                        pid = int(match.group(1))
                elif '"LastExitStatus"' in line:
                    match = re.search(r'"LastExitStatus"\s*=\s*(-?\d+)', line)
                    if match:
                        last_exit_status = int(match.group(1))

            # Determine status
            if pid is not None:
                status = RUNNING
            elif last_exit_status == 0:
                status = STOPPED
            else:
                status = DEAD  # Crashed

            return NodeProcess(node_id=node.id, pid=pid, status=status)

        except Exception as err:
            logging.error(f"Failed to get status for node {node.id}: {err}")
            return NodeProcess(node_id=node.id, pid=None, status=STOPPED)

    def remove_node(self, node: Node) -> bool:
        """
        Stop and remove all traces of a node.

        Args:
            node: Node database record

        Returns:
            True if node was removed successfully
        """
        logging.info(f"Removing launchd node {node.id}")

        # Stop the node first
        self.stop_node(node)

        # Remove plist file
        plist_path = self._get_plist_path(node)
        try:
            if os.path.exists(plist_path):
                os.remove(plist_path)
        except OSError as err:
            logging.error(f"Failed to remove plist file: {err}")
            return False

        # Remove node directories
        try:
            if os.path.exists(node.root_dir):
                shutil.rmtree(node.root_dir)
        except OSError as err:
            logging.error(f"Failed to remove node directory: {err}")
            return False

        # Remove log directory
        log_dir = os.path.join(LOG_DIR, f"antnode{node.node_name}")
        try:
            if os.path.exists(log_dir):
                shutil.rmtree(log_dir)
        except OSError as err:
            logging.warning(f"Failed to remove log directory: {err}")
            # Non-fatal

        # Disable firewall port
        if not self.disable_firewall_port(node.port):
            logging.warning(f"Failed to disable firewall for port {node.port}")

        return True

    def survey_nodes(self, machine_config) -> list:
        """
        Survey all launchd-managed antnode services.

        Scans ~/Library/LaunchAgents for com.autonomi.antnode-*.plist files
        and collects their configuration and current status.

        Args:
            machine_config: Machine configuration object

        Returns:
            List of node dictionaries ready for database insertion
        """
        plist_dir = self.plist_dir
        plist_names = []

        # Scan for antnode plist files
        if os.path.exists(plist_dir):
            try:
                for file in os.listdir(plist_dir):
                    if re.match(r"com\.autonomi\.antnode-\d+\.plist", file):
                        plist_names.append(file)
            except PermissionError as e:
                logging.error(f"Permission denied reading {plist_dir}: {e}")
                return []
            except Exception as e:
                logging.error(f"Error listing launchd plists: {e}")
                return []

        if not plist_names:
            logging.info("No launchd antnode services found")
            return []

        logging.info(f"Found {len(plist_names)} launchd services to survey")

        details = []
        for plist_name in plist_names:
            logging.debug(f"{time.strftime('%Y-%m-%d %H:%M')} surveying {plist_name}")

            # Extract node ID from plist name (e.g., "com.autonomi.antnode-1.plist" -> 1)
            node_id_match = re.findall(r"antnode-(\d+)\.plist", plist_name)
            if not node_id_match:
                logging.info(f"Can't decode {plist_name}")
                continue

            node_id = int(node_id_match[0])

            card = {
                "node_name": f"{node_id:04}",
                "service": plist_name,
                "timestamp": int(time.time()),
                "host": machine_config.host or "127.0.0.1",
                "method": "launchd",
                "layout": "1",
            }

            # Read configuration from plist file
            config = self._read_plist_file(plist_name, machine_config)
            card.update(config)

            if not config:
                logging.warning(f"Could not read config from {plist_name}")
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

    def _read_plist_file(self, plist_name: str, machine_config) -> dict:
        """
        Read node configuration from a launchd plist file.

        Args:
            plist_name: Name of the plist file (e.g., "com.autonomi.antnode-1.plist")
            machine_config: Machine configuration object

        Returns:
            Dictionary with node configuration, or empty dict on error
        """
        details = {}
        plist_path = os.path.join(self.plist_dir, plist_name)

        try:
            with open(plist_path, "rb") as file:
                plist_data = plistlib.load(file)

            # Extract node ID from label
            label = plist_data.get("Label", "")
            node_id_match = re.findall(r"antnode-(\d+)", label)
            if not node_id_match:
                logging.warning(f"Could not extract node ID from plist label: {label}")
                return details

            details["id"] = int(node_id_match[0])

            # Extract arguments from ProgramArguments
            args = plist_data.get("ProgramArguments", [])
            if len(args) < 1:
                logging.warning(f"No program arguments in plist: {plist_name}")
                return details

            details["binary"] = args[0]

            # Parse arguments
            i = 1
            while i < len(args):
                arg = args[i]
                if arg == "--port" and i + 1 < len(args):
                    details["port"] = int(args[i + 1])
                    i += 2
                elif arg == "--metrics-server-port" and i + 1 < len(args):
                    details["metrics_port"] = int(args[i + 1])
                    i += 2
                elif arg == "--root-dir" and i + 1 < len(args):
                    details["root_dir"] = args[i + 1]
                    i += 2
                elif arg == "--rewards-address" and i + 1 < len(args):
                    details["wallet"] = args[i + 1]
                    i += 1
                    # Network is the next argument
                    if i + 1 < len(args):
                        details["network"] = args[i + 1]
                    i += 1
                elif arg == "--ip" and i + 1 < len(args):
                    ip = args[i + 1]
                    details["host"] = machine_config.host if ip == "0.0.0.0" else ip
                    i += 2
                else:
                    i += 1

            # Default host if not specified
            if "host" not in details:
                details["host"] = machine_config.host

            # Extract environment variables
            env_vars = plist_data.get("EnvironmentVariables", {})
            details["environment"] = " ".join(f"{k}={v}" for k, v in env_vars.items())

            # macOS runs as current user (no user field in plist)
            details["user"] = os.getenv("USER", "unknown")

        except Exception as e:
            logging.debug(f"Error reading plist file {plist_path}: {e}")

        return details
