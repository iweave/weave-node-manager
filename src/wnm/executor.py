"""Action executor for performing node lifecycle operations.

This module contains the ActionExecutor class which takes planned actions
from the DecisionEngine and executes them using ProcessManager abstractions.
"""

import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from packaging.version import Version
from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import scoped_session

from wnm.actions import Action, ActionType
from wnm.common import (
    DEAD,
    DISABLED,
    METRICS_PORT_BASE,
    PORT_MULTIPLIER,
    REMOVING,
    RESTARTING,
    RPC_PORT_BASE,
    RUNNING,
    STOPPED,
    UPGRADING,
)
from wnm.config import LOG_DIR
from wnm.models import Machine, Node
from wnm.process_managers.factory import get_default_manager_type, get_process_manager
from wnm.utils import (
    get_antnode_version,
    parse_service_names,
    update_nodes,
)
from wnm.wallets import select_wallet_for_node


class ActionExecutor:
    """Executes planned actions on nodes.

    The ActionExecutor takes Action objects from the DecisionEngine and
    performs the actual operations by calling utility functions and
    managing database state.
    """

    def __init__(self, session_factory: scoped_session):
        """Initialize the action executor.

        Args:
            session_factory: SQLAlchemy session factory for database operations
        """
        self.S = session_factory
        self.machine_config = None  # Will be set in execute()

    def _get_process_manager(self, node: Node):
        """Get the appropriate process manager for a node.

        Args:
            node: Node database record

        Returns:
            ProcessManager instance for the node's manager type
        """
        # Get manager type from node, or use machine config default
        manager_type = getattr(node, "manager_type", None)
        if not manager_type and self.machine_config:
            manager_type = self.machine_config.get("process_manager")

        # If still no manager type, use default
        if not manager_type:
            manager_type = get_default_manager_type()

        return get_process_manager(manager_type, session_factory=self.S)

    def _set_node_status(self, node_id: int, status: str) -> bool:
        """Update node status in database.

        Args:
            node_id: ID of the node
            status: New status to set

        Returns:
            True if status was updated successfully
        """
        try:
            with self.S() as session:
                session.query(Node).filter(Node.id == node_id).update(
                    {"status": status, "timestamp": int(time.time())}
                )
                session.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to set node status for {node_id}: {e}")
            return False

    def _get_action_delay_ms(self, machine_config: Dict[str, Any]) -> int:
        """Get the effective action delay in milliseconds.

        Checks for transient override first, then falls back to persistent setting.

        Args:
            machine_config: Machine configuration dict (can be None)

        Returns:
            Delay in milliseconds (default: 0)
        """
        # Handle None or missing machine_config
        if not machine_config:
            return 0

        # Check for transient override (this_action_delay)
        if "this_action_delay" in machine_config and machine_config["this_action_delay"] is not None:
            return int(machine_config["this_action_delay"])

        # Fall back to persistent setting
        return machine_config.get("action_delay", 0)

    def _get_survey_delay_ms(self, machine_config: Dict[str, Any]) -> int:
        """Get the effective survey delay in milliseconds.

        Checks for transient override first, then falls back to persistent setting.

        Args:
            machine_config: Machine configuration dict (can be None)

        Returns:
            Delay in milliseconds (default: 0)
        """
        # Handle None or missing machine_config
        if not machine_config:
            return 0

        # Check for transient override (this_survey_delay)
        if "this_survey_delay" in machine_config and machine_config["this_survey_delay"] is not None:
            return int(machine_config["this_survey_delay"])

        # Fall back to persistent setting
        return machine_config.get("survey_delay", 0)

    def _upgrade_node_binary(self, node: Node, new_version: str) -> bool:
        """Upgrade a node's binary by stopping it, copying the new binary, and starting it again.

        For AntctlManager, this delegates to antctl's built-in upgrade command.
        For other managers, this manually stops, copies binary, and starts the node.

        Args:
            node: Node to upgrade
            new_version: Version string for the new binary

        Returns:
            True if upgrade succeeded
        """
        manager = self._get_process_manager(node)

        # Check if this is an AntctlManager - it has its own upgrade method
        from wnm.process_managers.antctl_manager import AntctlManager
        if isinstance(manager, AntctlManager):
            # Use antctl's built-in upgrade command
            logging.info(f"Using antctl upgrade for node {node.id}")
            if not manager.upgrade_node(node, new_version):
                logging.error(f"Failed to upgrade node {node.id} via antctl")
                return False

            # Update status to UPGRADING
            with self.S() as session:
                session.query(Node).filter(Node.id == node.id).update(
                    {
                        "status": UPGRADING,
                        "timestamp": int(time.time()),
                        "version": new_version,
                    }
                )
                session.commit()

            return True

        # For other managers (systemd, launchd, setsid), manually upgrade
        # Step 1: Stop the node (required to replace binary file)
        logging.info(f"Stopping node {node.id} for upgrade")
        if not manager.stop_node(node):
            logging.error(f"Failed to stop node {node.id} during upgrade")
            return False

        # Step 2: Copy new binary to node directory
        source_binary = os.path.expanduser(self.machine_config.antnode_path)
        try:
            shutil.copy2(source_binary, node.binary)
            os.chmod(node.binary, 0o755)
            logging.info(f"Copied new binary from {source_binary} to {node.binary}")
        except (OSError, shutil.Error) as err:
            logging.error(f"Failed to copy binary for upgrade: {err}")
            # Try to restart the node with old binary
            manager.start_node(node)
            return False

        # Step 3: Start the node with new binary
        logging.info(f"Starting node {node.id} with new binary")
        if not manager.start_node(node):
            logging.error(f"Failed to start node {node.id} after upgrade")
            return False

        # Update status to UPGRADING
        with self.S() as session:
            session.query(Node).filter(Node.id == node.id).update(
                {
                    "status": UPGRADING,
                    "timestamp": int(time.time()),
                    "version": new_version,
                }
            )
            session.commit()

        return True

    def execute(
        self,
        actions: List[Action],
        machine_config: Dict[str, Any],
        metrics: Dict[str, Any],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Execute a list of actions.

        Args:
            actions: List of Action objects to execute
            machine_config: Machine configuration dictionary
            metrics: Current system metrics
            dry_run: If True, log actions without executing them

        Returns:
            Dictionary with execution status and results
        """
        # Store machine_config for use in _get_process_manager
        self.machine_config = machine_config

        if not actions:
            return {"status": "no-actions", "results": []}

        results = []

        for action in actions:
            logging.info(
                f"Executing: {action.type.value} (priority={action.priority}, reason={action.reason})"
            )

            try:
                result = self._execute_action(action, machine_config, metrics, dry_run)
                results.append(result)
            except Exception as e:
                logging.error(f"Failed to execute {action.type.value}: {e}")
                results.append(
                    {"action": action.type.value, "success": False, "error": str(e)}
                )

        # Return status from the first (highest priority) action
        if results:
            return results[0]
        return {"status": "no-results"}

    def _execute_action(
        self,
        action: Action,
        machine_config: Dict[str, Any],
        metrics: Dict[str, Any],
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Execute a single action.

        Args:
            action: The action to execute
            machine_config: Machine configuration
            metrics: Current metrics
            dry_run: If True, log without executing

        Returns:
            Dictionary with execution result
        """
        if action.type == ActionType.RESURVEY_NODES:
            return self._execute_resurvey(action, machine_config, dry_run)

        elif action.type == ActionType.REMOVE_NODE:
            return self._execute_remove_node(action, dry_run)

        elif action.type == ActionType.STOP_NODE:
            return self._execute_stop_node(machine_config, dry_run)

        elif action.type == ActionType.UPGRADE_NODE:
            return self._execute_upgrade_node(metrics, dry_run)

        elif action.type == ActionType.START_NODE:
            return self._execute_start_node(metrics, dry_run)

        elif action.type == ActionType.ADD_NODE:
            return self._execute_add_node(machine_config, metrics, dry_run)

        elif action.type == ActionType.SURVEY_NODES:
            return self._execute_survey(dry_run)

        else:
            logging.warning(f"Unknown action type: {action.type}")
            return {"status": "unknown-action", "action": action.type.value}

    def _execute_resurvey(
        self, action: Action, machine_config: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Execute node resurvey after system reboot or initialization.

        Args:
            action: The action to execute (contains reason field)
            machine_config: Machine configuration
            dry_run: If True, log without executing

        Returns:
            Dictionary with status based on action reason
        """
        # Determine if this is an init or reboot based on action reason
        is_init = "initialized" in action.reason.lower()

        if dry_run:
            if is_init:
                logging.warning("DRYRUN: System initialized, survey nodes")
            else:
                logging.warning("DRYRUN: System rebooted, survey nodes")
        else:
            survey_delay_ms = self._get_survey_delay_ms(machine_config)
            update_nodes(self.S, survey_delay_ms=survey_delay_ms)
            # Update the last stopped time
            with self.S() as session:
                session.query(Machine).filter(Machine.id == 1).update(
                    {"last_stopped_at": int(time.time())}
                )
                session.commit()

        return {"status": "system-initialized" if is_init else "system-rebooted"}

    def _execute_remove_node(self, action: Action, dry_run: bool) -> Dict[str, Any]:
        """Execute node removal.

        If reason contains 'dead', remove all dead nodes.
        Otherwise, remove youngest stopped or running node based on reason.
        """
        if "dead" in action.reason.lower():
            # Remove all dead nodes
            if dry_run:
                logging.warning("DRYRUN: Remove Dead Nodes")
            else:
                with self.S() as session:
                    broken = session.execute(
                        select(Node)
                        .where(Node.status == DEAD)
                        .order_by(Node.timestamp.asc())
                    ).all()

                for row in broken:
                    node = row[0]
                    logging.info(f"Removing dead node {node.id}")
                    manager = self._get_process_manager(node)
                    manager.remove_node(node)
                    # Delete from database immediately (no delay for dead nodes)
                    with self.S() as session:
                        session.delete(node)
                        session.commit()

            return {"status": "removed-dead-nodes"}

        elif "stopped" in action.reason.lower():
            # Remove youngest stopped node
            with self.S() as session:
                youngest = session.execute(
                    select(Node).where(Node.status == STOPPED).order_by(Node.age.desc())
                ).first()

            if youngest:
                if dry_run:
                    logging.warning("DRYRUN: Remove youngest stopped node")
                else:
                    node = youngest[0]
                    manager = self._get_process_manager(node)
                    manager.remove_node(node)
                    # Delete from database immediately (no delay for stopped nodes)
                    with self.S() as session:
                        session.delete(node)
                        session.commit()
                return {"status": "removed-stopped-node"}
            else:
                return {"status": "no-stopped-nodes-to-remove"}

        else:
            # Remove youngest running node (with delay)
            with self.S() as session:
                youngest = session.execute(
                    select(Node).where(Node.status == RUNNING).order_by(Node.age.desc())
                ).first()

            if youngest:
                if dry_run:
                    logging.warning("DRYRUN: Remove youngest running node")
                else:
                    node = youngest[0]
                    manager = self._get_process_manager(node)
                    manager.stop_node(node)
                    # Mark as REMOVING (will be deleted later after delay)
                    self._set_node_status(node.id, REMOVING)
                return {"status": "removed-running-node"}
            else:
                return {"status": "no-running-nodes-to-remove"}

    def _execute_stop_node(
        self, machine_config: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Execute node stop (to reduce resource usage)."""
        with self.S() as session:
            youngest = session.execute(
                select(Node).where(Node.status == RUNNING).order_by(Node.age.desc())
            ).first()

        if youngest:
            if dry_run:
                logging.warning("DRYRUN: Stopping youngest node")
            else:
                node = youngest[0]
                manager = self._get_process_manager(node)
                manager.stop_node(node)
                self._set_node_status(node.id, STOPPED)
                # Update the last stopped time
                with self.S() as session:
                    session.query(Machine).filter(Machine.id == 1).update(
                        {"last_stopped_at": int(time.time())}
                    )
                    session.commit()
            return {"status": "stopped-node"}
        else:
            return {"status": "no-nodes-to-stop"}

    def _execute_upgrade_node(
        self, metrics: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Execute node upgrade (oldest running node with outdated version)."""
        with self.S() as session:
            oldest = session.execute(
                select(Node)
                .where(Node.status == RUNNING)
                .where(Node.version != metrics["antnode_version"])
                .order_by(Node.age.asc())
            ).first()

        if oldest:
            if dry_run:
                logging.warning("DRYRUN: Upgrade oldest node")
            else:
                node = oldest[0]
                # If we don't have a version number from metadata, grab from binary
                if not node.version:
                    node.version = get_antnode_version(node.binary)

                # Perform the upgrade (copies binary, restarts, sets UPGRADING status)
                if not self._upgrade_node_binary(node, metrics["antnode_version"]):
                    return {"status": "upgrade-failed"}

            return {"status": "upgrading-node"}
        else:
            return {"status": "no-nodes-to-upgrade"}

    def _execute_start_node(
        self, metrics: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Execute starting a stopped node (may upgrade first if needed)."""
        with self.S() as session:
            oldest = session.execute(
                select(Node).where(Node.status == STOPPED).order_by(Node.age.asc())
            ).first()

        if oldest:
            node = oldest[0]
            # If we don't have a version number from metadata, grab from binary
            if not node.version:
                node.version = get_antnode_version(node.binary)

            # If the stopped version is old, upgrade it (which also starts it)
            if Version(metrics["antnode_version"]) > Version(node.version):
                if dry_run:
                    logging.warning("DRYRUN: Upgrade and start stopped node")
                else:
                    # Perform the upgrade (copies binary, restarts, sets UPGRADING status)
                    if not self._upgrade_node_binary(node, metrics["antnode_version"]):
                        return {"status": "failed-upgrade"}
                return {"status": "upgrading-stopped-node"}
            else:
                if dry_run:
                    logging.warning("DRYRUN: Start stopped node")
                    return {"status": "starting-node"}
                else:
                    manager = self._get_process_manager(node)
                    if manager.start_node(node):
                        self._set_node_status(node.id, RESTARTING)
                        return {"status": "started-node"}
                    else:
                        return {"status": "failed-start-node"}
        else:
            return {"status": "no-stopped-nodes"}

    def _execute_add_node(
        self, machine_config: Dict[str, Any], metrics: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Execute adding a new node."""
        if dry_run:
            logging.warning("DRYRUN: Add a node")
            return {"status": "add-node"}

        # Find next available node ID (look for holes first)
        # First check if node 1 exists
        with self.S() as session:
            node_1_exists = session.execute(
                select(Node.id).where(Node.id == 1)
            ).first()

        if not node_1_exists:
            # Node 1 is available, use it
            node_id = 1
        else:
            # Look for holes in the sequence
            sql = text(
                "select n1.id + 1 as id from node n1 "
                + "left join node n2 on n2.id = n1.id + 1 "
                + "where n2.id is null "
                + "and n1.id <> (select max(id) from node) "
                + "order by n1.id;"
            )
            with self.S() as session:
                result = session.execute(sql).first()

            if result:
                node_id = result[0]
            else:
                # No holes, use max + 1
                with self.S() as session:
                    result = session.execute(
                        select(Node.id).order_by(Node.id.desc())
                    ).first()
                node_id = result[0] + 1 if result else 1

        # Use the machine config's process manager (includes mode like "systemd+sudo")
        manager_type = machine_config.get("process_manager") or get_default_manager_type()

        # Select wallet for this node from weighted distribution
        selected_wallet = select_wallet_for_node(
            machine_config["rewards_address"],
            machine_config["donate_address"]
        )

        # Create node object
        node = Node(
            id=node_id,
            node_name=f"{node_id:04}",
            service=f"antnode{node_id:04}.service",
            user=machine_config.get("user", "ant"),
            version=metrics["antnode_version"],
            root_dir=f"{machine_config['node_storage']}/antnode{node_id:04}",
            binary=f"{machine_config['node_storage']}/antnode{node_id:04}/antnode",
            port=machine_config["port_start"] * PORT_MULTIPLIER + node_id,
            metrics_port=machine_config["metrics_port_start"] * PORT_MULTIPLIER + node_id,
            rpc_port=machine_config["rpc_port_start"] * PORT_MULTIPLIER + node_id,
            network="evm-arbitrum-one",
            wallet=selected_wallet,
            peer_id="",
            status=STOPPED,
            timestamp=int(time.time()),
            records=0,
            uptime=0,
            shunned=0,
            age=int(time.time()),
            host=machine_config["host"],
            method=manager_type,
            layout="1",
            environment=machine_config.get("environment", ""),
            manager_type=manager_type,
        )

        # Insert into database
        with self.S() as session:
            session.add(node)
            session.commit()
            session.refresh(node)  # Get the persisted node

        # Create the node using process manager
        source_binary = os.path.expanduser(machine_config["antnode_path"])
        manager = self._get_process_manager(node)

        node_process = manager.create_node(node, source_binary)
        if not node_process:
            logging.error(f"Failed to create node {node.id}")
            return {"status": "failed-create-node"}

        # Persist metadata returned by process manager to database
        with self.S() as session:
            db_node = session.query(Node).filter_by(id=node.id).first()
            if db_node:
                # Store container_id if provided (for Docker/s6overlay managers)
                if node_process.container_id:
                    # Create or update Container record
                    from wnm.models import Container

                    container = session.query(Container).filter_by(
                        container_id=node_process.container_id
                    ).first()

                    if not container:
                        container = Container(
                            container_id=node_process.container_id,
                            name=f"antnode{node.node_name}",
                            image=getattr(manager, 'image', 'unknown'),
                            status="running",
                            created_at=int(time.time()),
                            machine_id=1,
                        )
                        session.add(container)
                        session.flush()  # Get container.id

                    # Link node to container
                    db_node.container_id = container.id

                # Store external_node_id if provided (for antctl manager)
                if node_process.external_node_id:
                    # Store in service field for now (antctl service name)
                    db_node.service = node_process.external_node_id

                session.commit()

        # Update status to RESTARTING (node is starting up)
        self._set_node_status(node.id, RESTARTING)

        return {"status": "added-node"}

    def _execute_survey(self, dry_run: bool) -> Dict[str, Any]:
        """Execute node survey (idle monitoring)."""
        if dry_run:
            logging.warning("DRYRUN: Update nodes")
        else:
            survey_delay_ms = self._get_survey_delay_ms(self.machine_config)
            update_nodes(self.S, survey_delay_ms=survey_delay_ms)
        return {"status": "idle"}

    def _parse_node_name(self, service_name: str) -> Optional[int]:
        """Parse node ID from service name like 'antnode0001'.

        Args:
            service_name: Node name (e.g., 'antnode0001')

        Returns:
            Node ID as integer, or None if parsing fails
        """
        import re
        match = re.match(r"antnode(\d+)", service_name)
        if match:
            return int(match.group(1))
        return None

    def _get_node_by_name(self, service_name: str) -> Optional[Node]:
        """Get node by service name.

        Args:
            service_name: Node name (e.g., 'antnode0001')

        Returns:
            Node object or None if not found
        """
        node_id = self._parse_node_name(service_name)
        if node_id is None:
            logging.error(f"Invalid node name format: {service_name}")
            return None

        with self.S() as session:
            result = session.execute(
                select(Node).where(Node.id == node_id)
            ).first()

        if result:
            return result[0]
        else:
            logging.error(f"Node not found: {service_name} (id={node_id})")
            return None

    def execute_forced_action(
        self,
        action_type: str,
        machine_config: Dict[str, Any],
        metrics: Dict[str, Any],
        service_name: Optional[str] = None,
        dry_run: bool = False,
        count: int = 1,
    ) -> Dict[str, Any]:
        """Execute a forced action bypassing the decision engine.

        Args:
            action_type: Type of action ('add', 'remove', 'upgrade', 'start', 'stop', 'disable', 'teardown')
            machine_config: Machine configuration
            metrics: Current system metrics
            service_name: Optional node name for targeted operations
            dry_run: If True, log without executing
            count: Number of nodes to affect (for add, remove, start, stop, upgrade actions)

        Returns:
            Dictionary with execution result
        """
        if action_type == "add":
            return self._force_add_node(machine_config, metrics, dry_run, count)
        elif action_type == "remove":
            return self._force_remove_node(service_name, dry_run, count)
        elif action_type == "upgrade":
            return self._force_upgrade_node(service_name, metrics, dry_run, count)
        elif action_type == "start":
            return self._force_start_node(service_name, metrics, dry_run, count)
        elif action_type == "stop":
            return self._force_stop_node(service_name, dry_run, count)
        elif action_type == "disable":
            return self._force_disable_node(service_name, dry_run)
        elif action_type == "teardown":
            return self._force_teardown_cluster(machine_config, dry_run)
        elif action_type == "survey":
            return self._force_survey_nodes(service_name, dry_run)
        else:
            return {"status": "error", "message": f"Unknown action type: {action_type}"}

    def _force_add_node(
        self, machine_config: Dict[str, Any], metrics: Dict[str, Any], dry_run: bool, count: int = 1
    ) -> Dict[str, Any]:
        """Force add new nodes.

        Args:
            machine_config: Machine configuration
            metrics: Current system metrics
            dry_run: If True, log without executing
            count: Number of nodes to add (default: 1)

        Returns:
            Dictionary with execution result
        """
        logging.info(f"Forced action: Adding {count} node(s)")

        if count < 1:
            return {"status": "error", "message": "count must be at least 1"}

        added_nodes = []
        failed_nodes = []

        # Track the start time to identify newly created nodes
        start_time = int(time.time())

        # Get action delay setting
        delay_ms = self._get_action_delay_ms(machine_config)

        for i in range(count):
            # Insert delay between operations (skip before first)
            if i > 0 and delay_ms > 0:
                delay_seconds = delay_ms / 1000.0
                logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node additions")
                time.sleep(delay_seconds)

            result = self._execute_add_node(machine_config, metrics, dry_run)
            if result["status"] in ["added-node", "add-node"]:
                # Get the node that was just added (youngest by age >= start_time)
                if not dry_run:
                    with self.S() as session:
                        newest = session.execute(
                            select(Node).where(Node.age >= start_time).order_by(Node.age.desc())
                        ).first()
                        if newest:
                            added_nodes.append(newest[0].service.replace(".service", ""))
                else:
                    added_nodes.append(f"node-{i+1}")
            else:
                failed_nodes.append({"index": i+1, "error": result.get("status", "unknown error")})

        if count == 1:
            # Keep backward compatibility for single node
            return result

        return {
            "status": "added-nodes" if not dry_run else "add-nodes-dryrun",
            "added_count": len(added_nodes),
            "added_nodes": added_nodes if added_nodes else None,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }

    def _force_remove_node(
        self, service_name: Optional[str], dry_run: bool, count: int = 1
    ) -> Dict[str, Any]:
        """Force remove nodes (specific or youngest by age).

        Args:
            service_name: Optional comma-separated list of service names
            dry_run: If True, log without executing
            count: Number of nodes to remove when service_name is not specified (default: 1)

        Returns:
            Dictionary with execution result
        """
        # Parse comma-separated service names
        service_names = parse_service_names(service_name)

        if service_names:
            # Remove specific nodes
            removed_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, name in enumerate(service_names):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node removals")
                    time.sleep(delay_seconds)

                node = self._get_node_by_name(name)
                if not node:
                    failed_nodes.append({"service": name, "error": "not found"})
                    continue

                logging.info(f"Forced action: Removing node {name}")
                if dry_run:
                    logging.warning(f"DRYRUN: Remove node {name}")
                    removed_nodes.append(name)
                else:
                    try:
                        manager = self._get_process_manager(node)
                        manager.remove_node(node)
                        # Remove from database immediately
                        with self.S() as session:
                            session.delete(node)
                            session.commit()
                        removed_nodes.append(name)
                    except Exception as e:
                        logging.error(f"Failed to remove node {name}: {e}")
                        failed_nodes.append({"service": name, "error": str(e)})

            return {
                "status": "removed-nodes" if not dry_run else "remove-dryrun",
                "removed_count": len(removed_nodes),
                "removed_nodes": removed_nodes,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }
        else:
            # Remove youngest nodes (default behavior - highest age value)
            if count < 1:
                return {"status": "error", "message": "count must be at least 1"}

            logging.info(f"Forced action: Removing {count} youngest node(s)")

            # Get youngest nodes (highest age values)
            with self.S() as session:
                youngest_nodes = session.execute(
                    select(Node).order_by(Node.age.desc()).limit(count)
                ).all()

            if not youngest_nodes:
                return {"status": "error", "message": "No nodes to remove"}

            if len(youngest_nodes) < count:
                logging.warning(f"Only {len(youngest_nodes)} nodes available, removing all of them")

            removed_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, row in enumerate(youngest_nodes):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node removals")
                    time.sleep(delay_seconds)

                node = row[0]
                if dry_run:
                    logging.warning(f"DRYRUN: Remove youngest node {node.node_name}")
                    removed_nodes.append(node.service.replace(".service", ""))
                else:
                    try:
                        manager = self._get_process_manager(node)
                        manager.remove_node(node)
                        # Remove from database immediately
                        with self.S() as session:
                            session.delete(node)
                            session.commit()
                        removed_nodes.append(node.service.replace(".service", ""))
                    except Exception as e:
                        logging.error(f"Failed to remove node {node.node_name}: {e}")
                        failed_nodes.append({"service": node.service.replace(".service", ""), "error": str(e)})

            if count == 1 and len(removed_nodes) == 1:
                # Keep backward compatibility for single node
                # Extract node name from service name (e.g., "antnode0001" -> "0001")
                node_name = removed_nodes[0].replace("antnode", "")
                return {"status": "removed-node", "node": node_name}

            return {
                "status": "removed-nodes" if not dry_run else "remove-dryrun",
                "removed_count": len(removed_nodes),
                "removed_nodes": removed_nodes if removed_nodes else None,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }

    def _force_upgrade_node(
        self, service_name: Optional[str], metrics: Dict[str, Any], dry_run: bool, count: int = 1
    ) -> Dict[str, Any]:
        """Force upgrade nodes (specific or oldest running nodes by age).

        Args:
            service_name: Optional comma-separated list of service names
            metrics: Current system metrics
            dry_run: If True, log without executing
            count: Number of nodes to upgrade when service_name is not specified (default: 1)

        Returns:
            Dictionary with execution result
        """
        # Parse comma-separated service names
        service_names = parse_service_names(service_name)

        if service_names:
            # Upgrade specific nodes
            upgraded_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, name in enumerate(service_names):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node upgrades")
                    time.sleep(delay_seconds)

                node = self._get_node_by_name(name)
                if not node:
                    failed_nodes.append({"service": name, "error": "not found"})
                    continue

                logging.info(f"Forced action: Upgrading node {name}")
                if dry_run:
                    logging.warning(f"DRYRUN: Upgrade node {name}")
                    upgraded_nodes.append(name)
                else:
                    try:
                        if not self._upgrade_node_binary(node, metrics["antnode_version"]):
                            failed_nodes.append({"service": name, "error": "upgrade failed"})
                        else:
                            upgraded_nodes.append(name)
                    except Exception as e:
                        logging.error(f"Failed to upgrade node {name}: {e}")
                        failed_nodes.append({"service": name, "error": str(e)})

            return {
                "status": "upgraded-nodes" if not dry_run else "upgrade-dryrun",
                "upgraded_count": len(upgraded_nodes),
                "upgraded_nodes": upgraded_nodes,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }
        else:
            # Upgrade oldest running nodes (default behavior - lowest age values)
            if count < 1:
                return {"status": "error", "message": "count must be at least 1"}

            logging.info(f"Forced action: Upgrading {count} oldest running node(s)")

            # Get oldest running nodes (lowest age values)
            with self.S() as session:
                oldest_nodes = session.execute(
                    select(Node)
                    .where(Node.status == RUNNING)
                    .order_by(Node.age.asc())
                    .limit(count)
                ).all()

            if not oldest_nodes:
                return {"status": "error", "message": "No running nodes to upgrade"}

            if len(oldest_nodes) < count:
                logging.warning(f"Only {len(oldest_nodes)} running nodes available, upgrading all of them")

            upgraded_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, row in enumerate(oldest_nodes):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node upgrades")
                    time.sleep(delay_seconds)

                node = row[0]
                if dry_run:
                    logging.warning(f"DRYRUN: Upgrade oldest node {node.node_name}")
                    upgraded_nodes.append(node.service.replace(".service", ""))
                else:
                    try:
                        if not self._upgrade_node_binary(node, metrics["antnode_version"]):
                            failed_nodes.append({"service": node.service.replace(".service", ""), "error": "upgrade failed"})
                        else:
                            upgraded_nodes.append(node.service.replace(".service", ""))
                    except Exception as e:
                        logging.error(f"Failed to upgrade node {node.node_name}: {e}")
                        failed_nodes.append({"service": node.service.replace(".service", ""), "error": str(e)})

            if count == 1 and len(upgraded_nodes) == 1:
                # Keep backward compatibility for single node
                # Extract node name from service name (e.g., "antnode0001" -> "0001")
                node_name = upgraded_nodes[0].replace("antnode", "")
                return {"status": "upgraded-node", "node": node_name}

            return {
                "status": "upgraded-nodes" if not dry_run else "upgrade-dryrun",
                "upgraded_count": len(upgraded_nodes),
                "upgraded_nodes": upgraded_nodes if upgraded_nodes else None,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }

    def _force_stop_node(
        self, service_name: Optional[str], dry_run: bool, count: int = 1
    ) -> Dict[str, Any]:
        """Force stop nodes (specific or youngest running nodes by age).

        Args:
            service_name: Optional comma-separated list of service names
            dry_run: If True, log without executing
            count: Number of nodes to stop when service_name is not specified (default: 1)

        Returns:
            Dictionary with execution result
        """
        # Parse comma-separated service names
        service_names = parse_service_names(service_name)

        if service_names:
            # Stop specific nodes
            stopped_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, name in enumerate(service_names):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node stops")
                    time.sleep(delay_seconds)

                node = self._get_node_by_name(name)
                if not node:
                    failed_nodes.append({"service": name, "error": "not found"})
                    continue

                logging.info(f"Forced action: Stopping node {name}")
                if dry_run:
                    logging.warning(f"DRYRUN: Stop node {name}")
                    stopped_nodes.append(name)
                else:
                    try:
                        manager = self._get_process_manager(node)
                        manager.stop_node(node)
                        self._set_node_status(node.id, STOPPED)
                        stopped_nodes.append(name)
                    except Exception as e:
                        logging.error(f"Failed to stop node {name}: {e}")
                        failed_nodes.append({"service": name, "error": str(e)})

            return {
                "status": "stopped-nodes" if not dry_run else "stop-dryrun",
                "stopped_count": len(stopped_nodes),
                "stopped_nodes": stopped_nodes,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }
        else:
            # Stop youngest running nodes (default behavior - highest age values)
            if count < 1:
                return {"status": "error", "message": "count must be at least 1"}

            logging.info(f"Forced action: Stopping {count} youngest running node(s)")

            # Get youngest running nodes (highest age values)
            with self.S() as session:
                youngest_nodes = session.execute(
                    select(Node)
                    .where(Node.status == RUNNING)
                    .order_by(Node.age.desc())
                    .limit(count)
                ).all()

            if not youngest_nodes:
                return {"status": "error", "message": "No running nodes to stop"}

            if len(youngest_nodes) < count:
                logging.warning(f"Only {len(youngest_nodes)} running nodes available, stopping all of them")

            stopped_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, row in enumerate(youngest_nodes):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node stops")
                    time.sleep(delay_seconds)

                node = row[0]
                if dry_run:
                    logging.warning(f"DRYRUN: Stop youngest node {node.node_name}")
                    stopped_nodes.append(node.service.replace(".service", ""))
                else:
                    try:
                        manager = self._get_process_manager(node)
                        manager.stop_node(node)
                        self._set_node_status(node.id, STOPPED)
                        stopped_nodes.append(node.service.replace(".service", ""))
                    except Exception as e:
                        logging.error(f"Failed to stop node {node.node_name}: {e}")
                        failed_nodes.append({"service": node.service.replace(".service", ""), "error": str(e)})

            if count == 1 and len(stopped_nodes) == 1:
                # Keep backward compatibility for single node
                # Extract node name from service name (e.g., "antnode0001" -> "0001")
                node_name = stopped_nodes[0].replace("antnode", "")
                return {"status": "stopped-node", "node": node_name}

            return {
                "status": "stopped-nodes" if not dry_run else "stop-dryrun",
                "stopped_count": len(stopped_nodes),
                "stopped_nodes": stopped_nodes if stopped_nodes else None,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }

    def _force_start_node(
        self, service_name: Optional[str], metrics: Dict[str, Any], dry_run: bool, count: int = 1
    ) -> Dict[str, Any]:
        """Force start nodes (specific or oldest stopped nodes by age).

        Args:
            service_name: Optional comma-separated list of service names
            metrics: Current system metrics
            dry_run: If True, log without executing
            count: Number of nodes to start when service_name is not specified (default: 1)

        Returns:
            Dictionary with execution result
        """
        # Parse comma-separated service names
        service_names = parse_service_names(service_name)

        if service_names:
            # Start specific nodes
            started_nodes = []
            upgraded_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, name in enumerate(service_names):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node starts")
                    time.sleep(delay_seconds)

                node = self._get_node_by_name(name)
                if not node:
                    failed_nodes.append({"service": name, "error": "not found"})
                    continue

                if node.status == RUNNING:
                    failed_nodes.append({"service": name, "error": "already running"})
                    continue

                logging.info(f"Forced action: Starting node {name}")
                if dry_run:
                    logging.warning(f"DRYRUN: Start node {name}")
                    started_nodes.append(name)
                else:
                    try:
                        # Check if node needs upgrade
                        if not node.version:
                            node.version = get_antnode_version(node.binary)

                        # If the stopped version is old, upgrade it (which also starts it)
                        if Version(metrics["antnode_version"]) > Version(node.version):
                            if not self._upgrade_node_binary(node, metrics["antnode_version"]):
                                failed_nodes.append({"service": name, "error": "upgrade failed"})
                            else:
                                upgraded_nodes.append(name)
                        else:
                            manager = self._get_process_manager(node)
                            if manager.start_node(node):
                                self._set_node_status(node.id, RESTARTING)
                                started_nodes.append(name)
                            else:
                                failed_nodes.append({"service": name, "error": "start failed"})
                    except Exception as e:
                        logging.error(f"Failed to start node {name}: {e}")
                        failed_nodes.append({"service": name, "error": str(e)})

            return {
                "status": "started-nodes" if not dry_run else "start-dryrun",
                "started_count": len(started_nodes),
                "started_nodes": started_nodes,
                "upgraded_count": len(upgraded_nodes),
                "upgraded_nodes": upgraded_nodes if upgraded_nodes else None,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }
        else:
            # Start oldest stopped nodes (default behavior - lowest age values)
            if count < 1:
                return {"status": "error", "message": "count must be at least 1"}

            logging.info(f"Forced action: Starting {count} oldest stopped node(s)")

            # Get oldest stopped nodes (lowest age values)
            with self.S() as session:
                oldest_nodes = session.execute(
                    select(Node)
                    .where(Node.status == STOPPED)
                    .order_by(Node.age.asc())
                    .limit(count)
                ).all()

            if not oldest_nodes:
                return {"status": "error", "message": "No stopped nodes to start"}

            if len(oldest_nodes) < count:
                logging.warning(f"Only {len(oldest_nodes)} stopped nodes available, starting all of them")

            started_nodes = []
            upgraded_nodes = []
            failed_nodes = []

            # Get action delay setting
            delay_ms = self._get_action_delay_ms(self.machine_config)

            for idx, row in enumerate(oldest_nodes):
                # Insert delay between operations (skip before first)
                if idx > 0 and delay_ms > 0:
                    delay_seconds = delay_ms / 1000.0
                    logging.info(f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between node starts")
                    time.sleep(delay_seconds)

                node = row[0]
                if dry_run:
                    logging.warning(f"DRYRUN: Start oldest stopped node {node.node_name}")
                    started_nodes.append(node.service.replace(".service", ""))
                else:
                    try:
                        # Check if node needs upgrade
                        if not node.version:
                            node.version = get_antnode_version(node.binary)

                        # If the stopped version is old, upgrade it (which also starts it)
                        if Version(metrics["antnode_version"]) > Version(node.version):
                            if not self._upgrade_node_binary(node, metrics["antnode_version"]):
                                failed_nodes.append({"service": node.service.replace(".service", ""), "error": "upgrade failed"})
                            else:
                                upgraded_nodes.append(node.service.replace(".service", ""))
                        else:
                            manager = self._get_process_manager(node)
                            if manager.start_node(node):
                                self._set_node_status(node.id, RESTARTING)
                                started_nodes.append(node.service.replace(".service", ""))
                            else:
                                failed_nodes.append({"service": node.service.replace(".service", ""), "error": "start failed"})
                    except Exception as e:
                        logging.error(f"Failed to start node {node.node_name}: {e}")
                        failed_nodes.append({"service": node.service.replace(".service", ""), "error": str(e)})

            if count == 1 and len(started_nodes) == 1:
                # Keep backward compatibility for single node
                # Extract node name from service name (e.g., "antnode0001" -> "0001")
                node_name = started_nodes[0].replace("antnode", "")
                return {"status": "started-node", "node": node_name}
            elif count == 1 and len(upgraded_nodes) == 1:
                # Keep backward compatibility for single node upgrade
                # Extract node name from service name (e.g., "antnode0001" -> "0001")
                node_name = upgraded_nodes[0].replace("antnode", "")
                return {"status": "upgrading-node", "node": node_name}

            return {
                "status": "started-nodes" if not dry_run else "start-dryrun",
                "started_count": len(started_nodes),
                "started_nodes": started_nodes if started_nodes else None,
                "upgraded_count": len(upgraded_nodes),
                "upgraded_nodes": upgraded_nodes if upgraded_nodes else None,
                "failed_count": len(failed_nodes),
                "failed_nodes": failed_nodes if failed_nodes else None,
            }

    def _force_disable_node(
        self, service_name: Optional[str], dry_run: bool
    ) -> Dict[str, Any]:
        """Force disable a specific node (service_name required)."""
        if not service_name:
            return {"status": "error", "message": "service_name required for disable action"}

        # Parse comma-separated service names
        service_names = parse_service_names(service_name)

        disabled_nodes = []
        failed_nodes = []

        for name in service_names:
            node = self._get_node_by_name(name)
            if not node:
                failed_nodes.append({"service": name, "error": "not found"})
                continue

            logging.info(f"Forced action: Disabling node {name}")
            if dry_run:
                logging.warning(f"DRYRUN: Disable node {name}")
                disabled_nodes.append(name)
            else:
                try:
                    # Stop the node if it's running
                    if node.status == RUNNING:
                        manager = self._get_process_manager(node)
                        manager.stop_node(node)
                    self._set_node_status(node.id, DISABLED)
                    disabled_nodes.append(name)
                except Exception as e:
                    logging.error(f"Failed to disable node {name}: {e}")
                    failed_nodes.append({"service": name, "error": str(e)})

        return {
            "status": "disabled-nodes" if not dry_run else "disable-dryrun",
            "disabled_count": len(disabled_nodes),
            "disabled_nodes": disabled_nodes,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }

    def _force_teardown_cluster(
        self, machine_config: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Force teardown the entire cluster."""
        logging.info("Forced action: Tearing down cluster")

        # Get all nodes
        with self.S() as session:
            all_nodes = session.execute(
                select(Node).order_by(Node.id.asc())
            ).all()

        if not all_nodes:
            return {"status": "no-nodes", "message": "No nodes to teardown"}

        # Get the process manager (use the first node's manager or default)
        if all_nodes:
            sample_node = all_nodes[0][0]
            manager = self._get_process_manager(sample_node)
        else:
            manager = get_process_manager()

        # Try manager-specific teardown first
        if hasattr(manager, 'teardown_cluster'):
            logging.info(f"Using {manager.__class__.__name__} teardown_cluster method")
            if dry_run:
                logging.warning("DRYRUN: Teardown cluster via manager")
            else:
                if manager.teardown_cluster():
                    # Remove all nodes from database
                    with self.S() as session:
                        session.query(Node).delete()
                        session.commit()
                    return {"status": "cluster-teardown", "method": "manager-specific"}

        # Fall back to removing each node individually (without delay)
        logging.info("Using default teardown (remove all nodes)")
        removed_count = 0
        for row in all_nodes:
            node = row[0]
            if dry_run:
                logging.warning(f"DRYRUN: Remove node {node.node_name}")
                removed_count += 1
            else:
                try:
                    manager = self._get_process_manager(node)
                    manager.remove_node(node)
                    with self.S() as session:
                        session.delete(node)
                        session.commit()
                    removed_count += 1
                    logging.info(f"Removed node {node.node_name}")
                except Exception as e:
                    logging.error(f"Failed to remove node {node.node_name}: {e}")

        return {
            "status": "cluster-teardown",
            "method": "individual-remove",
            "removed_count": removed_count,
        }

    def _survey_specific_nodes(self, service_names: List[str], dry_run: bool) -> Dict[str, Any]:
        """Survey specific nodes by service name.

        Args:
            service_names: List of service names to survey
            dry_run: If True, log without executing

        Returns:
            Dictionary with survey results
        """
        import time
        from wnm.utils import read_node_metrics, read_node_metadata, update_node_from_metrics

        surveyed_nodes = []
        failed_nodes = []
        survey_delay_ms = self._get_survey_delay_ms(self.machine_config)

        for idx, service_name in enumerate(service_names):
            node = self._get_node_by_name(service_name)
            if not node:
                failed_nodes.append({"service": service_name, "error": "not found"})
                continue

            if node.status == DISABLED:
                failed_nodes.append({"service": service_name, "error": "disabled"})
                continue

            if dry_run:
                logging.warning(f"DRYRUN: Survey node {service_name}")
                surveyed_nodes.append(service_name)
            else:
                logging.info(f"Surveying node {service_name}")

                # Check metadata first
                node_metadata = read_node_metadata(node.host, node.metrics_port)

                # If metadata fails, fake metrics with 0's
                if node_metadata["status"] == STOPPED:
                    node_metrics = {
                        "status": STOPPED,
                        "uptime": 0,
                        "records": 0,
                        "shunned": 0,
                        "connected_peers": 0
                    }
                else:
                    # Metadata succeeded, now get metrics
                    node_metrics = read_node_metrics(node.host, node.metrics_port)

                # Skip update if node is stopped and already marked as stopped
                if node_metadata["status"] == STOPPED and node.status == STOPPED:
                    surveyed_nodes.append(service_name)
                    continue

                update_node_from_metrics(self.S, node.id, node_metrics, node_metadata)
                surveyed_nodes.append(service_name)

            # Insert delay between nodes (but not after the last node)
            if survey_delay_ms > 0 and idx < len(service_names) - 1:
                time.sleep(survey_delay_ms / 1000.0)

        return {
            "status": "survey-complete" if not dry_run else "survey-dryrun",
            "surveyed_count": len(surveyed_nodes),
            "surveyed_nodes": surveyed_nodes,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }

    def _force_survey_nodes(self, service_name: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Force a survey of all nodes or specific nodes to update their status and metrics.

        Args:
            service_name: Optional comma-separated list of service names to survey
            dry_run: If True, log without executing

        Returns:
            Dictionary with survey results
        """
        # Parse service names if provided
        service_names = parse_service_names(service_name)

        if service_names:
            # Survey specific nodes
            logging.info(f"Forced action: Surveying {len(service_names)} specific nodes")
            return self._survey_specific_nodes(service_names, dry_run)
        else:
            # Survey all nodes
            logging.info("Forced action: Surveying all nodes")

            if dry_run:
                logging.warning("DRYRUN: Survey all nodes")
                # Get count of non-disabled nodes
                with self.S() as session:
                    from wnm.common import DISABLED
                    node_count = session.execute(
                        select(func.count(Node.id)).where(Node.status != DISABLED)
                    ).scalar()
                return {"status": "survey-dryrun", "node_count": node_count}

            # Update all nodes
            survey_delay_ms = self._get_survey_delay_ms(self.machine_config)
            update_nodes(self.S, survey_delay_ms=survey_delay_ms)

            # Get updated count
            with self.S() as session:
                from wnm.common import DISABLED
                node_count = session.execute(
                    select(func.count(Node.id)).where(Node.status != DISABLED)
                ).scalar()

            return {"status": "survey-complete", "node_count": node_count}
