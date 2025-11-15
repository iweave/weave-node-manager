"""
SetsidManager: Manage nodes as background processes using setsid.

This manager runs nodes as simple background processes without requiring
sudo privileges or systemd. Suitable for development and non-systemd environments.
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import psutil

from wnm.common import DEAD, RESTARTING, RUNNING, STOPPED, UPGRADING
from wnm.config import BOOTSTRAP_CACHE_DIR
from wnm.models import Node
from wnm.process_managers.base import NodeProcess, ProcessManager


class SetsidManager(ProcessManager):
    """Manage nodes as background processes via setsid"""

    def __init__(self, session_factory=None, firewall_type: str = None):
        """
        Initialize SetsidManager.

        Args:
            session_factory: SQLAlchemy session factory (optional, for status updates)
            firewall_type: Type of firewall to use (defaults to auto-detect)
        """
        super().__init__(firewall_type)
        self.S = session_factory

    def _get_pid_file(self, node: Node) -> Path:
        """Get path to PID file for a node"""
        return Path(node.root_dir) / "node.pid"

    def _write_pid_file(self, node: Node, pid: int):
        """Write PID to file"""
        pid_file = self._get_pid_file(node)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(pid))

    def _read_pid_file(self, node: Node) -> int | None:
        """Read PID from file, returns None if file doesn't exist or is invalid"""
        pid_file = self._get_pid_file(node)
        try:
            if pid_file.exists():
                pid = int(pid_file.read_text().strip())
                # Verify process exists
                if psutil.pid_exists(pid):
                    return pid
                # Stale PID file, remove it
                pid_file.unlink()
        except (ValueError, OSError) as e:
            logging.debug(f"Failed to read PID file {pid_file}: {e}")
        return None

    def create_node(self, node: Node, binary_path: str) -> NodeProcess:
        """
        Create and start a new node as a background process.

        Args:
            node: Node database record with configuration
            binary_path: Path to the antnode binary

        Returns:
            NodeProcess with metadata if successful, None if creation failed
        """
        logging.info(f"Creating setsid node {node.id}")

        # Create directories
        node_dir = Path(node.root_dir)
        log_dir = node_dir / "logs"

        try:
            node_dir.mkdir(parents=True, exist_ok=True)
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            logging.error(f"Failed to create directories: {err}")
            return None

        # Copy binary to node directory
        binary_dest = node_dir / "antnode"
        try:
            shutil.copy2(binary_path, binary_dest)
            binary_dest.chmod(0o755)
        except (OSError, shutil.Error) as err:
            logging.error(f"Failed to copy binary: {err}")
            return None

        # Start the node
        if not self.start_node(node):
            return None

        # Get the PID that was just started
        pid = self._read_pid_file(node)

        # Return NodeProcess with basic info (setsid doesn't provide external IDs)
        return NodeProcess(
            node_id=node.id,
            pid=pid,
            status=RESTARTING,  # Node is starting up
        )

    def start_node(self, node: Node) -> bool:
        """
        Start a node as a background process.

        Args:
            node: Node database record

        Returns:
            True if node started successfully
        """
        logging.info(f"Starting setsid node {node.id}")

        # Check if already running
        if self._read_pid_file(node):
            logging.warning(f"Node {node.id} already running")
            return True

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

        # Prepare command
        binary = Path(node.root_dir) / "antnode"
        if not binary.exists():
            logging.error(f"Binary not found: {binary}")
            return False

        log_dir = Path(node.root_dir) / "logs"

        cmd = [
            str(binary),
            "--bootstrap-cache-dir",
            BOOTSTRAP_CACHE_DIR,
            "--root-dir",
            node.root_dir,
            "--port",
            str(node.port),
            "--enable-metrics-server",
            "--metrics-server-port",
            str(node.metrics_port),
            "--log-output-dest",
            str(log_dir),
            "--max-log-files",
            "1",
            "--max-archived-log-files",
            "1",
        ]

        # Add --no-upnp if configured (defaults to True for backwards compatibility)
        if machine_config and getattr(machine_config, 'no_upnp', True):
            cmd.append("--no-upnp")

        cmd.extend(["--rewards-address", node.wallet, node.network])

        # Start process in background using setsid
        try:
            # Use setsid to detach from terminal
            process = subprocess.Popen(
                ["setsid"] + cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={
                    **os.environ,
                    **({"CUSTOM_ENV": node.environment} if node.environment else {}),
                },
            )

            # Give process a moment to start
            time.sleep(0.5)

            # Check if process started successfully
            if process.poll() is not None:
                logging.error(
                    f"Process exited immediately with code {process.returncode}"
                )
                return False

            # Get actual PID of the antnode process (not setsid wrapper)
            # The setsid process becomes the session leader, we need to find the child
            time.sleep(1)  # Give process time to spawn

            # Find the antnode process by command line
            for proc in psutil.process_iter(["pid", "cmdline"]):
                try:
                    cmdline = proc.info["cmdline"]
                    if (
                        cmdline
                        and "antnode" in cmdline[0]
                        and str(node.port) in " ".join(cmdline)
                    ):
                        pid = proc.info["pid"]
                        self._write_pid_file(node, pid)
                        logging.info(f"Node {node.id} started with PID {pid}")
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            else:
                logging.warning(
                    f"Could not find PID for node {node.id}, using setsid PID"
                )
                self._write_pid_file(node, process.pid)

        except (subprocess.SubprocessError, OSError) as err:
            logging.error(f"Failed to start node: {err}")
            return False

        # Open firewall port (best effort, may fail without sudo)
        self.enable_firewall_port(node.port)

        return True

    def stop_node(self, node: Node) -> bool:
        """
        Stop a node process.

        Args:
            node: Node database record

        Returns:
            True if node stopped successfully
        """
        logging.info(f"Stopping setsid node {node.id}")

        pid = self._read_pid_file(node)
        if not pid:
            logging.warning(f"No PID found for node {node.id}")
            return True

        try:
            # Try graceful shutdown first
            process = psutil.Process(pid)
            process.terminate()

            # Wait up to 10 seconds for graceful shutdown
            try:
                process.wait(timeout=10)
            except psutil.TimeoutExpired:
                logging.warning(f"Node {node.id} did not terminate gracefully, killing")
                process.kill()
                process.wait(timeout=5)

            # Remove PID file
            pid_file = self._get_pid_file(node)
            if pid_file.exists():
                pid_file.unlink()

        except psutil.NoSuchProcess:
            logging.debug(f"Process {pid} already terminated")
        except psutil.AccessDenied as err:
            logging.error(f"Access denied stopping process {pid}: {err}")
            return False
        except Exception as err:
            logging.error(f"Failed to stop node: {err}")
            return False

        # Close firewall port
        self.disable_firewall_port(node.port)

        return True

    def restart_node(self, node: Node) -> bool:
        """
        Restart a node.

        Args:
            node: Node database record

        Returns:
            True if node restarted successfully
        """
        logging.info(f"Restarting setsid node {node.id}")

        self.stop_node(node)
        time.sleep(1)  # Brief pause between stop and start
        return self.start_node(node)

    def get_status(self, node: Node) -> NodeProcess:
        """
        Get current status of a node.

        Args:
            node: Node database record

        Returns:
            NodeProcess with current status
        """
        pid = self._read_pid_file(node)

        # Check if root directory exists
        if not os.path.isdir(node.root_dir):
            return NodeProcess(node_id=node.id, pid=None, status=DEAD)

        if pid:
            try:
                process = psutil.Process(pid)
                # Verify it's actually our node process
                if process.is_running():
                    return NodeProcess(node_id=node.id, pid=pid, status=RUNNING)
            except psutil.NoSuchProcess:
                pass

        return NodeProcess(node_id=node.id, pid=None, status=STOPPED)

    def remove_node(self, node: Node) -> bool:
        """
        Stop and remove a node.

        Args:
            node: Node database record

        Returns:
            True if node was removed successfully
        """
        logging.info(f"Removing setsid node {node.id}")

        # Stop the node first
        self.stop_node(node)

        # Remove node directory
        try:
            node_dir = Path(node.root_dir)
            if node_dir.exists():
                shutil.rmtree(node_dir)
        except (OSError, shutil.Error) as err:
            logging.error(f"Failed to remove node directory: {err}")
            return False

        return True

    def survey_nodes(self, machine_config) -> list:
        """
        Survey all setsid-managed antnode processes.

        Setsid nodes are typically not used for migration scenarios.
        This returns an empty list as setsid processes are created
        fresh by WNM and don't pre-exist.

        Args:
            machine_config: Machine configuration object

        Returns:
            Empty list (setsid nodes don't pre-exist for migration)
        """
        logging.info(
            "Setsid survey not implemented (setsid nodes created fresh by WNM)"
        )
        return []
