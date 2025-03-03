import os, sys
import re, json, requests, time
import subprocess, logging
from collections import Counter
from packaging.version import Version
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# import .env
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# if WNM_CONFIG or -c parameter are set, check for existing config
# else:
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
    if os.path.exists("/var/antctl/block"):
        logging.info("anm still running, waiting...")
        sys.exit(1)

# Are we already running
if os.path.exists("/var/antctl/wnm_active"):
    logging.info("wnm still running")
    sys.exit(1)

# Get configuration
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
    anm_config["RewardsAddress"] = re.findall("--rewards-address (.*)",os.getenv('RewardsAddress'))[0] or '0x270A246bcdD03A4A70dc81C330586882a6ceDF8f'
    anm_config["MaxLoadAverageAllowed"]=os.getenv("MaxLoadAverageAllowed") or anm_config["CpuCount"]
    anm_config["DesiredLoadAverage"]=os.getenv("DesiredLoadAverage") or (anm_config["CpuCount"] * .6)

    # NodeCap
    # sudo sed -i 's/ntpr=55/ntpr='$PortRange'/g' /usr/bin/anms.sh
    # sudo sed -i 's,/var/antctl/services,'$NodeStorage',g' /usr/bin/anms.sh
    return anm_config

# Read confirm from systemd service file
def read_systemd_service(antnode):
    details={}
    try:
        with open('/etc/systemd/system/'+antnode, 'r') as file:
            data = file.read()
        details['antnode']=int(re.findall(r"antnode(\d+)",antnode)[0])
        details['binary']=re.findall(r"ExecStart=([^ ]+)",data)[0]
        details["user"]=re.findall(r"User=(\w+)",data)[0]
        details["rootdir"]=re.findall(r"--root-dir ([\w\/]+)",data)[0]
        details["port"]=int(re.findall(r"--port (\d+)",data)[0])
        details["metrics_port"]=int(re.findall(r"--metrics-server-port (\d+)",data)[0])
        details["wallet"]=re.findall(r"--rewards-address ([^ ]+)",data)[0]
        details["network"]=re.findall(r"--rewards-address [^ ]+ ([\w\-]+)",data)[0]
    except:
        return []
    
    return details

# Read data from metadata endpoint
def read_node_metadata(port):
    try:
        url = "http://127.0.0.1:{0}/metadata".format(port)
        response = requests.get(url)
        data=response.text
    except Exception as error:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return {"status": STOPPED}
    # collect a dict to return
    card={}
    try:
        card["version"] = re.findall(r'{antnode_version="([\d\.]+)"}',data)[0]
        card["peer_id"] = re.findall(r'{peer_id="([\w\d]+)"}',data)[0]
    except:
        pass
    card["status"] = RUNNING
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
            try:
                data = subprocess.run([card["binary"], '--version'], stdout=subprocess.PIPE).stdout.decode('utf-8')
                card["version"]=re.findall(r'Autonomi Node v([\d\.]+)',data)[0]
            except Exception as error:
                template = "An exception of type {0} occurred. Arguments:\n{1!r}"
                message = template.format(type(error).__name__, error.args)
                logging.info(message)
                card["version"]="--"
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
    antnodes=survey_nodes(antnodes)
    return antnodes


anm_config = load_anm_config()
Workers = survey_machine() or []


print(json.dumps(anm_config,indent=4))
print("Found {counter} nodes configured".format(counter=len(Workers)))
data = Counter(node['status'] for node in Workers)
print("Running Nodes:",data[RUNNING])
print("Stopped Nodes:",data[STOPPED])
versions = [v for worker in Workers if (v := worker.get('version'))]
data = Counter(ver for ver in versions)
print(data)
#print("details",counter)
print("End of program")