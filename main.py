import os, sys
import re, json, requests, time
import subprocess, logging
from collections import Counter
from packaging.version import Version
from dotenv import load_dotenv

# Turn a class into a storable object with ORM
from typing import Optional
from sqlalchemy import Integer, Unicode, UnicodeText
from sqlalchemy import create_engine, select, insert, update
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column

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

# create a Base class bound to sqlalchemy
class Base(DeclarativeBase):
    pass

# Extend the Base class to create our Node info
class Node(Base):
    __tablename__ = 'node'
    # No schema in sqlite3
    #__table_args__ = {"schema": "colony"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nodename: Mapped[str] = mapped_column(Unicode(10))
    service: Mapped[str] = mapped_column(UnicodeText)
    user: Mapped[str] = mapped_column(Unicode(24))
    binary: Mapped[str] = mapped_column(UnicodeText)
    version: Mapped[Optional[str]] = mapped_column(UnicodeText)
    root_dir: Mapped[str] = mapped_column(UnicodeText)
    port: Mapped[int] = mapped_column(Integer)
    metrics_port: Mapped[int] = mapped_column(Integer)
    network: Mapped[str] = mapped_column(UnicodeText)
    wallet: Mapped[Optional[str]] = mapped_column(Unicode(42),index=True)
    peer_id: Mapped[str] = mapped_column(Unicode(52))
    status: Mapped[str] = mapped_column(Unicode(32),index=True)
    timestamp: Mapped[int] = mapped_column(Integer,index=True)

    def __init__(self, id, nodename, service, user, binary, version, 
                 root_dir, port, metrics_port, network,
                 wallet, peer_id, status, timestamp):
        self.id = id
        self.nodename = nodename
        self.service = service
        self.user = user
        self.binary = binary
        self.version = version
        self.root_dir = root_dir
        self.port = port
        self.metrics_port = metrics_port
        self.network = network
        self.wallet = wallet
        self.peer_id = peer_id
        self.status = status
        self.timestamp = timestamp

    def __repr__(self):
        return f'Node({self.id},"{self.nodename}","{self.service}","{self.user},"{self.binary}"'+\
            f',"{self.version}","{self.root_dir}",{self.port},{self.metrics_port}' + \
            f',"{self.network}","{self.wallet}","{self.peer_id}","{self.status}",{self.timestamp})'


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
    anm_config["NodeCap"] = os.getenv('NodeCap') or 20
    anm_config["CpuLessThan"] = os.getenv('CpuLessThan') or 50
    anm_config["CpuRemove"] = os.getenv('CpuRemove') or 70
    anm_config["MemLessThan"] = os.getenv('MemLessThan') or 70
    anm_config["MemRemove"] = os.getenv('MemRemove') or 90
    anm_config["HDLessThan"] = os.getenv('HDLessThan') or 70
    anm_config["HDRemove"] = os.getenv('HDRemove') or 90
    anm_config["DelayStart"] = os.getenv('DelayStart') or 5
    anm_config["DelayUpgrade"] = os.getenv('DelayUpgrade') or 5
    anm_config["NodeStorage"] = os.getenv('NodeStorage') or "/var/antctl/services"
    # Default to the faucet donation address
    try:
        anm_config["RewardsAddress"] = re.findall(r"--rewards-address ([\dA-Fa-fXx]+)",os.getenv('RewardsAddress'))[0] or DONATE
    except:
        anm_config["RewardsAddress"] = DONATE

    anm_config["MaxLoadAverageAllowed"]=os.getenv("MaxLoadAverageAllowed") or anm_config["CpuCount"]
    anm_config["DesiredLoadAverage"]=os.getenv("DesiredLoadAverage") or (anm_config["CpuCount"] * .6)

    try:
        with open('/usr/bin/anms.sh', 'r') as file:
            data = file.read()
        anm_config["PortStart"]=int((re.findall(r"ntpr\=(\d+)",data) or [50])[0])
    except:
        pass
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
def read_node_metadata(port):
    try:
        url = "http://127.0.0.1:{0}/metadata".format(port)
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
def read_node_metrics(port):
    try:
        url = "http://127.0.0.1:{0}/metrics".format(port)
        response = requests.get(url)
        return {"status": RUNNING or response.text}
    except Exception as error:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return {"status": STOPPED}
    

# Survey nodes by reading metrics ports or binary --version
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
              "timestamp": int(time.time())
              }
        # Load what systemd has configured
        card.update(read_systemd_service(node))
        #print(json.dumps(card,indent=2))
        # Read metadata from metrics_port
        metrics = read_node_metadata(card["metrics_port"])
        #print(json.dumps(metrics,indent=2))
        if  isinstance(metrics,dict) and \
            "status" in metrics and \
            metrics["status"]==RUNNING:
            # soak up metrics
            card.update(metrics)
        # Else run binary to get version
        else:
            card["status"]=STOPPED
            card["peer_id"]=""
            try:
                data = subprocess.run([card["binary"], '--version'], stdout=subprocess.PIPE).stdout.decode('utf-8')
                card["version"]=re.findall(r'Autonomi Node v([\d\.]+)',data)[0]
            except Exception as error:
                template = "An exception of type {0} occurred. Arguments:\n{1!r}"
                message = template.format(type(error).__name__, error.args)
                logging.info(message)
                card["version"]="0"
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
    db_nodes=session.execute(select(Node.status,Node.version)).all()
if db_nodes:
    anm_config = load_anm_config()
    print(json.dumps(anm_config,indent=4))
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
    Workers = survey_machine() or []

    #""""
    with S() as session:
        session.execute(
            insert(Node),Workers
        )
        session.commit()
    #"""

    """
    for worker in Workers:
        card = Node(
            id=worker["id"],
            nodename = worker["nodename"],
            service = worker["service"],
            user = worker["user"],
            binary = worker["binary"],
            version = worker["version"],
            root_dir = worker["root_dir"],
            port = worker["port"],
            metrics_port = worker["metrics_port"],
            network = worker["network"],
            wallet = worker["wallet"],
            peer_id = worker["peer_id"],
            status = worker["status"],
            timestamp = worker["timestamp"],
        )
        with S() as session:
            session.add(card)
            session.commit()
    """

    print(json.dumps(anm_config,indent=4))
    print("Found {counter} nodes configured".format(counter=len(Workers)))
    data = Counter(node['status'] for node in Workers)
    print("Running Nodes:",data[RUNNING])
    print("Stopped Nodes:",data[STOPPED])
    versions = [v[1] for worker in Workers if (v := worker.get('version'))]
    data = Counter(ver for ver in versions)
    print("Versions:",data)

print("End of program")