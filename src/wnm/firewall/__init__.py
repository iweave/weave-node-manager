"""
Firewall management abstraction for WNM.

Provides a pluggable interface for firewall operations across different
firewall implementations (ufw, firewalld, iptables, or no-op).
"""

from wnm.firewall.base import FirewallManager
from wnm.firewall.factory import get_firewall_manager
from wnm.firewall.null_firewall import NullFirewall
from wnm.firewall.ufw_manager import UFWManager

__all__ = ["FirewallManager", "get_firewall_manager", "NullFirewall", "UFWManager"]
