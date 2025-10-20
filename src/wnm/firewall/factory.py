"""
Factory for creating firewall manager instances.

Provides auto-detection of available firewall implementations
and a factory function for creating the appropriate manager.
"""

import logging
import os

from wnm.firewall.base import FirewallManager
from wnm.firewall.null_firewall import NullFirewall
from wnm.firewall.ufw_manager import UFWManager


def get_default_firewall_type() -> str:
    """
    Auto-detect the best firewall manager for this system.

    Checks for available firewall tools in priority order:
    1. UFW (Ubuntu/Debian)
    2. Firewalld (RHEL/Fedora) - not yet implemented
    3. Iptables (Linux fallback) - not yet implemented
    4. NullFirewall (disabled/unavailable)

    Returns:
        Firewall type name: "ufw", "firewalld", "iptables", or "null"
    """
    # Check if firewall is disabled via environment variable
    if os.environ.get("WNM_FIREWALL_DISABLED", "").lower() in ("1", "true", "yes"):
        logging.info("Firewall disabled via WNM_FIREWALL_DISABLED environment variable")
        return "null"

    # Try UFW first (most common on Ubuntu/Debian)
    ufw = UFWManager()
    if ufw.is_available():
        logging.debug("Auto-detected UFW firewall")
        return "ufw"

    # TODO: Add firewalld detection
    # firewalld = FirewalldManager()
    # if firewalld.is_available():
    #     logging.debug("Auto-detected firewalld")
    #     return "firewalld"

    # TODO: Add iptables detection
    # iptables = IptablesManager()
    # if iptables.is_available():
    #     logging.debug("Auto-detected iptables")
    #     return "iptables"

    # Default to null firewall if nothing available
    logging.warning("No firewall implementation available, using NullFirewall")
    return "null"


def get_firewall_manager(firewall_type: str = None) -> FirewallManager:
    """
    Create a firewall manager instance.

    Args:
        firewall_type: Type of firewall ("ufw", "firewalld", "iptables", "null")
                      If None, auto-detects best available option

    Returns:
        FirewallManager instance

    Raises:
        ValueError: If firewall_type is not recognized
    """
    if firewall_type is None:
        firewall_type = get_default_firewall_type()

    firewall_type = firewall_type.lower()

    managers = {
        "ufw": UFWManager,
        "null": NullFirewall,
        "disabled": NullFirewall,  # Alias for null
        # TODO: Add when implemented
        # "firewalld": FirewalldManager,
        # "iptables": IptablesManager,
    }

    if firewall_type not in managers:
        raise ValueError(
            f"Unknown firewall type: {firewall_type}. "
            f"Available: {', '.join(managers.keys())}"
        )

    manager_class = managers[firewall_type]
    manager = manager_class()

    logging.debug(f"Created firewall manager: {firewall_type}")
    return manager
