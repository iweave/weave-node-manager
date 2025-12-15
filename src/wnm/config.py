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
    FAUCET,
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

# ============================================================================
# Port Normalization Utilities
# ============================================================================


def normalize_port_start(value):
    """
    Normalize port start values to thousands format.

    Accepts both abbreviated (55) and full port numbers (55000, 55001) and
    converts them to the thousands digit format used internally.

    Args:
        value: Port start value as string, int, or None

    Returns:
        int: Normalized port start in thousands format (e.g., 55 for 55000)
        None: If value is None

    Examples:
        normalize_port_start(55) -> 55
        normalize_port_start(55000) -> 55
        normalize_port_start(55001) -> 55  (rounds down)
        normalize_port_start("13000") -> 13
    """
    if value is None:
        return None

    # Convert to int if string
    if isinstance(value, str):
        value = int(value)

    # If value >= 1000, it's likely a full port number - truncate to thousands
    if value >= 1000:
        return value // 1000

    # Otherwise, use as-is (already in thousands format)
    return value


# ============================================================================
# Platform Detection and Path Constants
# ============================================================================

PLATFORM = platform.system()  # 'Linux', 'Darwin', 'Windows'

# Determine if running as root on Linux (kept for backwards compatibility)
IS_ROOT = PLATFORM == "Linux" and os.geteuid() == 0


def _detect_process_manager_mode():
    """
    Detect the process manager mode early to determine path selection.

    Checks (in priority order):
    1. --process_manager command line argument
    2. PROCESS_MANAGER environment variable
    3. Existing database in either sudo or user paths
    4. Fallback to IS_ROOT-based detection for backwards compatibility

    Returns:
        str: "sudo" or "user" indicating the mode
    """
    # Check command line args first (quick parse without configargparse)
    for i, arg in enumerate(sys.argv):
        if arg == "--process_manager" and i + 1 < len(sys.argv):
            pm = sys.argv[i + 1]
            if "+sudo" in pm:
                return "sudo"
            elif "+user" in pm:
                return "user"

    # Check environment variable
    pm_env = os.getenv("PROCESS_MANAGER")
    if pm_env:
        if "+sudo" in pm_env:
            return "sudo"
        elif "+user" in pm_env:
            return "user"

    # Check if .env file exists and load it
    env_file = os.path.expanduser("~/.local/share/wnm/.env")
    if os.path.exists(env_file):
        load_dotenv(env_file)
        pm_env = os.getenv("PROCESS_MANAGER")
        if pm_env:
            if "+sudo" in pm_env:
                return "sudo"
            elif "+user" in pm_env:
                return "user"

    # Check for existing databases to auto-detect mode
    # Try both potential locations and read process_manager from machine table
    import sqlite3

    db_locations = []

    # Check for --dbpath command line argument first
    for i, arg in enumerate(sys.argv):
        if arg == "--dbpath" and i + 1 < len(sys.argv):
            dbpath_arg = sys.argv[i + 1]
            # Remove sqlite:/// prefix if present
            if dbpath_arg.startswith("sqlite:///"):
                dbpath_arg = dbpath_arg[10:]
            # Expand ~ to home directory
            dbpath_arg = os.path.expanduser(dbpath_arg)
            db_locations.append(dbpath_arg)
            break

    # Check for DBPATH environment variable
    dbpath_env = os.getenv("DBPATH")
    if dbpath_env:
        # Remove sqlite:/// prefix if present
        if dbpath_env.startswith("sqlite:///"):
            dbpath_env = dbpath_env[10:]
        # Expand variables like $HOME and ~ for home directory
        dbpath_env = os.path.expandvars(dbpath_env)
        dbpath_env = os.path.expanduser(dbpath_env)
        db_locations.append(dbpath_env)

    # Add platform-specific default locations
    if PLATFORM == "Linux":
        db_locations.extend(
            [
                "/var/antctl/colony.db",  # sudo mode
                os.path.expanduser("~/.local/share/autonomi/colony.db"),  # user mode
            ]
        )
    elif PLATFORM == "Darwin":
        db_locations.extend(
            [
                "/Library/Application Support/autonomi/colony.db",  # sudo mode
                os.path.expanduser(
                    "~/Library/Application Support/autonomi/colony.db"
                ),  # user mode
            ]
        )

    for db_path in db_locations:
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT process_manager FROM machine WHERE id = 1")
                row = cursor.fetchone()
                conn.close()

                if row and row[0]:
                    pm = row[0]
                    if "+sudo" in pm:
                        return "sudo"
                    elif "+user" in pm:
                        return "user"
            except (sqlite3.Error, IndexError):
                # Database exists but can't read it - try next location
                continue

    # Fallback to IS_ROOT for backwards compatibility
    # If running as actual root, assume sudo mode (system-wide paths)
    if IS_ROOT:
        return "sudo"

    # Default to user mode
    return "user"


# Detect the process manager mode early
_PM_MODE = _detect_process_manager_mode()

# Platform-specific base directories based on process manager mode
if PLATFORM == "Darwin":
    # macOS paths
    if _PM_MODE == "sudo":
        # System-wide paths for launchd+sudo
        BASE_DIR = "/Library/Application Support/autonomi"
        NODE_STORAGE = "/Library/Application Support/autonomi/node"
        LOG_DIR = "/Library/Logs/autonomi"
        BOOTSTRAP_CACHE_DIR = "/Library/Caches/autonomi/bootstrap-cache"
    else:
        # User-level paths for launchd+user (default)
        BASE_DIR = os.path.expanduser("~/Library/Application Support/autonomi")
        NODE_STORAGE = os.path.expanduser("~/Library/Application Support/autonomi/node")
        LOG_DIR = os.path.expanduser("~/Library/Logs/autonomi")
        BOOTSTRAP_CACHE_DIR = os.path.expanduser(
            "~/Library/Caches/autonomi/bootstrap-cache"
        )
elif PLATFORM == "Linux":
    if _PM_MODE == "sudo":
        # System-wide paths for systemd+sudo or setsid+sudo
        BASE_DIR = "/var/antctl"
        NODE_STORAGE = "/var/antctl/services"
        LOG_DIR = "/var/log/antnode"
        BOOTSTRAP_CACHE_DIR = "/var/antctl/bootstrap-cache"
    else:
        # User-level paths for systemd+user or setsid+user (default)
        BASE_DIR = os.path.expanduser("~/.local/share/autonomi")
        NODE_STORAGE = os.path.expanduser("~/.local/share/autonomi/node")
        LOG_DIR = os.path.expanduser("~/.local/share/autonomi/logs")
        BOOTSTRAP_CACHE_DIR = os.path.expanduser(
            "~/.local/share/autonomi/bootstrap-cache"
        )
else:
    # Windows or other platforms (user-level only)
    BASE_DIR = os.path.expanduser("~/autonomi")
    NODE_STORAGE = os.path.expanduser("~/autonomi/node")
    LOG_DIR = os.path.expanduser("~/autonomi/logs")
    BOOTSTRAP_CACHE_DIR = os.path.expanduser("~/autonomi/bootstrap-cache")

# Derived paths
LOCK_FILE = os.path.join(BASE_DIR, "wnm_active")
DEFAULT_DB_PATH = f"sqlite:///{os.path.join(BASE_DIR, 'colony.db')}"

# Create minimal directories needed for config.py (except in test mode)
# Note: NODE_STORAGE and LOG_DIR are created by ProcessManager when nodes are created
if not os.getenv("WNM_TEST_MODE"):
    if _PM_MODE == "sudo":
        # For sudo mode with system paths, use sudo to create directories
        for directory in [BASE_DIR, BOOTSTRAP_CACHE_DIR]:
            if not os.path.exists(directory):
                try:
                    subprocess.run(
                        ["sudo", "mkdir", "-p", directory],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    # If sudo fails or isn't available, silently continue
                    # (logging not yet configured at module import time)
                    pass
    else:
        # For user mode, create directories normally (no sudo needed)
        os.makedirs(BASE_DIR, exist_ok=True)
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
        "--show_machine_config",
        help="Log machine config at INFO level on every run (default: disabled)",
        action="store_true",
    )
    c.add(
        "--show_machine_metrics",
        help="Log system metrics at INFO level on every run (default: disabled)",
        action="store_true",
    )
    c.add(
        "--show_decisions",
        help="Log decision engine features at INFO level (default: disabled)",
        action="store_true",
    )
    c.add(
        "-q",
        "--quiet",
        help="Quiet mode (suppress all output except errors)",
        action="store_true",
    )
    c.add("--version", help="Show version and exit", action="store_true")
    c.add(
        "--remove_lockfile", help="Remove the lock file and exit", action="store_true"
    )
    c.add(
        "--dbpath",
        env_var="DBPATH",
        help="Path to the database",
        default=DEFAULT_DB_PATH,
    )
    c.add(
        "--loglevel",
        env_var="LOGLEVEL",
        help="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        default="INFO",
    )
    c.add(
        "--dry_run", env_var="DRY_RUN", help="Do not save changes", action="store_true"
    )
    c.add("--init", help="Initialize a cluster", action="store_true")
    c.add("--migrate_anm", help="Migrate a cluster from anm", action="store_true")
    c.add(
        "--import",
        dest="import_nodes",
        help="Import existing nodes during initialization (used with --init)",
        action="store_true",
    )
    c.add(
        "--confirm",
        help="Confirm destructive operations (required for teardown)",
        action="store_true",
    )
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
    c.add("--survey_delay", env_var="SURVEY_DELAY", help="Survey Delay between nodes (milliseconds)")
    c.add(
        "--this_survey_delay",
        env_var="THIS_SURVEY_DELAY",
        help="Override survey_delay for this execution only (milliseconds)",
        type=int,
    )
    c.add(
        "--action_delay",
        env_var="ACTION_DELAY",
        help="Delay between node operations in milliseconds (default: 0)",
        type=int,
    )
    c.add(
        "--this_action_delay",
        env_var="THIS_ACTION_DELAY",
        help="Override action_delay for this execution only (milliseconds)",
        type=int,
    )
    c.add(
        "--interval",
        env_var="INTERVAL",
        help="Override action_delay for this execution only (milliseconds), compatible with antctl",
        type=int,
    )
    c.add(
        "--max_concurrent_upgrades",
        env_var="MAX_CONCURRENT_UPGRADES",
        help="Maximum number of nodes that can be upgrading simultaneously (default: 1)",
    )
    c.add(
        "--max_concurrent_starts",
        env_var="MAX_CONCURRENT_STARTS",
        help="Maximum number of nodes that can be starting/restarting simultaneously (default: 1)",
    )
    c.add(
        "--max_concurrent_removals",
        env_var="MAX_CONCURRENT_REMOVALS",
        help="Maximum number of nodes that can be in removal state simultaneously (default: 1)",
    )
    c.add(
        "--max_concurrent_operations",
        env_var="MAX_CONCURRENT_OPERATIONS",
        help="Maximum total number of concurrent operations (global limit across all types, default: 1)",
    )
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
        "--rpc_port_start",
        env_var="RPC_PORT_START",
        help="Range to begin RPC port assignment",
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
        help="Force an action: add, remove, upgrade, start, stop, disable, teardown, survey, wnm-db-migration, nullop, update_config",
        choices=[
            "add",
            "remove",
            "upgrade",
            "start",
            "stop",
            "disable",
            "teardown",
            "survey",
            "wnm-db-migration",
            "nullop",
            "update_config",
        ],
    )
    c.add(
        "--service_name",
        env_var="SERVICE_NAME",
        help="Node name for targeted operations or comma-separated list for reports and survey (e.g., antnode0001,antnode0003)",
    )
    c.add(
        "--report",
        env_var="REPORT",
        help="Generate a report: node-status, node-status-details, influx-resources, machine-config, machine-metrics",
        choices=["node-status", "node-status-details", "influx-resources", "machine-config", "machine-metrics"],
    )
    c.add(
        "--report_format",
        env_var="REPORT_FORMAT",
        help="Report output format: text, json, env, or config (default: text). The env and config formats are only supported for machine-config and machine-metrics reports.",
        choices=["text", "json", "env", "config"],
        default="text",
    )
    c.add(
        "--json",
        help="Shortcut for --report_format json",
        action="store_const",
        const="json",
        dest="report_format",
    )
    c.add(
        "--count",
        env_var="COUNT",
        help="Number of nodes to affect when using --force_action (default: 1). Works with add, remove, start, stop, upgrade actions.",
        type=int,
        default=1,
    )
    c.add(
        "--process_manager",
        env_var="PROCESS_MANAGER",
        help="Process manager to use: systemd+sudo, systemd+user, setsid+sudo, setsid+user, launchd+sudo, launchd+user, antctl+sudo, antctl+user",
        choices=[
            "systemd+sudo",
            "systemd+user",
            "setsid+sudo",
            "setsid+user",
            "launchd+sudo",
            "launchd+user",
            "antctl+sudo",
            "antctl+user",
        ],
    )
    c.add(
        "--no_upnp",
        env_var="NO_UPNP",
        help="Disable UPnP port forwarding on nodes (default: enabled)",
        action="store_true",
    )
    c.add(
        "--antnode_path",
        env_var="ANTNODE_PATH",
        help="Path to the antnode binary (default: ~/.local/bin/antnode)",
    )

    options = c.parse_known_args()[0] or []

    # Configure logging level based on options
    if options.quiet:
        log_level = logging.ERROR
    elif options.loglevel:
        # Convert string to logging level
        log_level = getattr(logging, options.loglevel.upper(), logging.INFO)
    else:
        log_level = logging.INFO

    # Set the logging level with a proper format
    logging.basicConfig(
        level=log_level,
        format='%(levelname)s [%(name)s] %(message)s',
        force=True
    )
    # Explicitly set root logger level to ensure it takes effect
    logging.getLogger().setLevel(log_level)

    # Info level logging for sqlalchemy is too verbose, only use when needed
    logging.getLogger("sqlalchemy.engine.Engine").disabled = True

    # Return the first result from parse_known_args, ignore unknown options
    return options


# Merge the changes from the config file with the database
def merge_config_changes(options, machine_config):
    # Collect updates
    cfg = {}
    if options.node_cap and int(options.node_cap) != machine_config.node_cap:
        cfg["node_cap"] = int(options.node_cap)
    if (
        options.cpu_less_than
        and int(options.cpu_less_than) != machine_config.cpu_less_than
    ):
        cfg["cpu_less_than"] = int(options.cpu_less_than)
    if options.cpu_remove and int(options.cpu_remove) != machine_config.cpu_remove:
        cfg["cpu_remove"] = int(options.cpu_remove)
    if (
        options.mem_less_than
        and int(options.mem_less_than) != machine_config.mem_less_than
    ):
        cfg["mem_less_than"] = int(options.mem_less_than)
    if options.mem_remove and int(options.mem_remove) != machine_config.mem_remove:
        cfg["mem_remove"] = int(options.mem_remove)
    if (
        options.hd_less_than
        and int(options.hd_less_than) != machine_config.hd_less_than
    ):
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
    if (
        options.delay_remove
        and int(options.delay_remove) != machine_config.delay_remove
    ):
        cfg["delay_remove"] = int(options.delay_remove)
    if (
        options.survey_delay
        and int(options.survey_delay) != machine_config.survey_delay
    ):
        cfg["survey_delay"] = int(options.survey_delay)
    if (
        options.action_delay is not None
        and int(options.action_delay) != machine_config.action_delay
    ):
        cfg["action_delay"] = int(options.action_delay)
    if (
        options.max_concurrent_upgrades
        and int(options.max_concurrent_upgrades) != machine_config.max_concurrent_upgrades
    ):
        cfg["max_concurrent_upgrades"] = int(options.max_concurrent_upgrades)
    if (
        options.max_concurrent_starts
        and int(options.max_concurrent_starts) != machine_config.max_concurrent_starts
    ):
        cfg["max_concurrent_starts"] = int(options.max_concurrent_starts)
    if (
        options.max_concurrent_removals
        and int(options.max_concurrent_removals) != machine_config.max_concurrent_removals
    ):
        cfg["max_concurrent_removals"] = int(options.max_concurrent_removals)
    if (
        options.max_concurrent_operations
        and int(options.max_concurrent_operations) != machine_config.max_concurrent_operations
    ):
        cfg["max_concurrent_operations"] = int(options.max_concurrent_operations)
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
    if (
        options.donate_address
        and options.donate_address != machine_config.donate_address
    ):
        cfg["donate_address"] = options.donate_address
    if (
        options.max_load_average_allowed
        and float(options.max_load_average_allowed)
        != machine_config.max_load_average_allowed
    ):
        cfg["max_load_average_allowed"] = float(options.max_load_average_allowed)
    if (
        options.desired_load_average
        and float(options.desired_load_average) != machine_config.desired_load_average
    ):
        cfg["desired_load_average"] = float(options.desired_load_average)
    if options.port_start and normalize_port_start(options.port_start) != machine_config.port_start:
        cfg["port_start"] = normalize_port_start(options.port_start)
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
    if (
        options.crisis_bytes
        and int(options.crisis_bytes) != machine_config.crisis_bytes
    ):
        cfg["crisis_bytes"] = int(options.crisis_bytes)
    if (
        options.metrics_port_start
        and normalize_port_start(options.metrics_port_start) != machine_config.metrics_port_start
    ):
        cfg["metrics_port_start"] = normalize_port_start(options.metrics_port_start)
    if (
        options.rpc_port_start
        and normalize_port_start(options.rpc_port_start) != machine_config.rpc_port_start
    ):
        cfg["rpc_port_start"] = normalize_port_start(options.rpc_port_start)
    if options.environment and options.environment != machine_config.environment:
        cfg["environment"] = options.environment
    if options.start_args and options.start_args != machine_config.start_args:
        cfg["start_args"] = options.start_args
    # process_manager can only be set during init (not allowed to change after initialization)
    # Similar to port_start and metrics_port_start
    if (
        options.process_manager
        and options.process_manager != machine_config.process_manager
    ):
        cfg["process_manager"] = options.process_manager
    # Only update no_upnp if explicitly provided (check if in command line or env var)
    # Don't update based on store_true default value of False
    import sys

    if "--no_upnp" in sys.argv or "--no-upnp" in sys.argv or os.getenv("NO_UPNP"):
        if bool(options.no_upnp) != bool(machine_config.no_upnp):
            cfg["no_upnp"] = bool(options.no_upnp)
    # Only update antnode_path if explicitly provided (not None)
    if options.antnode_path and options.antnode_path != machine_config.antnode_path:
        cfg["antnode_path"] = options.antnode_path

    return cfg


# Helper function to safely get option values (handles Mock objects in tests)
def _get_option(options, attr_name, default=None):
    """Safely get an attribute from options, handling Mock objects in tests."""
    value = getattr(options, attr_name, default)
    # If it's a Mock object (has _mock_name attribute), treat as None
    if hasattr(value, "_mock_name"):
        return default
    return value if value is not None else default


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
    anm_config["node_cap"] = int(
        os.getenv("NodeCap") or _get_option(options, "node_cap") or 20
    )
    anm_config["cpu_less_than"] = int(
        os.getenv("CpuLessThan") or _get_option(options, "cpu_less_than") or 50
    )
    anm_config["cpu_remove"] = int(
        os.getenv("CpuRemove") or _get_option(options, "cpu_remove") or 70
    )
    anm_config["mem_less_than"] = int(
        os.getenv("MemLessThan") or _get_option(options, "mem_less_than") or 60
    )
    anm_config["mem_remove"] = int(
        os.getenv("MemRemove") or _get_option(options, "mem_remove") or 75
    )
    anm_config["hd_less_than"] = int(
        os.getenv("HDLessThan") or _get_option(options, "hd_less_than") or 75
    )
    anm_config["hd_remove"] = int(
        os.getenv("HDRemove") or _get_option(options, "hd_remove") or 90
    )
    anm_config["delay_start"] = int(
        os.getenv("DelayStart") or _get_option(options, "delay_start") or 300
    )
    anm_config["delay_upgrade"] = int(
        os.getenv("DelayUpgrade") or _get_option(options, "delay_upgrade") or 300
    )
    anm_config["delay_restart"] = int(
        os.getenv("DelayRestart") or _get_option(options, "delay_restart") or 600
    )
    anm_config["delay_remove"] = int(
        os.getenv("DelayRemove") or _get_option(options, "delay_remove") or 300
    )
    anm_config["survey_delay"] = int(_get_option(options, "survey_delay") or 0)
    anm_config["action_delay"] = int(_get_option(options, "action_delay") or 0)
    anm_config["node_storage"] = (
        os.getenv("NodeStorage") or _get_option(options, "node_storage") or NODE_STORAGE
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
            anm_config["rewards_address"] = _get_option(options, "rewards_address")
            if not anm_config["rewards_address"]:
                logging.warning("Unable to detect RewardsAddress")
                sys.exit(1)
    anm_config["donate_address"] = (
        os.getenv("DonateAddress") or _get_option(options, "donate_address") or DONATE
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
        anm_config["port_start"] = normalize_port_start(int(re.findall(r"ntpr\=(\d+)", data)[0]))
    except (FileNotFoundError, IndexError, ValueError) as e:
        logging.debug(f"Unable to read PortStart from anms.sh: {e}")
        anm_config["port_start"] = normalize_port_start(_get_option(options, "port_start") or 55)

    anm_config["metrics_port_start"] = normalize_port_start(
        _get_option(options, "metrics_port_start") or 13
    )  # This is hardcoded in the anm.sh script

    anm_config["rpc_port_start"] = normalize_port_start(
        _get_option(options, "rpc_port_start") or 30
    )

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
    anm_config["host"] = (
        os.getenv("Host") or _get_option(options, "host") or "127.0.0.1"
    )
    anm_config["crisis_bytes"] = (
        _get_option(options, "crisis_bytes") or DEFAULT_CRISIS_BYTES
    )
    anm_config["environment"] = _get_option(options, "environment") or ""
    anm_config["start_args"] = _get_option(options, "start_args") or ""

    # Set default process manager based on platform if not specified
    if _get_option(options, "process_manager"):
        anm_config["process_manager"] = _get_option(options, "process_manager")
    elif PLATFORM == "Darwin":
        anm_config["process_manager"] = "launchd+user"
    elif PLATFORM == "Linux":
        anm_config["process_manager"] = "systemd+user"
    else:
        anm_config["process_manager"] = "systemd+user"

    # UPnP setting (defaults to True/enabled)
    anm_config["no_upnp"] = bool(_get_option(options, "no_upnp", False))

    # antnode binary path
    anm_config["antnode_path"] = (
        _get_option(options, "antnode_path") or "~/.local/bin/antnode"
    )

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


def define_machine(options):
    if not options.rewards_address:
        logging.warning("Rewards Address is required")
        return False

    # Determine donate_address that will be used for validation
    donate_address = options.donate_address or DONATE

    # Validate rewards_address format
    is_valid, error_msg = validate_rewards_address(
        options.rewards_address, donate_address
    )
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
        "node_cap": int(_get_option(options, "node_cap") or 20),
        "cpu_less_than": int(_get_option(options, "cpu_less_than") or 50),
        "cpu_remove": int(_get_option(options, "cpu_remove") or 70),
        "mem_less_than": int(_get_option(options, "mem_less_than") or 60),
        "mem_remove": int(_get_option(options, "mem_remove") or 75),
        "hd_less_than": int(_get_option(options, "hd_less_than") or 75),
        "hd_remove": int(_get_option(options, "hd_remove") or 90),
        "delay_start": int(_get_option(options, "delay_start") or 300),
        "delay_restart": int(_get_option(options, "delay_restart") or 600),
        "delay_upgrade": int(_get_option(options, "delay_upgrade") or 300),
        "delay_remove": int(_get_option(options, "delay_remove") or 300),
        "survey_delay": int(_get_option(options, "survey_delay") or 0),
        "action_delay": int(_get_option(options, "action_delay") or 0),
        "node_storage": _get_option(options, "node_storage") or NODE_STORAGE,
        "rewards_address": _get_option(options, "rewards_address"),
        "donate_address": _get_option(options, "donate_address") or FAUCET,
        "max_load_average_allowed": float(
            _get_option(options, "max_load_average_allowed") or cpucount
        ),
        "desired_load_average": float(
            _get_option(options, "desired_load_average") or cpucount * 0.6
        ),
        "port_start": normalize_port_start(_get_option(options, "port_start") or 55),
        "hdio_read_less_than": int(_get_option(options, "hdio_read_less_than") or 0),
        "hdio_read_remove": int(_get_option(options, "hdio_read_remove") or 0),
        "hdio_write_less_than": int(_get_option(options, "hdio_write_less_than") or 0),
        "hdio_write_remove": int(_get_option(options, "hdio_write_remove") or 0),
        "netio_read_less_than": int(_get_option(options, "netio_read_less_than") or 0),
        "netio_read_remove": int(_get_option(options, "netio_read_remove") or 0),
        "netio_write_less_than": int(
            _get_option(options, "netio_write_less_than") or 0
        ),
        "netio_write_remove": int(_get_option(options, "netio_write_remove") or 0),
        "last_stopped_at": 0,
        "host": _get_option(options, "host") or "127.0.0.1",
        "crisis_bytes": int(
            _get_option(options, "crisis_bytes") or DEFAULT_CRISIS_BYTES
        ),
        "metrics_port_start": normalize_port_start(_get_option(options, "metrics_port_start") or 13),
        "rpc_port_start": normalize_port_start(_get_option(options, "rpc_port_start") or 30),
        "environment": _get_option(options, "environment") or "",
        "start_args": _get_option(options, "start_args") or "",
        "max_concurrent_upgrades": int(_get_option(options, "max_concurrent_upgrades") or 1),
        "max_concurrent_starts": int(_get_option(options, "max_concurrent_starts") or 1),
        "max_concurrent_removals": int(_get_option(options, "max_concurrent_removals") or 1),
        "max_concurrent_operations": int(_get_option(options, "max_concurrent_operations") or 1),
        "node_removal_strategy": "youngest",
        "max_node_per_container": 200,
        "min_container_count": 1,
        "docker_image": "iweave/antnode:latest",
        "no_upnp": bool(_get_option(options, "no_upnp", False)),
        "antnode_path": _get_option(options, "antnode_path") or "~/.local/bin/antnode",
    }

    # Set default process manager based on platform if not specified
    if _get_option(options, "process_manager"):
        machine["process_manager"] = _get_option(options, "process_manager")
    elif PLATFORM == "Darwin":
        machine["process_manager"] = "launchd+user"
    elif PLATFORM == "Linux":
        machine["process_manager"] = "systemd+user"
    else:
        machine["process_manager"] = "systemd+user"

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

# Expand ~ and environment variables in dbpath if needed
if hasattr(options, "dbpath") and options.dbpath:
    # Handle both bare paths and sqlite:/// URLs
    if options.dbpath.startswith("sqlite:///"):
        path_part = options.dbpath[10:]
        path_part = os.path.expandvars(path_part)
        path_part = os.path.expanduser(path_part)
        options.dbpath = f"sqlite:///{path_part}"
    else:
        # If it's a bare path without sqlite:///, expand and re-add prefix
        path_part = os.path.expandvars(options.dbpath)
        path_part = os.path.expanduser(path_part)
        if not path_part.startswith("sqlite:///"):
            options.dbpath = f"sqlite:///{path_part}"
        else:
            options.dbpath = path_part

# Skip database initialization for --version, --remove_lockfile, and test mode
# These cases should work without any database or lock file checks
_SKIP_DB_INIT = (
    getattr(options, "version", False)
    or getattr(options, "remove_lockfile", False)
    or os.getenv("WNM_TEST_MODE")
)

# Setup Database engine (skip if --version, --remove_lockfile, or test mode)
if not _SKIP_DB_INIT:
    # Extract the actual file path from the database URL
    db_file_path = options.dbpath
    if db_file_path.startswith("sqlite:///"):
        db_file_path = db_file_path[10:]

    # Check if database exists
    db_exists = os.path.exists(db_file_path)

    # If database doesn't exist and we're not initializing, exit with helpful message
    if not db_exists and not getattr(options, "init", False):
        logging.error("No database found. Please initialize wnm first:")
        logging.error("  wnm --init --rewards_address YOUR_ETH_ADDRESS")
        logging.error("")
        logging.error("For more information, run: wnm --help")
        sys.exit(1)

    # Disable SQLAlchemy's echo to prevent it from reconfiguring logging
    engine = create_engine(options.dbpath, echo=False)
    # Generate ORM (this will create the database file if it doesn't exist)
    Base.metadata.create_all(engine)
    # Create a connection to the ORM
    session_factory = sessionmaker(bind=engine)
    S = scoped_session(session_factory)

    # Import migration utilities
    from wnm.db_migration import auto_stamp_new_database, check_and_warn_migrations

    # Auto-stamp new databases with current migration version
    auto_stamp_new_database(engine, options.dbpath)

    # Check for pending migrations (skip if running migration command)
    if not (
        hasattr(options, "force_action") and options.force_action == "wnm-db-migration"
    ):
        check_and_warn_migrations(engine, options.dbpath)
else:
    # Create dummy objects for --version, --remove_lockfile, or test mode
    engine = None
    S = None

# Remember if we init a new machine
did_we_init = False

# Skip machine configuration check in test mode, when using --version/--remove_lockfile, or when running migrations
if os.getenv("WNM_TEST_MODE") or _SKIP_DB_INIT or (
    hasattr(options, "force_action") and options.force_action == "wnm-db-migration"
):
    # In test mode, with --version/--remove_lockfile, or running migrations, use a minimal machine config or None
    machine_config = None
else:
    # Check if we have a defined machine
    try:
        with S() as session:
            machine_config = session.execute(select(Machine)).first()
    except Exception as e:
        # If there's an error loading the machine config (e.g., schema mismatch),
        # set to None and let the init process handle it
        logging.debug(f"Error loading machine config (may need schema upgrade): {e}")
        machine_config = None

# No machine configured
if (
    not machine_config
    and not os.getenv("WNM_TEST_MODE")
    and not _SKIP_DB_INIT
    and not (hasattr(options, "force_action") and options.force_action == "wnm-db-migration")
):
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
                        logging.error(
                            "Unable to locate record after successful migration"
                        )
                        sys.exit(1)
                    # Get Machine from Row
                    machine_config = machine_config[0]
                    did_we_init = True
                else:
                    logging.error("Failed to migrate machine from anm")
                    sys.exit(1)
            else:
                if define_machine(options):
                    with S() as session:
                        machine_config = session.execute(select(Machine)).first()
                    if not machine_config:
                        logging.error(
                            "Failed to locate record after successfully defining a machine"
                        )
                        sys.exit(1)
                    # Get Machine from Row
                    machine_config = machine_config[0]
                    did_we_init = True
                else:
                    logging.error("Failed to create machine")
                    sys.exit(1)

            # If we just initialized, set last_stopped_at to current system start time
            # This prevents the next execution from incorrectly detecting a reboot
            if did_we_init:
                from wnm.utils import get_system_start_time
                system_start = get_system_start_time()
                logging.info(f"Setting last_stopped_at to system start time: {system_start}")
                with S() as session:
                    session.query(Machine).filter(Machine.id == 1).update(
                        {"last_stopped_at": system_start}
                    )
                    session.commit()
                    # Reload machine config to reflect the update
                    machine_config = session.execute(select(Machine)).first()
                    if machine_config:
                        machine_config = machine_config[0]
    else:
        logging.error("No config found")
        sys.exit(1)
else:
    # Fail if we are trying to init a machine that is already initialized
    if options.init:
        logging.warning("Machine already initialized")
        sys.exit(1)
    # Get Machine from Row (skip in test mode, when using --version/--remove_lockfile, or when running migrations)
    if (
        not os.getenv("WNM_TEST_MODE")
        and not _SKIP_DB_INIT
        and not (hasattr(options, "force_action") and options.force_action == "wnm-db-migration")
    ):
        machine_config = machine_config[0]

# Collect the proposed changes unless we are initializing (skip in test mode or when using --version/--remove_lockfile)
config_updates = (
    merge_config_changes(options, machine_config)
    if not os.getenv("WNM_TEST_MODE") and not _SKIP_DB_INIT
    else {}
)
# Failfirst on invalid config change - only error if values are actually different
immutable_changes = []
if not did_we_init and machine_config:
    if options.port_start and normalize_port_start(options.port_start) != machine_config.port_start:
        immutable_changes.append(f"port_start (trying to change from {machine_config.port_start} to {normalize_port_start(options.port_start)})")
    if options.metrics_port_start and normalize_port_start(options.metrics_port_start) != machine_config.metrics_port_start:
        immutable_changes.append(f"metrics_port_start (trying to change from {machine_config.metrics_port_start} to {normalize_port_start(options.metrics_port_start)})")
    if options.rpc_port_start and normalize_port_start(options.rpc_port_start) != machine_config.rpc_port_start:
        immutable_changes.append(f"rpc_port_start (trying to change from {machine_config.rpc_port_start} to {normalize_port_start(options.rpc_port_start)})")
    if options.process_manager and options.process_manager != machine_config.process_manager:
        immutable_changes.append(f"process_manager (trying to change from {machine_config.process_manager} to {options.process_manager})")

if immutable_changes:
    logging.warning(
        f"Cannot change immutable settings on an active machine: {', '.join(immutable_changes)}"
    )
    sys.exit(1)


if __name__ == "__main__":
    logging.debug("Changes: " + json.dumps(config_updates))
    logging.debug(json.dumps(machine_config))
