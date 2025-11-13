"""
DockerManager: Manage nodes in Docker containers.

This manager runs nodes inside Docker containers, allowing for better isolation
and resource management. Supports both single-node and multi-node containers.
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path

from wnm.common import DEAD, RESTARTING, RUNNING, STOPPED, UPGRADING
from wnm.config import BOOTSTRAP_CACHE_DIR
from wnm.models import Node
from wnm.process_managers.base import NodeProcess, ProcessManager


class DockerManager(ProcessManager):
    """Manage nodes in Docker containers"""

    def __init__(
        self,
        session_factory=None,
        image="autonomi/node:latest",
        firewall_type: str = "null",
    ):
        """
        Initialize DockerManager.

        Args:
            session_factory: SQLAlchemy session factory (optional, for status updates)
            image: Docker image to use for nodes
            firewall_type: Type of firewall (defaults to "null" for Docker)
        """
        super().__init__(firewall_type)
        self.S = session_factory
        self.image = image

    def _get_container_name(self, node: Node) -> str:
        """Get Docker container name for a node"""
        return f"antnode{node.node_name}"

    def _ensure_image(self) -> bool:
        """Ensure Docker image is available"""
        try:
            # Check if image exists locally
            result = subprocess.run(
                ["docker", "image", "inspect", self.image],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                return True

            # Pull image if not found
            logging.info(f"Pulling Docker image: {self.image}")
            subprocess.run(
                ["docker", "pull", self.image],
                check=True,
            )
            return True

        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to ensure Docker image: {err}")
            return False

    def create_node(self, node: Node, binary_path: str) -> NodeProcess:
        """
        Create and start a new node in a Docker container.

        Args:
            node: Node database record with configuration
            binary_path: Path to the antnode binary (will be mounted into container)

        Returns:
            NodeProcess with container_id if successful, None if creation failed
        """
        logging.info(f"Creating docker node {node.id}")

        # Ensure image is available
        if not self._ensure_image():
            return None

        # Prepare directories
        node_dir = Path(node.root_dir)
        try:
            node_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            logging.error(f"Failed to create node directory: {err}")
            return None

        container_name = self._get_container_name(node)

        # Build docker run command
        cmd = [
            "docker",
            "run",
            "-d",  # Detached mode
            "--name",
            container_name,
            "--restart",
            "unless-stopped",
            # Port mappings
            "-p",
            f"{node.port}:{node.port}/udp",
            "-p",
            f"{node.metrics_port}:{node.metrics_port}/tcp",
            # Volume mounts
            "-v",
            f"{node.root_dir}:/data",
            "-v",
            f"{binary_path}:/usr/local/bin/antnode:ro",
            "-v",
            f"{BOOTSTRAP_CACHE_DIR}:/bootstrap-cache:ro",
        ]

        # Add environment variables
        if node.environment:
            for env_var in node.environment.split():
                cmd.extend(["-e", env_var])

        # Add the image
        cmd.append(self.image)

        # Add the command to run
        cmd.extend(
            [
                "antnode",
                "--root-dir",
                "/data",
                "--port",
                str(node.port),
                "--enable-metrics-server",
                "--metrics-server-port",
                str(node.metrics_port),
                "--bootstrap-cache-dir",
                "/bootstrap-cache",
                "--rewards-address",
                node.wallet,
                node.network,
            ]
        )

        # Run the container
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            container_id = result.stdout.strip()
            logging.info(f"Created container {container_name} with ID {container_id}")

        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to create container: {err}")
            logging.error(f"stderr: {err.stderr}")
            return None

        # Wait a moment for container to start
        time.sleep(1)

        # Return NodeProcess with container_id for persistence by executor
        return NodeProcess(
            node_id=node.id,
            status=RESTARTING,  # Container is starting up
            container_id=container_id,
        )

    def start_node(self, node: Node) -> bool:
        """
        Start a stopped Docker container.

        Args:
            node: Node database record

        Returns:
            True if node started successfully
        """
        logging.info(f"Starting docker node {node.id}")

        container_name = self._get_container_name(node)

        try:
            subprocess.run(
                ["docker", "start", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to start container: {err}")
            return False

        return True

    def stop_node(self, node: Node) -> bool:
        """
        Stop a Docker container.

        Args:
            node: Node database record

        Returns:
            True if node stopped successfully
        """
        logging.info(f"Stopping docker node {node.id}")

        container_name = self._get_container_name(node)

        try:
            # Stop with 30 second timeout for graceful shutdown
            subprocess.run(
                ["docker", "stop", "-t", "30", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to stop container: {err}")
            return False

        return True

    def restart_node(self, node: Node) -> bool:
        """
        Restart a Docker container.

        Args:
            node: Node database record

        Returns:
            True if node restarted successfully
        """
        logging.info(f"Restarting docker node {node.id}")

        container_name = self._get_container_name(node)

        try:
            subprocess.run(
                ["docker", "restart", "-t", "30", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to restart container: {err}")
            return False

        return True

    def get_status(self, node: Node) -> NodeProcess:
        """
        Get current status of a Docker node.

        Args:
            node: Node database record

        Returns:
            NodeProcess with current status
        """
        container_name = self._get_container_name(node)

        try:
            # Get container info
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Status}}|{{.State.Pid}}|{{.Id}}",
                    container_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            status_str, pid_str, container_id = result.stdout.strip().split("|")

            # Map Docker status to our status
            if status_str == "running":
                status = RUNNING
            elif status_str in ("created", "restarting"):
                status = RESTARTING
            elif status_str in ("exited", "dead"):
                status = STOPPED
            else:
                status = "UNKNOWN"

            pid = int(pid_str) if pid_str and pid_str != "0" else None

            # Check if root directory exists
            if not os.path.isdir(node.root_dir):
                status = DEAD

            return NodeProcess(
                node_id=node.id,
                pid=pid,
                status=status,
                container_id=container_id,
            )

        except subprocess.CalledProcessError:
            # Container doesn't exist
            return NodeProcess(node_id=node.id, pid=None, status=STOPPED)
        except (ValueError, IndexError) as err:
            logging.error(f"Failed to parse container status: {err}")
            return NodeProcess(node_id=node.id, pid=None, status="UNKNOWN")

    def remove_node(self, node: Node) -> bool:
        """
        Stop and remove a Docker container.

        Args:
            node: Node database record

        Returns:
            True if node was removed successfully
        """
        logging.info(f"Removing docker node {node.id}")

        container_name = self._get_container_name(node)

        # Stop the container first
        self.stop_node(node)

        # Remove the container
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        except subprocess.CalledProcessError as err:
            logging.error(f"Failed to remove container: {err}")

        # Remove node data directory
        try:
            import shutil

            node_dir = Path(node.root_dir)
            if node_dir.exists():
                shutil.rmtree(node_dir)
        except (OSError, Exception) as err:
            logging.error(f"Failed to remove node directory: {err}")

        return True

    def survey_nodes(self, machine_config) -> list:
        """
        Survey all docker-managed antnode containers.

        Docker nodes are typically not used for migration scenarios.
        This returns an empty list as docker containers are created
        fresh by WNM and don't pre-exist.

        Args:
            machine_config: Machine configuration object

        Returns:
            Empty list (docker nodes don't pre-exist for migration)
        """
        logging.info(
            "Docker survey not implemented (docker nodes created fresh by WNM)"
        )
        return []
