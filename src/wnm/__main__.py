import json
import logging
import os
import sys
import time

from packaging.version import Version

from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.orm import scoped_session, sessionmaker

from wnm.common import (
    DONATE,
    STOPPED,
    RUNNING,
    UPGRADING,
    DISABLED,
    RESTARTING,
    MIGRATING,
    REMOVING,
    DEAD,
    QUEEN,
)
from wnm.config import S, machine_config, options, config_updates, apply_config_updates
from wnm.models import Base, Machine, Node

from wnm.utils import (
    upgrade_node,
    update_counters,
    remove_node,
    get_antnode_version,
    stop_systemd_node,
    start_systemd_node,
    create_node,
    update_nodes,
    get_machine_metrics,
    survey_machine,
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
    features["AllowCpu"] = metrics["UsedCpuPercent"] < machine_config["CpuLessThan"]
    features["AllowMem"] = metrics["UsedMemPercent"] < machine_config["MemLessThan"]
    features["AllowHD"] = metrics["UsedHDPercent"] < machine_config["HDLessThan"]
    features["RemCpu"] = metrics["UsedCpuPercent"] > machine_config["CpuRemove"]
    features["RemMem"] = metrics["UsedMemPercent"] > machine_config["MemRemove"]
    features["RemHD"] = metrics["UsedHDPercent"] > machine_config["HDRemove"]
    features["AllowNodeCap"] = metrics["RunningNodes"] < machine_config["NodeCap"]
    # These are new features, so ignore them if not machine_configured
    if (
        machine_config["NetIOReadLessThan"]
        + machine_config["NetIOReadRemove"]
        + machine_config["NetIOWriteLessThan"]
        + machine_config["NetIOWriteRemove"]
        > 1
    ):
        features["AllowNetIO"] = (
            metrics["NetReadBytes"] < machine_config["NetIOReadLessThan"]
            and metrics["NetWriteBytes"] < machine_config["NetIOWriteLessThan"]
        )
        features["RemoveNetIO"] = (
            metrics["NetReadBytes"] > machine_config["NetIORemove"]
            or metrics["NetWriteBytes"] > machine_config["NetIORemove"]
        )
    else:
        features["AllowNetIO"] = True
        features["RemoveNetIO"] = False
    if (
        machine_config["HDIOReadLessThan"]
        + machine_config["HDIOReadRemove"]
        + machine_config["HDIOWriteLessThan"]
        + machine_config["HDIOWriteRemove"]
        > 1
    ):
        features["AllowHDIO"] = (
            metrics["HDReadBytes"] < machine_config["HDIOReadLessThan"]
            and metrics["HDWriteBytes"] < machine_config["HDIOWriteLessThan"]
        )
        features["RemoveHDIO"] = (
            metrics["HDReadBytes"] > machine_config["HDIORemove"]
            or metrics["HDWriteBytes"] > machine_config["HDtIORemove"]
        )
    else:
        features["AllowHDIO"] = True
        features["RemoveHDIO"] = False
    features["LoadAllow"] = (
        metrics["LoadAverage1"] < machine_config["DesiredLoadAverage"]
        and metrics["LoadAverage5"] < machine_config["DesiredLoadAverage"]
        and metrics["LoadAverage15"] < machine_config["DesiredLoadAverage"]
    )
    features["LoadNotAllow"] = (
        metrics["LoadAverage1"] > machine_config["MaxLoadAverageAllowed"]
        or metrics["LoadAverage5"] > machine_config["MaxLoadAverageAllowed"]
        or metrics["LoadAverage15"] > machine_config["MaxLoadAverageAllowed"]
    )
    # Check records for expired status
    if not dry_run:
        metrics = update_counters(S, metrics, machine_config)
    # If we have other thing going on, don't add more nodes
    features["AddNewNode"] = (
        sum(
            [
                metrics.get(m, 0)
                for m in [
                    "UpgradingNodes",
                    "RestartingNodes",
                    "MigratingNodes",
                    "RemovingNodes",
                ]
            ]
        )
        == 0
        and features["AllowCpu"]
        and features["AllowHD"]
        and features["AllowMem"]
        and features["AllowNodeCap"]
        and features["AllowHDIO"]
        and features["AllowNetIO"]
        and features["LoadAllow"]
        and metrics["TotalNodes"] < machine_config["NodeCap"]
    )
    # Are we overlimit on nodes
    features["Remove"] = (
        features["LoadNotAllow"]
        or features["RemCpu"]
        or features["RemHD"]
        or features["RemMem"]
        or features["RemoveHDIO"]
        or features["RemoveNetIO"]
        or metrics["TotalNodes"] > machine_config["NodeCap"]
    )
    # If we have nodes to upgrade
    if metrics["NodesToUpgrade"] >= 1:
        # Make sure current version is equal or newer than version on first node.
        if Version(metrics["AntNodeVersion"]) < metrics["QueenNodeVersion"]:
            logging.warning("node upgrade cancelled due to lower version")
            features["Upgrade"] = False
        else:
            if features["Remove"]:
                logging.info("Can't upgrade while removing is required")
                features["Upgrade"] = False
            else:
                features["Upgrade"] = True
    else:
        features["Upgrade"] = False

    logging.info(json.dumps(features, indent=2))
    ##### Decisions

    # Ugh, rebooting takes priority, resurvey the nodes and update the db
    if int(metrics["SystemStart"]) > int(machine_config["LastStoppedAt"]):
        if machine_config["LastStoppedAt"] == 0:
            if dry_run:
                logging.warning("DRYRUN: LastStoppedAt reset, survey nodes")
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
                    {"LastStoppedAt": int(metrics["SystemStart"])}
                )
                session.commit()
        return {"status": "system-rebooted"}

    # Actually, removing DEAD nodes take priority
    if metrics["DeadNodes"] > 1:
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
                remove_node(check[1])
        return {"status": "removed-dead-nodes"}
    # If we have nodes with no version number, update from binary
    if metrics["NodesNoVersion"] > 1:
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
    if metrics["RestartingNodes"]:
        logging.info("Still waiting for RestartDelay")
        return {"status": RESTARTING}
    # If we still have unexpired upgrade records, wait
    if metrics["UpgradingNodes"]:
        logging.info("Still waiting for UpgradeDelay")
        return {"status": UPGRADING}
    # First if we're removing, that takes top priority
    if features["Remove"]:
        # If we're under HD pressure, trimming node cap or upgrades are taking 
        # more resources, remove nodes
        if (
            features["RemHD"] or 
            metrics["TotalNodes"] > machine_config["NodeCap"] or 
            metrics["NodesToUpgrade"] > 0
        ):
            # Start removing with stopped nodes
            if metrics["StoppedNodes"] > 0:
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
                        remove_node(S, youngest[0])
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
            if metrics["RemovingNodes"]:
                logging.info("Still waiting for RemoveDelay")
                return {"status": 'waiting-to-remove'}
            # If we just stopped a node, wait
            if int(machine_config["LastStoppedAt"] or 0) > (
                int(time.time()) - (machine_config["DelayRemove"] * 60)
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
                            {"LastStoppedAt": int(time.time())}
                        )
                        session.commit()
                return {"status": STOPPED}
            else:
                return {"status": "nothing-to-stop"}

    # Do we have upgrading to do?
    if features["Upgrade"]:
        # Let's find the oldest running node not using the current version
        with S() as session:
            oldest = session.execute(
                select(Node)
                .where(Node.status == RUNNING)
                .where(Node.version != metrics["AntNodeVersion"])
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
    if features["AddNewNode"]:
        # Start activating with stopped nodes
        if metrics["StoppedNodes"] > 0:
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
                if Version(metrics["AntNodeVersion"]) > Version(oldest.version):
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
        if metrics["TotalNodes"] < machine_config["NodeCap"]:
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
    except:
        logging.error("Unable to create lock file, exiting")
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
        local_config["NodeStorage"],
        local_config["HDRemove"],
        local_config["CrisisBytes"],
    )
    logging.info(json.dumps(metrics, indent=2))

    # Do we already have nodes
    if metrics["TotalNodes"] == 0:
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
                        local_config["NodeStorage"],
                        local_config["HDRemove"],
                        local_config["CrisisBytes"],
                    )
                logging.info(
                    "Found {counter} nodes defined".format(
                        counter=metrics["TotalNodes"]
                    )
                )
            else:
                logging.warning("Requested migration but no nodes found")
        else:
            logging.info("No nodes found")
    else:
        logging.info(
            "Found {counter} nodes configured".format(counter=metrics["TotalNodes"])
        )

    this_action = choose_action(local_config, metrics, options.dry_run)
    print("Action:", json.dumps(this_action, indent=2))

    os.remove("/var/antctl/wnm_active")
    sys.exit(1)

    # See if we already have a known records in the database
    with S() as session:
        db_nodes = session.execute(
            select(
                Node.status,
                Node.version,
                Node.host,
                Node.metrics_port,
                Node.port,
                Node.age,
                Node.id,
                Node.timestamp,
            )
        ).all()

    if db_nodes:

        # node_metrics = read_node_metrics(db_nodes[0][2],db_nodes[0][3])
        # print(db_nodes[0])
        # print(node_metrics)
        # print(anm_config)
        # print(json.dumps(anm_config,indent=4))
        # print("Node: ",db_nodes)
        logging.info("Found {counter} nodes migrated".format(counter=len(db_nodes)))

    else:
        anm_config = load_anm_config()
        # print(anm_config)
        Workers = survey_machine() or []

        # """"
        with S() as session:
            session.execute(insert(Node), Workers)
            session.commit()
        # """

        with S() as session:
            session.execute(insert(Machine), [anm_config])
            session.commit()

        # Now load subset of data to work with
        with S() as session:
            db_nodes = session.execute(
                select(
                    Node.status,
                    Node.version,
                    Node.host,
                    Node.metrics_port,
                    Node.port,
                    Node.age,
                    Node.id,
                    Node.timestamp,
                )
            ).all()

        # print(json.dumps(anm_config,indent=4))
        logging.info("Found {counter} nodes configured".format(metrics["TotalNodes"]))

        # versions = [v[1] for worker in Workers if (v := worker.get('version'))]
        # data = Counter(ver for ver in versions)

    machine_metrics = get_machine_metrics(
        anm_config["NodeStorage"], anm_config["HDRemove"]
    )
    print(json.dumps(anm_config, indent=2))
    print(json.dumps(machine_metrics, indent=2))
    this_action = choose_action(anm_config, machine_metrics, options.dry_run)
    print("Action:", json.dumps(this_action, indent=2))
    # Remove lock file
    os.remove("/var/antctl/wnm_active")


if __name__ == "__main__":
    main()
    # print(options.MemRemove)

print("End of program")
