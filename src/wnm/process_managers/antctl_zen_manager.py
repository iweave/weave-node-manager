"""
AntctlZenManager: Manage nodes via antctl CLI wrapper using antctl defaults.

Handles node lifecycle operations by wrapping the antctl command-line tool.
Unlike AntctlManager which overrides all paths, this "zen" version specifies
only the ports (for router forwarding) and rewards address, allowing antctl
to use its own defaults for binary and log paths. The actual configuration
is then read from antctl status output to populate the database.

This approach provides better compatibility with antctl's native behavior
while still maintaining control over port assignments for network configuration.
"""

import json
import logging
import os
import re
import subprocess
from typing import Optional

from wnm.common import DEAD, RESTARTING, RUNNING, STOPPED
from wnm.config import machine_config
from wnm.models import Node
from wnm.process_managers.base import NodeProcess, ProcessManager
from wnm.utils import read_node_metadata


# Map antctl status strings to wnm status constants
ANTCTL_STATUS_MAP = {
    "Running": RUNNING,
    "Stopped": STOPPED,
    "Added": STOPPED,  # Not yet started
    "Removed": DEAD,  # Marked for cleanup
}


class AntctlZenManager(ProcessManager):
    """Manage nodes via antctl CLI wrapper using antctl defaults for paths"""

    def __init__(
        self, session_factory=None, firewall_type: str = None, mode: str = None
    ):
        """
        Initialize AntctlZenManager.

        Args:
            session_factory: SQLAlchemy session factory (optional, for status updates)
            firewall_type: Type of firewall to use (defaults to "null")
            mode: Operation mode - "sudo" for system-level antctl, "user" for user-level (default)
        """
        # Determine if we're using sudo mode
        # mode="sudo": Run antctl with sudo (system-level services)
        # mode="user": Run antctl without sudo (user-level services, default)
        if mode == "sudo":
            self.use_sudo = True
        elif mode == "user":
            self.use_sudo = False
        else:
            # Default to user mode (no sudo)
            self.use_sudo = False

        # Antctl doesn't manage its own firewall rules, so default to null firewall
        if firewall_type is None:
            firewall_type = "null"

        super().__init__(firewall_type)
        self.S = session_factory

        # Get antctl path from machine config
        antctl_path = "antctl"  # Default fallback
        if machine_config and hasattr(machine_config, 'antctl_path') and machine_config.antctl_path:
            # Expand ~ to user home directory
            antctl_path = os.path.expanduser(machine_config.antctl_path)

        # Build base antctl command
        if self.use_sudo:
            self.antctl_cmd = ["sudo", antctl_path]
        else:
            self.antctl_cmd = [antctl_path]

        # Check if we should enable debug mode
        # Debug is enabled if either:
        # 1. antctl_debug flag is set in machine config
        # 2. Current logging level is DEBUG
        debug_mode = False

        # Check machine config for antctl_debug setting
        if machine_config and hasattr(machine_config, 'antctl_debug') and machine_config.antctl_debug:
            debug_mode = True

        # Also enable debug mode if logging level is DEBUG
        if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
            debug_mode = True

        # Add --debug flag to command if debug mode is enabled
        if debug_mode:
            self.antctl_cmd.append("--debug")
            logging.debug("AntctlZenManager: Debug mode enabled for antctl commands")

    def _run_antctl(
        self, args: list, capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Execute antctl command with proper error handling.

        Args:
            args: List of arguments to pass to antctl
            capture_output: Whether to capture stdout/stderr

        Returns:
            CompletedProcess object with command results

        Raises:
            subprocess.CalledProcessError: If command fails
            FileNotFoundError: If antctl is not installed
        """
        cmd = self.antctl_cmd + args
        # Log command with proper shell quoting for debugging
        import shlex
        logging.debug(f"Running antctl command: {' '.join(shlex.quote(arg) for arg in cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=True,
            )
            # Log stdout at DEBUG level if available
            if result.stdout:
                logging.debug(f"antctl stdout:\n{result.stdout}")
            if result.stderr:
                logging.debug(f"antctl stderr:\n{result.stderr}")
            return result
        except FileNotFoundError:
            logging.error(
                "antctl command not found. Please install via: antup antctl"
            )
            raise
        except subprocess.CalledProcessError as err:
            logging.error(f"antctl command failed: {err}")
            logging.error(f"stdout: {err.stdout}")
            logging.error(f"stderr: {err.stderr}")
            raise

    def create_node(self, node: Node, binary_path: str) -> Optional[NodeProcess]:
        """
        Create and start a new node via antctl using antctl defaults for paths.

        This "zen" approach only specifies the ports (for router forwarding) and
        rewards address, allowing antctl to choose its own defaults for data, log,
        and binary paths. After creation, the actual paths are read from antctl
        add command output and updated in the database.

        Args:
            node: Node database record with port configuration
            binary_path: Ignored (antctl will use its default binary)

        Returns:
            NodeProcess with external_node_id set to service_name if successful
            None if creation failed
        """
        logging.info(f"Creating antctl zen node {node.id} with ports specified, paths from antctl defaults")

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

        # Build minimal antctl add command - let antctl choose paths
        # We only specify ports (for router forwarding) and rewards address
        args = [
            "add",
            "--count",
            "1",
            "--node-port",
            str(node.port),
            "--metrics-port",
            str(node.metrics_port),
            "--rpc-port",
            str(node.rpc_port),
            "--rewards-address",
            node.wallet,
        ]

        # Add --no-upnp if configured (defaults to True for backwards compatibility)
        if machine_config and getattr(machine_config, 'no_upnp', True):
            args.append("--no-upnp")

        # Add network
        args.append(node.network or "evm-arbitrum-one")

        try:
            result = self._run_antctl(args)

            # Parse output to extract service name
            service_name = self._extract_service_name_from_output(result.stdout)
            if not service_name:
                logging.error("Failed to extract service name from antctl output")
                return None

            logging.info(f"Created antctl service: {service_name}")

            # Parse output to get the actual paths chosen by antctl
            config = self._parse_node_config_from_add_output(result.stdout, service_name)
            if not config:
                logging.error("Failed to parse node configuration from antctl output")
                return None

            # Update node object with the paths from antctl
            node.service = service_name
            node.root_dir = config.get("root_dir", "")
            node.log_dir = config.get("log_dir", "")
            node.binary = config.get("binary", "")

            logging.info(f"Node {node.id} configuration from antctl: "
                        f"root_dir={node.root_dir}, log_dir={node.log_dir}, binary={node.binary}")

            # Persist the updated node to the database
            if self.S:
                try:
                    with self.S() as session:
                        # Use merge to handle detached instance from executor
                        node = session.merge(node)
                        session.commit()
                except Exception as e:
                    logging.error(f"Failed to update node in database: {e}")
                    return None

            # Start the node
            if not self.start_node(node):
                logging.error(f"Failed to start node after creation")
                return None

            # Return NodeProcess with external_node_id set to service_name
            return NodeProcess(
                node_id=node.id,
                external_node_id=service_name,
                status=RESTARTING,  # Node is starting up
            )

        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            logging.error(f"Failed to create antctl node: {err}")
            return None

    def start_node(self, node: Node) -> bool:
        """
        Start a stopped antctl node.

        Args:
            node: Node database record

        Returns:
            True if node started successfully
        """
        logging.info(f"Starting antctl node {node.id} ({node.service})")

        try:
            self._run_antctl(["start", "--service-name", node.service])
            # Open firewall port
            self.enable_firewall_port(node.port)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            logging.error(f"Failed to start antctl node: {err}")
            return False

    def stop_node(self, node: Node) -> bool:
        """
        Stop a running antctl node.

        Args:
            node: Node database record

        Returns:
            True if node stopped successfully
        """
        logging.info(f"Stopping antctl node {node.id} ({node.service})")

        try:
            self._run_antctl(["stop", "--service-name", node.service])
            # Close firewall port
            self.disable_firewall_port(node.port)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            logging.error(f"Failed to stop antctl node: {err}")
            return False

    def restart_node(self, node: Node) -> bool:
        """
        Restart an antctl node (stop then start).

        NOTE: This is required by the ProcessManager abstract base class,
        but should NOT be used for upgrades. For upgrades, use upgrade_node() instead.

        Args:
            node: Node database record

        Returns:
            True if node restarted successfully
        """
        logging.info(f"Restarting antctl node {node.id} ({node.service})")

        if not self.stop_node(node):
            return False

        return self.start_node(node)

    def upgrade_node(self, node: Node, new_version: str = None) -> bool:
        """
        Upgrade an antctl node using antctl's built-in upgrade command.

        This "zen" version lets antctl download and manage its own binary
        instead of specifying a path. Antctl will download the latest version
        automatically.

        Args:
            node: Node database record
            new_version: Optional version to upgrade to (not used, kept for compatibility)

        Returns:
            True if node upgrade succeeded
        """
        logging.info(f"Upgrading antctl zen node {node.id} ({node.service}) to version {new_version or 'latest (from antctl)'}")

        # Build minimal antctl upgrade command - let antctl download the binary
        args = ["upgrade", "--service-name", node.service]

        try:
            result = self._run_antctl(args)
            logging.info(f"Successfully upgraded node {node.id}: {result.stdout}")
            logging.debug(f"Successfully upgraded node_stderr {node.id}: {result.stderr}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            logging.error(f"Failed to upgrade antctl node: {err}")
            return False

    def get_status(self, node: Node) -> NodeProcess:
        """
        Get current status of an antctl node.

        NOTE: This method is required by the ProcessManager interface but is NOT
        actually called by the executor. The executor determines status by calling
        read_node_metadata() directly on the metrics port.

        This is a minimal stub implementation.

        Args:
            node: Node database record

        Returns:
            NodeProcess with current status
        """
        # Simple implementation: Just check if metrics port responds
        metadata = read_node_metadata(node.host, node.metrics_port)

        if isinstance(metadata, dict) and metadata.get("status") == RUNNING:
            status = RUNNING
        else:
            # Check if root directory exists
            if not os.path.isdir(node.root_dir):
                status = DEAD
            else:
                status = STOPPED

        return NodeProcess(node_id=node.id, status=status)

    def remove_node(self, node: Node) -> bool:
        """
        Stop and remove an antctl node.

        Args:
            node: Node database record

        Returns:
            True if node was removed successfully
        """
        logging.info(f"Removing antctl node {node.id} ({node.service})")

        # Stop node first
        self.stop_node(node)

        # Remove via antctl
        try:
            self._run_antctl(["remove", "--service-name", node.service])
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            logging.error(f"Failed to remove antctl node: {err}")
            return False

    def survey_nodes(self, machine_config) -> list:
        """
        Survey all antctl-managed nodes.

        Uses 'antctl status --json' to discover existing nodes and collect
        their configuration and current status.

        Args:
            machine_config: Machine configuration object

        Returns:
            List of node dictionaries ready for database insertion
        """
        logging.info("Surveying antctl nodes")

        try:
            result = self._run_antctl(["status", "--json"])

            # Extract JSON block from debug output
            # When --debug is enabled, stdout contains logging mixed with JSON
            # JSON starts with a line containing just "{" and ends with just "}"
            json_match = re.search(r'^\{$.*?^\}$', result.stdout, re.MULTILINE | re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # No debug output, use entire stdout
                json_str = result.stdout

            nodes_data = json.loads(json_str)
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as err:
            logging.error(f"Failed to get antctl status: {err}")
            return []

        if not nodes_data or not isinstance(nodes_data, dict):
            logging.info("No antctl nodes found")
            return []

        # Parse the JSON output to extract node details
        return self._parse_status_json(nodes_data, machine_config)

    def teardown_cluster(self) -> bool:
        """
        Teardown entire cluster using antctl reset.

        This provides efficient bulk cleanup by using antctl's built-in
        cluster reset functionality.

        Returns:
            True if cluster was torn down successfully
        """
        logging.info("Tearing down antctl cluster")

        try:
            self._run_antctl(["reset", "--force"])
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            logging.error(f"Failed to teardown antctl cluster: {err}")
            return False

    def _extract_service_name_from_output(self, output: str) -> Optional[str]:
        """
        Parse antctl add output to find the created service name.

        Example output: "Service antnode1 created successfully"

        Args:
            output: stdout from antctl add command

        Returns:
            Service name (e.g., "antnode1") or None if not found
        """
        # Look for patterns like "antnode1", "antnode2", etc.
        match = re.search(r"(antnode\d+)", output, re.IGNORECASE)
        if match:
            return match.group(1)

        # Log output for debugging if pattern not found
        logging.debug(f"Could not extract service name from output: {output}")
        return None

    def _parse_node_config_from_add_output(self, output: str, service_name: str) -> Optional[dict]:
        """
        Parse antctl add output to extract node configuration paths.

        Example output format:
        Services Added:
         ✓ antnode1
            - Antnode path: /Users/dawn/Library/Application Support/autonomi/node/antnode1/antnode
            - Data path: /Users/dawn/Library/Application Support/autonomi/node/antnode1
            - Log path: /Users/dawn/Library/Application Support/autonomi/node/antnode1/logs
            - RPC port: 127.0.0.1:55227

        Args:
            output: stdout from antctl add command
            service_name: The service name to look for (e.g., "antnode1")

        Returns:
            Dictionary with keys: binary, root_dir, log_dir, or None if parsing failed
        """
        config = {}

        # Extract the section for this service
        # Look for the service name with a checkmark
        service_pattern = rf"✓\s+{re.escape(service_name)}\s*\n"
        match = re.search(service_pattern, output)
        if not match:
            logging.warning(f"Could not find service {service_name} in antctl add output")
            return None

        # Find the start of this service's info
        start_pos = match.end()

        # Find the end (either next service or end of output)
        next_service = re.search(r"✓\s+antnode\d+", output[start_pos:])
        if next_service:
            section = output[start_pos:start_pos + next_service.start()]
        else:
            section = output[start_pos:]

        # Parse the configuration lines
        # - Antnode path: /path/to/binary
        antnode_match = re.search(r"-\s+Antnode path:\s+(.+)$", section, re.MULTILINE)
        if antnode_match:
            config["binary"] = antnode_match.group(1).strip()

        # - Data path: /path/to/data
        data_match = re.search(r"-\s+Data path:\s+(.+)$", section, re.MULTILINE)
        if data_match:
            config["root_dir"] = data_match.group(1).strip()

        # - Log path: /path/to/logs
        log_match = re.search(r"-\s+Log path:\s+(.+)$", section, re.MULTILINE)
        if log_match:
            config["log_dir"] = log_match.group(1).strip()

        # Verify we got the essential paths
        if not config.get("root_dir"):
            logging.error(f"Failed to parse data path from antctl add output")
            return None

        logging.debug(f"Parsed node config: {config}")
        return config

    def _parse_status_json(self, json_data: dict, machine_config) -> list:
        """
        Parse antctl status --json output to extract node details.

        NOTE: We do NOT assign node.id from the antctl service name number.
        In multi-container scenarios, each container can have "antnode1", "antnode2", etc.
        The database will auto-assign sequential IDs on insertion.

        Args:
            json_data: Parsed JSON from antctl status command
            machine_config: Machine configuration object

        Returns:
            List of node dictionaries ready for database insertion
        """
        details = []

        # The JSON structure from antctl status --json should have a "nodes" key
        # containing a list of node objects
        nodes = json_data.get("nodes", [])

        for idx, node_data in enumerate(nodes, start=1):
            try:
                # Extract service name
                service_name = node_data.get("service_name", "")
                if not service_name:
                    logging.warning(f"Node {idx} missing service_name: {node_data}")
                    continue

                # Build node card
                # NOTE: We do NOT set "id" field - let database auto-assign it
                # The service name is stored in "service" field
                card = {
                    "node_name": service_name,  # Store full service name (e.g., "antnode1")
                    "service": service_name,  # Used for antctl commands
                    "host": machine_config.host or "127.0.0.1",
                    "method": "antctl",
                    "layout": "1",
                    "manager_type": "antctl",
                }

                # Extract configuration from JSON
                card["root_dir"] = node_data.get("data_dir_path", "")
                card["log_dir"] = node_data.get("log_dir_path", "")  # Store log directory
                card["port"] = node_data.get("node_port", 0)
                card["metrics_port"] = node_data.get("metrics_port", 0)

                # Extract RPC port from rpc_socket_addr (e.g., "127.0.0.1:30001")
                rpc_socket = node_data.get("rpc_socket_addr", "")
                if rpc_socket and ":" in rpc_socket:
                    try:
                        card["rpc_port"] = int(rpc_socket.split(":")[-1])
                    except (ValueError, IndexError):
                        card["rpc_port"] = 0
                else:
                    card["rpc_port"] = 0

                card["wallet"] = node_data.get("rewards_address", "")
                card["peer_id"] = node_data.get("peer_id", "")
                card["version"] = node_data.get("version", "")

                # Map antctl status to wnm status
                antctl_status = node_data.get("status", "Unknown")
                card["status"] = ANTCTL_STATUS_MAP.get(antctl_status, STOPPED)

                # Check if root directory exists
                if not os.path.isdir(card.get("root_dir", "")):
                    card["status"] = DEAD

                # Set default values for fields not in antctl output
                card["binary"] = node_data.get("antnode_path", "")
                card["user"] = os.getenv("USER", "nobody")
                card["network"] = node_data.get("network", "evm-arbitrum-one")
                card["records"] = 0
                card["uptime"] = node_data.get("uptime_secs", 0)
                card["shunned"] = 0
                card["age"] = 0  # Will be calculated from root_dir
                card["timestamp"] = 0  # Will be set by import process

                details.append(card)

            except (ValueError, KeyError) as err:
                logging.error(f"Error parsing node data: {err}")
                logging.debug(f"Node data: {node_data}")
                continue

        logging.info(f"Found {len(details)} antctl nodes")
        return details