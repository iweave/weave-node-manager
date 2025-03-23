import os, sys
import re, json, requests, time
import subprocess, logging
from collections import Counter
from packaging.version import Version
from dotenv import load_dotenv
import psutil, shutil

from wnm.models import Base, Machine, Node
from sqlalchemy import create_engine, select, insert, update, delete, text
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
config['DonateAddress'] = os.getenv('DonateAddress') or '0x00455d78f850b0358E8cea5be24d415E01E107CF'
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
REMOVING="REMOVING" #5 Removing node in progress
DEAD="DEAD" #-86 Broken node to cleanup

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
        try:
            subprocess.run(['sudo','rm', '/etc/cron.d/anm'])
        except Exception as error:
            template = "In GAV - An exception of type {0} occurred. Arguments:\n{1!r}"
            message = template.format(type(error).__name__, error.args)
            logging.info(message)
            sys.exit(1)
        os.remove("/etc/cron.d/anm")
    # Is anm sitll running? We'll wait
    if os.path.exists("/var/antctl/block"):
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
    anm_config["DelayRestart"] = int(os.getenv('DelayRestart') or 10)
    anm_config["DelayRemove"] = int(os.getenv('DelayRemove') or 300)
    anm_config["NodeStorage"] = os.getenv('NodeStorage') or "/var/antctl/services"
    # Default to the faucet donation address
    try:
        anm_config["RewardsAddress"] = re.findall(r"--rewards-address ([\dA-Fa-fXx]+)",os.getenv('RewardsAddress'))[0]
    except:
        try:
            anm_config["RewardsAddress"] = re.findall(r"([\dA-Fa-fXx]+)",os.getenv("RewardsAddress"))[0]
        except:
            logging.warning("Unable to detect RewardsAddress")
            sys.exit(1)
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
    # Timer for last stopped nodes
    anm_config["LastStoppedAt"]=0


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
    # Only return version number when we have one, to stop clobbering the binary check
    try:
        url = "http://{0}:{1}/metadata".format(host,port)
        response = requests.get(url)
        data=response.text
    except requests.exceptions.ConnectionError:
        logging.debug("Connection Refused on port: {0}:{1}".format(host,str(port)))
        return {"status": STOPPED, "peer_id":""}
    except Exception as error:
        template = "In RNMd - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.info(message)
        return {"status": STOPPED, "peer_id":""}
    # collect a dict to return
    card={}
    try:
        card["version"] = re.findall(r'{antnode_version="([\d\.]+)"}',data)[0]
    except:
        logging.info('No version found')
    try:
        card["peer_id"] = re.findall(r'{peer_id="([\w\d]+)"}',data)[0]
    except:
        card["peer_id"] = ""
    card["status"] = RUNNING if "version" in card else STOPPED
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
    except requests.exceptions.ConnectionError:
        logging.debug("Connection Refused on port: {0}:{1}".format(host,str(port)))
        metrics["status"] = STOPPED
        metrics["uptime"] = 0
        metrics["records"] = 0
        metrics["shunned"] = 0
    except Exception as error:
        template = "in:RNM - An exception of type {0} occurred. Arguments:\n{1!r}"
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
        template = "In GAV - An exception of type {0} occurred. Arguments:\n{1!r}"
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
            # The ports up, so grab metrics too
            card.update(read_node_metrics(card["host"],card["metrics_port"]))
        # Else run binary to get version
        else:
            # If the root directory of the node is missing, it's a bad node
            if not os.path.isdir(card["root_dir"]):
                card["status"]=DEAD
                card["version"]=''
            else:
                card["status"]=STOPPED
                card["version"]=get_antnode_version(card["binary"])
            card["peer_id"]=''
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
        db_nodes=session.execute(select(Node.status,Node.version)).all()
    
    # Get some initial stats for comparing after a few seconds
    # We start these counters AFTER reading the database
    start_time=time.time()
    start_disk_counters=psutil.disk_io_counters()
    start_net_counters=psutil.net_io_counters()

    metrics["TotalNodes"]=len(db_nodes)
    data = Counter(node[0] for node in db_nodes)
    metrics["RunningNodes"] = data[RUNNING]
    metrics["StoppedNodes"] = data[STOPPED]
    metrics["RestartingNodes"] = data[RESTARTING]
    metrics["UpgradingNodes"] = data[UPGRADING]
    metrics["MigratingNodes"] = data[MIGRATING]
    metrics["RemovingNodes"] = data[REMOVING]
    metrics["DeadNodes"] = data[DEAD]
    metrics["antnode"]=shutil.which("antnode")
    if not metrics["antnode"]:
        logging.warning("Unable to locate current antnode binary, exiting")
        sys.exit(1)
    metrics["AntNodeVersion"]=get_antnode_version(metrics["antnode"])
    metrics["NodesLatestV"]=sum(1 for node in db_nodes if node[1]==metrics["AntNodeVersion"]) or 0
    metrics["NodesNoVersion"]=sum(1 for node in db_nodes if not node[1]) or 0
    metrics["NodesToUpgrade"]=metrics["TotalNodes"] - metrics["NodesLatestV"] - metrics["NodesNoVersion"]

    # Windows has to build load average over 5 seconds. The first 5 seconds returns 0's
    # I don't plan on supporting windows, but if this get's modular, I don't want this 
    # issue to be skipped
    #if platform.system() == "Windows":
    #    discard=psutil.getloadavg()
    #    time.sleep(5)
    metrics["LoadAverage1"],metrics["LoadAverage5"],metrics["LoadAverage15"]=psutil.getloadavg()
    # Get CPU Metrics over 1 second
    metrics["IdleCpuPercent"],metrics["IOWait"] = psutil.cpu_times_percent(1)[3:5]
    # Really we returned Idle percent, subtract from 100 to get used.
    metrics["UsedCpuPercent"] = 100 - metrics["IdleCpuPercent"]
    data=psutil.virtual_memory()
    #print(data)
    metrics["UsedMemPercent"]=data.percent
    metrics["FreeMemPercent"]=100-metrics["UsedMemPercent"]
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

# Update node with metrics result
def update_node_from_metrics(id,metrics,metadata):
    try:
        # We check the binary version in other code, so lets stop clobbering it when a node is stopped
        card={'status': metrics["status"], 'timestamp': int(time.time()),
                        'uptime': metrics["uptime"], 'records': metrics["records"],
                        'shunned': metrics["shunned"],
                        'peer_id': metadata["peer_id"]}
        if "version" in metadata:
            card['version']=metadata["version"]
        with S() as session:
            session.query(Node).filter(Node.id == id).\
                update(card)
            session.commit()
    except Exception as error:
        template = "In UNFM - An exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(error).__name__, error.args)
        logging.warning(message)
        return False
    else:
        return True
    
# Set Node status
def set_node_status(id,status):
    logging.info("Setting node status: {0} {1}".format(id,status))
    try:
        with S() as session:
            session.query(Node).filter(Node.id == id).\
                update({'status': status, 'timestamp': int(time.time())})
            session.commit()
    except:
        return False
    else:
        return True

# Update metrics after checking counters
def update_counters(old,config):
    # Are we already removing a node
    if old["RemovingNodes"]:
        with S() as session:
            removals=session.execute(select(Node.timestamp,Node.id)\
                                         .where(Node.status == REMOVING)\
                                         .order_by(Node.timestamp.asc())).all()
        # Iterate through active removals
        records_to_remove = len(removals)
        for check in removals:
            # If the DelayRemove timer has expired, delete the entry
            if isinstance(check[0],int) and \
                check[0] < (int(time.time()) - (config["DelayRemove"]*60)):
                logging.info("Deleting removed node "+str(check[1]))
                with S() as session:
                    session.execute(delete(Node).where(Node.id==check[1]))
                    session.commit()
                records_to_remove-=1
        old["RemovingNodes"]=records_to_remove
    # Are we already upgrading a node
    if old["UpgradingNodes"]:
        with S() as session:
            upgrades=session.execute(select(Node.timestamp,Node.id,Node.host,Node.metrics_port)\
                                         .where(Node.status == UPGRADING)\
                                         .order_by(Node.timestamp.asc())).all()
        # Iterate through active upgrades
        records_to_upgrade = len(upgrades)
        for check in upgrades:
            # If the DelayUpgrade timer has expired, check on status
            if isinstance(check[0],int) and \
                check[0] < (int(time.time()) - (config["DelayUpgrade"]*60)):
                logging.info("Updating upgraded node "+str(check[1]))
                node_metrics=read_node_metrics(check[2],check[3])
                node_metadata=read_node_metadata(check[2],check[3])
                if node_metrics and node_metadata:
                    update_node_from_metrics(check[1],node_metrics,node_metadata)
                records_to_upgrade-=1
        old["UpgradingNodes"]=records_to_upgrade
    # Are we already restarting a node
    if old["RestartingNodes"]:
        with S() as session:
            restarts=session.execute(select(Node.timestamp,Node.id,Node.host,Node.metrics_port)\
                                         .where(Node.status == RESTARTING)\
                                         .order_by(Node.timestamp.asc())).all()
        # Iterate through active upgrades
        records_to_restart = len(restarts)
        for check in restarts:
            # If the DelayUpgrade timer has expired, check on status
            if isinstance(check[0],int) and \
                check[0] < (int(time.time()) - (config["DelayStart"]*60)):
                logging.info("Updating restarted node "+str(check[1]))
                node_metrics=read_node_metrics(check[2],check[3])
                node_metadata=read_node_metadata(check[2],check[3])
                if node_metrics and node_metadata:
                    update_node_from_metrics(check[1],node_metrics,node_metadata)
                records_to_restart-=1
        old["RestartingNodes"]=records_to_restart
    return(old)

# Enable firewall for port
def enable_firewall(port,node):
    logging.info("enable firewall port {0}/udp".format(port))
    # Close ufw firewall
    try:
        subprocess.run(['sudo','ufw','allow',"{0}/udp".format(port),'comment',node], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'EF Error:', err )

# Disable firewall for port
def disable_firewall(port):
    logging.info("disable firewall port {0}/udp".format(port))
    # Close ufw firewall
    try:
        subprocess.run(['sudo','ufw','delete','allow',"{0}/udp".format(port)], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'DF ERROR:', err )

# Start a systemd node
def start_systemd_node(node):
    logging.info("Starting node "+str(node.id))
    # Try to start the service
    try:
        p = subprocess.run(['sudo', 'systemctl', 'start', node.service], stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode('utf-8')
        if re.match(r'Failed to start',p):
            logging.error( 'SSN2 ERROR:', p )
            return False
    except subprocess.CalledProcessError as err:
            logging.error( 'SSN1 ERROR:', err )
            return False
    # Open a firewall hole for the data port
    enable_firewall(node.port,node.service)
    # Update node status
    set_node_status(node.id,RESTARTING)
    return True

# Stop a systemd node
def stop_systemd_node(node):
    logging.info("Stopping node: "+node.service)
    # Send a stop signal to the process
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', node.service], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'SSN2 ERROR:', err )
    disable_firewall(node.port)
    set_node_status(node.id,STOPPED)

    return True

# Upgrade a node
def upgrade_node(node,metrics):
    logging.info("Upgrading node "+str(node.id))
    # Copy current node binary
    try:
        subprocess.run(['sudo', 'cp', '-f', metrics["antnode"], node.binary])
    except subprocess.CalledProcessError as err:
        logging.error( 'UN1 ERROR:', err )
    try:
        subprocess.run(['sudo', 'systemctl', 'restart', node.service])
    except subprocess.CalledProcessError as err:
        logging.error( 'UN2 ERROR:', err )
    version=get_antnode_version(node.binary)
    try:
        with S() as session:
            session.query(Node).filter(Node.id == node.id).\
                update({'status': UPGRADING, 'timestamp': int(time.time()),
                        'version': metrics["AntNodeVersion"]})
            session.commit()
    except:
        return False
    else:
        return True

# Remove a node
def remove_node(id):
    logging.info("Removing node "+str(id))

    with S() as session:
        node = session.execute(select(Node).where(Node.id == id)).first()
    # Grab Node from Row
    node=node[0]
    if stop_systemd_node(node):
        # Mark this node as REMOVING
        set_node_status(id,REMOVING)

        nodename=f"antnode{node.nodename}"
        # Remove node data and log
        try:
            subprocess.run(['sudo', 'rm', '-rf', node.root_dir, f"/var/log/antnode/{nodename}"])
        except subprocess.CalledProcessError as err:
            logging.error( 'RN1 ERROR:', err )
        # Remove systemd service file
        try:
            subprocess.run(['sudo', 'rm', '-f', f"/etc/systemd/system/{node.service}"])
        except subprocess.CalledProcessError as err:
            logging.error( 'RN2 ERROR:', err )
        # Tell system to reload systemd files   
        try:
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'])
        except subprocess.CalledProcessError as err:
            logging.error( 'RN3 ERROR:', err ) 
    #print(json.dumps(node,indent=2))

# Rescan nodes for status
def update_nodes():
    with S() as session:
        nodes=session.execute(select(Node.timestamp,Node.id,Node.host,Node.metrics_port,Node.status)\
                                        .where(Node.status != DISABLED)\
                                        .order_by(Node.timestamp.asc())).all()
    # Iterate through all records
    for check in nodes:
        # Check on status
        if isinstance(check[0],int):
            logging.debug("Updating info on node "+str(check[1]))
            node_metrics=read_node_metrics(check[2],check[3])
            node_metadata=read_node_metadata(check[2],check[3])
            if node_metrics and node_metadata:
                # Don't write updates for stopped nodes that are already marked as stopped
                if node_metadata["status"]==STOPPED and check[4]==STOPPED:
                    continue
                update_node_from_metrics(check[1],node_metrics,node_metadata)
     
# Create a new node
def create_node(config,metrics):
    logging.info("Creating new node")
    # Create a holding place for the new node
    card = {}
    # Find the next available node number by first looking for holes
    sql = text('select n1.id + 1 as id from node n1 ' + \
                'left join node n2 on n2.id = n1.id + 1 ' + \
                'where n2.id is null ' + \
                'and n1.id <> (select max(id) from node) ' + \
                'order by n1.id;')
    with S() as session:
        result = session.execute(sql).first()
    if result:
        card['id']=result[0]
    # Otherwise get the max node number and add 1
    else:
        with S() as session:
            result = session.execute(select(Node.id).order_by(Node.id.desc())).first()
        card['id']=result[0]+1
    # Set the node name
    card['nodename']=f'{card['id']:04}'
    card['service']=f'antnode{card['nodename']}.service'
    card['user']='ant'
    card['version']=metrics["AntNodeVersion"]
    card['root_dir']=f"{config['NodeStorage']}/antnode{card['nodename']}"
    card['binary']=f"{card['root_dir']}/antnode"
    card['port']=config["PortStart"]*1000+card['id']
    card['metrics_port']=13*1000+card['id']
    card['network']='evm-arbitrum-one'
    card['wallet']=config["RewardsAddress"]
    card['peer_id']=''
    card['status']=STOPPED
    card['timestamp']=int(time.time())
    card['records']=0
    card['uptime']=0
    card['shunned']=0
    card['age']=card['timestamp']
    card['host']=ANM_HOST
    log_dir=f"/var/log/antnode/antnode{card['nodename']}"
    # Create the node directory and log directory
    try:
        subprocess.run(['sudo','mkdir','-p',card["root_dir"],log_dir], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'CN1 ERROR:', err )
    # Copy the binary to the node directory
    try:
        subprocess.run(['sudo','cp',metrics["antnode"],card["root_dir"]], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'CN2 ERROR:', err )
    # Change owner of the node directory and log directories
    try:
        subprocess.run(['sudo','chown','-R',f'{card["user"]}:{card["user"]}',card["root_dir"],log_dir], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'CN3 ERROR:', err )
    # build the systemd service unit
    service=f"""[Unit]
Description=antnode{card['nodename']}
[Service]
User={card['user']}
ExecStart={card['binary']} --bootstrap-cache-dir /var/antctl/bootstrap-cache --root-dir {card['root_dir']} --port {card['port']} --enable-metrics-server --metrics-server-port {card['metrics_port']} --log-output-dest {log_dir} --max-log-files 1 --max-archived-log-files 1 --rewards-address {card['wallet']} {card['network']}
Restart=always
#RestartSec=300
"""
    # Write the systemd service unit with sudo tee since we're running as not root
    try:
        subprocess.run(['sudo','tee',f'/etc/systemd/system/{card["service"]}'],input=service,text=True, stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'CN4 ERROR:', err )
    # Reload systemd service files to get our new one
    try:
        subprocess.run(['sudo','systemctl','daemon-reload'], stdout=subprocess.PIPE)
    except subprocess.CalledProcessError as err:
            logging.error( 'CN5 ERROR:', err )
    # Add the new node to the database
    with S() as session:
        session.execute(
            insert(Node),[card]
        )
        session.commit()
    # Now we grab the node object from the database to pass to start node
    with S() as session:
        card=session.execute(select(Node).where(Node.id == card['id'])).first()
    # Get the Node object from the Row
    card=card[0]
    # Start the new node
    return start_systemd_node(card)
    #print(json.dumps(card,indent=2))
    return True
    

# Make a decision about what to do
def choose_action(config,metrics,db_nodes):
    # Gather knowlege
    features={}
    features["AllowCpu"]=metrics["UsedCpuPercent"] < config["CpuLessThan"]
    features["AllowMem"]=metrics["UsedMemPercent"] < config["MemLessThan"]
    features["AllowHD"]=metrics["UsedHDPercent"] < config["HDLessThan"]
    features["RemCpu"]=metrics["UsedCpuPercent"] > config["CpuRemove"]
    features["RemMem"]=metrics["UsedMemPercent"] > config["MemRemove"]
    features["RemHD"]=metrics["UsedHDPercent"] > config["HDRemove"]
    features["AllowNodeCap"]=metrics["RunningNodes"] < config["NodeCap"]
    # These are new features, so ignore them if not configured
    if (config["NetIOReadLessThan"]+config["NetIOReadRemove"]+
        config["NetIOWriteLessThan"]+config["NetIOWriteRemove"]>1):
        features["AllowNetIO"]=metrics["NetReadBytes"] < config["NetIOReadLessThan"] and \
                              metrics["NetWriteBytes"] < config["NetIOWriteLessThan"]
        features["RemoveNetIO"]=metrics["NetReadBytes"] > config["NetIORemove"] or \
                              metrics["NetWriteBytes"] > config["NetIORemove"]
    else:
        features["AllowNetIO"]=True
        features["RemoveNetIO"]=False
    if (config["HDIOReadLessThan"]+config["HDIOReadRemove"]+
        config["HDIOWriteLessThan"]+config["HDIOWriteRemove"]>1):
        features["AllowHDIO"]=metrics["HDReadBytes"] < config["HDIOReadLessThan"] and \
                              metrics["HDWriteBytes"] < config["HDIOWriteLessThan"]
        features["RemoveHDIO"]=metrics["HDReadBytes"] > config["HDIORemove"] or \
                              metrics["HDWriteBytes"] > config["HDtIORemove"]
    else:
        features["AllowHDIO"]=True
        features["RemoveHDIO"]=False
    features["LoadAllow"] = metrics["LoadAverage1"] < config["DesiredLoadAverage"] and \
                            metrics["LoadAverage5"] < config["DesiredLoadAverage"] and \
                            metrics["LoadAverage15"] < config["DesiredLoadAverage"] 
    features["LoadNotAllow"] = metrics["LoadAverage1"] > config["MaxLoadAverageAllowed"] or \
                            metrics["LoadAverage5"] > config["MaxLoadAverageAllowed"] or \
                            metrics["LoadAverage15"] > config["MaxLoadAverageAllowed"] 
    # Check records for expired status
    metrics=update_counters(metrics,config)
    # If we have other thing going on, don't add more nodes
    features["AddNewNode"]=sum([ metrics.get(m, 0) \
                                for m in ['UpgradingNodes',
                                          'RestartingNodes','MigratingNodes',
                                          'RemovingNodes'] ]) == 0 and \
                            features["AllowCpu"] and features["AllowHD"] and \
                            features["AllowMem"] and features["AllowNodeCap"] and \
                            features["AllowHDIO"] and features["AllowNetIO"] and \
                            features["LoadAllow"]
    # Are we overlimit on nodes
    features["Remove"] =features["LoadNotAllow"] or features["RemCpu"] or \
                        features["RemHD"] or features["RemMem"] or \
                        features["RemoveHDIO"] or features["RemoveNetIO"] or \
                        metrics["TotalNodes"] > config["NodeCap"]
    # If we have nodes to upgrade
    if metrics["NodesToUpgrade"] >= 1:
        # Make sure current version is equal or newer than version on first node.
        if Version(metrics["AntNodeVersion"]) < Version(db_nodes[0][1]):
            logging.warning("node upgrade cancelled due to lower version")
            features["Upgrade"]=False
        else:
            if features["Remove"]:
                logging.info("Can't upgrade while removing is required")
                features["Upgrade"]=False
            else:
                features["Upgrade"]=True
    else:
        features["Upgrade"]=False


    logging.info(json.dumps(features,indent=2))
    ##### Decisions

    # Actually, removing DEAD nodes take priority
    if metrics["DeadNodes"] > 1:
        with S() as session:
            broken=session.execute(select(Node.timestamp,Node.id,Node.host,Node.metrics_port)\
                                         .where(Node.status == DEAD)\
                                         .order_by(Node.timestamp.asc())).all()
        # Iterate through dead nodes and remove them all
        for check in broken:
            # Remove broken nodes
            logging.info("Removing dead node "+str(check[1]))
            remove_node(check[1])
        return {"status": "removed-dead-nodes"}
    # If we have nodes with no version number, update from binary
    if metrics["NodesNoVersion"] > 1:
        with S() as session:
            no_version=session.execute(select(Node.timestamp,Node.id,Node.binary)\
                                         .where(Node.version == '')\
                                         .order_by(Node.timestamp.asc())).all()
        # Iterate through nodes with no version number
        for check in no_version:
            # Update version number from binary
            version=get_antnode_version(check[2])
            logging.info(f"Updating version number for node {check[1]} to {version}")
            with S() as session:
                session.query(Node).filter(Node.id == check[1]).\
                    update({'version': version})
                session.commit()
            
    # If we're restarting, wait patiently as metrics could be skewed
    if metrics["RestartingNodes"]:
        logging.info("Still waiting for RestartDelay")
        return {"status": RESTARTING}
    # If we still have unexpired upgrade records, wait
    if metrics["UpgradingNodes"]:
        logging.info("Still waiting for UpgradeDelay")
        return {"status": UPGRADING}
    # First if we're removing, that takes top priority
    if features["Remove"]:
        # If we still have unexpired removal records, wait
        if metrics["RemovingNodes"]:
            logging.info("Still waiting for RemoveDelay")
            return {"status": REMOVING}
        # If we're under HD pressure or trimming node cap, remove nodes
        if features["RemHD"] or metrics["TotalNodes"] > config["NodeCap"]:
            # Start removing with stopped nodes
            if metrics["StoppedNodes"] > 0:
                # What is the youngest stopped node
                with S() as session:
                    youngest=session.execute(select(Node.id)\
                                            .where(Node.status == STOPPED)\
                                            .order_by(Node.age.desc())).first()
                if youngest:
                    # Remove the youngest node
                    remove_node(youngest[0])
                    return{"status": REMOVING}
            # No low hanging fruit. let's start with the youngest running node
            with S() as session:
                youngest=session.execute(select(Node.id)\
                                        .where(Node.status == RUNNING)\
                                        .order_by(Node.age.desc())).first()
            if youngest:
                # Remove the youngest node
                remove_node(youngest[0])
                return{"status": REMOVING}
            return{"status": "nothing-to-remove"}
        # Otherwise, let's try just stopping a node to bring IO/Mem/Cpu down
        else:
            # If we just stopped a node, wait
            if int(config["LastStoppedAt"] or 0) > (int(time.time()) - (config["DelayRemove"]*60)):
                logging.info("Still waiting for RemoveDelay")
                return {"status": 'waiting-to-stop'}
            # Start with the youngest running node
            with S() as session:
                youngest=session.execute(select(Node)\
                                        .where(Node.status == RUNNING)\
                                        .order_by(Node.age.desc())).first()
            if youngest:
                # Stop the youngest node
                stop_systemd_node(youngest[0])
                # Update the last stopped time
                with S() as session:
                    session.query(Machine).filter(Machine.id == 1).\
                        update({'LastStoppedAt': int(time.time())})
                    session.commit()
                return{"status": STOPPED}
            else:
                return{"status": "nothing-to-stop"}
    
    # Do we have upgrading to do?
    if features["Upgrade"]:    
        # Let's find the oldest running node not using the current version
        with S() as session:
            oldest=session.execute(select(Node)\
                                        .where(Node.status == RUNNING)\
                                        .where(Node.version != metrics["AntNodeVersion"])
                                        .order_by(Node.age.asc())).first()
        if oldest:
            # Get Node from Row
            oldest = oldest[0]
            # If we don't have a version number from metadata, grab from binary
            if not oldest.version:
                oldest.version=get_antnode_version(oldest.binary)
            #print(json.dumps(oldest))
            # Upgrade the oldest node
            upgrade_node(oldest,metrics)
            return{"status": UPGRADING}
        
    # If AddNewNode
    #   If stopped nodes available
    #     Check oldest stopped version
    #     If out of date
    #         upgrade node which starts it
    #     else
    #         restart node
    #   else
    #     Create a Node which starts it
    if features["AddNewNode"]:
        # Start adding with stopped nodes
        if metrics["StoppedNodes"] > 0:
            # What is the oldest stopped node
            with S() as session:
                oldest=session.execute(select(Node)\
                                        .where(Node.status == STOPPED)\
                                        .order_by(Node.age.asc())).first()
            if oldest:
                # Get Node from Row
                oldest=oldest[0]
                # If we don't have a version number from metadata, grab from binary
                if not oldest.version:
                    oldest.version=get_antnode_version(oldest.binary)
                # If the stopped version is old, upgrade it
                if Version(metrics["AntNodeVersion"]) > Version(oldest.version):
                    upgrade_node(oldest,metrics)
                    return{"status": UPGRADING}
                else:
                    if start_systemd_node(oldest):
                        return{"status": RESTARTING}
                    else:
                        return{"status": "failed-start-node"}
            # Hmm, still in Start mode, we shouldn't get here
            return {"status": 'START'}
        # Still in Add mode, add a new node
        if metrics["TotalNodes"] < config["NodeCap"]:
            if create_node(config,metrics):
                return {"status": "ADD"}
            else:
                return {"status": "failed-create-node"}
        else:
            return {"status": "node-cap-reached"}
    # If we have nothing to do, Survey the node ports
    update_nodes()
    return{"status": "idle"}

def main():
    # We're starting, so lets create a lock file
    try:
        with open('/var/antctl/wnm_active', 'w') as file:
            file.write(str(int(time.time())))
    except:
        logging.error("Unable to create lock file, exiting")
        sys.exit(1)

    # See if we already have a known state in the database
    with S() as session:
        db_nodes=session.execute(select(Node.status,Node.version,
                                        Node.host,Node.metrics_port,
                                        Node.port,Node.age,Node.id,
                                        Node.timestamp)).all()
        anm_config=session.execute(select(Machine)).all()

    if db_nodes:
        # anm_config by default loads a parameter array, 
        # use the __json__ method to return a dict from the first node
        anm_config = json.loads(json.dumps(anm_config[0][0])) or load_anm_config()
        metrics=get_machine_metrics(anm_config["NodeStorage"],anm_config["HDRemove"])
        #node_metrics = read_node_metrics(db_nodes[0][2],db_nodes[0][3])
        #print(db_nodes[0])
        #print(node_metrics)
        #print(anm_config)
        #print(json.dumps(anm_config,indent=4))
        #print("Node: ",db_nodes)
        logging.info("Found {counter} nodes migrated".format(counter=len(db_nodes)))

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

        # Now load subset of data to work with
        with S() as session:
            db_nodes=session.execute(select(Node.status,Node.version,
                                            Node.host,Node.metrics_port,
                                            Node.port,Node.age,Node.id,
                                            Node.timestamp)).all()



        #print(json.dumps(anm_config,indent=4))
        logging.info("Found {counter} nodes configured".format(counter=len(db_nodes)))

        #versions = [v[1] for worker in Workers if (v := worker.get('version'))]
        #data = Counter(ver for ver in versions)


    data = Counter(status[0] for status in db_nodes)
    #print(data)
    print("Running Nodes:",data[RUNNING])
    print("Restarting Nodes:",data[RESTARTING])
    print("Stopped Nodes:",data[STOPPED])
    print("Upgrading Nodes:",data[UPGRADING])
    print("Removing Nodes:",data[REMOVING])
    data = Counter(ver[1] for ver in db_nodes)
    print("Versions:",data)

    machine_metrics = get_machine_metrics(anm_config['NodeStorage'],anm_config["HDRemove"])
    print(json.dumps(anm_config,indent=2))
    print(json.dumps(machine_metrics,indent=2))
    this_action=choose_action(anm_config,machine_metrics,db_nodes)
    print("Action:",json.dumps(this_action,indent=2))
    # Remove lock file
    os.remove("/var/antctl/wnm_active")

if __name__ == "__main__":
    main()

print("End of program")
