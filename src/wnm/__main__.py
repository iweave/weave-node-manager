import json
import logging
import os
import sys
import time

from sqlalchemy import insert, select

from wnm import __version__
from wnm.config import (
    LOCK_FILE,
    S,
    apply_config_updates,
    config_updates,
    machine_config,
    options,
)
from wnm.decision_engine import DecisionEngine
from wnm.executor import ActionExecutor
from wnm.migration import survey_machine
from wnm.models import Node
from wnm.utils import (
    get_antnode_version,
    get_machine_metrics,
    update_counters,
)

logging.basicConfig(level=logging.INFO)
# Info level logging for sqlalchemy is too verbose, only use when needed
logging.getLogger("sqlalchemy.engine.Engine").disabled = True


# A storage place for ant node data
Workers = []

# Detect ANM


# Make a decision about what to do (new implementation using DecisionEngine)
def choose_action(machine_config, metrics, dry_run):
    """Plan and execute actions using DecisionEngine and ActionExecutor.

    This function now acts as a thin wrapper around the new decision engine
    and action executor classes.

    Args:
        machine_config: Machine configuration dictionary
        metrics: Current system metrics
        dry_run: If True, log actions without executing

    Returns:
        Dictionary with execution status
    """
    # Check records for expired status (must be done before planning)
    if not dry_run:
        metrics = update_counters(S, metrics, machine_config)

    # Handle nodes with no version number (done before planning)
    if metrics["nodes_no_version"] > 0:
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

    # Use the new DecisionEngine to plan actions
    engine = DecisionEngine(machine_config, metrics)
    actions = engine.plan_actions()

    # Log the computed features for debugging
    logging.info(json.dumps(engine.get_features(), indent=2))

    # Use ActionExecutor to execute the planned actions
    executor = ActionExecutor(S)
    result = executor.execute(actions, machine_config, metrics, dry_run)

    return result


def main():
    # Handle --version flag (before any lock file or database checks)
    if options.version:
        print(f"wnm version {__version__}")
        sys.exit(0)

    # Handle --remove_lockfile flag (before normal lock file check)
    if options.remove_lockfile:
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
                print(f"Lock file removed: {LOCK_FILE}")
                sys.exit(0)
            except (PermissionError, OSError) as e:
                print(f"Error removing lock file: {e}")
                sys.exit(1)
        else:
            print(f"Lock file does not exist: {LOCK_FILE}")
            sys.exit(0)

    # Are we already running
    if os.path.exists(LOCK_FILE):
        logging.warning("wnm still running")
        sys.exit(1)

    # We're starting, so lets create a lock file
    try:
        with open(LOCK_FILE, "w") as file:
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

    # Check for reports
    if options.report:
        from wnm.reports import generate_node_status_report, generate_node_status_details_report

        # If survey action is specified, run it first
        if options.force_action == "survey":
            logging.info("Running survey before generating report")
            executor = ActionExecutor(S)
            survey_result = executor.execute_forced_action(
                "survey",
                local_config,
                metrics,
                service_name=options.service_name,
                dry_run=options.dry_run,
            )
            logging.info(f"Survey result: {survey_result}")

        # Generate the report
        if options.report == "node-status":
            report_output = generate_node_status_report(
                S, options.service_name, options.report_format
            )
        elif options.report == "node-status-details":
            report_output = generate_node_status_details_report(
                S, options.service_name, options.report_format
            )
        else:
            report_output = f"Unknown report type: {options.report}"

        print(report_output)
        os.remove(LOCK_FILE)
        sys.exit(0)

    # Check for forced actions
    if options.force_action:
        logging.info(f"Executing forced action: {options.force_action}")
        executor = ActionExecutor(S)
        this_action = executor.execute_forced_action(
            options.force_action,
            local_config,
            metrics,
            service_name=options.service_name,
            dry_run=options.dry_run,
            count=options.count if hasattr(options, 'count') else 1,
        )
    else:
        this_action = choose_action(local_config, metrics, options.dry_run)

    print("Action:", json.dumps(this_action, indent=2))

    os.remove(LOCK_FILE)
    sys.exit(1)


if __name__ == "__main__":
    main()
    # print(options.MemRemove)

print("End of program")
