import os, sys
import re, json, requests, time
import subprocess, logging
from collections import Counter
from packaging.version import Version
from dotenv import load_dotenv
import psutil, shutil, platform

from models import Base, Machine, Node
from sqlalchemy import create_engine, select, insert, update
from sqlalchemy.orm import sessionmaker, scoped_session

logging.basicConfig(level=logging.INFO)
#Info level logging for sqlalchemy is too verbose, only use when needed
logging.getLogger('sqlalchemy.engine.Engine').disabled = True
        
# import .env
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# simulate arg/yaml configuration
config = {}
config['db']='sqlite:///colony.db'
config['DonateAddress'] = os.getenv('DonateAddress') or '0x270A246bcdD03A4A70dc81C330586882a6ceDF8f'
config['ANMHost'] = os.getenv('ANMHost') or '127.0.0.1'
config['CrisisBytes'] = os.getenv('CrisisBytes') or 2 * 10 ** 9 # default 2gb/node


# Setup Database engine
engine = create_engine(config["db"], echo=True)

# Generate ORM
Base.metadata.create_all(engine)

# Create a connection to the ORM
session_factory = sessionmaker(bind=engine)
S = scoped_session(session_factory)


# if WNM_CONFIG or -c parameter are set, check for existing config
# else:

# Primary node for want of one
QUEEN=1

# Donation address
DONATE=config["DonateAddress"]
#Keep these as strings so they can be grepped in logs
STOPPED="STOPPED" #0 Node is not responding to it's metrics port
RUNNING="RUNNING" #1 Node is responding to it's metrics port
UPGRADING="UPGRADING" #2 Upgrade in progress
DISABLED="DISABLED" #-1 Do not start
RESTARTING="RESTARTING" #3 re/starting a server intionally
MIGRATING="MIGRATING" #4 Moving volumes in progress

ANM_HOST=config["ANMHost"]
# Baseline bytes per node
CRISIS_BYTES=config["CrisisBytes"]

# A storage place for ant node data
Workers=[]

# Detect ANM (but don't upgrade)
if os.path.exists("/var/antctl/system"):
    # Is anm scheduled to run
    if os.path.exists("/etc/cron.d/anm"):
        # remove cron to disable old anm
        pass
        #os.path.remove("/etc/cron.d/anm"):
    # Is anm sitll running? We'll wait
    if False and os.path.exists("/var/antctl/block"):
        logging.info("anm still running, waiting...")
        sys.exit(1)

# Are we already running
if os.path.exists("/var/antctl/wnm_active"):
    logging.info("wnm still running")
    sys.exit(1)

# Get anm configuration
def load_anm_config():
    anm_config = {}

    # Let's get the real count of CPU's available to this process
    anm_config["CpuCount"] = len(os.sched_getaffinity(0))

    # What can we save from /var/antctl/config
    if os.path.exists("/var/antctl/config"):
        load_dotenv("/var/antctl/config")
    anm_config["NodeCap"] = int(os.getenv('NodeCap') or 20)
    anm_config["CpuLessThan"] = int(os.getenv('CpuLessThan') or 50)
    anm_config["CpuRemove"] = int(os.getenv('CpuRemove') or 70)
    anm_config["MemLessThan"] = int(os.getenv('MemLessThan') or 70)
    anm_config["MemRemove"] = int(os.getenv('MemRemove') or 90)
    anm_config["HDLessThan"] = int(os.getenv('HDLessThan') or 70)
    anm_config["HDRemove"] = int(os.getenv('HDRemove') or 90)
    anm_config["DelayStart"] = int(os.getenv('DelayStart') or 5)
    anm_config["DelayUpgrade"] = int(os.getenv('DelayUpgrade') or 5)
    anm_config["NodeStorage"] = os.getenv('NodeStorage') or "/var/antctl/services"
    # Default to the faucet donation address
    try:
        anm_config["RewardsAddress"] = re.findall(r"--rewards-address ([\dA-Fa-fXx]+)",os.getenv('RewardsAddress'))[0]
    except:
        logging.warning("Unable to detect RewardsAddress, defaulting to Community Faucet wallet: "+DONATE)
        anm_config["RewardsAddress"] = DONATE
    anm_config["DonateAddress"]=os.getenv("DonateAddress") or DONATE
    anm_config["MaxLoadAverageAllowed"]=float(os.getenv("MaxLoadAverageAllowed") or anm_config["CpuCount"])
    anm_config["DesiredLoadAverage"]=float(os.getenv("DesiredLoadAverage") or (anm_config["CpuCount"] * .6))

    try:
        with open('/usr/bin/anms.sh', 'r') as file:
            data = file.read()
        anm_config["PortStart"]=int(re.findall(r"ntpr\=(\d+)",data)[0])
    except:
        anm_config["PortStart"]=55

    anm_config["HDIOReadLessThan"] = float(os.getenv('HDIOReadLessThan') or 0.0)
    anm_config["HDIOReadRemove"] = float(os.getenv('HDIOReadRemove') or 0.0)
    anm_config["HDIOWriteLessThan"] = float(os.getenv('HDIOWriteLessThan') or 0.0)
    anm_config["HDIOWriteRemove"] = float(os.getenv('HDIOWriteRemove') or 0.0)
    anm_config["NetIOReadLessThan"] = float(os.getenv('NetIOReadLessThan') or 0.0)
    anm_config["NetIOReadRemove"] = float(os.getenv('NetIOReadRemove') or 0.0)
    anm_config["NetIOWriteLessThan"] = float(os.getenv('NetIOWriteLessThan') or 0.0)
    anm_config["NetIOWriteRemove"] = float(os.getenv('NetIOWriteRemove') or 0.0)


    return anm_config

# Read confirm from systemd service file
def read_systemd_service(antnode):
    details={}
    try:
        with open('/etc/systemd/system/'+antnode, 'r') as file:
            data = file.read()
        details['id']=int(re.findall(r"antnode(\d+)",antnode)[0])
        details['binary']=re.findall(r"ExecStart=([^ ]+)",data)[0]
        details["user"]=re.findall(r"User=(\w+)",data)[0]
        details["root_dir"]=re.findall(r"--root-dir ([\w\/]+)",data)[0]
        details["port"]=int(re.findall(r"--port (\d+)",data)[0])
        details["metrics_port"]=int(re.findall(r"--metrics-server-port (\d+)",data)[0])
        details["wallet"]=re.findall(r"--rewards-address ([^ ]+)",data)[0]
        details["network"]=re.findall(r"--rewards-address [^ ]+ ([\w\-]+)",data)[0]
    except:
        pass
    
    return details

# Read data from metadata endpoint
def read_node_metadata(host,port):
    try:
        url = "http://{0}:{1}/metadata".format(host,port)
        response = requests.get(url)
        data=response.text
    except requests.exceptions.ConnectionError:
        logging.debug("Connection Refused on port: {0}:{1}".format(host,str(port)))
        return {"status": STOPPED, "version": "", "peer_id":""}
    except Exception as error:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return {"status": STOPPED, "version": "", "peer_id":""}
    # collect a dict to return
    card={}
    try:
        card["version"] = re.findall(r'{antnode_version="([\d\.]+)"}',data)[0]
    except:
        card["version"] = ""
    try:
        card["peer_id"] = re.findall(r'{peer_id="([\w\d]+)"}',data)[0]
    except:
        card["peer_id"] = ""
    card["status"] = RUNNING if card["version"] else STOPPED
    return card

# Read data from metrics port
def read_node_metrics(host,port):
    metrics={}
    try:
        url = "http://{0}:{1}/metrics".format(host,port)
        response = requests.get(url)
        metrics["status"] = RUNNING
        metrics["uptime"] = int((re.findall(r'ant_node_uptime ([\d]+)',response.text) or [0])[0])
        metrics["records"] = int((re.findall(r'ant_networking_records_stored ([\d]+)',response.text) or [0])[0])
        metrics["shunned"] = int((re.findall(r'ant_networking_shunned_by_close_group ([\d]+)',response.text) or [0])[0])
    except Exception as error:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
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
        data = subprocess.run([binary, '--version'], stdout=subprocess.PIPE).stdout.decode('utf-8')
        return re.findall(r'Autonomi Node v([\d\.]+)',data)[0]
    except Exception as error:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return 0
    
# Determine how long this node has been around by looking at it's secret_key file
def get_node_age(root_dir):
    try:
        return int(os.stat("{0}/secret-key".format(root_dir)).st_mtime)
    except:
        return 0
    
# Survey nodes by reading metadata from metrics ports or binary --version
def survey_anm_nodes(antnodes):
    # Build a list of node dictionaries to return
    details=[]
    # Iterate on nodes
    for node in antnodes:
        # Initialize a dict
        logging.debug("{0} surveying node {1} ".format(time.strftime("%Y-%m-%d %H:%M"),node))
        if not re.findall(r"antnode([\d]+).service",node):
            logging.info("can't decode "+str(node))
            continue
        card={"nodename":re.findall(r"antnode([\d]+).service",node)[0],
              "service": node,
              "timestamp": int(time.time()),
              "host": ANM_HOST or '127.0.0.1'
              }
        # Load what systemd has configured
        card.update(read_systemd_service(node))
        #print(json.dumps(card,indent=2))
        # Read metadata from metrics_port
        metadata = read_node_metadata(card["host"],card["metrics_port"])
        #print(json.dumps(metadata,indent=2))
        if  isinstance(metadata,dict) and \
            "status" in metadata and \
            metadata["status"]==RUNNING:
            # soak up metadata
            card.update(metadata)
            card.update(read_node_metrics(card["host"],card["metrics_port"]))
        # Else run binary to get version
        else:
            card["status"]=STOPPED
            card["peer_id"]=""
            card["version"]=get_antnode_version(card["binary"])
            card["records"]=0
            card["uptime"]=0
            card["shunned"]=0
        card["age"]=get_node_age(card["root_dir"])
        # harcoded for anm
        card["host"]=ANM_HOST
        # Append the node dict to the detail list
        details.append(card)
    
    return details

# Survey server instance
def survey_machine():
    # Make a bucket
    antnodes=[]
    # For all service files
    for file in os.listdir("/etc/systemd/system"):
        # Find antnodes
        if re.match(r'antnode[\d]+\.service',file):
            antnodes.append(file)
        #if len(antnodes)>=5:
        #   break
    # Iterate over defined nodes and get details
    # Ingests a list of service files and outputs a list of dictionaries
    return survey_anm_nodes(antnodes)

# Read system status
def get_machine_metrics(node_storage,remove_limit):
    metrics = {}

    with S() as session:
        db_nodes=session.execute(select(Node.status)).all()
    
    # Get some initial stats for comparing after a few seconds
    # We start these counters AFTER reading the database
    start_time=time.time()
    start_disk_counters=psutil.disk_io_counters()
    start_net_counters=psutil.net_io_counters()

    metrics["TotalNodes"]=len(db_nodes)
    data = Counter(node[0] for node in db_nodes)
    metrics["RunningNodes"] = data[RUNNING]
    metrics["StoppedNodes"] = data[STOPPED]
    metrics["RestaringNodes"] = data[RESTARTING]
    metrics["UpgradingNodes"] = data[UPGRADING]
    metrics["MigratingNodes"] = data[MIGRATING]
    metrics["antnode"]=shutil.which("antnode")
    if not metrics["antnode"]:
        logging.warning("Unable to locate current antnode binary, exiting")
        sys.exit(1)
    metrics["NodesLatestV"]=get_antnode_version(metrics["antnode"])
    # Windows has to build load average over 5 seconds. The first 5 seconds returns 0's
    # I don't plan on supporting windows, but if this get's modular, I don't want this 
    # issue to be skipped
    if platform.system() == "Windows":
        discard=psutil.getloadavg()
        time.sleep(5)
    metrics["LoadAverage1"],metrics["LoadAverage5"],metrics["LoadAverage15"]=psutil.getloadavg()
    # Get CPU Metrics over 1 second
    metrics["UsedCpuPercent"],metrics["IOWait"] = psutil.cpu_times_percent(1)[3:5]
    # Really we returned Idle percent, subtract from 100 to get used.
    metrics["UsedCpuPercent"] = 100 - metrics["UsedCpuPercent"]
    data=psutil.virtual_memory()
    #print(data)
    metrics["FreeMemPercent"]=data.percent
    metrics["UsedMemPercent"]=100-metrics["FreeMemPercent"]
    data=psutil.disk_io_counters()
    # This only checks the drive mapped to the first node and will need to be updated
    # when we eventually support multiple drives
    data=psutil.disk_usage(node_storage)
    metrics["UsedHDPercent"]=data.percent
    metrics["TotalHDBytes"]=data.total
    end_time=time.time()
    end_disk_counters=psutil.disk_io_counters()
    end_net_counters=psutil.net_io_counters()
    metrics["HDWriteBytes"]=int((end_disk_counters.write_bytes-start_disk_counters.write_bytes)/(end_time-start_time))
    metrics["HDReadBytes"]=int((end_disk_counters.read_bytes-start_disk_counters.read_bytes)/(end_time-start_time))
    metrics["NetWriteBytes"]=int((end_net_counters.bytes_sent-start_net_counters.bytes_sent)/(end_time-start_time))
    metrics["NetReadBytes"]=int((end_net_counters.bytes_recv-start_net_counters.bytes_recv)/(end_time-start_time))
    #print (json.dumps(metrics,indent=2))
    # How close (out of 100) to removal limit will we be with a max bytes per node (2GB default)
    # For running nodes with Porpoise(tm).
    metrics["NodeHDCrisis"]=int((((metrics["TotalNodes"])*CRISIS_BYTES)/(metrics["TotalHDBytes"]*(remove_limit/100)))*100)
    return metrics

# Make a decision about what to do
def choose_action(config,metrics):
    # Gather knowlege
    features={}
    features["AllowCpu"]=metrics["UsedCpuPercent"] < config["CpuLessThan"]
    features["AllowMem"]=metrics["UsedMemPercent"] < config["MemLessThan"]
    features["AllowHD"]=metrics["UsedHDPercent"] < config["HDLessThan"]
    features["RemCpu"]=metrics["UsedCpuPercent"] > config["CpuRemove"]
    features["RemMem"]=metrics["UsedMemPercent"] > config["MemRemove"]
    features["RemHD"]=metrics["UsedHDPercent"] > config["HDRemove"]
    features["AllowNodeCap"]=metrics["TotalNodes"] < config["NodeCap"]
    if (config["NetIOReadLessThan"]+config["NetIOReadRemove"]+
        config["NetIOWriteLessThan"]+config["NetIOWriteRemove"]>1):
        features["AllowNetIO"]=metrics["NetReadBytes"] < config["NetIOReadLessThan"] and \
                              metrics["NetWriteBytes"] < config["NetIOWriteLessThan"]
        features["RemoveNetIO"]=metrics["NetReadBytes"] > config["NetIORemoveThan"] or \
                              metrics["NetWriteBytes"] > config["NetIORemoveThan"]
    else:
        features["AllowNetIO"]=1
        features["RemoveNetIO"]=0
    if (config["HDIOReadLessThan"]+config["HDIOReadRemove"]+
        config["HDIOWriteLessThan"]+config["HDIOWriteRemove"]>1):
        features["AllowHDIO"]=metrics["HDReadBytes"] < config["HDIOReadLessThan"] and \
                              metrics["HDWriteBytes"] < config["HDIOWriteLessThan"]
        features["RemoveHDIO"]=metrics["HDReadBytes"] > config["HDIORemoveThan"] or \
                              metrics["HDWriteBytes"] > config["HDtIORemoveThan"]
    else:
        features["AllowHDIO"]=1
        features["RemoveHDIO"]=0
    # Decisions




# See if we already have a known state in the database
with S() as session:
    db_nodes=session.execute(select(Node.status,Node.version,Node.host,Node.metrics_port)).all()
    anm_config=session.execute(select(Machine)).all()

if db_nodes:
    # anm_config by default loads a parameter array, 
    # use the __json__ method to return a dict from the first node
    anm_config = json.loads(json.dumps(anm_config[0][0])) or load_anm_config()
    metrics=get_machine_metrics(anm_config["NodeStorage"],anm_config["HDRemove"])
    node_metrics = read_node_metrics(db_nodes[0][2],db_nodes[0][3])
    print(db_nodes[0])
    print(node_metrics)
    #print(anm_config)
    #print(json.dumps(anm_config,indent=4))
    #print("Node: ",db_nodes)
    print("Found {counter} nodes migrated".format(counter=len(db_nodes)))
    data = Counter(status[0] for status in db_nodes)
    #print(data)
    print("Running Nodes:",data[RUNNING])
    print("Stopped Nodes:",data[STOPPED])
    print("Upgrading Nodes:",data[UPGRADING])
    data = Counter(ver[1] for ver in db_nodes)
    print("Versions:",data)
else:
    anm_config = load_anm_config()
    #print(anm_config)
    Workers = survey_machine() or []

    #""""
    with S() as session:
        session.execute(
            insert(Node),Workers
        )
        session.commit()
    #"""

    with S() as session:
        session.execute(
            insert(Machine),[anm_config]
        )
        session.commit()


    #print(json.dumps(anm_config,indent=4))
    print("Found {counter} nodes configured".format(counter=len(Workers)))
    data = Counter(node['status'] for node in Workers)
    print("Running Nodes:",data[RUNNING])
    print("Stopped Nodes:",data[STOPPED])
    print("Upgrading Nodes:",data[UPGRADING])
    versions = [v[1] for worker in Workers if (v := worker.get('version'))]
    data = Counter(ver for ver in versions)
    print("Versions:",data)

machine_metrics = get_machine_metrics(anm_config['NodeStorage'],anm_config["HDRemove"])
print(json.dumps(machine_metrics,indent=2))
next_action=choose_action(anm_config,machine_metrics)
print("End of program")