"""Wallet address resolution and weighted distribution.

This module provides functionality for:
1. Resolving named wallets (faucet/donate) to actual addresses
2. Parsing weighted wallet lists
3. Selecting wallets based on weights for node assignment
"""

import logging
import random
import re
from typing import List, Optional, Tuple

from wnm.common import FAUCET


def resolve_wallet_name(name: str, donate_address: str) -> str:
    """Resolve named wallet to actual address.

    Args:
        name: Wallet name or address. Can be:
            - "faucet" (case-insensitive) -> FAUCET constant (not changeable by user)
            - "donate" (case-insensitive) -> donate_address from machine config (user can override)
            - Ethereum address (0x...) -> returned as-is
        donate_address: The donate address from machine config 

    Returns:
        Resolved Ethereum address

    Raises:
        ValueError: If name is neither a valid address nor known name
    """
    name_lower = name.lower().strip()

    # Check for named wallets
    if name_lower == "faucet":
        return FAUCET  # Always use the constant (not changeable)
    if name_lower == "donate":
        return donate_address  # Use machine config value (user can override)

    # Validate as Ethereum address (0x followed by 40 hex chars)
    if re.match(r"^0x[0-9A-Fa-f]{40}$", name.strip()):
        return name.strip()

    raise ValueError(
        f"Invalid wallet identifier: '{name}'. "
        f"Must be 'donate', 'faucet', or a valid Ethereum address (0x...)"
    )


def parse_weighted_wallets(
    wallet_string: str, donate_address: str
) -> List[Tuple[str, int]]:
    """Parse comma-separated weighted wallet list.

    Supports formats:
    - Single wallet: "0xABC" or "donate"
    - Weighted list: "0xABC:100,faucet:1,donate:10"

    Args:
        wallet_string: Wallet specification string
        donate_address: The donate address from machine config for resolving names

    Returns:
        List of (address, weight) tuples. For single wallet, weight=1.

    Raises:
        ValueError: If format is invalid or wallets cannot be resolved
    """
    if not wallet_string or not wallet_string.strip():
        raise ValueError("Wallet string cannot be empty")

    wallet_string = wallet_string.strip()

    # Check if this is a weighted list (contains comma or colon)
    if "," not in wallet_string and ":" not in wallet_string:
        # Single wallet without weight
        address = resolve_wallet_name(wallet_string, donate_address)
        return [(address, 1)]

    # Parse weighted list
    weighted_wallets = []
    parts = wallet_string.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check for weight suffix
        if ":" in part:
            wallet_part, weight_part = part.rsplit(":", 1)
            wallet_part = wallet_part.strip()
            weight_part = weight_part.strip()

            try:
                weight = int(weight_part)
            except ValueError:
                raise ValueError(f"Invalid weight in '{part}': {weight_part}")

            if weight <= 0:
                raise ValueError(f"Weight must be positive: {part}")

            address = resolve_wallet_name(wallet_part, donate_address)
            weighted_wallets.append((address, weight))
        else:
            # No weight specified, default to 1
            address = resolve_wallet_name(part, donate_address)
            weighted_wallets.append((address, 1))

    if not weighted_wallets:
        raise ValueError("No valid wallets found in wallet string")

    return weighted_wallets


def select_wallet_for_node(
    wallet_string: str, donate_address: str, seed: Optional[int] = None
) -> str:
    """Select a wallet address for a node based on weighted distribution.

    Uses random weighted selection to choose from the wallet list.
    Each node creation will randomly pick according to weights.

    Args:
        wallet_string: Wallet specification (single or weighted list)
        donate_address: The donate address from machine config
        seed: Optional random seed for deterministic testing

    Returns:
        Selected Ethereum address

    Raises:
        ValueError: If wallet_string is invalid
    """
    weighted_wallets = parse_weighted_wallets(wallet_string, donate_address)

    # If only one wallet, return it
    if len(weighted_wallets) == 1:
        return weighted_wallets[0][0]

    # Extract addresses and weights
    addresses = [addr for addr, _ in weighted_wallets]
    weights = [weight for _, weight in weighted_wallets]

    # Set seed if provided (for testing)
    if seed is not None:
        random.seed(seed)

    # Randomly select based on weights
    selected = random.choices(addresses, weights=weights, k=1)[0]

    logging.debug(
        f"Selected wallet {selected} from {len(weighted_wallets)} options "
        f"with weights {weights}"
    )

    return selected


def validate_rewards_address(
    rewards_address: str, donate_address: str
) -> Tuple[bool, Optional[str]]:
    """Validate a rewards address string.

    Args:
        rewards_address: The rewards address string to validate
        donate_address: The donate address for resolving named wallets

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    try:
        parse_weighted_wallets(rewards_address, donate_address)
        return (True, None)
    except ValueError as e:
        return (False, str(e))
