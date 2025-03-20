import json_fix

# Turn a class into a storable object with ORM
from typing import Optional
from sqlalchemy import Integer, Unicode, UnicodeText, Float
from sqlalchemy import create_engine, select, insert, update
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column

# create a Base class bound to sqlalchemy
class Base(DeclarativeBase):
    pass

# Extend the Base class to create our Host info
class Machine(Base):
    __tablename__ = 'machine'
    # No schema in sqlite3
    # __table_args__ = {"schema": "colony"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    CpuCount: Mapped[int] = mapped_column(Integer)
    NodeCap: Mapped[int] = mapped_column(Integer)
    CpuLessThan: Mapped[int] = mapped_column(Integer)
    CpuRemove: Mapped[int] = mapped_column(Integer)
    MemLessThan: Mapped[int] = mapped_column(Integer)
    MemRemove: Mapped[int] = mapped_column(Integer)
    HDLessThan: Mapped[int] = mapped_column(Integer)
    HDRemove: Mapped[int] = mapped_column(Integer)
    DelayStart: Mapped[int] = mapped_column(Integer)
    DelayUpgrade: Mapped[int] = mapped_column(Integer)
    DelayRemove: Mapped[int] = mapped_column(Integer)
    NodeStorage: Mapped[str] = mapped_column(UnicodeText)
    RewardsAddress: Mapped[str] = mapped_column(UnicodeText)
    DonateAddress: Mapped[str] = mapped_column(UnicodeText)
    MaxLoadAverageAllowed: Mapped[float] = mapped_column(Float)
    DesiredLoadAverage: Mapped[float] = mapped_column(Float)
    # What port to begin assigning nodes
    PortStart: Mapped[int] = mapped_column(Integer)
    HDIOReadLessThan: Mapped[float] = mapped_column(Float)
    HDIOReadRemove: Mapped[float] = mapped_column(Float)
    HDIOWriteLessThan: Mapped[float] = mapped_column(Float)
    HDIOWriteRemove: Mapped[float] = mapped_column(Float)
    NetIOReadLessThan: Mapped[float] = mapped_column(Float)
    NetIOReadRemove: Mapped[float] = mapped_column(Float)
    NetIOWriteLessThan: Mapped[float] = mapped_column(Float)
    NetIOWriteRemove: Mapped[float] = mapped_column(Float)
    LastStoppedAt: Mapped[int] = mapped_column(Integer)

    def __init__(self, CpuCount, NodeCap, CpuLessThan, CpuRemove,
                 MemLessThan, MemRemove, HDLessThan, HDRemove,
                 DelayStart, DelayUpgrade, DelayRemove, NodeStorage,
                 RewardsAddress, DonateAddress, MaxLoadAverageAllowed, 
                 DesiredLoadAverage, PortStart, HDIOReadLessThan, 
                 HDIOReadRemove, HDIOWriteLessThan, HDIOWriteRemove, 
                 NetIOReadLessThan, NetIOReadRemove, NetIOWriteLessThan, 
                 NetIOWriteRemove, LastStoppedAt):
        
        self.CpuCount = CpuCount
        self.NodeCap = NodeCap
        self.CpuLessThan = CpuLessThan
        self.CpuRemove = CpuRemove
        self.MemLessThan = MemLessThan
        self.MemRemove = MemRemove
        self.HDLessThan = HDLessThan
        self.HDRemove = HDRemove
        self.DelayStart = DelayStart
        self.DelayUpgrade = DelayUpgrade
        self.DelayRemove = DelayRemove
        self.NodeStorage = NodeStorage
        self.RewardsAddress = RewardsAddress
        self.DonateAddress = DonateAddress
        self.MaxLoadAverageAllowed = MaxLoadAverageAllowed
        self.DesiredLoadAverage = DesiredLoadAverage
        self.PortStart = PortStart
        self.HDIOReadLessThan = HDIOReadLessThan
        self.HDIOReadRemove = HDIOReadRemove
        self.HDIOWriteLessThan = HDIOWriteLessThan
        self.HDIOWriteRemove = HDIOWriteRemove
        self.NetIOReadLessThan = NetIOReadLessThan
        self.NetIOReadRemove = NetIOReadRemove
        self.NetIOWriteLessThan = NetIOWriteLessThan
        self.NetIOWriteRemove = NetIOWriteRemove
        self.LastStoppedAt = LastStoppedAt

    def __repr__(self):
        return f'Machine({self.CpuCount},{self.NodeCap},{self.CpuLessThan},{self.CpuRemove}' + \
            f',{self.MemLessThan},{self.MemRemove},{self.HDLessThan}' + \
            f',{self.HDRemove},{self.DelayStart},{self.DelayUpgrade}' + \
            f',{self.DelayRemove}' + \
            f',"{self.NodeStorage}","{self.RewardsAddress}","{self.DonateAddress}"' + \
            f',{self.MaxLoadAverageAllowed},{self.DesiredLoadAverage}' + \
            f',{self.PortStart},{self.HDIOReadLessThan},{self.HDIOReadRemove}' + \
            f',{self.HDIOWriteLessThan},{self.HDIOWriteRemove}' + \
            f',{self.NetIOReadLessThan},{self.NetIOReadRemove}' + \
            f',{self.NetIOWriteLessThan},{self.NetIOWriteRemove}' + \
            f',{self.LastStoppedAt})'
    
    def __json__(self):
        return { 'CpuCount': self.CpuCount, 'NodeCap': self.NodeCap, 'CpuLessThan': self.CpuLessThan,
            'CpuRemove': self.CpuRemove, 'MemLessThan': self.MemLessThan, 'MemRemove': self.MemRemove,
            'HDLessThan': self.HDLessThan, 'HDRemove': self.HDRemove, 'DelayStart': self.DelayStart,
            'DelayUpgrade': self.DelayUpgrade, 'DelayRemove': self.DelayRemove, 'NodeStorage': f"{self.NodeStorage}",
            'RewardsAddress': f"{self.RewardsAddress}", 'DonateAddress': f"{self.DonateAddress}",
            'MaxLoadAverageAllowed': self.MaxLoadAverageAllowed, 'DesiredLoadAverage': self.DesiredLoadAverage,
            'PortStart': self.PortStart, 'HDIOReadLessThan': self.HDIOReadLessThan, 'HDIOReadRemove': self.HDIOReadRemove,
            'HDIOWriteLessThan': self.HDIOWriteLessThan, 'HDIOWriteRemove': self.HDIOWriteRemove,
            'NetIOReadLessThan': self.NetIOReadLessThan, 'NetIOReadRemove': self.NetIOReadRemove,
            'NetIOWriteLessThan': self.NetIOWriteLessThan, 'NetIOWriteRemove': self.NetIOWriteRemove,
            'LastStoppedAt': self.LastStoppedAt }

   
# Extend the Base class to create our Node info
class Node(Base):
    __tablename__ = 'node'
    # No schema in sqlite3
    #__table_args__ = {"schema": "colony"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Maps to antnode-{nodename}
    nodename: Mapped[str] = mapped_column(Unicode(10))
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
    # Node open port
    port: Mapped[int] = mapped_column(Integer)
    # Node metrics port
    metrics_port: Mapped[int] = mapped_column(Integer)
    # Network to use ( Live is evm-arbitrum-one )
    network: Mapped[str] = mapped_column(UnicodeText)
    # Reward address
    wallet: Mapped[Optional[str]] = mapped_column(Unicode(42),index=True)
    # Reported peer_id
    peer_id: Mapped[Optional[str]] = mapped_column(Unicode(52))
    # Node's last probed status
    status: Mapped[str] = mapped_column(Unicode(32),index=True)
    # Timestamp of last update
    timestamp: Mapped[int] = mapped_column(Integer,index=True)
    # Number of node records stored as reported by node
    records: Mapped[int] = mapped_column(Integer,index=True)
    # Node reported uptime
    uptime: Mapped[int] = mapped_column(Integer)
    # Number of shuns
    shunned: Mapped[int] = mapped_column(Integer)
    # Timestamp of node first launch
    age: Mapped[int] = mapped_column(Integer)
    # Host ip/name for data and metrics ports
    host: Mapped[Optional[str]] = mapped_column(UnicodeText)

    def __init__(self, id, nodename, service, user, binary, version, 
                 root_dir, port, metrics_port, network,
                 wallet, peer_id, status, timestamp, records,
                 uptime, shunned, age, host):
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
        self.records = records
        self.uptime = uptime
        self.shunned = shunned
        self.age = age
        self.host = host

    def __repr__(self):
        return f'Node({self.id},"{self.nodename}","{self.service}","{self.user},"{self.binary}"'+\
            f',"{self.version}","{self.root_dir}",{self.port},{self.metrics_port}' + \
            f',"{self.network}","{self.wallet}","{self.peer_id}","{self.status}",{self.timestamp}' + \
            f',{self.records},{self.uptime},{self.shunned},{self.age},"{self.host}")'
    
    def __json__(self):
        return { "id": self.id, "nodename": f"{self.nodename}", "service": f"{self.service}",
            "user": f"{self.user}", "binary": f"{self.binary}", "version": f"{self.version}",
            "root_dir": f"{self.root_dir}", "port": self.port, "metrics_port": self.metrics_port,
            "network": f"{self.network}", "wallet": f"{self.wallet}", "peer_id": f"{self.peer_id}",
            "status": f"{self.status}", "timestamp": self.timestamp, "records": self.records,
            "uptime": self.uptime, "shunned": self.shunned, "age": self.age,
            "host": f"{self.host}" }
