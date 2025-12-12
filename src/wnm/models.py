# Turn a class into a storable object with ORM
from typing import Optional

import json_fix
from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    scoped_session,
    sessionmaker,
)


# create a Base class bound to sqlalchemy
class Base(DeclarativeBase):
    pass


# Extend the Base class to create our Host info
class Machine(Base):
    """One row per wnm instance (single physical machine)"""

    __tablename__ = "machine"
    # No schema in sqlite3
    # __table_args__ = {"schema": "colony"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # System configuration
    cpu_count: Mapped[int] = mapped_column(Integer)
    node_cap: Mapped[int] = mapped_column(Integer)

    # Resource thresholds for adding nodes
    cpu_less_than: Mapped[int] = mapped_column(Integer)
    mem_less_than: Mapped[int] = mapped_column(Integer)
    hd_less_than: Mapped[int] = mapped_column(Integer)
    hdio_read_less_than: Mapped[int] = mapped_column(Integer)
    hdio_write_less_than: Mapped[int] = mapped_column(Integer)
    netio_read_less_than: Mapped[int] = mapped_column(Integer)
    netio_write_less_than: Mapped[int] = mapped_column(Integer)

    # Resource thresholds for removing nodes
    cpu_remove: Mapped[int] = mapped_column(Integer)
    mem_remove: Mapped[int] = mapped_column(Integer)
    hd_remove: Mapped[int] = mapped_column(Integer)
    hdio_read_remove: Mapped[int] = mapped_column(Integer)
    hdio_write_remove: Mapped[int] = mapped_column(Integer)
    netio_read_remove: Mapped[int] = mapped_column(Integer)
    netio_write_remove: Mapped[int] = mapped_column(Integer)

    # Load average thresholds
    max_load_average_allowed: Mapped[float] = mapped_column(Float)
    desired_load_average: Mapped[float] = mapped_column(Float)

    # Delay timers (in seconds, changed from minutes)
    delay_start: Mapped[int] = mapped_column(Integer)
    delay_restart: Mapped[int] = mapped_column(Integer)
    delay_upgrade: Mapped[int] = mapped_column(Integer)
    delay_remove: Mapped[int] = mapped_column(Integer)
    survey_delay: Mapped[int] = mapped_column(Integer, default=0)  # milliseconds
    action_delay: Mapped[int] = mapped_column(Integer, default=0)  # milliseconds

    # Node configuration
    node_storage: Mapped[str] = mapped_column(UnicodeText)
    rewards_address: Mapped[str] = mapped_column(UnicodeText)
    donate_address: Mapped[str] = mapped_column(UnicodeText)

    # Port configuration
    port_start: Mapped[int] = mapped_column(Integer)
    metrics_port_start: Mapped[int] = mapped_column(Integer)
    rpc_port_start: Mapped[int] = mapped_column(Integer, default=30)

    # System state
    last_stopped_at: Mapped[int] = mapped_column(Integer)
    host: Mapped[str] = mapped_column(UnicodeText)
    crisis_bytes: Mapped[int] = mapped_column(Integer)

    # Runtime configuration
    environment: Mapped[Optional[str]] = mapped_column(UnicodeText)
    start_args: Mapped[Optional[str]] = mapped_column(UnicodeText)

    # NEW: Concurrency limits (Phase 5)
    max_concurrent_upgrades: Mapped[int] = mapped_column(Integer, default=1)
    max_concurrent_starts: Mapped[int] = mapped_column(Integer, default=1)
    max_concurrent_removals: Mapped[int] = mapped_column(Integer, default=1)
    max_concurrent_operations: Mapped[int] = mapped_column(Integer, default=1)

    # NEW: Node selection strategy (Phase 6)
    node_removal_strategy: Mapped[str] = mapped_column(UnicodeText, default="youngest")

    # Process manager type
    process_manager: Mapped[Optional[str]] = mapped_column(UnicodeText, default=None)

    # S6overlay / Docker configuration (for s6overlay process manager)
    max_node_per_container: Mapped[int] = mapped_column(Integer, default=200)
    min_container_count: Mapped[int] = mapped_column(Integer, default=1)
    docker_image: Mapped[Optional[str]] = mapped_column(
        UnicodeText, default="autonomi/node:latest"
    )

    # Node runtime flags
    no_upnp: Mapped[bool] = mapped_column(
        Integer, default=1
    )  # SQLite uses 0/1 for boolean

    # Binary path configuration
    antnode_path: Mapped[Optional[str]] = mapped_column(
        UnicodeText, default="~/.local/bin/antnode"
    )

    # Relationships
    containers: Mapped[list["Container"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan"
    )
    nodes: Mapped[list["Node"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        cpu_count,
        node_cap,
        cpu_less_than,
        cpu_remove,
        mem_less_than,
        mem_remove,
        hd_less_than,
        hd_remove,
        delay_start,
        delay_restart,
        delay_upgrade,
        delay_remove,
        node_storage,
        rewards_address,
        donate_address,
        max_load_average_allowed,
        desired_load_average,
        port_start,
        hdio_read_less_than,
        hdio_read_remove,
        hdio_write_less_than,
        hdio_write_remove,
        netio_read_less_than,
        netio_read_remove,
        netio_write_less_than,
        netio_write_remove,
        last_stopped_at,
        host,
        crisis_bytes,
        metrics_port_start,
        rpc_port_start,
        environment,
        start_args,
        max_concurrent_upgrades=1,
        max_concurrent_starts=1,
        max_concurrent_removals=1,
        max_concurrent_operations=1,
        node_removal_strategy="youngest",
        process_manager=None,
        max_node_per_container=200,
        min_container_count=1,
        docker_image="autonomi/node:latest",
        no_upnp=True,
        antnode_path="~/.local/bin/antnode",
        survey_delay=0,
        action_delay=0,
    ):
        self.cpu_count = cpu_count
        self.node_cap = node_cap
        self.cpu_less_than = cpu_less_than
        self.cpu_remove = cpu_remove
        self.mem_less_than = mem_less_than
        self.mem_remove = mem_remove
        self.hd_less_than = hd_less_than
        self.hd_remove = hd_remove
        self.delay_start = delay_start
        self.delay_restart = delay_restart
        self.delay_upgrade = delay_upgrade
        self.delay_remove = delay_remove
        self.survey_delay = survey_delay
        self.action_delay = action_delay
        self.node_storage = node_storage
        self.rewards_address = rewards_address
        self.donate_address = donate_address
        self.max_load_average_allowed = max_load_average_allowed
        self.desired_load_average = desired_load_average
        self.port_start = port_start
        self.hdio_read_less_than = hdio_read_less_than
        self.hdio_read_remove = hdio_read_remove
        self.hdio_write_less_than = hdio_write_less_than
        self.hdio_write_remove = hdio_write_remove
        self.netio_read_less_than = netio_read_less_than
        self.netio_read_remove = netio_read_remove
        self.netio_write_less_than = netio_write_less_than
        self.netio_write_remove = netio_write_remove
        self.last_stopped_at = last_stopped_at
        self.host = host
        self.crisis_bytes = crisis_bytes
        self.metrics_port_start = metrics_port_start
        self.rpc_port_start = rpc_port_start
        self.environment = environment
        self.start_args = start_args
        self.max_concurrent_upgrades = max_concurrent_upgrades
        self.max_concurrent_starts = max_concurrent_starts
        self.max_concurrent_removals = max_concurrent_removals
        self.max_concurrent_operations = max_concurrent_operations
        self.node_removal_strategy = node_removal_strategy
        self.process_manager = process_manager
        self.max_node_per_container = max_node_per_container
        self.min_container_count = min_container_count
        self.docker_image = docker_image
        self.no_upnp = no_upnp
        self.antnode_path = antnode_path

    def __repr__(self):
        return (
            f"Machine({self.cpu_count},{self.node_cap},{self.cpu_less_than},{self.cpu_remove}"
            + f",{self.mem_less_than},{self.mem_remove},{self.hd_less_than}"
            + f",{self.hd_remove},{self.delay_start},{self.delay_upgrade}"
            + f",{self.delay_remove}"
            + f',"{self.node_storage}","{self.rewards_address}","{self.donate_address}"'
            + f",{self.max_load_average_allowed},{self.desired_load_average}"
            + f",{self.port_start},{self.hdio_read_less_than},{self.hdio_read_remove}"
            + f",{self.hdio_write_less_than},{self.hdio_write_remove}"
            + f",{self.netio_read_less_than},{self.netio_read_remove}"
            + f",{self.netio_write_less_than},{self.netio_write_remove}"
            + f",{self.last_stopped_at},{self.host},{self.crisis_bytes}"
            + f",{self.metrics_port_start},{self.environment},{self.start_args})"
        )

    def __json__(self):
        return {
            "cpu_count": self.cpu_count,
            "node_cap": self.node_cap,
            "cpu_less_than": self.cpu_less_than,
            "cpu_remove": self.cpu_remove,
            "mem_less_than": self.mem_less_than,
            "mem_remove": self.mem_remove,
            "hd_less_than": self.hd_less_than,
            "hd_remove": self.hd_remove,
            "delay_start": self.delay_start,
            "delay_upgrade": self.delay_upgrade,
            "delay_remove": self.delay_remove,
            "survey_delay": self.survey_delay,
            "action_delay": self.action_delay,
            "node_storage": f"{self.node_storage}",
            "rewards_address": f"{self.rewards_address}",
            "donate_address": f"{self.donate_address}",
            "max_load_average_allowed": self.max_load_average_allowed,
            "desired_load_average": self.desired_load_average,
            "port_start": self.port_start,
            "hdio_read_less_than": self.hdio_read_less_than,
            "hdio_read_remove": self.hdio_read_remove,
            "hdio_write_less_than": self.hdio_write_less_than,
            "hdio_write_remove": self.hdio_write_remove,
            "netio_read_less_than": self.netio_read_less_than,
            "netio_read_remove": self.netio_read_remove,
            "netio_write_less_than": self.netio_write_less_than,
            "netio_write_remove": self.netio_write_remove,
            "last_stopped_at": self.last_stopped_at,
            "host": f"{self.host}",
            "crisis_bytes": self.crisis_bytes,
            "metrics_port_start": self.metrics_port_start,
            "rpc_port_start": self.rpc_port_start,
            "environment": f"{self.environment}",
            "start_args": f"{self.start_args}",
            "max_concurrent_upgrades": self.max_concurrent_upgrades,
            "max_concurrent_starts": self.max_concurrent_starts,
            "max_concurrent_removals": self.max_concurrent_removals,
            "max_concurrent_operations": self.max_concurrent_operations,
            "node_removal_strategy": f"{self.node_removal_strategy}",
            "process_manager": (
                f"{self.process_manager}" if self.process_manager else None
            ),
            "no_upnp": bool(self.no_upnp),
            "antnode_path": f"{self.antnode_path}" if self.antnode_path else None,
        }


# NEW: Container table for Docker container management
class Container(Base):
    """Optional: Docker containers hosting nodes"""

    __tablename__ = "container"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key to machine
    machine_id: Mapped[int] = mapped_column(ForeignKey("machine.id"), default=1)

    # Docker container details
    container_id: Mapped[str] = mapped_column(Unicode(64), unique=True)
    name: Mapped[str] = mapped_column(UnicodeText)
    image: Mapped[str] = mapped_column(UnicodeText)
    status: Mapped[str] = mapped_column(Unicode(32))  # running, stopped, etc.
    created_at: Mapped[int] = mapped_column(Integer)

    # Port range tracking for s6overlay block-based allocation
    port_range_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    port_range_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metrics_port_range_start: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    metrics_port_range_end: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Relationships
    machine: Mapped["Machine"] = relationship(back_populates="containers")
    nodes: Mapped[list["Node"]] = relationship(
        back_populates="container", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        container_id,
        name,
        image,
        status,
        created_at,
        machine_id=1,
        port_range_start=None,
        port_range_end=None,
        metrics_port_range_start=None,
        metrics_port_range_end=None,
    ):
        self.container_id = container_id
        self.name = name
        self.image = image
        self.status = status
        self.created_at = created_at
        self.machine_id = machine_id
        self.port_range_start = port_range_start
        self.port_range_end = port_range_end
        self.metrics_port_range_start = metrics_port_range_start
        self.metrics_port_range_end = metrics_port_range_end

    def __repr__(self):
        return (
            f'Container({self.id},"{self.container_id}","{self.name}","{self.image}"'
            + f',"{self.status}",{self.created_at})'
        )

    def __json__(self):
        return {
            "id": self.id,
            "container_id": f"{self.container_id}",
            "name": f"{self.name}",
            "image": f"{self.image}",
            "status": f"{self.status}",
            "created_at": self.created_at,
            "machine_id": self.machine_id,
        }


# Extend the Base class to create our Node info
class Node(Base):
    """Nodes on host OS or in containers"""

    __tablename__ = "node"
    # No schema in sqlite3
    # __table_args__ = {"schema": "colony"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key to machine
    machine_id: Mapped[int] = mapped_column(ForeignKey("machine.id"), default=1)

    # NEW: Optional container reference
    container_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("container.id"), nullable=True
    )

    # NEW: Process manager type
    manager_type: Mapped[str] = mapped_column(
        UnicodeText, default="systemd"
    )  # "systemd", "docker", "setsid", "antctl", "launchctl"

    # Maps to antnode-{nodename}
    node_name: Mapped[str] = mapped_column(Unicode(10))
    # service definition name
    service: Mapped[str] = mapped_column(UnicodeText)
    # User running node
    user: Mapped[str] = mapped_column(Unicode(24))
    # Full path to node binary
    binary: Mapped[str] = mapped_column(UnicodeText)
    # Last polled version of the binary
    version: Mapped[Optional[str]] = mapped_column(UnicodeText)
    # Root directory of the node
    root_dir: Mapped[str] = mapped_column(UnicodeText)
    # Log directory of the node (optional, defaults to platform-specific location)
    log_dir: Mapped[Optional[str]] = mapped_column(UnicodeText, nullable=True)
    # Node open port
    port: Mapped[int] = mapped_column(Integer)
    # Node metrics port
    metrics_port: Mapped[int] = mapped_column(Integer)
    # Node RPC port
    rpc_port: Mapped[int] = mapped_column(Integer, default=0)
    # Network to use ( Live is evm-arbitrum-one )
    network: Mapped[str] = mapped_column(UnicodeText)
    # Reward address
    wallet: Mapped[Optional[str]] = mapped_column(Unicode(42), index=True)
    # Reported peer_id
    peer_id: Mapped[Optional[str]] = mapped_column(Unicode(52))
    # Node's last probed status
    status: Mapped[str] = mapped_column(Unicode(32), index=True)
    # Timestamp of last update
    timestamp: Mapped[int] = mapped_column(Integer, index=True)
    # Number of node records stored as reported by node
    records: Mapped[int] = mapped_column(Integer, index=True)
    # Node reported uptime
    uptime: Mapped[int] = mapped_column(Integer)
    # Number of shuns
    shunned: Mapped[int] = mapped_column(Integer)
    # Number of connected peers as reported by node
    connected_peers: Mapped[int] = mapped_column(Integer, default=0)

    # InfluxDB-specific metrics (collected from /metrics endpoint)
    # Number of GET requests (not currently exposed by node, kept for compatibility)
    gets: Mapped[int] = mapped_column(Integer, default=0)
    # Number of PUT requests (from ant_node_put_record_ok_total)
    puts: Mapped[int] = mapped_column(Integer, default=0)
    # Memory usage in MB * 100 (from ant_networking_process_memory_used_mb, e.g., 97.8125 MB = 9781)
    mem: Mapped[int] = mapped_column(Integer, default=0)
    # CPU usage percentage * 100 (from ant_networking_process_cpu_usage_percentage, e.g., 0.0353% = 4)
    cpu: Mapped[int] = mapped_column(Integer, default=0)
    # Number of open connections (from ant_networking_open_connections)
    open_connections: Mapped[int] = mapped_column(Integer, default=0)
    # Total peers in routing table (from ant_networking_peers_in_routing_table)
    total_peers: Mapped[int] = mapped_column(Integer, default=0)
    # Number of bad peers (from ant_networking_bad_peers_count_total)
    bad_peers: Mapped[int] = mapped_column(Integer, default=0)
    # Relevant records count (from ant_networking_relevant_records)
    rel_records: Mapped[int] = mapped_column(Integer, default=0)
    # Maximum records capacity (from ant_networking_max_records)
    max_records: Mapped[int] = mapped_column(Integer, default=0)
    # Rewards balance as TEXT for 18-decimal precision (from ant_node_current_reward_wallet_balance)
    rewards: Mapped[Optional[str]] = mapped_column(UnicodeText, default="0")
    # Number of payments received (from ant_networking_received_payment_count)
    payment_count: Mapped[int] = mapped_column(Integer, default=0)
    # Live time in seconds (from ant_networking_live_time)
    live_time: Mapped[int] = mapped_column(Integer, default=0)
    # Estimated network size (from ant_networking_estimated_network_size)
    network_size: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamp of node first launch
    age: Mapped[int] = mapped_column(Integer)
    # Host ip for data
    host: Mapped[str] = mapped_column(UnicodeText)
    # node launch method
    method: Mapped[str] = mapped_column(UnicodeText)
    # node layout
    layout: Mapped[str] = mapped_column(UnicodeText)
    # node environment settings
    environment: Mapped[Optional[str]] = mapped_column(UnicodeText)

    # Relationships
    machine: Mapped["Machine"] = relationship(back_populates="nodes")
    container: Mapped[Optional["Container"]] = relationship(back_populates="nodes")

    def __init__(
        self,
        id,
        node_name,
        service,
        user,
        binary,
        version,
        root_dir,
        port,
        metrics_port,
        rpc_port,
        network,
        wallet,
        peer_id,
        status,
        timestamp,
        records,
        uptime,
        shunned,
        connected_peers=0,
        age=None,
        host=None,
        method=None,
        layout=None,
        environment=None,
        machine_id=1,
        container_id=None,
        manager_type="systemd",
        log_dir=None,
    ):
        self.id = id
        self.node_name = node_name
        self.service = service
        self.user = user
        self.binary = binary
        self.version = version
        self.root_dir = root_dir
        self.log_dir = log_dir
        self.port = port
        self.metrics_port = metrics_port
        self.rpc_port = rpc_port
        self.network = network
        self.wallet = wallet
        self.peer_id = peer_id
        self.status = status
        self.timestamp = timestamp
        self.records = records
        self.uptime = uptime
        self.shunned = shunned
        self.connected_peers = connected_peers
        self.age = age
        self.host = host
        self.method = method
        self.layout = layout
        self.environment = environment
        self.machine_id = machine_id
        self.container_id = container_id
        self.manager_type = manager_type

    def __repr__(self):
        return (
            f'Node({self.id},"{self.node_name}","{self.service}","{self.user},"{self.binary}"'
            + f',"{self.version}","{self.root_dir}",{self.port},{self.metrics_port}'
            + f',"{self.network}","{self.wallet}","{self.peer_id}","{self.status}",{self.timestamp}'
            + f',{self.records},{self.uptime},{self.shunned},{self.connected_peers},{self.age},"{self.host}"'
            + f',{self.method},{self.layout},"{self.environment}"'
            + f',{self.machine_id},{self.container_id},"{self.manager_type}")'
        )

    def __json__(self):
        return {
            "id": self.id,
            "node_name": f"{self.node_name}",
            "service": f"{self.service}",
            "user": f"{self.user}",
            "binary": f"{self.binary}",
            "version": f"{self.version}",
            "root_dir": f"{self.root_dir}",
            "port": self.port,
            "metrics_port": self.metrics_port,
            "network": f"{self.network}",
            "wallet": f"{self.wallet}",
            "peer_id": f"{self.peer_id}",
            "status": f"{self.status}",
            "timestamp": self.timestamp,
            "records": self.records,
            "uptime": self.uptime,
            "shunned": self.shunned,
            "connected_peers": self.connected_peers,
            "age": self.age,
            "host": f"{self.host}",
            "method": f"{self.method}",
            "layout": f"{self.layout}",
            "environment": f"{self.environment}",
            "machine_id": self.machine_id,
            "container_id": self.container_id,
            "manager_type": f"{self.manager_type}",
        }
