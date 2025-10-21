"""Action executor for performing node lifecycle operations.

This module contains the ActionExecutor class which takes planned actions
from the DecisionEngine and executes them by calling the appropriate utility
functions.
"""

import logging
import time
from typing import Any, Dict, List

from packaging.version import Version
from sqlalchemy import select
from sqlalchemy.orm import scoped_session

from wnm.actions import Action, ActionType
from wnm.common import DEAD, RUNNING, STOPPED
from wnm.models import Machine, Node
from wnm.utils import (
    create_node,
    get_antnode_version,
    remove_node,
    start_systemd_node,
    stop_systemd_node,
    update_nodes,
    upgrade_node,
)


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
                results.append({"action": action.type.value, "success": False, "error": str(e)})

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
            return self._execute_resurvey(machine_config, dry_run)

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
        self, machine_config: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Execute node resurvey after system reboot."""
        if dry_run:
            logging.warning("DRYRUN: System rebooted, survey nodes")
        else:
            update_nodes(self.S)
            # Update the last stopped time
            with self.S() as session:
                session.query(Machine).filter(Machine.id == 1).update(
                    {"last_stopped_at": int(time.time())}
                )
                session.commit()

        return {"status": "system-rebooted"}

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
                        select(Node.timestamp, Node.id, Node.host, Node.metrics_port)
                        .where(Node.status == DEAD)
                        .order_by(Node.timestamp.asc())
                    ).all()

                for check in broken:
                    logging.info(f"Removing dead node {check[1]}")
                    remove_node(self.S, check[1], no_delay=True)

            return {"status": "removed-dead-nodes"}

        elif "stopped" in action.reason.lower():
            # Remove youngest stopped node
            with self.S() as session:
                youngest = session.execute(
                    select(Node.id).where(Node.status == STOPPED).order_by(Node.age.desc())
                ).first()

            if youngest:
                if dry_run:
                    logging.warning("DRYRUN: Remove youngest stopped node")
                else:
                    remove_node(self.S, youngest[0], no_delay=True)
                return {"status": "removed-stopped-node"}
            else:
                return {"status": "no-stopped-nodes-to-remove"}

        else:
            # Remove youngest running node
            with self.S() as session:
                youngest = session.execute(
                    select(Node.id).where(Node.status == RUNNING).order_by(Node.age.desc())
                ).first()

            if youngest:
                if dry_run:
                    logging.warning("DRYRUN: Remove youngest running node")
                else:
                    remove_node(self.S, youngest[0])
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
                stop_systemd_node(self.S, youngest[0])
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
                oldest = oldest[0]
                # If we don't have a version number from metadata, grab from binary
                if not oldest.version:
                    oldest.version = get_antnode_version(oldest.binary)
                upgrade_node(oldest, metrics)
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
            oldest = oldest[0]
            # If we don't have a version number from metadata, grab from binary
            if not oldest.version:
                oldest.version = get_antnode_version(oldest.binary)

            # If the stopped version is old, upgrade it (which also starts it)
            if Version(metrics["antnode_version"]) > Version(oldest.version):
                if dry_run:
                    logging.warning("DRYRUN: Upgrade and start stopped node")
                else:
                    upgrade_node(oldest, metrics)
                return {"status": "upgrading-stopped-node"}
            else:
                if dry_run:
                    logging.warning("DRYRUN: Start stopped node")
                    return {"status": "starting-node"}
                else:
                    if start_systemd_node(oldest):
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
        else:
            if create_node(machine_config, metrics):
                return {"status": "added-node"}
            else:
                return {"status": "failed-create-node"}

    def _execute_survey(self, dry_run: bool) -> Dict[str, Any]:
        """Execute node survey (idle monitoring)."""
        if dry_run:
            logging.warning("DRYRUN: Update nodes")
        else:
            update_nodes(self.S)
        return {"status": "idle"}
