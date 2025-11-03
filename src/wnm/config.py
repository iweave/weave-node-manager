import json
import logging
import os
import platform
import re
import subprocess
import sys

import configargparse
from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.orm import scoped_session, sessionmaker

from wnm.common import (
    DEAD,
    DEFAULT_CRISIS_BYTES,
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
from wnm.models import Base, Machine, Node
from wnm.wallets import validate_rewards_address

logging.getLogger("sqlalchemy.engine.Engine").disabled = True


# ============================================================================
# Platform Detection and Path Constants
# ============================================================================

PLATFORM = platform.system()  # 'Linux', 'Darwin', 'Windows'

# Determine if running as root on Linux
IS_ROOT = PLATFORM == "Linux" and os.geteuid() == 0

# Platform-specific base directories
if PLATFORM == "Darwin":
    # macOS: Use standard macOS application directories
    BASE_DIR = os.path.expanduser("~/Library/Application Support/autonomi")
    NODE_STORAGE = os.path.expanduser("~/Library/Application Support/autonomi/node")
    LOG_DIR = os.path.expanduser("~/Library/Logs/autonomi")
    BOOTSTRAP_CACHE_DIR = os.path.expanduser("~/Library/Caches/autonomi/bootstrap-cache")
elif PLATFORM == "Linux":
    if IS_ROOT:
        # Linux root: Use legacy /var/antctl paths for backwards compatibility
        BASE_DIR = "/var/antctl"
        NODE_STORAGE = "/var/antctl/services"
        LOG_DIR = "/var/log/antnode"
        BOOTSTRAP_CACHE_DIR = "/var/antctl/bootstrap-cache"
    else:
        # Linux user: Use XDG Base Directory specification
        BASE_DIR = os.path.expanduser("~/.local/share/autonomi")
        NODE_STORAGE = os.path.expanduser("~/.local/share/autonomi/node")
        LOG_DIR = os.path.expanduser("~/.local/share/autonomi/logs")
        BOOTSTRAP_CACHE_DIR = os.path.expanduser("~/.local/share/autonomi/bootstrap-cache")
else:
    # Windows or other platforms
    BASE_DIR = os.path.expanduser("~/autonomi")
    NODE_STORAGE = os.path.expanduser("~/autonomi/node")
    LOG_DIR = os.path.expanduser("~/autonomi/logs")
    BOOTSTRAP_CACHE_DIR = os.path.expanduser("~/autonomi/bootstrap-cache")

# Derived paths
LOCK_FILE = os.path.join(BASE_DIR, "wnm_active")
DEFAULT_DB_PATH = f"sqlite:///{os.path.join(BASE_DIR, 'colony.db')}"

# Create directories if they don't exist (except in test mode)
if not os.getenv("WNM_TEST_MODE"):
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(NODE_STORAGE, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(BOOTSTRAP_CACHE_DIR, exist_ok=True)


# Config file parser
# This is a simple wrapper around configargparse that reads the config file from the default locations
# and allows for command line overrides. It also sets up the logging level and database path
def load_config():
    c = configargparse.ArgParser(
        default_config_files=["~/.local/share/wnm/config", "~/wnm/config"],
        description="wnm - Weave Node Manager",
    )

    c.add("-c", "--config", is_config_file=True, help="config file path")
    c.add("-v", help="verbose", action="store_true")
    c.add(
        "--dbpath",
        env_var="DBPATH",
        help="Path to the database",
        default="sqlite:///colony.db",
    )
    c.add("--loglevel", env_var="LOGLEVEL", help="Log level")
    c.add(
        "--dry_run", env_var="DRY_RUN", help="Do not save changes", action="store_true"
    )
    c.add("--init", help="Initialize a cluster", action="store_true")
    c.add("--migrate_anm", help="Migrate a cluster from anm", action="store_true")
    c.add("--teardown", help="Remove a cluster", action="store_true")
    c.add("--confirm", help="Confirm teardown without ui", action="store_true")
    c.add("--node_cap", env_var="NODE_CAP", help="Node Capacity")
    c.add("--cpu_less_than", env_var="CPU_LESS_THAN", help="CPU Add Threshold")
    c.add("--cpu_remove", env_var="CPU_REMOVE", help="CPU Remove Threshold")
    c.add("--mem_less_than", env_var="MEM_LESS_THAN", help="Memory Add Threshold")
    c.add("--mem_remove", env_var="MEM_REMOVE", help="Memory Remove Threshold")
    c.add("--hd_less_than", env_var="HD_LESS_THAN", help="Hard Drive Add Threshold")
    c.add("--hd_remove", env_var="HD_REMOVE", help="Hard Drive Remove Threshold")
    c.add("--delay_start", env_var="DELAY_START", help="Delay Start Timer")
    c.add("--delay_restart", env_var="DELAY_RESTART", help="Delay Restart Timer")
    c.add("--delay_upgrade", env_var="DELAY_UPGRADE", help="Delay Upgrade Timer")
    c.add("--delay_remove", env_var="DELAY_REMOVE", help="Delay Remove Timer")
    c.add("--node_storage", env_var="NODE_STORAGE", help="Node Storage Path")
    c.add("--rewards_address", env_var="REWARDS_ADDRESS", help="Rewards Address")
    c.add("--donate_address", env_var="DONATE_ADDRESS", help="Donate Address")
    c.add(
        "--max_load_average_allowed",
        env_var="MAX_LOAD_AVERAGE_ALLOWED",
        help="Max Load Average Allowed Remove Threshold",
    )
    c.add(
        "--desired_load_average",
        env_var="DESIRED_LOAD_AVERAGE",
        help="Desired Load Average Add Threshold",
    )
    c.add(
        "--port_start", env_var="PORT_START", help="Range to begin Node port assignment"
    )  # Only allowed during init
    c.add(
        "--metrics_port_start",
        env_var="METRICS_PORT_START",
        help="Range to begin Metrics port assignment",
    )  # Only allowed during init
    c.add(
        "--hdio_read_less_than",
        env_var="HDIO_READ_LESS_THAN",
        help="Hard Drive IO Read Add Threshold",
    )
    c.add(
        "--hdio_read_remove",
        env_var="HDIO_READ_REMOVE",
        help="Hard Drive IO Read Remove Threshold",
    )
    c.add(
        "--hdio_write_less_than",
        env_var="HDIO_WRITE_LESS_THAN",
        help="Hard Drive IO Write Add Threshold",
    )
    c.add(
        "--hdio_write_remove",
        env_var="HDIO_WRITE_REMOVE",
        help="Hard Drive IO Write Remove Threshold",
    )
    c.add(
        "--netio_read_less_than",
        env_var="NETIO_READ_LESS_THAN",
        help="Network IO Read Add Threshold",
    )
    c.add(
        "--netio_read_remove",
        env_var="NETIO_READ_REMOVE",
        help="Network IO Read Remove Threshold",
    )
    c.add(
        "--netio_write_less_than",
        env_var="NETIO_WRITE_LESS_THAN",
        help="Network IO Write Add Threshold",
    )
    c.add(
        "--netio_write_remove",
        env_var="NETIO_WRITE_REMOVE",
        help="Network IO Write Remove Threshold",
    )
    c.add("--crisis_bytes", env_var="CRISIS_BYTES", help="Crisis Bytes Threshold")
    c.add("--last_stopped_at", env_var="LAST_STOPPED_AT", help="Last Stopped Timestamp")
    c.add("--host", env_var="HOST", help="Hostname")
    c.add(
        "--environment", env_var="ENVIRONMENT", help="Environment variables for antnode"
    )
    c.add(
        "--start_args",
        env_var="START_ARGS",
        help="Arguments to pass to antnode",
    )
    c.add(
        "--force_action",
        env_var="FORCE_ACTION",
        help="Force an action: add, remove, upgrade, start, stop, disable, teardown, survey",
        choices=["add", "remove", "upgrade", "start", "stop", "disable", "teardown", "survey"],
    )
    c.add(
        "--service_name",
        env_var="SERVICE_NAME",
        help="Node name for targeted operations or comma-separated list for reports and survey (e.g., antnode0001,antnode0003)",
    )
    c.add(
        "--report",
        env_var="REPORT",
        help="Generate a report: node-status, node-status-details",
        choices=["node-status", "node-status-details"],
    )
    c.add(
        "--report_format",
        env_var="REPORT_FORMAT",
        help="Report output format: text or json (default: text)",
        choices=["text", "json"],
        default="text",
    )
    c.add(
        "--count",
        env_var="COUNT",
        help="Number of nodes to affect when using --force_action (default: 1). Works with add, remove, start, stop, upgrade actions.",
        type=int,
        default=1,
    )

    options = c.parse_known_args()[0] or []
    # Return the first result from parse_known_args, ignore unknown options
    return options


# Merge the changes from the config file with the database
def merge_config_changes(options, machine_config):
    # Collect updates
    cfg = {}
    if options.node_cap and int(options.node_cap) != machine_config.node_cap:
        cfg["node_cap"] = int(options.node_cap)
    if options.cpu_less_than and int(options.cpu_less_than) != machine_config.cpu_less_than:
        cfg["cpu_less_than"] = int(options.cpu_less_than)
    if options.cpu_remove and int(options.cpu_remove) != machine_config.cpu_remove:
        cfg["cpu_remove"] = int(options.cpu_remove)
    if options.mem_less_than and int(options.mem_less_than) != machine_config.mem_less_than:
        cfg["mem_less_than"] = int(options.mem_less_than)
    if options.mem_remove and int(options.mem_remove) != machine_config.mem_remove:
        cfg["mem_remove"] = int(options.mem_remove)
    if options.hd_less_than and int(options.hd_less_than) != machine_config.hd_less_than:
        cfg["hd_less_than"] = int(options.hd_less_than)
    if options.hd_remove and int(options.hd_remove) != machine_config.hd_remove:
        cfg["hd_remove"] = int(options.hd_remove)
    if options.delay_start and int(options.delay_start) != machine_config.delay_start:
        cfg["delay_start"] = int(options.delay_start)
    if (
        options.delay_restart
        and int(options.delay_restart) != machine_config.delay_restart
    ):
        cfg["delay_restart"] = int(options.delay_restart)
    if (
        options.delay_upgrade
        and int(options.delay_upgrade) != machine_config.delay_upgrade
    ):
        cfg["delay_upgrade"] = int(options.delay_upgrade)
    if options.delay_remove and int(options.delay_remove) != machine_config.delay_remove:
        cfg["delay_remove"] = int(options.delay_remove)
    if options.node_storage and options.node_storage != machine_config.node_storage:
        cfg["node_storage"] = options.node_storage
    if (
        options.rewards_address
        and options.rewards_address != machine_config.rewards_address
    ):
        # Validate the new rewards_address
        is_valid, error_msg = validate_rewards_address(
            options.rewards_address, machine_config.donate_address
        )
        if not is_valid:
            logging.error(f"Invalid rewards_address: {error_msg}")
            sys.exit(1)
        cfg["rewards_address"] = options.rewards_address
    if options.donate_address and options.donate_address != machine_config.donate_address:
        cfg["donate_address"] = options.donate_address
    if (
        options.max_load_average_allowed
        and float(options.max_load_average_allowed) != machine_config.max_load_average_allowed
    ):
        cfg["max_load_average_allowed"] = float(options.max_load_average_allowed)
    if (
        options.desired_load_average
        and float(options.desired_load_average) != machine_config.desired_load_average
    ):
        cfg["desired_load_average"] = float(options.desired_load_average)
    if options.port_start and int(options.port_start) != machine_config.port_start:
        cfg["port_start"] = int(options.port_start)
    if (
        options.hdio_read_less_than
        and int(options.hdio_read_less_than) != machine_config.hdio_read_less_than
    ):
        cfg["hdio_read_less_than"] = int(options.hdio_read_less_than)
    if (
        options.hdio_read_remove
        and int(options.hdio_read_remove) != machine_config.hdio_read_remove
    ):
        cfg["hdio_read_remove"] = int(options.hdio_read_remove)
    if (
        options.hdio_write_less_than
        and int(options.hdio_write_less_than) != machine_config.hdio_write_less_than
    ):
        cfg["hdio_write_less_than"] = int(options.hdio_write_less_than)
    if (
        options.hdio_write_remove
        and int(options.hdio_write_remove) != machine_config.hdio_write_remove
    ):
        cfg["hdio_write_remove"] = int(options.hdio_write_remove)
    if (
        options.netio_read_less_than
        and int(options.netio_read_less_than) != machine_config.netio_read_less_than
    ):
        cfg["netio_read_less_than"] = int(options.netio_read_less_than)
    if (
        options.netio_read_remove
        and int(options.netio_read_remove) != machine_config.netio_read_remove
    ):
        cfg["netio_read_remove"] = int(options.netio_read_remove)
    if (
        options.netio_write_less_than
        and int(options.netio_write_less_than) != machine_config.netio_write_less_than
    ):
        cfg["netio_write_less_than"] = int(options.netio_write_less_than)
    if (
        options.netio_write_remove
        and int(options.netio_write_remove) != machine_config.netio_write_remove
    ):
        cfg["netio_write_remove"] = int(options.netio_write_remove)
    if options.crisis_bytes and int(options.crisis_bytes) != machine_config.crisis_bytes:
        cfg["crisis_bytes"] = int(options.crisis_bytes)
    if (
        options.metrics_port_start
        and int(options.metrics_port_start) != machine_config.metrics_port_start
    ):
        cfg["metrics_port_start"] = int(options.metrics_port_start)
    if options.environment and options.environment != machine_config.environment:
        cfg["environment"] = options.environment
    if options.start_args and options.start_args != machine_config.start_args:
        cfg["start_args"] = options.start_args

    return cfg


# Get anm configuration
def load_anm_config(options):
    anm_config = {}

    # Let's get the real count of CPU's available to this process
    if PLATFORM == "Linux":
        # Linux: use sched_getaffinity for accurate count (respects cgroups/taskset)
        anm_config["cpu_count"] = len(os.sched_getaffinity(0))
    else:
        # macOS/other: use os.cpu_count()
        anm_config["cpu_count"] = os.cpu_count() or 1

    # What can we save from /var/antctl/config
    if os.path.exists("/var/antctl/config"):
        load_dotenv("/var/antctl/config")
    anm_config["node_cap"] = int(os.getenv("NodeCap") or options.node_cap or 20)
    anm_config["cpu_less_than"] = int(
        os.getenv("CpuLessThan") or options.cpu_less_than or 50
    )
    anm_config["cpu_remove"] = int(os.getenv("CpuRemove") or options.cpu_remove or 70)
    anm_config["mem_less_than"] = int(
        os.getenv("MemLessThan") or options.mem_less_than or 70
    )
    anm_config["mem_remove"] = int(os.getenv("MemRemove") or options.mem_remove or 90)
    anm_config["hd_less_than"] = int(os.getenv("HDLessThan") or options.hd_less_than or 70)
    anm_config["hd_remove"] = int(os.getenv("HDRemove") or options.hd_remove or 90)
    anm_config["delay_start"] = int(os.getenv("DelayStart") or options.delay_start or 300)
    anm_config["delay_upgrade"] = int(
        os.getenv("DelayUpgrade") or options.delay_upgrade or 300
    )
    anm_config["delay_restart"] = int(
        os.getenv("DelayRestart") or options.delay_restart or 600
    )
    anm_config["delay_remove"] = int(
        os.getenv("DelayRemove") or options.delay_remove or 300
    )
    anm_config["node_storage"] = (
        os.getenv("NodeStorage") or options.node_storage or NODE_STORAGE
    )
    # Default to the faucet donation address
    try:
        anm_config["rewards_address"] = re.findall(
            r"--rewards-address ([\dA-Fa-fXx]+)", os.getenv("RewardsAddress")
        )[0]
    except (IndexError, TypeError) as e:
        try:
            anm_config["rewards_address"] = re.findall(
                r"([\dA-Fa-fXx]+)", os.getenv("RewardsAddress")
            )[0]
        except (IndexError, TypeError) as e:
            logging.debug(f"Unable to parse RewardsAddress from env: {e}")
            anm_config["rewards_address"] = options.rewards_address
            if not anm_config["rewards_address"]:
                logging.warning("Unable to detect RewardsAddress")
                sys.exit(1)
    anm_config["donate_address"] = (
        os.getenv("DonateAddress") or options.donate_address or DONATE
    )
    anm_config["max_load_average_allowed"] = float(
        os.getenv("MaxLoadAverageAllowed") or anm_config["cpu_count"]
    )
    anm_config["desired_load_average"] = float(
        os.getenv("DesiredLoadAverage") or (anm_config["cpu_count"] * 0.6)
    )

    try:
        with open("/usr/bin/anms.sh", "r") as file:
            data = file.read()
        anm_config["port_start"] = int(re.findall(r"ntpr\=(\d+)", data)[0])
    except (FileNotFoundError, IndexError, ValueError) as e:
        logging.debug(f"Unable to read PortStart from anms.sh: {e}")
        anm_config["port_start"] = options.port_start or 55

    anm_config["metrics_port_start"] = (
        options.metrics_port_start or 13
    )  # This is hardcoded in the anm.sh script

    anm_config["hdio_read_less_than"] = int(os.getenv("HDIOReadLessThan") or 0)
    anm_config["hdio_read_remove"] = int(os.getenv("HDIOReadRemove") or 0)
    anm_config["hdio_write_less_than"] = int(os.getenv("HDIOWriteLessThan") or 0)
    anm_config["hdio_write_remove"] = int(os.getenv("HDIOWriteRemove") or 0)
    anm_config["netio_read_less_than"] = int(os.getenv("NetIOReadLessThan") or 0)
    anm_config["netio_read_remove"] = int(os.getenv("NetIOReadRemove") or 0)
    anm_config["netio_write_less_than"] = int(os.getenv("NetIOWriteLessThan") or 0)
    anm_config["netio_write_remove"] = int(os.getenv("NetIOWriteRemove") or 0)
    # Timer for last stopped nodes
    anm_config["last_stopped_at"] = 0
    anm_config["host"] = os.getenv("Host") or options.host or "127.0.0.1"
    anm_config["crisis_bytes"] = options.host or DEFAULT_CRISIS_BYTES
    anm_config["environment"] = options.environment or ""
    anm_config["start_args"] = options.start_args or ""

    return anm_config


# This belongs someplace else
def migrate_anm(options):
    if os.path.exists("/var/antctl/system"):
        # Is anm scheduled to run
        if os.path.exists("/etc/cron.d/anm"):
            # remove cron to disable old anm
            try:
                subprocess.run(["sudo", "rm", "/etc/cron.d/anm"])
            except Exception as error:
                template = (
                    "In GAV - An exception of type {0} occurred. Arguments:\n{1!r}"
                )
                message = template.format(type(error).__name__, error.args)
                logging.info(message)
                sys.exit(1)
        # Is anm sitll running? We'll wait
        if os.path.exists("/var/antctl/block"):
            logging.info("anm still running, waiting...")
            sys.exit(1)
        # Ok, load anm config
        return load_anm_config(options)
    else:
        return False


# Teardown the machine
def teardown_machine(machine_config):
    logging.info("Teardown machine")
    pass
    # disable cron
    # with S() as session:
    #     select Nodes
    #     for node in nodes:
    #         delete node


def define_machine(options):
    if not options.rewards_address:
        logging.warning("Rewards Address is required")
        return False

    # Determine donate_address that will be used for validation
    donate_address = options.donate_address or DONATE

    # Validate rewards_address format
    is_valid, error_msg = validate_rewards_address(options.rewards_address, donate_address)
    if not is_valid:
        logging.error(f"Invalid rewards_address: {error_msg}")
        return False

    if PLATFORM == "Linux":
        # Linux: use sched_getaffinity for accurate count (respects cgroups/taskset)
        cpucount = len(os.sched_getaffinity(0))
    else:
        # macOS/other: use os.cpu_count()
        cpucount = os.cpu_count() or 1
    machine = {
        "id": 1,
        "cpu_count": cpucount,
        "node_cap": int(options.node_cap) if options.node_cap else 20,
        "cpu_less_than": int(options.cpu_less_than) if options.cpu_less_than else 50,
        "cpu_remove": int(options.cpu_remove) if options.cpu_remove else 70,
        "mem_less_than": int(options.mem_less_than) if options.mem_less_than else 70,
        "mem_remove": int(options.mem_remove) if options.mem_remove else 90,
        "hd_less_than": int(options.hd_less_than) if options.hd_less_than else 70,
        "hd_remove": int(options.hd_remove) if options.hd_remove else 90,
        "delay_start": int(options.delay_start) if options.delay_start else 300,
        "delay_upgrade": int(options.delay_upgrade) if options.delay_upgrade else 300,
        "delay_remove": int(options.delay_remove) if options.delay_remove else 300,
        "node_storage": options.node_storage or NODE_STORAGE,
        "rewards_address": options.rewards_address,
        "donate_address": options.donate_address
        or "0x00455d78f850b0358E8cea5be24d415E01E107CF",
        "max_load_average_allowed": (
            float(options.max_load_average_allowed)
            if options.max_load_average_allowed
            else cpucount
        ),
        "desired_load_average": (
            float(options.desired_load_average)
            if options.desired_load_average
            else cpucount * 0.6
        ),
        "port_start": int(options.port_start) if options.port_start else 55,
        "hdio_read_less_than": (
            int(options.hdio_read_less_than) if options.hdio_read_less_than else 0
        ),
        "hdio_read_remove": int(options.hdio_read_remove) if options.hdio_read_remove else 0,
        "hdio_write_less_than": (
            int(options.hdio_write_less_than) if options.hdio_write_less_than else 0
        ),
        "hdio_write_remove": (
            int(options.hdio_write_remove) if options.hdio_write_remove else 0
        ),
        "netio_read_less_than": (
            int(options.netio_read_less_than) if options.netio_read_less_than else 0
        ),
        "netio_read_remove": (
            int(options.netio_read_remove) if options.netio_read_remove else 0
        ),
        "netio_write_less_than": (
            int(options.netio_write_less_than) if options.netio_write_less_than else 0
        ),
        "netio_write_remove": (
            int(options.netio_write_remove) if options.netio_write_remove else 0
        ),
        "last_stopped_at": 0,
        "host": options.host or "127.0.0.1",
        "crisis_bytes": (
            int(options.crisis_bytes) if options.crisis_bytes else DEFAULT_CRISIS_BYTES
        ),
        "metrics_port_start": (
            int(options.metrics_port_start) if options.metrics_port_start else 13
        ),
        "environment": options.environment if options.environment else "",
        "start_args": options.start_args if options.start_args else "",
    }
    with S() as session:
        session.execute(insert(Machine), [machine])
        session.commit()
    return True


# Apply changes to system
def apply_config_updates(config_updates):
    global machine_config
    if config_updates:
        with S() as session:
            session.query(Machine).filter(Machine.id == 1).update(config_updates)
            session.commit()
            # Reload the machine config
            machine_config = session.execute(select(Machine)).first()
            # Get Machine from Row
            machine_config = machine_config[0]


# Load options now so we know what database to load
options = load_config()

# Setup Database engine
engine = create_engine(options.dbpath, echo=True)

# Generate ORM
Base.metadata.create_all(engine)

# Create a connection to the ORM
session_factory = sessionmaker(bind=engine)
S = scoped_session(session_factory)

# Remember if we init a new machine
did_we_init = False

# Skip machine configuration check in test mode
if os.getenv("WNM_TEST_MODE"):
    # In test mode, use a minimal machine config or None
    machine_config = None
else:
    # Check if we have a defined machine
    with S() as session:
        machine_config = session.execute(select(Machine)).first()

# No machine configured
if not machine_config and not os.getenv("WNM_TEST_MODE"):
    # Are we initializing a new machine?
    if options.init:
        # Init and dry-run are mutually exclusive
        if options.dry_run:
            logging.error("dry run not supported during init.")
            sys.exit(1)
        else:
            # Did we get a request to migrate from anm?
            if options.migrate_anm:
                if anm_config := migrate_anm(options):
                    # Save and reload config
                    with S() as session:
                        session.execute(insert(Machine), [anm_config])
                        session.commit()
                        machine_config = session.execute(select(Machine)).first()
                    if not machine_config:
                        print("Unable to locate record after successful migration")
                        sys.exit(1)
                    # Get Machine from Row
                    machine_config = machine_config[0]
                    did_we_init = True
                else:
                    print("Failed to migrate machine from anm")
                    sys.exit(1)
            else:
                if define_machine(options):
                    with S() as session:
                        machine_config = session.execute(select(Machine)).first()
                    if not machine_config:
                        print(
                            "Failed to locate record after successfully defining a machine"
                        )
                        sys.exit(1)
                    # Get Machine from Row
                    machine_config = machine_config[0]
                    did_we_init = True
                else:
                    print("Failed to create machine")
                    sys.exit(1)
    else:
        print("No config found")
        sys.exit(1)
else:
    # Fail if we are trying to init a machine that is already initialized
    if options.init:
        logging.warning("Machine already initialized")
        sys.exit(1)
    # Initate a teardown of the machine
    if options.teardown:
        if options.confirm:
            if options.dry_run:
                logging.info("DRY_RUN: Initiate Teardown")
            else:
                teardown_machine(machine_config)
            sys.exit(0)
        else:
            logging.warning("Please confirm the teardown with --confirm")
            sys.exit(1)
    # Get Machine from Row (skip in test mode)
    if not os.getenv("WNM_TEST_MODE"):
        machine_config = machine_config[0]

# Collect the proposed changes unless we are initializing (skip in test mode)
config_updates = merge_config_changes(options, machine_config) if not os.getenv("WNM_TEST_MODE") else {}
# Failfirst on invalid config change
if (
    "port_start" in config_updates or "metrics_port_start" in config_updates
) and not did_we_init:
    logging.warning("Can not change start port numbers on an active machine")
    sys.exit(1)


if __name__ == "__main__":
    print("Changes:", json.loads(json.dumps(config_updates)))
    print(json.loads(json.dumps(machine_config)))
