"""Forced action functions for bypassing the decision engine.

These functions execute node lifecycle operations immediately when invoked
via --force_action. They accept an ActionExecutor instance for access to
database sessions, process managers, and shared utilities.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from packaging.version import Version
from sqlalchemy import func, select

from wnm.common import DISABLED, RESTARTING, RUNNING, STOPPED
from wnm.models import Machine, Node
from wnm.process_managers.factory import get_process_manager
from wnm.utils import (
    get_antnode_version,
    parse_service_names,
    read_node_metadata,
    read_node_metrics,
    update_node_from_metrics,
    update_nodes,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _validate_service_input(service_name):
    """Validate and parse comma-separated service names.

    Args:
        service_name: Raw service name string (possibly comma-separated)

    Returns:
        (service_names, error_response) — if error_response is not None,
        the caller should return it immediately.
    """
    service_names = parse_service_names(service_name)

    if (
        service_name is not None
        and service_names is not None
        and len(service_names) == 0
    ):
        logging.error(
            f"Invalid service_name provided (empty after parsing): {repr(service_name)}"
        )
        return None, {
            "status": "error",
            "message": f"Invalid service_name provided: {repr(service_name)}. No nodes specified.",
        }

    return service_names, None


def _apply_action_delay(executor, machine_config, idx, operation_name):
    """Sleep between batch operations if delay is configured.

    Args:
        executor: ActionExecutor instance
        machine_config: Machine configuration dict
        idx: Current iteration index (delay skipped when 0)
        operation_name: Human-readable name for log messages (e.g. "node removals")
    """
    if idx > 0:
        delay_ms = executor._get_action_delay_ms(machine_config)
        if delay_ms > 0:
            delay_seconds = delay_ms / 1000.0
            logging.info(
                f"Action delay: waiting {delay_ms}ms ({delay_seconds:.2f}s) between {operation_name}"
            )
            time.sleep(delay_seconds)


def _all_failed_response(failed_nodes, operation_verb, message_template=None):
    """Build error response when all targeted nodes failed.

    Args:
        failed_nodes: List of failure dicts with 'service' keys
        operation_verb: Past tense verb for the message (e.g. "removed", "upgraded")
        message_template: Optional custom message template with {node_list} placeholder.
                         Defaults to "None of the specified service names exist: {node_list}"

    Returns:
        Error dict if all failed, or None if not all failed.
    """
    if len(failed_nodes) == 0:
        return None

    node_list = ", ".join([f["service"] for f in failed_nodes])
    logging.warning(
        f"All specified nodes failed: {node_list}. No nodes were {operation_verb}."
    )
    if message_template is None:
        message_template = "None of the specified service names exist: {node_list}"
    return {
        "status": "error",
        "message": message_template.format(node_list=node_list),
        "failed_nodes": failed_nodes,
    }


# ---------------------------------------------------------------------------
# Force functions
# ---------------------------------------------------------------------------


def force_add_node(executor, machine_config, metrics, dry_run, count=1):
    """Force add new nodes.

    Args:
        executor: ActionExecutor instance
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

    start_time = int(time.time())

    for i in range(count):
        _apply_action_delay(executor, machine_config, i, "node additions")

        result = executor._execute_add_node(machine_config, metrics, dry_run)
        if result["status"] in ["added-node", "add-node"]:
            if not dry_run:
                with executor.S() as session:
                    newest = session.execute(
                        select(Node)
                        .where(Node.age >= start_time)
                        .order_by(Node.age.desc())
                    ).first()
                    if newest:
                        added_nodes.append(newest[0].service.replace(".service", ""))
            else:
                added_nodes.append(f"node-{i+1}")
        else:
            failed_nodes.append(
                {"index": i + 1, "error": result.get("status", "unknown error")}
            )

    if count == 1:
        return result

    return {
        "status": "added-nodes" if not dry_run else "add-nodes-dryrun",
        "added_count": len(added_nodes),
        "added_nodes": added_nodes if added_nodes else None,
        "failed_count": len(failed_nodes),
        "failed_nodes": failed_nodes if failed_nodes else None,
    }


def force_remove_node(executor, service_name, dry_run, count=1):
    """Force remove nodes (specific or youngest by age).

    Args:
        executor: ActionExecutor instance
        service_name: Optional comma-separated list of service names
        dry_run: If True, log without executing
        count: Number of nodes to remove when service_name is not specified (default: 1)

    Returns:
        Dictionary with execution result
    """
    service_names, error = _validate_service_input(service_name)
    if error:
        return error

    if service_names:
        removed_nodes = []
        failed_nodes = []

        for idx, name in enumerate(service_names):
            _apply_action_delay(executor, executor.machine_config, idx, "node removals")

            node = executor._get_node_by_name(name)
            if not node:
                failed_nodes.append({"service": name, "error": "not found"})
                continue

            logging.info(f"Forced action: Removing node {name}")
            if dry_run:
                logging.warning(f"DRYRUN: Remove node {name}")
                removed_nodes.append(name)
            else:
                try:
                    manager = executor._get_process_manager(node)
                    manager.remove_node(node)
                    with executor.S() as session:
                        session.delete(node)
                        session.commit()
                    removed_nodes.append(name)
                except Exception as e:
                    logging.error(f"Failed to remove node {name}: {e}")
                    failed_nodes.append({"service": name, "error": str(e)})

        if len(removed_nodes) == 0 and len(failed_nodes) > 0:
            return _all_failed_response(failed_nodes, "removed")

        return {
            "status": "removed-nodes" if not dry_run else "remove-dryrun",
            "removed_count": len(removed_nodes),
            "removed_nodes": removed_nodes,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }
    else:
        if count < 1:
            return {"status": "error", "message": "count must be at least 1"}

        logging.info(f"Forced action: Removing {count} youngest node(s)")

        with executor.S() as session:
            youngest_nodes = session.execute(
                select(Node).order_by(Node.age.desc()).limit(count)
            ).all()

        if not youngest_nodes:
            return {"status": "error", "message": "No nodes to remove"}

        if len(youngest_nodes) < count:
            logging.warning(
                f"Only {len(youngest_nodes)} nodes available, removing all of them"
            )

        removed_nodes = []
        failed_nodes = []

        for idx, row in enumerate(youngest_nodes):
            _apply_action_delay(executor, executor.machine_config, idx, "node removals")

            node = row[0]
            if dry_run:
                logging.warning(f"DRYRUN: Remove youngest node {node.node_name}")
                removed_nodes.append(node.service.replace(".service", ""))
            else:
                try:
                    manager = executor._get_process_manager(node)
                    manager.remove_node(node)
                    with executor.S() as session:
                        session.delete(node)
                        session.commit()
                    removed_nodes.append(node.service.replace(".service", ""))
                except Exception as e:
                    logging.error(f"Failed to remove node {node.node_name}: {e}")
                    failed_nodes.append(
                        {
                            "service": node.service.replace(".service", ""),
                            "error": str(e),
                        }
                    )

        if count == 1 and len(removed_nodes) == 1:
            node_name = removed_nodes[0].replace("antnode", "")
            return {"status": "removed-node", "node": node_name}

        return {
            "status": "removed-nodes" if not dry_run else "remove-dryrun",
            "removed_count": len(removed_nodes),
            "removed_nodes": removed_nodes if removed_nodes else None,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }


def force_upgrade_node(executor, service_name, metrics, dry_run, count=1):
    """Force upgrade nodes (specific or oldest running nodes by age).

    Args:
        executor: ActionExecutor instance
        service_name: Optional comma-separated list of service names
        metrics: Current system metrics
        dry_run: If True, log without executing
        count: Number of nodes to upgrade when service_name is not specified (default: 1)

    Returns:
        Dictionary with execution result
    """
    service_names, error = _validate_service_input(service_name)
    if error:
        return error

    if service_names:
        upgraded_nodes = []
        failed_nodes = []

        for idx, name in enumerate(service_names):
            _apply_action_delay(executor, executor.machine_config, idx, "node upgrades")

            node = executor._get_node_by_name(name)
            if not node:
                failed_nodes.append({"service": name, "error": "not found"})
                continue

            logging.info(f"Forced action: Upgrading node {name}")
            if dry_run:
                logging.warning(f"DRYRUN: Upgrade node {name}")
                upgraded_nodes.append(name)
            else:
                try:
                    if not executor._upgrade_node_binary(
                        node, metrics["antnode_version"]
                    ):
                        failed_nodes.append(
                            {"service": name, "error": "upgrade failed"}
                        )
                    else:
                        upgraded_nodes.append(name)
                except Exception as e:
                    logging.error(f"Failed to upgrade node {name}: {e}")
                    failed_nodes.append({"service": name, "error": str(e)})

        if len(upgraded_nodes) == 0 and len(failed_nodes) > 0:
            return _all_failed_response(failed_nodes, "upgraded")

        return {
            "status": "upgraded-nodes" if not dry_run else "upgrade-dryrun",
            "upgraded_count": len(upgraded_nodes),
            "upgraded_nodes": upgraded_nodes,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }
    else:
        if count < 1:
            return {"status": "error", "message": "count must be at least 1"}

        logging.info(f"Forced action: Upgrading {count} oldest running node(s)")

        with executor.S() as session:
            oldest_nodes = session.execute(
                select(Node)
                .where(Node.status == RUNNING)
                .order_by(Node.age.asc())
                .limit(count)
            ).all()

        if not oldest_nodes:
            return {"status": "error", "message": "No running nodes to upgrade"}

        if len(oldest_nodes) < count:
            logging.warning(
                f"Only {len(oldest_nodes)} running nodes available, upgrading all of them"
            )

        upgraded_nodes = []
        failed_nodes = []

        for idx, row in enumerate(oldest_nodes):
            _apply_action_delay(executor, executor.machine_config, idx, "node upgrades")

            node = row[0]
            if dry_run:
                logging.warning(f"DRYRUN: Upgrade oldest node {node.node_name}")
                upgraded_nodes.append(node.service.replace(".service", ""))
            else:
                try:
                    if not executor._upgrade_node_binary(
                        node, metrics["antnode_version"]
                    ):
                        failed_nodes.append(
                            {
                                "service": node.service.replace(".service", ""),
                                "error": "upgrade failed",
                            }
                        )
                    else:
                        upgraded_nodes.append(node.service.replace(".service", ""))
                except Exception as e:
                    logging.error(f"Failed to upgrade node {node.node_name}: {e}")
                    failed_nodes.append(
                        {
                            "service": node.service.replace(".service", ""),
                            "error": str(e),
                        }
                    )

        if count == 1 and len(upgraded_nodes) == 1:
            node_name = upgraded_nodes[0].replace("antnode", "")
            return {"status": "upgraded-node", "node": node_name}

        return {
            "status": "upgraded-nodes" if not dry_run else "upgrade-dryrun",
            "upgraded_count": len(upgraded_nodes),
            "upgraded_nodes": upgraded_nodes if upgraded_nodes else None,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }


def force_stop_node(executor, service_name, dry_run, count=1):
    """Force stop nodes (specific or youngest running nodes by age).

    Args:
        executor: ActionExecutor instance
        service_name: Optional comma-separated list of service names
        dry_run: If True, log without executing
        count: Number of nodes to stop when service_name is not specified (default: 1)

    Returns:
        Dictionary with execution result
    """
    service_names, error = _validate_service_input(service_name)
    if error:
        return error

    if service_names:
        stopped_nodes = []
        failed_nodes = []

        for idx, name in enumerate(service_names):
            _apply_action_delay(executor, executor.machine_config, idx, "node stops")

            node = executor._get_node_by_name(name)
            if not node:
                failed_nodes.append({"service": name, "error": "not found"})
                continue

            logging.info(f"Forced action: Stopping node {name}")
            if dry_run:
                logging.warning(f"DRYRUN: Stop node {name}")
                stopped_nodes.append(name)
            else:
                try:
                    manager = executor._get_process_manager(node)
                    manager.stop_node(node)
                    executor._set_node_status(node.id, STOPPED)
                    stopped_nodes.append(name)
                except Exception as e:
                    logging.error(f"Failed to stop node {name}: {e}")
                    failed_nodes.append({"service": name, "error": str(e)})

        if len(stopped_nodes) == 0 and len(failed_nodes) > 0:
            return _all_failed_response(failed_nodes, "stopped")

        return {
            "status": "stopped-nodes" if not dry_run else "stop-dryrun",
            "stopped_count": len(stopped_nodes),
            "stopped_nodes": stopped_nodes,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }
    else:
        if count < 1:
            return {"status": "error", "message": "count must be at least 1"}

        logging.info(f"Forced action: Stopping {count} youngest running node(s)")

        with executor.S() as session:
            youngest_nodes = session.execute(
                select(Node)
                .where(Node.status == RUNNING)
                .order_by(Node.age.desc())
                .limit(count)
            ).all()

        if not youngest_nodes:
            return {"status": "error", "message": "No running nodes to stop"}

        if len(youngest_nodes) < count:
            logging.warning(
                f"Only {len(youngest_nodes)} running nodes available, stopping all of them"
            )

        stopped_nodes = []
        failed_nodes = []

        for idx, row in enumerate(youngest_nodes):
            _apply_action_delay(executor, executor.machine_config, idx, "node stops")

            node = row[0]
            if dry_run:
                logging.warning(f"DRYRUN: Stop youngest node {node.node_name}")
                stopped_nodes.append(node.service.replace(".service", ""))
            else:
                try:
                    manager = executor._get_process_manager(node)
                    manager.stop_node(node)
                    executor._set_node_status(node.id, STOPPED)
                    stopped_nodes.append(node.service.replace(".service", ""))
                except Exception as e:
                    logging.error(f"Failed to stop node {node.node_name}: {e}")
                    failed_nodes.append(
                        {
                            "service": node.service.replace(".service", ""),
                            "error": str(e),
                        }
                    )

        if count == 1 and len(stopped_nodes) == 1:
            node_name = stopped_nodes[0].replace("antnode", "")
            return {"status": "stopped-node", "node": node_name}

        return {
            "status": "stopped-nodes" if not dry_run else "stop-dryrun",
            "stopped_count": len(stopped_nodes),
            "stopped_nodes": stopped_nodes if stopped_nodes else None,
            "failed_count": len(failed_nodes),
            "failed_nodes": failed_nodes if failed_nodes else None,
        }


def force_start_node(executor, service_name, metrics, dry_run, count=1):
    """Force start nodes (specific or oldest stopped nodes by age).

    Args:
        executor: ActionExecutor instance
        service_name: Optional comma-separated list of service names
        metrics: Current system metrics
        dry_run: If True, log without executing
        count: Number of nodes to start when service_name is not specified (default: 1)

    Returns:
        Dictionary with execution result
    """
    service_names, error = _validate_service_input(service_name)
    if error:
        return error

    if service_names:
        started_nodes = []
        upgraded_nodes = []
        failed_nodes = []

        for idx, name in enumerate(service_names):
            _apply_action_delay(executor, executor.machine_config, idx, "node starts")

            node = executor._get_node_by_name(name)
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
                    if not node.version:
                        node.version = get_antnode_version(node.binary)

                    if Version(metrics["antnode_version"]) > Version(node.version):
                        if not executor._upgrade_node_binary(
                            node, metrics["antnode_version"]
                        ):
                            failed_nodes.append(
                                {"service": name, "error": "upgrade failed"}
                            )
                        else:
                            upgraded_nodes.append(name)
                    else:
                        manager = executor._get_process_manager(node)
                        if manager.start_node(node):
                            executor._set_node_status(node.id, RESTARTING)
                            started_nodes.append(name)
                        else:
                            failed_nodes.append(
                                {"service": name, "error": "start failed"}
                            )
                except Exception as e:
                    logging.error(f"Failed to start node {name}: {e}")
                    failed_nodes.append({"service": name, "error": str(e)})

        if (
            len(started_nodes) == 0
            and len(upgraded_nodes) == 0
            and len(failed_nodes) > 0
        ):
            return _all_failed_response(
                failed_nodes,
                "started",
                "None of the specified service names could be started: {node_list}",
            )

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
        if count < 1:
            return {"status": "error", "message": "count must be at least 1"}

        logging.info(f"Forced action: Starting {count} oldest stopped node(s)")

        with executor.S() as session:
            oldest_nodes = session.execute(
                select(Node)
                .where(Node.status == STOPPED)
                .order_by(Node.age.asc())
                .limit(count)
            ).all()

        if not oldest_nodes:
            return {"status": "error", "message": "No stopped nodes to start"}

        if len(oldest_nodes) < count:
            logging.warning(
                f"Only {len(oldest_nodes)} stopped nodes available, starting all of them"
            )

        started_nodes = []
        upgraded_nodes = []
        failed_nodes = []

        for idx, row in enumerate(oldest_nodes):
            _apply_action_delay(executor, executor.machine_config, idx, "node starts")

            node = row[0]
            if dry_run:
                logging.warning(f"DRYRUN: Start oldest stopped node {node.node_name}")
                started_nodes.append(node.service.replace(".service", ""))
            else:
                try:
                    if not node.version:
                        node.version = get_antnode_version(node.binary)

                    if Version(metrics["antnode_version"]) > Version(node.version):
                        if not executor._upgrade_node_binary(
                            node, metrics["antnode_version"]
                        ):
                            failed_nodes.append(
                                {
                                    "service": node.service.replace(".service", ""),
                                    "error": "upgrade failed",
                                }
                            )
                        else:
                            upgraded_nodes.append(node.service.replace(".service", ""))
                    else:
                        manager = executor._get_process_manager(node)
                        if manager.start_node(node):
                            executor._set_node_status(node.id, RESTARTING)
                            started_nodes.append(node.service.replace(".service", ""))
                        else:
                            failed_nodes.append(
                                {
                                    "service": node.service.replace(".service", ""),
                                    "error": "start failed",
                                }
                            )
                except Exception as e:
                    logging.error(f"Failed to start node {node.node_name}: {e}")
                    failed_nodes.append(
                        {
                            "service": node.service.replace(".service", ""),
                            "error": str(e),
                        }
                    )

        if count == 1 and len(started_nodes) == 1:
            node_name = started_nodes[0].replace("antnode", "")
            return {"status": "started-node", "node": node_name}
        elif count == 1 and len(upgraded_nodes) == 1:
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


def force_disable_node(executor, service_name, dry_run):
    """Force disable a specific node (service_name required).

    Args:
        executor: ActionExecutor instance
        service_name: Comma-separated list of service names
        dry_run: If True, log without executing

    Returns:
        Dictionary with execution result
    """
    if not service_name:
        return {
            "status": "error",
            "message": "service_name required for disable action",
        }

    service_names, error = _validate_service_input(service_name)
    if error:
        return error

    disabled_nodes = []
    failed_nodes = []

    for name in service_names:
        node = executor._get_node_by_name(name)
        if not node:
            logging.warning(f"Cannot disable node {name}: not found")
            failed_nodes.append({"service": name, "error": "not found"})
            continue

        logging.info(f"Forced action: Disabling node {name}")
        if dry_run:
            logging.warning(f"DRYRUN: Disable node {name}")
            disabled_nodes.append(name)
        else:
            try:
                manager = executor._get_process_manager(node)
                manager.stop_node(node)
                executor._set_node_status(node.id, DISABLED)
                disabled_nodes.append(name)
            except Exception as e:
                logging.error(f"Failed to disable node {name}: {e}")
                failed_nodes.append({"service": name, "error": str(e)})

    if len(disabled_nodes) == 0 and len(failed_nodes) > 0:
        return _all_failed_response(failed_nodes, "disabled")

    return {
        "status": "disabled-nodes" if not dry_run else "disable-dryrun",
        "disabled_count": len(disabled_nodes),
        "disabled_nodes": disabled_nodes,
        "failed_count": len(failed_nodes),
        "failed_nodes": failed_nodes if failed_nodes else None,
    }


def force_teardown_cluster(executor, machine_config, dry_run):
    """Force teardown the entire cluster.

    Args:
        executor: ActionExecutor instance
        machine_config: Machine configuration
        dry_run: If True, log without executing

    Returns:
        Dictionary with execution result
    """
    logging.info("Forced action: Tearing down cluster")

    with executor.S() as session:
        all_nodes = session.execute(select(Node).order_by(Node.id.asc())).all()

    if not all_nodes:
        return {"status": "no-nodes", "message": "No nodes to teardown"}

    if all_nodes:
        sample_node = all_nodes[0][0]
        manager = executor._get_process_manager(sample_node)
    else:
        manager = get_process_manager()

    if hasattr(manager, "teardown_cluster"):
        logging.info(f"Using {manager.__class__.__name__} teardown_cluster method")
        if dry_run:
            logging.warning("DRYRUN: Teardown cluster via manager")
        else:
            if manager.teardown_cluster():
                from wnm.process_managers.antctl_manager import AntctlManager
                from wnm.process_managers.antctl_zen_manager import AntctlZenManager

                if isinstance(manager, (AntctlManager, AntctlZenManager)):
                    logging.info(
                        "Resetting highest_node_id_used to 0 after antctl reset"
                    )
                    with executor.S() as session:
                        session.query(Machine).filter(Machine.id == 1).update(
                            {"highest_node_id_used": 0}
                        )
                        session.commit()

                with executor.S() as session:
                    session.query(Node).delete()
                    session.commit()
                return {"status": "cluster-teardown", "method": "manager-specific"}

    logging.info("Using default teardown (remove all nodes)")
    removed_count = 0
    for row in all_nodes:
        node = row[0]
        if dry_run:
            logging.warning(f"DRYRUN: Remove node {node.node_name}")
            removed_count += 1
        else:
            try:
                manager = executor._get_process_manager(node)
                manager.remove_node(node)
                with executor.S() as session:
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


def _survey_specific_nodes(executor, service_names, dry_run):
    """Survey specific nodes by service name.

    Args:
        executor: ActionExecutor instance
        service_names: List of service names to survey
        dry_run: If True, log without executing

    Returns:
        Dictionary with survey results
    """
    surveyed_nodes = []
    failed_nodes = []
    survey_delay_ms = executor._get_survey_delay_ms(executor.machine_config)

    for idx, service_name in enumerate(service_names):
        node = executor._get_node_by_name(service_name)
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

            node_metadata = read_node_metadata(node.host, node.metrics_port)

            if node_metadata["status"] == STOPPED:
                node_metrics = {
                    "status": STOPPED,
                    "uptime": 0,
                    "records": 0,
                    "shunned": 0,
                    "connected_peers": 0,
                }
            else:
                node_metrics = read_node_metrics(node.host, node.metrics_port)

            if node_metadata["status"] == STOPPED and node.status == STOPPED:
                surveyed_nodes.append(service_name)
                continue

            update_node_from_metrics(executor.S, node.id, node_metrics, node_metadata)
            surveyed_nodes.append(service_name)

        if survey_delay_ms > 0 and idx < len(service_names) - 1:
            time.sleep(survey_delay_ms / 1000.0)

    return {
        "status": "survey-complete" if not dry_run else "survey-dryrun",
        "surveyed_count": len(surveyed_nodes),
        "surveyed_nodes": surveyed_nodes,
        "failed_count": len(failed_nodes),
        "failed_nodes": failed_nodes if failed_nodes else None,
    }


def force_survey_nodes(executor, service_name=None, dry_run=False):
    """Force a survey of all nodes or specific nodes.

    Args:
        executor: ActionExecutor instance
        service_name: Optional comma-separated list of service names to survey
        dry_run: If True, log without executing

    Returns:
        Dictionary with survey results
    """
    service_names = parse_service_names(service_name)

    if service_names:
        logging.info(f"Forced action: Surveying {len(service_names)} specific nodes")
        return _survey_specific_nodes(executor, service_names, dry_run)
    else:
        logging.info("Forced action: Surveying all nodes")

        if dry_run:
            logging.warning("DRYRUN: Survey all nodes")
            with executor.S() as session:
                node_count = session.execute(
                    select(func.count(Node.id)).where(Node.status != DISABLED)
                ).scalar()
            return {"status": "survey-dryrun", "node_count": node_count}

        survey_delay_ms = executor._get_survey_delay_ms(executor.machine_config)
        update_nodes(executor.S, survey_delay_ms=survey_delay_ms)

        with executor.S() as session:
            node_count = session.execute(
                select(func.count(Node.id)).where(Node.status != DISABLED)
            ).scalar()

        return {"status": "survey-complete", "node_count": node_count}
