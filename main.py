import os, sys
import re, json
from dotenv import load_dotenv

# import .env
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# if WNM_CONFIG or -c parameter are set, check for existing config
# else:

# Detect ANM (but don't upgrade)
if os.path.exists("/var/antctl/system"):
    # Is anm scheduled to run
    if os.path.exists("/etc/cron.d/anm"):
        # remove cron to disable old anm
        pass
        #os.path.remove("/etc/cron.d/anm"):
    # Is anm sitll running? We'll wait
    if False and os.path.exists("/var/antctl/block"):
        print("anm still running, waiting...")
        sys.exit(1)

# Are we already running
if os.path.exists("/var/antctl/wnm_active"):
    print("wnm still running")
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
        details['antnode']=int(re.findall("antnode(\d+)",antnode)[0])
        details['binary']=re.findall(r"ExecStart=([^ ]+)",data)[0]
        details["user"]=re.findall("User=(\w+)",data)[0]
        details["rootdir"]=re.findall(r"--root-dir ([\w\/]+)",data)[0]
        details["port"]=int(re.findall("--port (\d+)",data)[0])
        details["metrics"]=int(re.findall("--metrics-server-port (\d+)",data)[0])
        details["wallet"]=re.findall(r"--rewards-address ([^ ]+)",data)[0]
        details["network"]=re.findall(r"--rewards-address [^ ]+ ([\w\-]+)",data)[0]
    except:
        return []
    
    return details

# Read data from metrics port
def read_node_metrics(node):
    pass

# Survey nodes by reading metrics ports or binary --version
def survey_nodes(antnodes):
    # Iterate on nodes
    for node in antnodes:
        # Read port
        metrics = read_node_metrics(node)
        # Else run binary to get version

# Survey instance
def survey_instance():
    # Make a bucket
    antnodes=[]
    # For all service files
    for file in os.listdir("/etc/systemd/system"):
        # Find antnodes
        if re.match('antnode\d+\.service',file):
            antnodes.append(file)
    # Iterate over nodes and get initial details
    #for antnode in antnodes:
    #    details = read_systemd_service(antnode)
    antnodes=read_systemd_service(antnodes[0])
    survey_nodes(antnodes)
    return antnodes


anm_config = load_anm_config()
counter = survey_instance() or []


print(json.dumps(anm_config,indent=4))
print("Found {counter} nodes configured".format(counter=len(counter)))
print("details",counter)
print("End of program")