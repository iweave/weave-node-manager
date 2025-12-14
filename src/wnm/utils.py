import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from typing import List, Optional

import psutil
import requests
from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.orm import scoped_session, sessionmaker

from wnm.common import (
    DEAD,
    DISABLED,
    DONATE,
    METRICS_PORT_BASE,
    MIGRATING,
    MIN_NODES_THRESHOLD,
    PORT_MULTIPLIER,
    QUEEN,
    REMOVING,
    RESTARTING,
    RUNNING,
    STOPPED,
    UPGRADING,
)
from wnm.config import BOOTSTRAP_CACHE_DIR, LOG_DIR, PLATFORM
from wnm.models import Base, Machine, Node


def parse_service_names(service_name_str: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated service names.

    Args:
        service_name_str: Comma-separated service names (e.g., "antnode0001,antnode0003")

    Returns:
        List of service names, or None if input is None/empty
    """
    if not service_name_str:
        return None

    # Split by comma and strip whitespace
    names = [name.strip() for name in service_name_str.split(',')]
    # Filter out empty strings
    return [name for name in names if name]


# Read config from systemd service file
def read_node_metadata(host, port):
    # Only return version number when we have one, to stop clobbering the binary check
    try:
        url = "http://{0}:{1}/metadata".format(host, port)
        response = requests.get(url, timeout=5)
        data = response.text
    except requests.exceptions.ConnectionError:
        logging.debug("Connection Refused on port: {0}:{1}".format(host, str(port)))
        return {"status": STOPPED, "peer_id": ""}
    except Exception as error:
        template = "In RNMd - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return {"status": STOPPED, "peer_id": ""}
    # collect a dict to return
    card = {}
    try:
        card["version"] = re.findall(r'{antnode_version="([\d\.]+)"}', data)[0]
    except (IndexError, KeyError) as e:
        logging.info(f"No version found: {e}")
    try:
        card["peer_id"] = re.findall(r'{peer_id="([\w\d]+)"}', data)[0]
    except (IndexError, KeyError) as e:
        logging.debug(f"No peer_id found: {e}")
        card["peer_id"] = ""
    card["status"] = RUNNING if "version" in card else STOPPED
    return card


# Read data from metrics port
def read_node_metrics(host, port):
    metrics = {}
    try:
        url = "http://{0}:{1}/metrics".format(host, port)
        response = requests.get(url, timeout=5)
        metrics["status"] = RUNNING

        # Original metrics (already collected)
        metrics["uptime"] = int(
            (re.findall(r"ant_node_uptime ([\d]+)", response.text) or [0])[0]
        )
        metrics["records"] = int(
            (
                re.findall(r"ant_networking_records_stored ([\d]+)", response.text)
                or [0]
            )[0]
        )
        metrics["shunned"] = int(
            (
                re.findall(
                    r"ant_networking_shunned_by_close_group ([\d]+)", response.text
                )
                or [0]
            )[0]
        )
        metrics["connected_peers"] = int(
            (
                re.findall(r"ant_networking_connected_peers ([\d]+)", response.text)
                or [0]
            )[0]
        )

        # New influx-specific metrics
        # PUTs (counter, use _total suffix)
        metrics["puts"] = int(
            (re.findall(r"ant_node_put_record_ok_total(?:\{[^}]*\})? ([\d]+)", response.text) or [0])[0]
        )

        # GETs (not currently exposed, default to 0)
        metrics["gets"] = 0

        # Rewards (as string for high precision)
        metrics["rewards"] = str(
            (re.findall(r"ant_node_current_reward_wallet_balance ([\d.]+)", response.text) or ["0"])[0]
        )

        # Memory in MB * 100 (e.g., 97.8125 -> 9781)
        mem_mb = float((re.findall(r"ant_networking_process_memory_used_mb ([\d.]+)", response.text) or [0])[0])
        metrics["mem"] = int(mem_mb * 100)

        # CPU percentage * 100 (e.g., 0.0353 -> 4)
        cpu_pct = float((re.findall(r"ant_networking_process_cpu_usage_percentage ([\d.]+)", response.text) or [0])[0])
        metrics["cpu"] = int(cpu_pct * 100)

        # Open connections
        metrics["open_connections"] = int(
            (re.findall(r"ant_networking_open_connections ([\d]+)", response.text) or [0])[0]
        )

        # Total peers in routing table
        metrics["total_peers"] = int(
            (re.findall(r"ant_networking_peers_in_routing_table ([\d]+)", response.text) or [0])[0]
        )

        # Bad peers (counter, use _total suffix)
        metrics["bad_peers"] = int(
            (re.findall(r"ant_networking_bad_peers_count_total ([\d]+)", response.text) or [0])[0]
        )

        # Relevant records
        metrics["rel_records"] = int(
            (re.findall(r"ant_networking_relevant_records ([\d]+)", response.text) or [0])[0]
        )

        # Maximum records
        metrics["max_records"] = int(
            (re.findall(r"ant_networking_max_records ([\d]+)", response.text) or [0])[0]
        )

        # Payment count
        metrics["payment_count"] = int(
            (re.findall(r"ant_networking_received_payment_count ([\d]+)", response.text) or [0])[0]
        )

        # Live time
        metrics["live_time"] = int(
            (re.findall(r"ant_networking_live_time ([\d]+)", response.text) or [0])[0]
        )

        # Network size
        metrics["network_size"] = int(
            (re.findall(r"ant_networking_estimated_network_size ([\d]+)", response.text) or [0])[0]
        )
    except requests.exceptions.ConnectionError:
        logging.debug("Connection Refused on port: {0}:{1}".format(host, str(port)))
        metrics["status"] = STOPPED
        metrics["uptime"] = 0
        metrics["records"] = 0
        metrics["shunned"] = 0
        metrics["connected_peers"] = 0
    except Exception as error:
        template = "in:RNM - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        metrics["status"] = STOPPED
        metrics["uptime"] = 0
        metrics["records"] = 0
        metrics["shunned"] = 0
        metrics["connected_peers"] = 0
    return metrics


# Read antnode binary version
def get_antnode_version(binary):
    try:
        data = subprocess.run(
            [binary, "--version"], stdout=subprocess.PIPE
        ).stdout.decode("utf-8")
        return re.findall(r"Autonomi Node v([\d\.]+)", data)[0]
    except Exception as error:
        template = "In GAV - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return 0


# Determine how long this node has been around by looking at it's secret_key file
def get_node_age(root_dir):
    try:
        return int(os.stat("{0}/secret-key".format(root_dir)).st_mtime)
    except (FileNotFoundError, OSError) as e:
        logging.debug(f"Unable to get node age for {root_dir}: {e}")
        return 0


# Get the system start time (boot time) as a Unix timestamp
def get_system_start_time():
    """Get system boot time as Unix timestamp.

    Returns:
        int: Unix timestamp of system boot time, or 0 on error
    """
    try:
        if PLATFORM == "Darwin":
            # macOS: use sysctl kern.boottime
            p = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
            ).stdout.decode("utf-8")
            # Parse: { sec = 1234567890, usec = 0 }
            match = re.search(r"sec = (\d+)", p)
            if match:
                return int(match.group(1))
            else:
                raise ValueError("Could not parse kern.boottime")
        else:
            # Linux: use uptime --since
            p = subprocess.run(
                ["uptime", "--since"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            ).stdout.decode("utf-8")
            if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", p):
                return int(
                    time.mktime(time.strptime(p.strip(), "%Y-%m-%d %H:%M:%S"))
                )
    except (subprocess.CalledProcessError, ValueError) as err:
        logging.error(f"Error getting system start time: {err}")
        return 0

    return 0


# Survey nodes by reading metadata from metrics ports or binary --version
def get_machine_metrics(S, node_storage, remove_limit, crisis_bytes):
    metrics = {}

    with S() as session:
        db_nodes = session.execute(select(Node.status, Node.version)).all()

    # Get system start time before we probe metrics
    metrics["system_start"] = get_system_start_time()

    # Get some initial stats for comparing after a few seconds
    # We start these counters AFTER reading the database
    start_time = time.time()
    start_disk_counters = psutil.disk_io_counters()
    start_net_counters = psutil.net_io_counters()

    metrics["total_nodes"] = len(db_nodes)
    data = Counter(node[0] for node in db_nodes)
    metrics["running_nodes"] = data[RUNNING]
    metrics["stopped_nodes"] = data[STOPPED]
    metrics["restarting_nodes"] = data[RESTARTING]
    metrics["upgrading_nodes"] = data[UPGRADING]
    metrics["migrating_nodes"] = data[MIGRATING]
    metrics["removing_nodes"] = data[REMOVING]
    metrics["dead_nodes"] = data[DEAD]
    metrics["antnode"] = shutil.which("antnode")
    if not metrics["antnode"]:
        logging.warning("Unable to locate current antnode binary, exiting")
        sys.exit(1)
    metrics["antnode_version"] = get_antnode_version(metrics["antnode"])
    metrics["queen_node_version"] = (
        db_nodes[0][1] if metrics["total_nodes"] > 0 else metrics["antnode_version"]
    )
    metrics["nodes_latest_v"] = (
        sum(1 for node in db_nodes if node[1] == metrics["antnode_version"]) or 0
    )
    metrics["nodes_no_version"] = sum(1 for node in db_nodes if not node[1]) or 0
    metrics["nodes_to_upgrade"] = (
        metrics["total_nodes"] - metrics["nodes_latest_v"] - metrics["nodes_no_version"]
    )
    metrics["nodes_by_version"] = Counter(ver[1] for ver in db_nodes)

    # Windows has to build load average over 5 seconds. The first 5 seconds returns 0's
    # I don't plan on supporting windows, but if this get's modular, I don't want this
    # issue to be skipped
    # if platform.system() == "Windows":
    #    discard=psutil.getloadavg()
    #    time.sleep(5)
    metrics["load_average_1"], metrics["load_average_5"], metrics["load_average_15"] = (
        psutil.getloadavg()
    )
    # Get CPU Metrics over 1 second
    cpu_times = psutil.cpu_times_percent(1)
    if PLATFORM == "Darwin":
        # macOS: cpu_times has (user, nice, system, idle) - no iowait
        metrics["idle_cpu_percent"] = cpu_times.idle
        metrics["io_wait"] = 0  # Not available on macOS
    else:
        # Linux: cpu_times has (user, nice, system, idle, iowait, ...)
        metrics["idle_cpu_percent"], metrics["io_wait"] = cpu_times[3:5]
    # Really we returned Idle percent, subtract from 100 to get used.
    metrics["used_cpu_percent"] = 100 - metrics["idle_cpu_percent"]
    data = psutil.virtual_memory()
    # print(data)
    metrics["used_mem_percent"] = data.percent
    metrics["free_mem_percent"] = 100 - metrics["used_mem_percent"]
    data = psutil.disk_io_counters()
    # This only checks the drive mapped to the first node and will need to be updated
    # when we eventually support multiple drives
    # Ensure the node_storage directory exists before checking disk usage
    if not os.path.exists(node_storage):
        logging.warning(f"node_storage path does not exist: {node_storage}. Creating it.")
        os.makedirs(node_storage, exist_ok=True)
    data = psutil.disk_usage(node_storage)
    metrics["used_hd_percent"] = data.percent
    metrics["total_hd_bytes"] = data.total
    end_time = time.time()
    end_disk_counters = psutil.disk_io_counters()
    end_net_counters = psutil.net_io_counters()
    metrics["hdio_write_bytes"] = int(
        (end_disk_counters.write_bytes - start_disk_counters.write_bytes)
        / (end_time - start_time)
    )
    metrics["hdio_read_bytes"] = int(
        (end_disk_counters.read_bytes - start_disk_counters.read_bytes)
        / (end_time - start_time)
    )
    metrics["netio_write_bytes"] = int(
        (end_net_counters.bytes_sent - start_net_counters.bytes_sent)
        / (end_time - start_time)
    )
    metrics["netio_read_bytes"] = int(
        (end_net_counters.bytes_recv - start_net_counters.bytes_recv)
        / (end_time - start_time)
    )
    # print (json.dumps(metrics,indent=2))
    # How close (out of 100) to removal limit will we be with a max bytes per node (2GB default)
    # For running nodes with Porpoise(tm).
    metrics["node_hd_crisis"] = int(
        (
            ((metrics["total_nodes"]) * int(crisis_bytes))
            / (metrics["total_hd_bytes"] * (remove_limit / 100))
        )
        * 100
    )
    return metrics


# Update node with metrics result
def update_node_from_metrics(S, id, metrics, metadata):
    try:
        # We check the binary version in other code, so lets stop clobbering it when a node is stopped
        card = {
            "status": metrics["status"],
            "timestamp": int(time.time()),
            "uptime": metrics["uptime"],
            "records": metrics["records"],
            "shunned": metrics["shunned"],
            "connected_peers": metrics["connected_peers"],
            "peer_id": metadata["peer_id"],
        }

        # Add influx-specific metrics if available (only for RUNNING nodes)
        if metrics["status"] == RUNNING:
            card["gets"] = metrics.get("gets", 0)
            card["puts"] = metrics.get("puts", 0)
            card["mem"] = metrics.get("mem", 0)
            card["cpu"] = metrics.get("cpu", 0)
            card["open_connections"] = metrics.get("open_connections", 0)
            card["total_peers"] = metrics.get("total_peers", 0)
            card["bad_peers"] = metrics.get("bad_peers", 0)
            card["rel_records"] = metrics.get("rel_records", 0)
            card["max_records"] = metrics.get("max_records", 0)
            card["rewards"] = metrics.get("rewards", "0")
            card["payment_count"] = metrics.get("payment_count", 0)
            card["live_time"] = metrics.get("live_time", 0)
            card["network_size"] = metrics.get("network_size", 0)

        if "version" in metadata:
            card["version"] = metadata["version"]

        with S() as session:
            session.query(Node).filter(Node.id == id).update(card)
            session.commit()
    except Exception as error:
        template = "In UNFM - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.warning(message)
        return False
    else:
        return True


# Set Node status
def update_counters(S, old, config):
    # Are we already removing a node
    if old["removing_nodes"]:
        with S() as session:
            removals = session.execute(
                select(Node.timestamp, Node.id)
                .where(Node.status == REMOVING)
                .order_by(Node.timestamp.asc())
            ).all()
        # Iterate through active removals
        records_to_remove = len(removals)
        for check in removals:
            # If the delay_remove timer has expired, delete the entry
            if isinstance(check[0], int) and check[0] < (
                int(time.time()) - config["delay_remove"]
            ):
                logging.info("Deleting removed node " + str(check[1]))
                with S() as session:
                    session.execute(delete(Node).where(Node.id == check[1]))
                    session.commit()
                records_to_remove -= 1
        old["removing_nodes"] = records_to_remove
    # Are we already upgrading a node
    if old["upgrading_nodes"]:
        with S() as session:
            upgrades = session.execute(
                select(Node.timestamp, Node.id, Node.host, Node.metrics_port)
                .where(Node.status == UPGRADING)
                .order_by(Node.timestamp.asc())
            ).all()
        # Iterate through active upgrades
        records_to_upgrade = len(upgrades)
        for check in upgrades:
            # If the delay_upgrade timer has expired, check on status
            if isinstance(check[0], int) and check[0] < (
                int(time.time()) - config["delay_upgrade"]
            ):
                logging.info("Updating upgraded node " + str(check[1]))
                node_metrics = read_node_metrics(check[2], check[3])
                node_metadata = read_node_metadata(check[2], check[3])
                if node_metrics and node_metadata:
                    update_node_from_metrics(S, check[1], node_metrics, node_metadata)
                records_to_upgrade -= 1
        old["upgrading_nodes"] = records_to_upgrade
    # Are we already restarting a node
    if old["restarting_nodes"]:
        with S() as session:
            restarts = session.execute(
                select(Node.timestamp, Node.id, Node.host, Node.metrics_port)
                .where(Node.status == RESTARTING)
                .order_by(Node.timestamp.asc())
            ).all()
        # Iterate through active upgrades
        records_to_restart = len(restarts)
        for check in restarts:
            # If the delay_start timer has expired, check on status
            if isinstance(check[0], int) and check[0] < (
                int(time.time()) - config["delay_start"]
            ):
                logging.info("Updating restarted node " + str(check[1]))
                node_metrics = read_node_metrics(check[2], check[3])
                node_metadata = read_node_metadata(check[2], check[3])
                if node_metrics and node_metadata:
                    update_node_from_metrics(S, check[1], node_metrics, node_metadata)
                records_to_restart -= 1
        old["restarting_nodes"] = records_to_restart
    return old


# Enable firewall for port
def update_nodes(S, survey_delay_ms=0):
    """Update all nodes with current metrics.

    Args:
        S: SQLAlchemy session factory
        survey_delay_ms: Delay in milliseconds between surveying each node (default: 0)
    """
    with S() as session:
        nodes = session.execute(
            select(Node.timestamp, Node.id, Node.host, Node.metrics_port, Node.status)
            .where(Node.status != DISABLED)
            .order_by(Node.timestamp.asc())
        ).all()
    # Iterate through all records
    for idx, check in enumerate(nodes):
        # Check on status
        if isinstance(check[0], int):
            logging.debug("Updating info on node " + str(check[1]))
            node_metrics = read_node_metrics(check[2], check[3])
            node_metadata = read_node_metadata(check[2], check[3])
            if node_metrics and node_metadata:
                # Don't write updates for stopped nodes that are already marked as stopped
                if node_metadata["status"] == STOPPED and check[4] == STOPPED:
                    continue
                update_node_from_metrics(S, check[1], node_metrics, node_metadata)

            # Insert delay between nodes (but not after the last node)
            if survey_delay_ms > 0 and idx < len(nodes) - 1:
                time.sleep(survey_delay_ms / 1000.0)
