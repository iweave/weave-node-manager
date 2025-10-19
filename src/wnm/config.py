import json
import logging
import os
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

logging.getLogger("sqlalchemy.engine.Engine").disabled = True

import wnm.utils


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
    c.add("--NodeCap", env_var="NodeCap", help="Node Capacity")
    c.add("--CpuLessThan", env_var="CpuLessThan", help="CPU Add Threshold")
    c.add("--CpuRemove", env_var="CpuRemove", help="CPU Remove Threshold")
    c.add("--MemLessThan", env_var="MemLessThan", help="Memory Add Threshold")
    c.add("--MemRemove", env_var="MemRemove", help="Memory Remove Threshold")
    c.add("--HDLessThan", env_var="HDLessThan", help="Hard Drive Add Threshold")
    c.add("--HDRemove", env_var="HDRemove", help="Hard Drive Remove Threshold")
    c.add("--DelayStart", env_var="DelayStart", help="Delay Start Timer")
    c.add("--DelayRestart", env_var="DelayRestart", help="Delay Restart Timer")
    c.add("--DelayUpgrade", env_var="DelayUpgrade", help="Delay Upgrade Timer")
    c.add("--DelayRemove", env_var="DelayRemove", help="Delay Remove Timer")
    c.add("--NodeStorage", env_var="NodeStorage", help="Node Storage Path")
    c.add("--RewardsAddress", env_var="RewardsAddress", help="Rewards Address")
    c.add("--DonateAddress", env_var="DonateAddress", help="Donate Address")
    c.add(
        "--MaxLoadAverageAllowed",
        env_var="MaxLoadAverageAllowed",
        help="Max Load Average Allowed Remove Threshold",
    )
    c.add(
        "--DesiredLoadAverage",
        env_var="DesiredLoadAverage",
        help="Desired Load Average Add Threshold",
    )
    c.add(
        "--PortStart", env_var="PortStart", help="Range to begin Node port assignment"
    )  # Only allowed during init
    c.add(
        "--MetricsPortStart",
        env_var="MetricsPortStart",
        help="Range to begin Metrics port assignment",
    )  # Only allowed during init
    c.add(
        "--HDIOReadLessThan",
        env_var="MDIOReadLessThan",
        help="Hard Drive IO Read Add Threshold",
    )
    c.add(
        "--HDIOReadRemove",
        env_var="HDIOReadRemove",
        help="Hard Drive IO Read Remove Threshold",
    )
    c.add(
        "--HDIOWriteLessThan",
        env_var="HDIOWriteLessThan",
        help="Hard Drive IO Write Add Threshold",
    )
    c.add(
        "--HDIOWriteRemove",
        env_var="HDIOWriteRemove",
        help="Hard Drive IO Write Remove Threshold",
    )
    c.add(
        "--NetIOReadLessThan",
        env_var="NetIOReadLessThan",
        help="Network IO Read Add Threshold",
    )
    c.add(
        "--NetIOReadRemove",
        env_var="NetIOReadRemove",
        help="Network IO Read Remove Threshold",
    )
    c.add(
        "--NetIOWriteLessThan",
        env_var="NetIOWriteLessThan",
        help="Network IO Write Add Threshold",
    )
    c.add(
        "--NetIOWriteRemove",
        env_var="NetIOWriteRemove",
        help="Network IO Write Remove Threshold",
    )
    c.add("--CrisisBytes", env_var="CrisisBytes", help="Crisis Bytes Threshold")
    c.add("--LastStoppedAt", env_var="LastStoppedAt", help="Last Stopped Timestamp")
    c.add("--Host", env_var="Host", help="Hostname")
    c.add(
        "--Environment", env_var="Environment", help="Environment variables for antnode"
    )
    c.add(
        "--StartArgs", env_var="StartArgs", help="Arguments to pass to antnode",
    )

    options = c.parse_known_args()[0] or []
    # Return the first result from parse_known_args, ignore unknown options
    return options


# Merge the changes from the config file with the database
def merge_config_changes(options, machine_config):
    # Collect updates
    cfg = {}
    if options.NodeCap and int(options.NodeCap) != machine_config.NodeCap:
        cfg["NodeCap"] = int(options.NodeCap)
    if options.CpuLessThan and int(options.CpuLessThan) != machine_config.CpuLessThan:
        cfg["CpuLessThan"] = int(options.CpuLessThan)
    if options.CpuRemove and int(options.CpuRemove) != machine_config.CpuRemove:
        cfg["CpuRemove"] = int(options.CpuRemove)
    if options.MemLessThan and int(options.MemLessThan) != machine_config.MemLessThan:
        cfg["MemLessThan"] = int(options.MemLessThan)
    if options.MemRemove and int(options.MemRemove) != machine_config.MemRemove:
        cfg["MemRemove"] = int(options.MemRemove)
    if options.HDLessThan and int(options.HDLessThan) != machine_config.HDLessThan:
        cfg["HDLessThan"] = int(options.HDLessThan)
    if options.HDRemove and int(options.HDRemove) != machine_config.HDRemove:
        cfg["HDRemove"] = int(options.HDRemove)
    if options.DelayStart and int(options.DelayStart) != machine_config.DelayStart:
        cfg["DelayStart"] = int(options.DelayStart)
    if (
        options.DelayRestart
        and int(options.DelayRestart) != machine_config.DelayRestart
    ):
        cfg["DelayRestart"] = int(options.DelayRestart)
    if (
        options.DelayUpgrade
        and int(options.DelayUpgrade) != machine_config.DelayUpgrade
    ):
        cfg["DelayUpgrade"] = int(options.DelayUpgrade)
    if options.DelayRemove and int(options.DelayRemove) != machine_config.DelayRemove:
        cfg["DelayRemove"] = int(options.DelayRemove)
    if options.NodeStorage and options.NodeStorage != machine_config.NodeStorage:
        cfg["NodeStorage"] = options.NodeStorage
    if (
        options.RewardsAddress
        and options.RewardsAddress != machine_config.RewardsAddress
    ):
        cfg["RewardsAddress"] = options.RewardsAddress
    if options.DonateAddress and options.DonateAddress != machine_config.DonateAddress:
        cfg["DonateAddress"] = options.DonateAddress
    if (
        options.MaxLoadAverageAllowed
        and float(options.MaxLoadAverageAllowed) != machine_config.MaxLoadAverageAllowed
    ):
        cfg["MaxLoadAverageAllowed"] = float(options.MaxLoadAverageAllowed)
    if (
        options.DesiredLoadAverage
        and float(options.DesiredLoadAverage) != machine_config.DesiredLoadAverage
    ):
        cfg["DesiredLoadAverage"] = float(options.DesiredLoadAverage)
    if options.PortStart and int(options.PortStart) != machine_config.PortStart:
        cfg["PortStart"] = int(options.PortStart)
    if (
        options.HDIOReadLessThan
        and int(options.HDIOReadLessThan) != machine_config.HDIOReadLessThan
    ):
        cfg["HDIOReadLessThan"] = int(options.HDIOReadLessThan)
    if (
        options.HDIOReadRemove
        and int(options.HDIOReadRemove) != machine_config.HDIOReadRemove
    ):
        cfg["HDIOReadRemove"] = int(options.HDIOReadRemove)
    if (
        options.HDIOWriteLessThan
        and int(options.HDIOWriteLessThan) != machine_config.HDIOWriteLessThan
    ):
        cfg["HDIOWriteLessThan"] = int(options.HDIOWriteLessThan)
    if (
        options.HDIOWriteRemove
        and int(options.HDIOWriteRemove) != machine_config.HDIOWriteRemove
    ):
        cfg["HDIOWriteRemove"] = int(options.HDIOWriteRemove)
    if (
        options.NetIOReadLessThan
        and int(options.NetIOReadLessThan) != machine_config.NetIOReadLessThan
    ):
        cfg["NetIOReadLessThan"] = int(options.NetIOReadLessThan)
    if (
        options.NetIOReadRemove
        and int(options.NetIOReadRemove) != machine_config.NetIOReadRemove
    ):
        cfg["NetIOReadRemove"] = int(options.NetIOReadRemove)
    if (
        options.NetIOWriteLessThan
        and int(options.NetIOWriteLessThan) != machine_config.NetIOWriteLessThan
    ):
        cfg["NetIOWriteLessThan"] = int(options.NetIOWriteLessThan)
    if (
        options.NetIOWriteRemove
        and int(options.NetIOWriteRemove) != machine_config.NetIOWriteRemove
    ):
        cfg["NetIOWriteRemove"] = int(options.NetIOWriteRemove)
    if options.CrisisBytes and int(options.CrisisBytes) != machine_config.CrisisBytes:
        cfg["CrisisBytes"] = int(options.CrisisBytes)
    if (
        options.MetricsPortStart
        and int(options.MetricsPortStart) != machine_config.MetricsPortStart
    ):
        cfg["MetricsPortStart"] = int(options.MetricsPortStart)
    if options.Environment and options.Environment != machine_config.Environment:
        cfg["Environment"] = options.Environment
    if options.StartArgs and options.StartArgs != machine_config.StartArgs:
        cfg["StartArgs"] = options.StartArgs

    return cfg


# Get anm configuration
def load_anm_config(options):
    anm_config = {}

    # Let's get the real count of CPU's available to this process
    anm_config["CpuCount"] = len(os.sched_getaffinity(0))

    # What can we save from /var/antctl/config
    if os.path.exists("/var/antctl/config"):
        load_dotenv("/var/antctl/config")
    anm_config["NodeCap"] = int(os.getenv("NodeCap") or options.NodeCap or 20)
    anm_config["CpuLessThan"] = int(
        os.getenv("CpuLessThan") or options.CpuLessThan or 50
    )
    anm_config["CpuRemove"] = int(os.getenv("CpuRemove") or options.CpuRemove or 70)
    anm_config["MemLessThan"] = int(
        os.getenv("MemLessThan") or options.MemLessThan or 70
    )
    anm_config["MemRemove"] = int(os.getenv("MemRemove") or options.MemRemove or 90)
    anm_config["HDLessThan"] = int(os.getenv("HDLessThan") or options.HDLessThan or 70)
    anm_config["HDRemove"] = int(os.getenv("HDRemove") or options.HDRemove or 90)
    anm_config["DelayStart"] = int(os.getenv("DelayStart") or options.DelayStart or 5)
    anm_config["DelayUpgrade"] = int(
        os.getenv("DelayUpgrade") or options.DelayUpgrade or 5
    )
    anm_config["DelayRestart"] = int(
        os.getenv("DelayRestart") or options.DelayRestart or 10
    )
    anm_config["DelayRemove"] = int(
        os.getenv("DelayRemove") or options.DelayRemove or 300
    )
    anm_config["NodeStorage"] = (
        os.getenv("NodeStorage") or options.NodeStorage or "/var/antctl/services"
    )
    # Default to the faucet donation address
    try:
        anm_config["RewardsAddress"] = re.findall(
            r"--rewards-address ([\dA-Fa-fXx]+)", os.getenv("RewardsAddress")
        )[0]
    except (IndexError, TypeError) as e:
        try:
            anm_config["RewardsAddress"] = re.findall(
                r"([\dA-Fa-fXx]+)", os.getenv("RewardsAddress")
            )[0]
        except (IndexError, TypeError) as e:
            logging.debug(f"Unable to parse RewardsAddress from env: {e}")
            anm_config["RewardsAddress"] = options.RewardsAddress
            if not anm_config["RewardsAddress"]:
                logging.warning("Unable to detect RewardsAddress")
                sys.exit(1)
    anm_config["DonateAddress"] = (
        os.getenv("DonateAddress") or options.DonateAddress or DONATE
    )
    anm_config["MaxLoadAverageAllowed"] = float(
        os.getenv("MaxLoadAverageAllowed") or anm_config["CpuCount"]
    )
    anm_config["DesiredLoadAverage"] = float(
        os.getenv("DesiredLoadAverage") or (anm_config["CpuCount"] * 0.6)
    )

    try:
        with open("/usr/bin/anms.sh", "r") as file:
            data = file.read()
        anm_config["PortStart"] = int(re.findall(r"ntpr\=(\d+)", data)[0])
    except (FileNotFoundError, IndexError, ValueError) as e:
        logging.debug(f"Unable to read PortStart from anms.sh: {e}")
        anm_config["PortStart"] = options.PortStart or 55

    anm_config["MetricsPortStart"] = (
        options.MetricsPortStart or 13
    )  # This is hardcoded in the anm.sh script

    anm_config["HDIOReadLessThan"] = int(os.getenv("HDIOReadLessThan") or 0)
    anm_config["HDIOReadRemove"] = int(os.getenv("HDIOReadRemove") or 0)
    anm_config["HDIOWriteLessThan"] = int(os.getenv("HDIOWriteLessThan") or 0)
    anm_config["HDIOWriteRemove"] = int(os.getenv("HDIOWriteRemove") or 0)
    anm_config["NetIOReadLessThan"] = int(os.getenv("NetIOReadLessThan") or 0)
    anm_config["NetIOReadRemove"] = int(os.getenv("NetIOReadRemove") or 0)
    anm_config["NetIOWriteLessThan"] = int(os.getenv("NetIOWriteLessThan") or 0)
    anm_config["NetIOWriteRemove"] = int(os.getenv("NetIOWriteRemove") or 0)
    # Timer for last stopped nodes
    anm_config["LastStoppedAt"] = 0
    anm_config["Host"] = os.getenv("Host") or options.Host or "127.0.0.1"
    anm_config["CrisisBytes"] = options.Host or DEFAULT_CRISIS_BYTES
    anm_config["Environment"] = options.Environment or ""
    anm_config["StartArgs"] = options.StartArgs or ""

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
    if not options.RewardsAddress:
        logging.warning("Rewards Address is required")
        return False
    cpucount = len(os.sched_getaffinity(0))
    machine = {
        "id": 1,
        "CpuCount": cpucount,
        "NodeCap": int(options.NodeCap) if options.NodeCap else 20,
        "CpuLessThan": int(options.CpuLessThan) if options.CpuLessThan else 50,
        "CpuRemove": int(options.CpuRemove) if options.CpuRemove else 70,
        "MemLessThan": int(options.MemLessThan) if options.MemLessThan else 70,
        "MemRemove": int(options.MemRemove) if options.MemRemove else 90,
        "HDLessThan": int(options.HDLessThan) if options.HDLessThan else 70,
        "HDRemove": int(options.HDRemove) if options.HDRemove else 90,
        "DelayStart": int(options.DelayStart) if options.DelayStart else 5,
        "DelayUpgrade": int(options.DelayUpgrade) if options.DelayUpgrade else 5,
        "DelayRemove": int(options.DelayRemove) if options.DelayRemove else 5,
        "NodeStorage": options.NodeStorage or "/var/antctl/services",
        "RewardsAddress": options.RewardsAddress,
        "DonateAddress": options.DonateAddress
        or "0x00455d78f850b0358E8cea5be24d415E01E107CF",
        "MaxLoadAverageAllowed": (
            float(options.MaxLoadAverageAllowed)
            if options.MaxLoadAverageAllowed
            else cpucount
        ),
        "DesiredLoadAverage": (
            float(options.DesiredLoadAverage)
            if options.DesiredLoadAverage
            else cpucount * 0.6
        ),
        "PortStart": int(options.PortStart) if options.PortStart else 55,
        "HDIOReadLessThan": (
            int(options.HDIOReadLessThan) if options.HDIOReadLessThan else 0
        ),
        "HDIOReadRemove": int(options.HDIOReadRemove) if options.HDIOReadRemove else 0,
        "HDIOWriteLessThan": (
            int(options.HDIOWriteLessThan) if options.HDIOWriteLessThan else 0
        ),
        "HDIOWriteRemove": (
            int(options.HDIOWriteRemove) if options.HDIOWriteRemove else 0
        ),
        "NetIOReadLessThan": (
            int(options.NetIOReadLessThan) if options.NetIOReadLessThan else 0
        ),
        "NetIOReadRemove": (
            int(options.NetIOReadRemove) if options.NetIOReadRemove else 0
        ),
        "NetIOWriteLessThan": (
            int(options.NetIOWriteLessThan) if options.NetIOWriteLessThan else 0
        ),
        "NetIOWriteRemove": (
            int(options.NetIOWriteRemove) if options.NetIOWriteRemove else 0
        ),
        "LastStoppedAt": 0,
        "Host": options.Host or "127.0.0.1",
        "CrisisBytes": int(options.CrisisBytes) if options.CrisisBytes else DEFAULT_CRISIS_BYTES,
        "MetricsPortStart": (
            int(options.MetricsPortStart) if options.MetricsPortStart else 13
        ),
        "Environment": options.Environment if options.Environment else "",
        "StartArgs": options.StartArgs if options.StartArgs else "",
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

# Check if we have a defined machine
with S() as session:
    machine_config = session.execute(select(Machine)).first()

# No machine configured
if not machine_config:
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
    # Get Machine from Row
    machine_config = machine_config[0]

# Collect the proposed changes unless we are initializing
config_updates = merge_config_changes(options, machine_config)
# Failfirst on invalid config change
if (
    "PortStart" in config_updates or "MetricsPortStart" in config_updates
) and not did_we_init:
    logging.warning("Can not change start port numbers on an active machine")
    sys.exit(1)


if __name__ == "__main__":
    print("Changes:", json.loads(json.dumps(config_updates)))
    print(json.loads(json.dumps(machine_config)))
