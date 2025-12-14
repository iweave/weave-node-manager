"""Decision engine for planning node lifecycle actions.

This module contains the DecisionEngine class which analyzes machine metrics,
resource thresholds, and node status to determine what actions should be taken.
It replaces the monolithic choose_action() function with a more modular approach.
"""

import logging
from typing import Any, Dict, List, Optional

from packaging.version import Version

from wnm.actions import Action, ActionType
from wnm.common import DEAD, DISABLED, REMOVING, RESTARTING, RUNNING, STOPPED, UPGRADING


class DecisionEngine:
    """Analyzes system state and plans node lifecycle actions.

    The DecisionEngine separates decision-making from execution. It takes machine
    configuration and current metrics, then returns a prioritized list of actions
    to perform.
    """

    def __init__(self, machine_config: Dict[str, Any], metrics: Dict[str, Any], is_init: bool = False, should_survey_init: bool = False):
        """Initialize the decision engine.

        Args:
            machine_config: Machine configuration dictionary with thresholds
            metrics: Current system metrics and node status
            is_init: Whether this is an --init operation
            should_survey_init: Whether to survey nodes during init (only if --import or --migrate_anm)
        """
        self.config = machine_config
        self.metrics = metrics
        self.is_init = is_init
        self.should_survey_init = should_survey_init
        self.features = self._compute_features()

    def _compute_features(self) -> Dict[str, bool]:
        """Compute decision features from metrics and config.

        Returns:
            Dictionary of boolean features used for decision-making
        """
        features = {}

        # Resource availability checks
        features["allow_cpu"] = (
            self.metrics["used_cpu_percent"] < self.config["cpu_less_than"]
        )
        features["allow_mem"] = (
            self.metrics["used_mem_percent"] < self.config["mem_less_than"]
        )
        features["allow_hd"] = (
            self.metrics["used_hd_percent"] < self.config["hd_less_than"]
        )

        # Resource pressure checks
        features["remove_cpu"] = (
            self.metrics["used_cpu_percent"] > self.config["cpu_remove"]
        )
        features["remove_mem"] = (
            self.metrics["used_mem_percent"] > self.config["mem_remove"]
        )
        features["remove_hd"] = (
            self.metrics["used_hd_percent"] > self.config["hd_remove"]
        )

        features["allow_node_cap"] = (
            self.metrics["running_nodes"] < self.config["node_cap"]
        )

        # Network I/O checks (if configured)
        if self._is_netio_configured():
            features["allow_netio"] = (
                self.metrics["netio_read_bytes"]
                < self.config["netio_read_less_than"]
                and self.metrics["netio_write_bytes"]
                < self.config["netio_write_less_than"]
            )
            features["remove_netio"] = (
                self.metrics["netio_read_bytes"] > self.config["netio_read_remove"]
                or self.metrics["netio_write_bytes"] > self.config["netio_write_remove"]
            )
        else:
            features["allow_netio"] = True
            features["remove_netio"] = False

        # Disk I/O checks (if configured)
        if self._is_hdio_configured():
            features["allow_hdio"] = (
                self.metrics["hdio_read_bytes"] < self.config["hdio_read_less_than"]
                and self.metrics["hdio_write_bytes"]
                < self.config["hdio_write_less_than"]
            )
            features["remove_hdio"] = (
                self.metrics["hdio_read_bytes"] > self.config["hdio_read_remove"]
                or self.metrics["hdio_write_bytes"] > self.config["hdio_write_remove"]
            )
        else:
            features["allow_hdio"] = True
            features["remove_hdio"] = False

        # Load average checks
        features["load_allow"] = (
            self.metrics["load_average_1"] < self.config["desired_load_average"]
            and self.metrics["load_average_5"] < self.config["desired_load_average"]
            and self.metrics["load_average_15"] < self.config["desired_load_average"]
        )
        features["load_not_allow"] = (
            self.metrics["load_average_1"] > self.config["max_load_average_allowed"]
            or self.metrics["load_average_5"] > self.config["max_load_average_allowed"]
            or self.metrics["load_average_15"] > self.config["max_load_average_allowed"]
        )

        # Can we add a new node?
        features["add_new_node"] = (
            sum(
                [
                    self.metrics.get(m, 0)
                    for m in [
                        "upgrading_nodes",
                        "restarting_nodes",
                        "migrating_nodes",
                        "removing_nodes",
                    ]
                ]
            )
            == 0
            and features["allow_cpu"]
            and features["allow_hd"]
            and features["allow_mem"]
            and features["allow_node_cap"]
            and features["allow_hdio"]
            and features["allow_netio"]
            and features["load_allow"]
            and self.metrics["total_nodes"] < self.config["node_cap"]
        )

        # Do we need to remove nodes?
        features["remove"] = (
            features["load_not_allow"]
            or features["remove_cpu"]
            or features["remove_hd"]
            or features["remove_mem"]
            or features["remove_hdio"]
            or features["remove_netio"]
            or self.metrics["total_nodes"] > self.config["node_cap"]
        )

        # Can we upgrade nodes?
        if self.metrics["nodes_to_upgrade"] >= 1:
            # Make sure current version is equal or newer than version on first node
            if Version(self.metrics["antnode_version"]) < Version(
                self.metrics["queen_node_version"]
            ):
                logging.warning("node upgrade cancelled due to lower version")
                features["upgrade"] = False
            else:
                if features["remove"]:
                    logging.info("Can't upgrade while removing is required")
                    features["upgrade"] = False
                else:
                    features["upgrade"] = True
        else:
            features["upgrade"] = False

        return features

    def _is_netio_configured(self) -> bool:
        """Check if network I/O thresholds are configured."""
        return (
            self.config["netio_read_less_than"]
            + self.config["netio_read_remove"]
            + self.config["netio_write_less_than"]
            + self.config["netio_write_remove"]
            > 1
        )

    def _is_hdio_configured(self) -> bool:
        """Check if disk I/O thresholds are configured."""
        return (
            self.config["hdio_read_less_than"]
            + self.config["hdio_read_remove"]
            + self.config["hdio_write_less_than"]
            + self.config["hdio_write_remove"]
            > 1
        )

    def plan_actions(self) -> List[Action]:
        """Plan the actions to take based on current state.

        Returns prioritized list of actions, respecting concurrency thresholds.

        Returns:
            List of Action objects in priority order
        """
        actions = []

        # Priority 1: System initialization or reboot detection
        if int(self.metrics["system_start"]) > int(self.config["last_stopped_at"]):
            # If this is an --init operation, handle it specially
            if self.is_init:
                # Only survey if we imported nodes (--import or --migrate_anm)
                if self.should_survey_init:
                    return [
                        Action(
                            type=ActionType.RESURVEY_NODES,
                            priority=100,
                            reason="system initialized",
                        )
                    ]
                else:
                    # No nodes to survey during init, just report initialized
                    return [
                        Action(
                            type=ActionType.SURVEY_NODES,
                            priority=0,
                            reason="system initialized",
                        )
                    ]
            else:
                # Normal system reboot detection
                return [
                    Action(
                        type=ActionType.RESURVEY_NODES,
                        priority=100,
                        reason="system rebooted",
                    )
                ]

        # Priority 2: Remove dead nodes
        if self.metrics["dead_nodes"] > 0:
            actions.extend(self._plan_dead_node_removals())
            return actions  # Dead nodes take absolute priority

        # Priority 3: Update nodes with missing version numbers
        if self.metrics.get("nodes_no_version", 0) > 0:
            # This is handled by update_counters, not as an action
            # We'll include it as informational but not block other actions
            pass

        # Priority 4: Check if at global capacity
        current_ops = self._get_current_operations()
        if current_ops >= self.config["max_concurrent_operations"]:
            logging.info(
                f"At global concurrent operations limit ({current_ops}/{self.config['max_concurrent_operations']})"
            )
            return [
                Action(
                    type=ActionType.SURVEY_NODES,
                    priority=0,
                    reason="at global capacity",
                )
            ]

        # Log individual operation type capacities (debug)
        if self.metrics["upgrading_nodes"] >= self.config["max_concurrent_upgrades"]:
            logging.debug(
                f"At upgrade capacity ({self.metrics['upgrading_nodes']}/{self.config['max_concurrent_upgrades']})"
            )

        if self.metrics["restarting_nodes"] >= self.config["max_concurrent_starts"]:
            logging.debug(
                f"At start capacity ({self.metrics['restarting_nodes']}/{self.config['max_concurrent_starts']})"
            )

        if self.metrics["removing_nodes"] >= self.config["max_concurrent_removals"]:
            logging.debug(
                f"At removal capacity ({self.metrics['removing_nodes']}/{self.config['max_concurrent_removals']})"
            )

        # Priority 5: Resource pressure - remove nodes
        if self.features["remove"]:
            actions.extend(self._plan_resource_removal())
            if actions:
                return actions

        # Priority 6: Upgrades (only if not removing)
        if self.features["upgrade"]:
            actions.extend(self._plan_upgrades())
            if actions:
                return actions

        # Priority 7: Add nodes (if resources allow)
        if self.features["add_new_node"]:
            actions.extend(self._plan_node_additions())
            if actions:
                return actions

        # Default: Survey nodes
        return [
            Action(type=ActionType.SURVEY_NODES, priority=0, reason="idle monitoring")
        ]

    def _plan_dead_node_removals(self) -> List[Action]:
        """Plan removal of dead nodes (highest priority).

        Returns:
            List of removal actions for all dead nodes
        """
        # Dead nodes should be removed immediately, all at once
        # The executor will need to query for dead nodes
        return [
            Action(
                type=ActionType.REMOVE_NODE,
                node_id=None,  # Executor will query for dead nodes
                priority=90,
                reason="dead node cleanup",
            )
        ]

    def _plan_resource_removal(self) -> List[Action]:
        """Plan node removals due to resource pressure with aggressive scaling.

        Returns:
            List of removal/stop actions, limited by capacity AND actual available nodes
        """
        actions = []

        # Calculate available removal slots
        current_removing = self.metrics.get("removing_nodes", 0)
        current_ops = self._get_current_operations()

        # Determine capacity
        removal_capacity = min(
            self.config["max_concurrent_removals"] - current_removing,
            self.config["max_concurrent_operations"] - current_ops
        )

        if removal_capacity <= 0:
            return []

        # If under HD pressure, over node cap, or upgrades need resources
        if (
            self.features["remove_hd"]
            or self.metrics["total_nodes"] > self.config["node_cap"]
            or (
                self.metrics["nodes_to_upgrade"] > 0
                and self.metrics["removing_nodes"] == 0
            )
        ):
            # CRITICAL: Remove stopped nodes first (limited by actual stopped nodes)
            stopped_to_remove = min(
                self.metrics.get("stopped_nodes", 0),
                removal_capacity
            )

            for i in range(stopped_to_remove):
                actions.append(
                    Action(
                        type=ActionType.REMOVE_NODE,
                        node_id=None,  # Executor will query for youngest stopped
                        priority=80,
                        reason=f"remove stopped node ({i+1}/{stopped_to_remove})",
                    )
                )

            # CRITICAL: Remove running nodes for remaining capacity
            remaining_capacity = removal_capacity - stopped_to_remove
            running_to_remove = min(
                self.metrics.get("running_nodes", 0),
                remaining_capacity
            )

            for i in range(running_to_remove):
                actions.append(
                    Action(
                        type=ActionType.REMOVE_NODE,
                        node_id=None,  # Executor will query for youngest running
                        priority=75,
                        reason=f"remove running node ({i+1}/{running_to_remove})",
                    )
                )
        else:
            # Just stop nodes to reduce resource usage
            if self.metrics["removing_nodes"]:
                logging.info("Still waiting for RemoveDelay")
                return []

            # CRITICAL: Stop youngest running nodes (limited by actual running nodes)
            nodes_to_stop = min(
                self.metrics.get("running_nodes", 0),
                removal_capacity
            )

            for i in range(nodes_to_stop):
                actions.append(
                    Action(
                        type=ActionType.STOP_NODE,
                        node_id=None,  # Executor will query for youngest running
                        priority=70,
                        reason=f"stop node ({i+1}/{nodes_to_stop})",
                    )
                )

        return actions

    def _plan_upgrades(self) -> List[Action]:
        """Plan node upgrades with aggressive scaling to capacity.

        Returns:
            List of upgrade actions, limited by capacity AND actual upgradeable nodes
        """
        actions = []

        # Calculate available upgrade slots
        current_upgrading = self.metrics.get("upgrading_nodes", 0)
        current_ops = self._get_current_operations()

        # Determine capacity
        upgrade_capacity = min(
            self.config["max_concurrent_upgrades"] - current_upgrading,
            self.config["max_concurrent_operations"] - current_ops
        )

        if upgrade_capacity <= 0:
            return []

        # CRITICAL: Don't plan more upgrades than nodes needing upgrade
        actual_upgrades_needed = self.metrics.get("nodes_to_upgrade", 0)
        upgrades_to_plan = min(upgrade_capacity, actual_upgrades_needed)

        if upgrades_to_plan <= 0:
            return []

        # Plan multiple upgrades up to actual available count
        for i in range(upgrades_to_plan):
            actions.append(
                Action(
                    type=ActionType.UPGRADE_NODE,
                    node_id=None,  # Executor will query for oldest outdated nodes
                    priority=60,
                    reason=f"upgrade outdated node ({i+1}/{upgrades_to_plan})",
                )
            )

        return actions

    def _plan_node_additions(self) -> List[Action]:
        """Plan adding new nodes or starting stopped nodes with aggressive scaling.

        Returns:
            List of start/add actions, limited by capacity AND actual available nodes
        """
        actions = []

        # Calculate available start slots
        current_starting = self.metrics.get("restarting_nodes", 0)
        current_ops = self._get_current_operations()

        # Determine capacity
        start_capacity = min(
            self.config["max_concurrent_starts"] - current_starting,
            self.config["max_concurrent_operations"] - current_ops
        )

        if start_capacity <= 0:
            return []

        # CRITICAL: Plan starts for stopped nodes (limited by actual stopped nodes)
        stopped_to_start = min(
            self.metrics.get("stopped_nodes", 0),
            start_capacity
        )

        for i in range(stopped_to_start):
            actions.append(
                Action(
                    type=ActionType.START_NODE,
                    node_id=None,  # Executor will query for oldest stopped nodes
                    priority=50,
                    reason=f"start stopped node ({i+1}/{stopped_to_start})",
                )
            )

        # CRITICAL: Plan additions for remaining capacity (if under node cap)
        remaining_capacity = start_capacity - stopped_to_start
        nodes_to_add = min(
            remaining_capacity,
            self.config["node_cap"] - self.metrics["total_nodes"]
        )

        for i in range(nodes_to_add):
            actions.append(
                Action(
                    type=ActionType.ADD_NODE,
                    priority=40,
                    reason=f"add new node ({i+1}/{nodes_to_add})",
                )
            )

        return actions

    def _get_current_operations(self) -> int:
        """Get total number of current concurrent operations.

        Returns:
            Count of nodes in transitional states (upgrading, restarting, removing)
        """
        return (
            self.metrics.get("upgrading_nodes", 0)
            + self.metrics.get("restarting_nodes", 0)
            + self.metrics.get("removing_nodes", 0)
        )

    def get_features(self) -> Dict[str, bool]:
        """Get the computed decision features.

        Returns:
            Dictionary of boolean features used for decisions
        """
        return self.features
