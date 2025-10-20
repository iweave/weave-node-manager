import json
import logging
import os
import sys
import time

from packaging.version import Version
from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.orm import scoped_session, sessionmaker

from wnm.common import (
    DEAD,
    DISABLED,
    DONATE,
    MIGRATING,
    QUEEN,
    REMOVING,
    RESTARTING,
    RUNNING,
    STOPPED,
    UPGRADING,
)
from wnm.config import S, apply_config_updates, config_updates, machine_config, options
from wnm.models import Base, Machine, Node
from wnm.utils import (
    create_node,
    get_antnode_version,
    get_machine_metrics,
    remove_node,
    start_systemd_node,
    stop_systemd_node,
    survey_machine,
    update_counters,
    update_nodes,
    upgrade_node,
)

logging.basicConfig(level=logging.INFO)
# Info level logging for sqlalchemy is too verbose, only use when needed
logging.getLogger("sqlalchemy.engine.Engine").disabled = True


# A storage place for ant node data
Workers = []

# Detect ANM


# Make a decision about what to do
def choose_action(machine_config, metrics, dry_run):
    # Gather knowlege
    features = {}
    features["allow_cpu"] = (
        metrics["used_cpu_percent"] < machine_config["cpu_less_than"]
    )
    features["allow_mem"] = (
        metrics["used_mem_percent"] < machine_config["mem_less_than"]
    )
    features["allow_hd"] = metrics["used_hd_percent"] < machine_config["hd_less_than"]
    features["remove_cpu"] = metrics["used_cpu_percent"] > machine_config["cpu_remove"]
    features["remove_mem"] = metrics["used_mem_percent"] > machine_config["mem_remove"]
    features["remove_hd"] = metrics["used_hd_percent"] > machine_config["hd_remove"]
    features["allow_node_cap"] = metrics["running_nodes"] < machine_config["node_cap"]
    # These are new features, so ignore them if not machine_configured
    if (
        machine_config["netio_read_less_than"]
        + machine_config["netio_read_remove"]
        + machine_config["netio_write_less_than"]
        + machine_config["netio_write_remove"]
        > 1
    ):
        features["allow_netio"] = (
            metrics["netio_read_bytes"] < machine_config["netio_read_less_than"]
            and metrics["netio_write_bytes"] < machine_config["netio_write_less_than"]
        )
        features["remove_netio"] = (
            metrics["netio_read_bytes"] > machine_config["netio_read_remove"]
            or metrics["netio_write_bytes"] > machine_config["netio_write_remove"]
        )
    else:
        features["allow_netio"] = True
        features["remove_netio"] = False
    if (
        machine_config["hdio_read_less_than"]
        + machine_config["hdio_read_remove"]
        + machine_config["hdio_write_less_than"]
        + machine_config["hdio_write_remove"]
        > 1
    ):
        features["allow_hdio"] = (
            metrics["hdio_read_bytes"] < machine_config["hdio_read_less_than"]
            and metrics["hdio_write_bytes"] < machine_config["hdio_write_less_than"]
        )
        features["remove_hdio"] = (
            metrics["hdio_read_bytes"] > machine_config["hdio_read_remove"]
            or metrics["hdio_write_bytes"] > machine_config["hdio_write_remove"]
        )
    else:
        features["allow_hdio"] = True
        features["remove_hdio"] = False
    features["load_allow"] = (
        metrics["load_average_1"] < machine_config["desired_load_average"]
        and metrics["load_average_5"] < machine_config["desired_load_average"]
        and metrics["load_average_15"] < machine_config["desired_load_average"]
    )
    features["load_not_allow"] = (
        metrics["load_average_1"] > machine_config["max_load_average_allowed"]
        or metrics["load_average_5"] > machine_config["max_load_average_allowed"]
        or metrics["load_average_15"] > machine_config["max_load_average_allowed"]
    )
    # Check records for expired status
    if not dry_run:
        metrics = update_counters(S, metrics, machine_config)
    # If we have other thing going on, don't add more nodes
    features["add_new_node"] = (
        sum(
            [
                metrics.get(m, 0)
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
        and metrics["total_nodes"] < machine_config["node_cap"]
    )
    # Are we overlimit on nodes
    features["remove"] = (
        features["load_not_allow"]
        or features["remove_cpu"]
        or features["remove_hd"]
        or features["remove_mem"]
        or features["remove_hdio"]
        or features["remove_netio"]
        or metrics["total_nodes"] > machine_config["node_cap"]
    )
    # If we have nodes to upgrade
    if metrics["nodes_to_upgrade"] >= 1:
        # Make sure current version is equal or newer than version on first node.
        if Version(metrics["antnode_version"]) < metrics["queen_node_version"]:
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

    logging.info(json.dumps(features, indent=2))
    ##### Decisions

    # Ugh, rebooting takes priority, resurvey the nodes and update the db
    if int(metrics["system_start"]) > int(machine_config["last_stopped_at"]):
        if machine_config["last_stopped_at"] == 0:
            if dry_run:
                logging.warning("DRYRUN: last_stopped_at reset, survey nodes")
            else:
                update_nodes(S)
        else:
            if dry_run:
                logging.warning("DRYRUN: System rebooted, survey nodes")
            else:
                update_nodes(S)
        if not dry_run:
            # Update the last stopped time
            with S() as session:
                session.query(Machine).filter(Machine.id == 1).update(
                    {"last_stopped_at": int(metrics["system_start"])}
                )
                session.commit()
        return {"status": "system-rebooted"}

    # Actually, removing DEAD nodes take priority
    if metrics["dead_nodes"] > 1:
        if dry_run:
            logging.warning("DRYRUN: Remove Dead Nodes")
        else:
            with S() as session:
                broken = session.execute(
                    select(Node.timestamp, Node.id, Node.host, Node.metrics_port)
                    .where(Node.status == DEAD)
                    .order_by(Node.timestamp.asc())
                ).all()
            # Iterate through dead nodes and remove them all
            for check in broken:
                # Remove broken nodes
                logging.info("Removing dead node " + str(check[1]))
                remove_node(S, check[1], no_delay=True)
        return {"status": "removed-dead-nodes"}
    # If we have nodes with no version number, update from binary
    if metrics["nodes_no_version"] > 1:
        if dry_run:
            logging.warning("DRYRUN: Update NoVersion nodes")
        else:
            with S() as session:
                no_version = session.execute(
                    select(Node.timestamp, Node.id, Node.binary)
                    .where(Node.version == "")
                    .order_by(Node.timestamp.asc())
                ).all()
            # Iterate through nodes with no version number
            for check in no_version:
                # Update version number from binary
                version = get_antnode_version(check[2])
                logging.info(
                    f"Updating version number for node {check[1]} to {version}"
                )
                with S() as session:
                    session.query(Node).filter(Node.id == check[1]).update(
                        {"version": version}
                    )
                    session.commit()

    # If we're restarting, wait patiently as metrics could be skewed
    if metrics["restarting_nodes"]:
        logging.info("Still waiting for RestartDelay")
        return {"status": RESTARTING}
    # If we still have unexpired upgrade records, wait
    if metrics["upgrading_nodes"]:
        logging.info("Still waiting for UpgradeDelay")
        return {"status": UPGRADING}
    # First if we're removing, that takes top priority
    if features["remove"]:
        # If we're under HD pressure, trimming node cap or upgrades are taking
        # more resources, remove nodes
        if (
            features["remove_hd"]
            or metrics["total_nodes"] > machine_config["node_cap"]
            or (metrics["nodes_to_upgrade"] > 0 and metrics["removing_nodes"] == 0)
        ):
            # Start removing with stopped nodes
            if metrics["stopped_nodes"] > 0:
                # What is the youngest stopped node
                with S() as session:
                    youngest = session.execute(
                        select(Node.id)
                        .where(Node.status == STOPPED)
                        .order_by(Node.age.desc())
                    ).first()
                if youngest:
                    if dry_run:
                        logging.warning("DRYRUN: Remove youngest stopped node")
                    else:
                        # Remove the youngest node
                        remove_node(S, youngest[0], no_delay=True)
                    return {"status": REMOVING}
            # No low hanging fruit. let's start with the youngest running node
            with S() as session:
                youngest = session.execute(
                    select(Node.id)
                    .where(Node.status == RUNNING)
                    .order_by(Node.age.desc())
                ).first()
            if youngest:
                if dry_run:
                    logging.warning("DRYRUN: remove youngest running node")
                else:
                    # Remove the youngest node
                    remove_node(S, youngest[0])
                return {"status": REMOVING}
            return {"status": "nothing-to-remove"}
        # Otherwise, let's try just stopping a node to bring IO/Mem/Cpu down
        else:
            # If we still have unexpired removal records, wait
            if metrics["removing_nodes"]:
                logging.info("Still waiting for RemoveDelay")
                return {"status": "waiting-to-remove"}
            # If we just stopped a node, wait
            if int(machine_config["last_stopped_at"] or 0) > (
                int(time.time()) - machine_config["delay_remove"]
            ):
                logging.info("Still waiting for RemoveDelay")
                return {"status": "waiting-to-stop"}
            # Start with the youngest running node
            with S() as session:
                youngest = session.execute(
                    select(Node).where(Node.status == RUNNING).order_by(Node.age.desc())
                ).first()
            if youngest:
                if dry_run:
                    logging.warning("DRYRUN: Stopping youngest nodes")
                else:
                    # Stop the youngest node
                    stop_systemd_node(S, youngest[0])
                    # Update the last stopped time
                    with S() as session:
                        session.query(Machine).filter(Machine.id == 1).update(
                            {"last_stopped_at": int(time.time())}
                        )
                        session.commit()
                return {"status": STOPPED}
            else:
                return {"status": "nothing-to-stop"}

    # Do we have upgrading to do?
    if features["upgrade"]:
        # Let's find the oldest running node not using the current version
        with S() as session:
            oldest = session.execute(
                select(Node)
                .where(Node.status == RUNNING)
                .where(Node.version != metrics["antnode_version"])
                .order_by(Node.age.asc())
            ).first()
        if oldest:
            if dry_run:
                logging.warning("DRYRUN: upgrade oldest node")
            else:
                # Get Node from Row
                oldest = oldest[0]
                # If we don't have a version number from metadata, grab from binary
                if not oldest.version:
                    oldest.version = get_antnode_version(oldest.binary)
                # print(json.dumps(oldest))
                # Upgrade the oldest node
                upgrade_node(oldest, metrics)
            return {"status": UPGRADING}

    # If AddNewNode
    #   If stopped nodes available
    #     Check oldest stopped version
    #     If out of date
    #         upgrade node which starts it
    #     else
    #         restart node
    #   else
    #     Create a Node which starts it
    if features["add_new_node"]:
        # Start activating with stopped nodes
        if metrics["stopped_nodes"] > 0:
            # What is the oldest stopped node
            with S() as session:
                oldest = session.execute(
                    select(Node).where(Node.status == STOPPED).order_by(Node.age.asc())
                ).first()
            if oldest:
                # Get Node from Row
                oldest = oldest[0]
                # If we don't have a version number from metadata, grab from binary
                if not oldest.version:
                    oldest.version = get_antnode_version(oldest.binary)
                # If the stopped version is old, upgrade it
                if Version(metrics["antnode_version"]) > Version(oldest.version):
                    if dry_run:
                        logging.warning("DRYRUN: Upgrade and start stopped node")
                    else:
                        upgrade_node(oldest, metrics)
                    return {"status": UPGRADING}
                else:
                    if dry_run:
                        logging.warning("DRYRUN: Start stopped node")
                        return {"status": RESTARTING}
                    else:
                        if start_systemd_node(oldest):
                            return {"status": RESTARTING}
                        else:
                            return {"status": "failed-start-node"}
            # Hmm, still in Start mode, we shouldn't get here
            return {"status": "START"}
        # Still in Add mode, add a new node
        if metrics["total_nodes"] < machine_config["node_cap"]:
            if dry_run:
                logging.warning("DRYRUN: Add a node")
                return {"status": "ADD"}
            else:
                if create_node(machine_config, metrics):
                    return {"status": "ADD"}
                else:
                    return {"status": "failed-create-node"}
        else:
            return {"status": "node-cap-reached"}
    # If we have nothing to do, Survey the node ports
    if dry_run:
        logging.warning("DRYRUN: update nodes")
    else:
        update_nodes(S)
    return {"status": "idle"}


def main():

    # Are we already running
    if os.path.exists("/var/antctl/wnm_active"):
        logging.warning("wnm still running")
        sys.exit(1)

    # We're starting, so lets create a lock file
    try:
        with open("/var/antctl/wnm_active", "w") as file:
            file.write(str(int(time.time())))
    except (PermissionError, OSError) as e:
        logging.error(f"Unable to create lock file: {e}")
        sys.exit(1)

    # Config should have loaded the machine_config
    if machine_config:
        logging.info("Machine: " + json.dumps(machine_config))
    else:
        logging.error("Unable to load machine config, exiting")
        sys.exit(1)
    # Check for config updates
    if config_updates:
        logging.info("Update: " + json.dumps(config_updates))
        if options.dry_run:
            logging.warning("Dry run, not saving requested updates")
            # Create a dictionary for the machine config
            # Machine by default returns a parameter array,
            # use the __json__ method to return a dict
            local_config = json.loads(json.dumps(machine_config))
            # Apply the local config with the requested updates
            local_config.update(config_updates)
        else:
            # Store the config changes to the database
            apply_config_updates(config_updates)
            # Create a working dictionary for the machine config
            # Machine by default returns a parameter array,
            # use the __json__ method to return a dict
            local_config = json.loads(json.dumps(machine_config))
    else:
        local_config = json.loads(json.dumps(machine_config))

    metrics = get_machine_metrics(
        S,
        local_config["node_storage"],
        local_config["hd_remove"],
        local_config["crisis_bytes"],
    )
    logging.info(json.dumps(metrics, indent=2))

    # Do we already have nodes
    if metrics["total_nodes"] == 0:
        # Are we migrating an anm server
        if options.init and options.migrate_anm:
            Workers = survey_machine(machine_config) or []
            if Workers:
                if options.dry_run:
                    logging.warning(f"DRYRUN: Not saving {len(Workers)} detected nodes")
                else:
                    with S() as session:
                        session.execute(insert(Node), Workers)
                        session.commit()
                    # Reload metrics
                    metrics = get_machine_metrics(
                        S,
                        local_config["node_storage"],
                        local_config["hd_remove"],
                        local_config["crisis_bytes"],
                    )
                logging.info(
                    "Found {counter} nodes defined".format(
                        counter=metrics["total_nodes"]
                    )
                )
            else:
                logging.warning("Requested migration but no nodes found")
        else:
            logging.info("No nodes found")
    else:
        logging.info(
            "Found {counter} nodes configured".format(counter=metrics["total_nodes"])
        )

    this_action = choose_action(local_config, metrics, options.dry_run)
    print("Action:", json.dumps(this_action, indent=2))

    os.remove("/var/antctl/wnm_active")
    sys.exit(1)


if __name__ == "__main__":
    main()
    # print(options.MemRemove)

print("End of program")
