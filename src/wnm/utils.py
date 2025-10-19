import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter

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
from wnm.models import Base, Machine, Node


# Read config from systemd service file
def read_systemd_service(antnode, machine_config):
    details = {}
    try:
        with open("/etc/systemd/system/" + antnode, "r") as file:
            data = file.read()
        details["id"] = int(re.findall(r"antnode(\d+)", antnode)[0])
        details["binary"] = re.findall(r"ExecStart=([^ ]+)", data)[0]
        details["user"] = re.findall(r"User=(\w+)", data)[0]
        details["root_dir"] = re.findall(r"--root-dir ([\w\/]+)", data)[0]
        details["port"] = int(re.findall(r"--port (\d+)", data)[0])
        details["metrics_port"] = int(
            re.findall(r"--metrics-server-port (\d+)", data)[0]
        )
        details["wallet"] = re.findall(r"--rewards-address ([^ ]+)", data)[0]
        details["network"] = re.findall(r"--rewards-address [^ ]+ ([\w\-]+)", data)[0]
        # See if IP listen address is defined
        if ip := re.findall(r"--ip ([^ ]+)", data)[0]:
            # If we have the special wildcard listen address, use default
            if ip == "0.0.0.0":
                details["host"] = machine_config.Host
            else:
                details["host"] = ip
        if optional := re.findall(r'Environment="(.+)"', data):
            details["environment"] = optional[0]
        else:
            details["environment"] = ""

    except Exception as e:
        logging.debug(f"Error reading service file {service_file}: {e}")

    return details


# Read data from metadata endpoint
def read_node_metadata(host, port):
    # Only return version number when we have one, to stop clobbering the binary check
    try:
        url = "http://{0}:{1}/metadata".format(host, port)
        response = requests.get(url)
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
        response = requests.get(url)
        metrics["status"] = RUNNING
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
    except requests.exceptions.ConnectionError:
        logging.debug("Connection Refused on port: {0}:{1}".format(host, str(port)))
        metrics["status"] = STOPPED
        metrics["uptime"] = 0
        metrics["records"] = 0
        metrics["shunned"] = 0
    except Exception as error:
        template = "in:RNM - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        metrics["status"] = STOPPED
        metrics["uptime"] = 0
        metrics["records"] = 0
        metrics["shunned"] = 0
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


# Survey nodes by reading metadata from metrics ports or binary --version
def survey_systemd_nodes(antnodes, machine_config):
    # Build a list of node dictionaries to return
    details = []
    # Iterate on nodes
    for node in antnodes:
        # Initialize a dict
        logging.debug(
            "{0} surveying node {1} ".format(time.strftime("%Y-%m-%d %H:%M"), node)
        )
        if not re.findall(r"antnode([\d]+).service", node):
            logging.info("can't decode " + str(node))
            continue
        card = {
            "nodename": re.findall(r"antnode([\d]+).service", node)[0],
            "service": node,
            "timestamp": int(time.time()),
            "host": machine_config.Host or "127.0.0.1",
            "method": "systemd",
            "layout": "1",
        }
        # Load what systemd has configured
        card.update(read_systemd_service(node, machine_config))
        # print(json.dumps(card,indent=2))
        # Read metadata from metrics_port
        metadata = read_node_metadata(card["host"], card["metrics_port"])
        # print(json.dumps(metadata,indent=2))
        if (
            isinstance(metadata, dict)
            and "status" in metadata
            and metadata["status"] == RUNNING
        ):
            # soak up metadata
            card.update(metadata)
            # The ports up, so grab metrics too
            card.update(read_node_metrics(card["host"], card["metrics_port"]))
        # Else run binary to get version
        else:
            # If the root directory of the node is missing, it's a bad node
            if not os.path.isdir(card["root_dir"]):
                card["status"] = DEAD
                card["version"] = ""
            else:
                card["status"] = STOPPED
                card["version"] = get_antnode_version(card["binary"])
            card["peer_id"] = ""
            card["records"] = 0
            card["uptime"] = 0
            card["shunned"] = 0
        card["age"] = get_node_age(card["root_dir"])
        # harcoded for anm
        card["host"] = machine_config.Host
        # Append the node dict to the detail list
        details.append(card)

    return details


# Survey server instance
def survey_machine(machine_config):
    # Make a bucket
    antnodes = []
    # For all service files
    for file in os.listdir("/etc/systemd/system"):
        # Find antnodes
        if re.match(r"antnode[\d]+\.service", file):
            antnodes.append(file)
    # Iterate over defined nodes and get details
    # Ingests a list of service files and outputs a list of dictionaries
    return survey_systemd_nodes(antnodes, machine_config)


# Read system status
def get_machine_metrics(S, node_storage, remove_limit, crisis_bytes):
    metrics = {}

    with S() as session:
        db_nodes = session.execute(select(Node.status, Node.version)).all()

    # Get system start time before we probe metrics
    try:
        p = subprocess.run(
            ["uptime", "--since"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout.decode("utf-8")
        if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", p):
            metrics["SystemStart"] = int(
                time.mktime(time.strptime(p.strip(), "%Y-%m-%d %H:%M:%S"))
            )
    except subprocess.CalledProcessError as err:
        logging.error("GMM ERROR:", err)
        metrics["SystemStart"] = 0

    # Get some initial stats for comparing after a few seconds
    # We start these counters AFTER reading the database
    start_time = time.time()
    start_disk_counters = psutil.disk_io_counters()
    start_net_counters = psutil.net_io_counters()

    metrics["TotalNodes"] = len(db_nodes)
    data = Counter(node[0] for node in db_nodes)
    metrics["RunningNodes"] = data[RUNNING]
    metrics["StoppedNodes"] = data[STOPPED]
    metrics["RestartingNodes"] = data[RESTARTING]
    metrics["UpgradingNodes"] = data[UPGRADING]
    metrics["MigratingNodes"] = data[MIGRATING]
    metrics["RemovingNodes"] = data[REMOVING]
    metrics["DeadNodes"] = data[DEAD]
    metrics["antnode"] = shutil.which("antnode")
    if not metrics["antnode"]:
        logging.warning("Unable to locate current antnode binary, exiting")
        sys.exit(1)
    metrics["AntNodeVersion"] = get_antnode_version(metrics["antnode"])
    metrics["QueenNodeVersion"] = (
        db_nodes[0][1] if metrics["TotalNodes"] > 0 else metrics["AntNodeVersion"]
    )
    metrics["NodesLatestV"] = (
        sum(1 for node in db_nodes if node[1] == metrics["AntNodeVersion"]) or 0
    )
    metrics["NodesNoVersion"] = sum(1 for node in db_nodes if not node[1]) or 0
    metrics["NodesToUpgrade"] = (
        metrics["TotalNodes"] - metrics["NodesLatestV"] - metrics["NodesNoVersion"]
    )
    metrics["NodesByVersion"] = Counter(ver[1] for ver in db_nodes)

    # Windows has to build load average over 5 seconds. The first 5 seconds returns 0's
    # I don't plan on supporting windows, but if this get's modular, I don't want this
    # issue to be skipped
    # if platform.system() == "Windows":
    #    discard=psutil.getloadavg()
    #    time.sleep(5)
    metrics["LoadAverage1"], metrics["LoadAverage5"], metrics["LoadAverage15"] = (
        psutil.getloadavg()
    )
    # Get CPU Metrics over 1 second
    metrics["IdleCpuPercent"], metrics["IOWait"] = psutil.cpu_times_percent(1)[3:5]
    # Really we returned Idle percent, subtract from 100 to get used.
    metrics["UsedCpuPercent"] = 100 - metrics["IdleCpuPercent"]
    data = psutil.virtual_memory()
    # print(data)
    metrics["UsedMemPercent"] = data.percent
    metrics["FreeMemPercent"] = 100 - metrics["UsedMemPercent"]
    data = psutil.disk_io_counters()
    # This only checks the drive mapped to the first node and will need to be updated
    # when we eventually support multiple drives
    data = psutil.disk_usage(node_storage)
    metrics["UsedHDPercent"] = data.percent
    metrics["TotalHDBytes"] = data.total
    end_time = time.time()
    end_disk_counters = psutil.disk_io_counters()
    end_net_counters = psutil.net_io_counters()
    metrics["HDWriteBytes"] = int(
        (end_disk_counters.write_bytes - start_disk_counters.write_bytes)
        / (end_time - start_time)
    )
    metrics["HDReadBytes"] = int(
        (end_disk_counters.read_bytes - start_disk_counters.read_bytes)
        / (end_time - start_time)
    )
    metrics["NetWriteBytes"] = int(
        (end_net_counters.bytes_sent - start_net_counters.bytes_sent)
        / (end_time - start_time)
    )
    metrics["NetReadBytes"] = int(
        (end_net_counters.bytes_recv - start_net_counters.bytes_recv)
        / (end_time - start_time)
    )
    # print (json.dumps(metrics,indent=2))
    # How close (out of 100) to removal limit will we be with a max bytes per node (2GB default)
    # For running nodes with Porpoise(tm).
    metrics["NodeHDCrisis"] = int(
        (
            ((metrics["TotalNodes"]) * int(crisis_bytes))
            / (metrics["TotalHDBytes"] * (remove_limit / 100))
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
            "peer_id": metadata["peer_id"],
        }
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
def set_node_status(S, id, status):
    logging.info("Setting node status: {0} {1}".format(id, status))
    try:
        with S() as session:
            session.query(Node).filter(Node.id == id).update(
                {"status": status, "timestamp": int(time.time())}
            )
            session.commit()
    except Exception as e:
        logging.error(f"Failed to set node status for {id}: {e}")
        return False
    else:
        return True


# Update metrics after checking counters
def update_counters(S, old, config):
    # Are we already removing a node
    if old["RemovingNodes"]:
        with S() as session:
            removals = session.execute(
                select(Node.timestamp, Node.id)
                .where(Node.status == REMOVING)
                .order_by(Node.timestamp.asc())
            ).all()
        # Iterate through active removals
        records_to_remove = len(removals)
        for check in removals:
            # If the DelayRemove timer has expired, delete the entry
            if isinstance(check[0], int) and check[0] < (
                int(time.time()) - (config["DelayRemove"] * 60)
            ):
                logging.info("Deleting removed node " + str(check[1]))
                with S() as session:
                    session.execute(delete(Node).where(Node.id == check[1]))
                    session.commit()
                records_to_remove -= 1
        old["RemovingNodes"] = records_to_remove
    # Are we already upgrading a node
    if old["UpgradingNodes"]:
        with S() as session:
            upgrades = session.execute(
                select(Node.timestamp, Node.id, Node.host, Node.metrics_port)
                .where(Node.status == UPGRADING)
                .order_by(Node.timestamp.asc())
            ).all()
        # Iterate through active upgrades
        records_to_upgrade = len(upgrades)
        for check in upgrades:
            # If the DelayUpgrade timer has expired, check on status
            if isinstance(check[0], int) and check[0] < (
                int(time.time()) - (config["DelayUpgrade"] * 60)
            ):
                logging.info("Updating upgraded node " + str(check[1]))
                node_metrics = read_node_metrics(check[2], check[3])
                node_metadata = read_node_metadata(check[2], check[3])
                if node_metrics and node_metadata:
                    update_node_from_metrics(check[1], node_metrics, node_metadata)
                records_to_upgrade -= 1
        old["UpgradingNodes"] = records_to_upgrade
    # Are we already restarting a node
    if old["RestartingNodes"]:
        with S() as session:
            restarts = session.execute(
                select(Node.timestamp, Node.id, Node.host, Node.metrics_port)
                .where(Node.status == RESTARTING)
                .order_by(Node.timestamp.asc())
            ).all()
        # Iterate through active upgrades
        records_to_restart = len(restarts)
        for check in restarts:
            # If the DelayUpgrade timer has expired, check on status
            if isinstance(check[0], int) and check[0] < (
                int(time.time()) - (config["DelayStart"] * 60)
            ):
                logging.info("Updating restarted node " + str(check[1]))
                node_metrics = read_node_metrics(check[2], check[3])
                node_metadata = read_node_metadata(check[2], check[3])
                if node_metrics and node_metadata:
                    update_node_from_metrics(check[1], node_metrics, node_metadata)
                records_to_restart -= 1
        old["RestartingNodes"] = records_to_restart
    return old


# Enable firewall for port
def enable_firewall(port, node):
    logging.info("enable firewall port {0}/udp".format(port))
    # Close ufw firewall
    try:
        subprocess.run(
            ["sudo", "ufw", "allow", "{0}/udp".format(port), "comment", node],
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        logging.error("EF Error:", err)


# Disable firewall for port
def disable_firewall(port):
    logging.info("disable firewall port {0}/udp".format(port))
    # Close ufw firewall
    try:
        subprocess.run(
            ["sudo", "ufw", "delete", "allow", "{0}/udp".format(port)],
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        logging.error("DF ERROR:", err)


# Start a systemd node
def start_systemd_node(S, node):
    logging.info("Starting node " + str(node.id))
    # Try to start the service
    try:
        p = subprocess.run(
            ["sudo", "systemctl", "start", node.service],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout.decode("utf-8")
        if re.match(r"Failed to start", p):
            logging.error("SSN2 ERROR:", p)
            return False
    except subprocess.CalledProcessError as err:
        logging.error("SSN1 ERROR:", err)
        return False
    # Open a firewall hole for the data port
    enable_firewall(node.port, node.service)
    # Update node status
    set_node_status(S, node.id, RESTARTING)
    return True


# Stop a systemd node
def stop_systemd_node(S, node):
    logging.info("Stopping node: " + node.service)
    # Send a stop signal to the process
    try:
        subprocess.run(
            ["sudo", "systemctl", "stop", node.service], stdout=subprocess.PIPE
        )
    except subprocess.CalledProcessError as err:
        logging.error("SSN2 ERROR:", err)
    disable_firewall(node.port)
    set_node_status(S, node.id, STOPPED)

    return True


# Upgrade a node
def upgrade_node(S, node, metrics):
    logging.info("Upgrading node " + str(node.id))
    # Copy current node binary
    try:
        subprocess.run(["sudo", "cp", "-f", metrics["antnode"], node.binary])
    except subprocess.CalledProcessError as err:
        logging.error("UN1 ERROR:", err)
    try:
        migrate_node(S, node, metrics)
    except subprocess.CalledProcessError as err:
        logging.error("UN3 ERROR:", err)
    try:
        subprocess.run(["sudo", "systemctl", "restart", node.service])
    except subprocess.CalledProcessError as err:
        logging.error("UN2 ERROR:", err)
    version = get_antnode_version(node.binary)
    try:
        with S() as session:
            session.query(Node).filter(Node.id == node.id).update(
                {
                    "status": UPGRADING,
                    "timestamp": int(time.time()),
                    "version": metrics["AntNodeVersion"],
                }
            )
            session.commit()
    except Exception as e:
        logging.error(f"Failed to upgrade node {id}: {e}")
        return False
    else:
        return True


# Remove a node
def remove_node(S, id, no_delay=False):
    logging.info("Removing node " + str(id))

    with S() as session:
        node = session.execute(select(Node).where(Node.id == id)).first()
    # Grab Node from Row
    node = node[0]
    if stop_systemd_node(S, node):
        # Override remove delay when removing a stopped node
        if not no_delay:
            # Mark this node as REMOVING
            set_node_status(S, id, REMOVING)

        nodename = f"antnode{node.nodename}"
        # Remove node data and log
        try:
            subprocess.run(
                ["sudo", "rm", "-rf", node.root_dir, f"/var/log/antnode/{nodename}"]
            )
        except subprocess.CalledProcessError as err:
            logging.error("RN1 ERROR:", err)
        # Remove systemd service file
        try:
            subprocess.run(["sudo", "rm", "-f", f"/etc/systemd/system/{node.service}"])
        except subprocess.CalledProcessError as err:
            logging.error("RN2 ERROR:", err)
        # Tell system to reload systemd files
        try:
            subprocess.run(["sudo", "systemctl", "daemon-reload"])
        except subprocess.CalledProcessError as err:
            logging.error("RN3 ERROR:", err)
    # print(json.dumps(node,indent=2))


# Rescan nodes for status
def update_nodes(S):
    with S() as session:
        nodes = session.execute(
            select(Node.timestamp, Node.id, Node.host, Node.metrics_port, Node.status)
            .where(Node.status != DISABLED)
            .order_by(Node.timestamp.asc())
        ).all()
    # Iterate through all records
    for check in nodes:
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


# Create a new node
def create_node(S, config, metrics):
    logging.info("Creating new node")
    # Create a holding place for the new node
    card = {}
    # Find the next available node number by first looking for holes
    sql = text(
        "select n1.id + 1 as id from node n1 "
        + "left join node n2 on n2.id = n1.id + 1 "
        + "where n2.id is null "
        + "and n1.id <> (select max(id) from node) "
        + "order by n1.id;"
    )
    with S() as session:
        result = session.execute(sql).first()
    if result:
        card["id"] = result[0]
    # Otherwise get the max node number and add 1
    else:
        with S() as session:
            result = session.execute(select(Node.id).order_by(Node.id.desc())).first()
        card["id"] = result[0] + 1
    # Set the node name
    card["nodename"] = f"{card['id']:04}"
    card["service"] = f"antnode{card['nodename']}.service"
    card["user"] = "ant"
    card["version"] = metrics["AntNodeVersion"]
    card["root_dir"] = f"{config['NodeStorage']}/antnode{card['nodename']}"
    card["binary"] = f"{card['root_dir']}/antnode"
    card["port"] = config["PortStart"] * PORT_MULTIPLIER + card["id"]
    card["metrics_port"] = METRICS_PORT_BASE + card["id"]
    card["network"] = "evm-arbitrum-one"
    card["wallet"] = config["RewardsAddress"]
    card["peer_id"] = ""
    card["status"] = STOPPED
    card["timestamp"] = int(time.time())
    card["records"] = 0
    card["uptime"] = 0
    card["shunned"] = 0
    card["age"] = card["timestamp"]
    card["host"] = config["Host"]
    card["environment"] = config["Environment"]
    if card["environment"]:
        env_string = f'Environment="{0}"'.format(card["environment"])
    else:
        env_string = ""

    log_dir = f"/var/log/antnode/antnode{card['nodename']}"
    # Create the node directory and log directory
    try:
        subprocess.run(
            ["sudo", "mkdir", "-p", card["root_dir"], log_dir], stdout=subprocess.PIPE
        )
    except subprocess.CalledProcessError as err:
        logging.error("CN1 ERROR:", err)
    # Copy the binary to the node directory
    try:
        subprocess.run(
            ["sudo", "cp", metrics["antnode"], card["root_dir"]], stdout=subprocess.PIPE
        )
    except subprocess.CalledProcessError as err:
        logging.error("CN2 ERROR:", err)
    # Change owner of the node directory and log directories
    try:
        subprocess.run(
            [
                "sudo",
                "chown",
                "-R",
                f'{card["user"]}:{card["user"]}',
                card["root_dir"],
                log_dir,
            ],
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        logging.error("CN3 ERROR:", err)
    # build the systemd service unit
    service = f"""[Unit]
Description=antnode{card['nodename']}
[Service]
{env_string}
User={card['user']}
ExecStart={card['binary']} --bootstrap-cache-dir /var/antctl/bootstrap-cache --root-dir {card['root_dir']} --port {card['port']} --enable-metrics-server --metrics-server-port {card['metrics_port']} --log-output-dest {log_dir} --max-log-files 1 --max-archived-log-files 1 --rewards-address {card['wallet']} {card['network']}
Restart=always
#RestartSec=300
"""
    # Write the systemd service unit with sudo tee since we're running as not root
    try:
        subprocess.run(
            ["sudo", "tee", f'/etc/systemd/system/{card["service"]}'],
            input=service,
            text=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        logging.error("CN4 ERROR:", err)
    # Reload systemd service files to get our new one
    try:
        subprocess.run(["sudo", "systemctl", "daemon-reload"], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
        logging.error("CN5 ERROR:", err)
    # Add the new node to the database
    with S() as session:
        session.execute(insert(Node), [card])
        session.commit()
    # Now we grab the node object from the database to pass to start node
    with S() as session:
        card = session.execute(select(Node).where(Node.id == card["id"])).first()
    # Get the Node object from the Row
    card = card[0]
    # Start the new node
    return start_systemd_node(S, card)
    # print(json.dumps(card,indent=2))
    return True

    # Migrate a new node to new systemd service file format
def migrate_node(S, config, metrics):
    logging.info("Updating node to new service file format")
    # Get the node
    with S() as session:
        card = session.execute(select(Node).where(Node.id == config.id)).first()
    card = card[0]
    if card["environment"]:
        env_string = f'Environment="{0}"'.format(card["environment"])
    else:
        env_string = ""

    log_dir = f"/var/log/antnode/antnode{card['nodename']}"
    # build the systemd service unit
    service = f"""[Unit]
Description=antnode{card['nodename']}
[Service]
{env_string}
User={card['user']}
ExecStart={card['binary']} --bootstrap-cache-dir /var/antctl/bootstrap-cache --no-upnp --root-dir {card['root_dir']} --port {card['port']} --enable-metrics-server --metrics-server-port {card['metrics_port']} --log-output-dest {log_dir} --max-log-files 1 --max-archived-log-files 1 --rewards-address {card['wallet']} {card['network']}
Restart=always
#RestartSec=300
"""
    # Write the systemd service unit with sudo tee since we're running as not root
    try:
        subprocess.run(
            ["sudo", "tee", f'/etc/systemd/system/{card["service"]}'],
            input=service,
            text=True,
            stdout=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        logging.error("CN4 ERROR:", err)
    # Reload systemd service files to get our new one
    try:
        subprocess.run(["sudo", "systemctl", "daemon-reload"], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
        logging.error("CN5 ERROR:", err)
    # print(json.dumps(card,indent=2))
    return True
