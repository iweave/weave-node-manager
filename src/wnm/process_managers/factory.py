"""
Factory for creating process manager instances.

Provides a centralized way to instantiate the appropriate process manager
based on the manager type.
"""

import logging

from wnm.process_managers.antctl_manager import AntctlManager
from wnm.process_managers.base import ProcessManager
from wnm.process_managers.docker_manager import DockerManager
from wnm.process_managers.launchd_manager import LaunchdManager
from wnm.process_managers.setsid_manager import SetsidManager
from wnm.process_managers.systemd_manager import SystemdManager


def get_process_manager(
    manager_type: str, session_factory=None, **kwargs
) -> ProcessManager:
    """
    Get a process manager instance for the specified type.

    Args:
        manager_type: Type of process manager (e.g., "systemd+sudo", "systemd+user", "setsid", etc.)
        session_factory: SQLAlchemy session factory for database operations
        **kwargs: Additional arguments to pass to the manager constructor

    Returns:
        ProcessManager instance

    Raises:
        ValueError: If manager_type is not supported
    """
    # Parse manager type (e.g., "systemd+sudo" -> ("systemd", "sudo"))
    if "+" in manager_type:
        base_type, mode = manager_type.split("+", 1)
    else:
        base_type = manager_type
        mode = None

    managers = {
        "systemd": SystemdManager,
        "docker": DockerManager,
        "setsid": SetsidManager,
        "launchd": LaunchdManager,
        "antctl": AntctlManager,
    }

    manager_class = managers.get(base_type)
    if not manager_class:
        supported = ", ".join(managers.keys())
        raise ValueError(
            f"Unsupported manager type: {base_type}. "
            f"Supported types: {supported}"
        )

    # Pass the mode to the manager constructor
    if mode:
        kwargs["mode"] = mode

    logging.debug(f"Creating {manager_type} process manager")
    return manager_class(session_factory=session_factory, **kwargs)


def get_default_manager_type() -> str:
    """
    Determine the default process manager type for the current system.

    Returns:
        Default manager type string ("systemd", "setsid", etc.)
    """
    import platform
    import shutil

    system = platform.system()

    # Linux: prefer systemd if available
    if system == "Linux":
        if shutil.which("systemctl"):
            return "systemd"
        return "setsid"

    # macOS: use launchd for native macOS support
    if system == "Darwin":
        return "launchd"

    # Windows: not supported
    if system == "Windows":
        raise RuntimeError("Windows is not currently supported")

    # Unknown system: fall back to setsid
    logging.warning(f"Unknown system {system}, defaulting to setsid manager")
    return "setsid"
