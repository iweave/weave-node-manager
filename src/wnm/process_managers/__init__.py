"""
Process managers for node lifecycle management.

Supports multiple backends: systemd, docker, setsid, antctl, launchd
"""

from wnm.process_managers.base import NodeProcess, ProcessManager
from wnm.process_managers.docker_manager import DockerManager
from wnm.process_managers.factory import get_default_manager_type, get_process_manager
from wnm.process_managers.launchd_manager import LaunchdManager
from wnm.process_managers.setsid_manager import SetsidManager
from wnm.process_managers.systemd_manager import SystemdManager

__all__ = [
    "NodeProcess",
    "ProcessManager",
    "get_process_manager",
    "get_default_manager_type",
    "SystemdManager",
    "DockerManager",
    "SetsidManager",
    "LaunchdManager",
]
