import os, sys
import re, json, requests, time
import subprocess, logging
from collections import Counter
from packaging.version import Version
from dotenv import load_dotenv

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
STOPPED="STOPPED" #0
RUNNING="RUNNING" #1
UPGRADING="UPGRADING" #2
DISABLED="DISABLED" #-1
RESTARTING="RESTARTING" #3

ANM_HOST=config["ANMHost"]

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
        logging.debug("Connection Refused on port: "+str(port))
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
    except Exception as error:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        metrics["status"] = STOPPED
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
    
# Survey nodes by reading metadata from metrics ports or binary --version
def survey_nodes(antnodes):
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
    return survey_nodes(antnodes)


# See if we already have a known state in the database
with S() as session:
    db_nodes=session.execute(select(Node.status,Node.version,Node.host,Node.metrics_port)).all()
    anm_config=session.execute(select(Machine)).all()

if db_nodes:
    anm_config = anm_config[0][0] or load_anm_config()
    node_metrics = read_node_metrics(db_nodes[0][2],db_nodes[0][3])
    print(node_metrics)
    #print(anm_config)
    #print(json.dumps(anm_config,indent=4))
    #print("Node: ",db_nodes)
    print("Found {counter} nodes migrated".format(counter=len(db_nodes)))
    data = Counter(status[0] for status in db_nodes)
    #print(data)
    print("Running Nodes:",data[RUNNING])
    print("Stopped Nodes:",data[STOPPED])
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
    versions = [v[1] for worker in Workers if (v := worker.get('version'))]
    data = Counter(ver for ver in versions)
    print("Versions:",data)

print("End of program")