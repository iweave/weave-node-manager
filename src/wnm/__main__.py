import atexit
import json
import logging
import os
import signal
import sys
import time

from sqlalchemy import insert, select

from wnm import __version__
from wnm.config import (
    LOCK_FILE,
    S,
    apply_config_updates,
    config_updates,
    engine,
    machine_config,
    options,
)
from wnm.decision_engine import DecisionEngine
from wnm.executor import ActionExecutor
from wnm.migration import detect_port_ranges_from_nodes, survey_machine
from wnm.models import Machine, Node
from wnm.utils import (
    get_antnode_version,
    get_machine_metrics,
    get_system_start_time,
    update_counters,
)

# Logging is configured in config.py based on --loglevel and --quiet flags


# A storage place for ant node data
Workers = []

# Track whether we created the lock file
_lock_file_created = False

# Detect ANM


def cleanup_lock_file():
    """Safely remove lock file if it was created by this process."""
    global _lock_file_created
    if _lock_file_created and os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
            logging.debug("Lock file removed during cleanup")
        except (PermissionError, OSError) as e:
            logging.error(f"Error removing lock file during cleanup: {e}")


def signal_handler(signum, frame):
    """Handle termination signals by cleaning up and exiting."""
    signal_name = signal.Signals(signum).name
    logging.info(f"Received {signal_name}, cleaning up...")
    cleanup_lock_file()
    sys.exit(1)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Register cleanup function to run on normal exit
atexit.register(cleanup_lock_file)


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

    # Determine if this is an --init operation and whether we should survey
    is_init = getattr(options, 'init', False)
    should_survey_init = is_init and (
        getattr(options, 'migrate_anm', False) or
        getattr(options, 'import_nodes', False)
    )

    # Use the new DecisionEngine to plan actions
    engine = DecisionEngine(machine_config, metrics, is_init=is_init, should_survey_init=should_survey_init)
    actions = engine.plan_actions()

    # Log the computed features for debugging
    if options.show_decisions or options.v:
        logging.info(json.dumps(engine.get_features(), indent=2))

    # Inject transient action delay override into machine_config if provided
    # Priority: --interval takes precedence over --this_action_delay
    if options.interval is not None:
        machine_config["this_action_delay"] = options.interval
    elif options.this_action_delay is not None:
        machine_config["this_action_delay"] = options.this_action_delay

    # Inject transient survey delay override into machine_config if provided
    if options.this_survey_delay is not None:
        machine_config["this_survey_delay"] = options.this_survey_delay

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
                logging.info(f"Lock file removed: {LOCK_FILE}")
                sys.exit(0)
            except (PermissionError, OSError) as e:
                logging.error(f"Error removing lock file: {e}")
                sys.exit(1)
        else:
            logging.info(f"Lock file does not exist: {LOCK_FILE}")
            sys.exit(0)

    # Are we already running
    if os.path.exists(LOCK_FILE):
        logging.warning("wnm still running")
        sys.exit(1)

    # We're starting, so lets create a lock file
    global _lock_file_created
    try:
        with open(LOCK_FILE, "w") as file:
            file.write(str(int(time.time())))
        _lock_file_created = True
        logging.debug(f"Lock file created: {LOCK_FILE}")
    except (PermissionError, OSError) as e:
        logging.error(f"Unable to create lock file: {e}")
        sys.exit(1)

    # Handle database migration command first (before any config checks)
    if options.force_action == "wnm-db-migration":
        if not options.confirm:
            logging.error("Database migration requires --confirm flag for safety")
            logging.info("Use: wnm --force_action wnm-db-migration --confirm")
            sys.exit(1)

        # Import migration utilities
        from wnm.db_migration import run_migrations, has_pending_migrations

        # Check if there are pending migrations
        pending, current, head = has_pending_migrations(engine, options.dbpath)

        if not pending:
            logging.info("Database is already up to date!")
            logging.info(f"Current revision: {current}")
            sys.exit(0)

        logging.info("=" * 70)
        logging.info("RUNNING DATABASE MIGRATIONS")
        logging.info("=" * 70)
        logging.info(
            f"Upgrading database from {current or 'unversioned'} to {head}"
        )

        try:
            run_migrations(engine, options.dbpath)
            logging.info("Database migration completed successfully!")
            logging.info("=" * 70)
            sys.exit(0)
        except Exception as e:
            logging.error(f"Migration failed: {e}")
            logging.error("Please restore from backup and report this issue.")
            logging.info("=" * 70)
            sys.exit(1)

    # Config should have loaded the machine_config
    if machine_config:
        # Only log machine config at INFO level if --show_machine_config or -v is set
        if options.show_machine_config or options.v:
            logging.info("Machine: " + json.dumps(machine_config))
    else:
        logging.error("Unable to load machine config, exiting")
        sys.exit(1)

    # Handle nullop/update_config force action early (bypasses decision engine)
    if options.force_action in ["nullop", "update_config"]:
        logging.info(f"Executing {options.force_action}: updating config only")
        # Check for config updates
        if config_updates:
            logging.info("Update: " + json.dumps(config_updates))
            if options.dry_run:
                logging.warning("Dry run, not saving requested updates")
            else:
                # Store the config changes to the database
                apply_config_updates(config_updates)
                logging.info("Configuration updated successfully")
        else:
            logging.info("No configuration changes detected")
        # Exit immediately (atexit will clean up lock file)
        sys.exit(0)

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
    # Only log metrics at INFO level if --show_machine_metrics or -v is set
    if options.show_machine_metrics or options.v:
        logging.info(json.dumps(metrics, indent=2))

    # Do we already have nodes
    if metrics["total_nodes"] == 0:
        # Survey for existing nodes only if explicitly requested:
        # 1. Migrating from anm (--init --migrate_anm)
        # 2. Importing existing nodes (--init --import)
        should_survey = options.init and (
            options.migrate_anm or getattr(options, "import_nodes", False)
        )

        if should_survey:
            Workers = survey_machine(machine_config) or []
            if Workers:
                logging.info(f"Found {len(Workers)} existing nodes to import")
                # Detect port ranges from discovered nodes
                detected_ports = detect_port_ranges_from_nodes(Workers)

                # Update machine config with detected port ranges if different from current
                if detected_ports:
                    port_config_updates = {}
                    if (
                        detected_ports.get("port_start")
                        and detected_ports["port_start"] != machine_config.port_start
                    ):
                        logging.info(
                            f"Updating port_start from {machine_config.port_start} "
                            f"to {detected_ports['port_start']} (detected from nodes)"
                        )
                        port_config_updates["port_start"] = detected_ports["port_start"]

                    if (
                        detected_ports.get("metrics_port_start")
                        and detected_ports["metrics_port_start"] != machine_config.metrics_port_start
                    ):
                        logging.info(
                            f"Updating metrics_port_start from {machine_config.metrics_port_start} "
                            f"to {detected_ports['metrics_port_start']} (detected from nodes)"
                        )
                        port_config_updates["metrics_port_start"] = detected_ports["metrics_port_start"]

                    # Apply port configuration updates if any
                    if port_config_updates and not options.dry_run:
                        with S() as session:
                            session.query(Machine).filter(Machine.id == 1).update(
                                port_config_updates
                            )
                            session.commit()
                        logging.info("Port configuration updated in database")
                        # Update local_config with new port settings
                        local_config.update(port_config_updates)

                if options.dry_run:
                    logging.warning(f"DRYRUN: Not saving {len(Workers)} detected nodes")
                else:
                    with S() as session:
                        session.execute(insert(Node), Workers)
                        session.commit()
                    logging.info(f"Successfully imported {len(Workers)} node{'s' if len(Workers) != 1 else ''}")
                    # Reload metrics
                    metrics = get_machine_metrics(
                        S,
                        local_config["node_storage"],
                        local_config["hd_remove"],
                        local_config["crisis_bytes"],
                    )
                    logging.info(
                        "Found {counter} nodes configured".format(
                            counter=metrics["total_nodes"]
                        )
                    )
            else:
                logging.info("No existing nodes found to import")
        else:
            logging.info("No nodes found")
    else:
        logging.info(
            "Found {counter} nodes configured".format(counter=metrics["total_nodes"])
        )

    # Handle --init flag: exit after initialization (and optional survey)
    if options.init:
        logging.info("Initialization complete")
        sys.exit(0)

    # Check for reports
    if options.report:
        from wnm.reports import (
            generate_node_status_report,
            generate_node_status_details_report,
            generate_influx_resources_report,
            generate_machine_config_report,
            generate_machine_metrics_report,
        )

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
        elif options.report == "influx-resources":
            report_output = generate_influx_resources_report(S, options.service_name)
        elif options.report == "machine-config":
            report_output = generate_machine_config_report(
                S, options.dbpath, options.report_format
            )
        elif options.report == "machine-metrics":
            report_output = generate_machine_metrics_report(
                metrics, options.report_format
            )
        else:
            report_output = f"Unknown report type: {options.report}"

        print(report_output)
        sys.exit(0)

    # Check for forced actions
    if options.force_action:
        # Teardown requires confirmation for safety
        if options.force_action == "teardown" and not options.confirm:
            logging.error("Teardown requires --confirm flag for safety")
            sys.exit(1)

        logging.info(f"Executing forced action: {options.force_action}")
        executor = ActionExecutor(S)
        this_action = executor.execute_forced_action(
            options.force_action,
            local_config,
            metrics,
            service_name=options.service_name,
            dry_run=options.dry_run,
            count=options.count if hasattr(options, "count") else 1,
        )
    else:
        this_action = choose_action(local_config, metrics, options.dry_run)

    logging.info("Action: " + json.dumps(this_action, indent=2))

    # Exit normally (atexit will clean up lock file)
    sys.exit(0)


if __name__ == "__main__":
    main()
    # print(options.MemRemove)
    logging.debug("End of program")
