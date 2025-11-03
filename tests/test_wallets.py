"""Tests for wallet resolution and weighted distribution."""

import pytest

from wnm.common import FAUCET
from wnm.wallets import (
    parse_weighted_wallets,
    resolve_wallet_name,
    select_wallet_for_node,
    validate_rewards_address,
)

# Test constants - use different address from FAUCET so we can tell them apart
DONATE_ADDRESS = "0xDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"  # Different from FAUCET
TEST_ADDRESS_1 = "0x1111111111111111111111111111111111111111"
TEST_ADDRESS_2 = "0x2222222222222222222222222222222222222222"


class TestResolveWalletName:
    """Tests for resolve_wallet_name function."""

    def test_resolve_donate_lowercase(self):
        """Test resolving 'donate' to donate address."""
        result = resolve_wallet_name("donate", DONATE_ADDRESS)
        assert result == DONATE_ADDRESS

    def test_resolve_donate_uppercase(self):
        """Test resolving 'DONATE' (case insensitive)."""
        result = resolve_wallet_name("DONATE", DONATE_ADDRESS)
        assert result == DONATE_ADDRESS

    def test_resolve_faucet_lowercase(self):
        """Test resolving 'faucet' to FAUCET constant."""
        result = resolve_wallet_name("faucet", DONATE_ADDRESS)
        assert result == FAUCET

    def test_resolve_faucet_uppercase(self):
        """Test resolving 'FAUCET' (case insensitive) to FAUCET constant."""
        result = resolve_wallet_name("FAUCET", DONATE_ADDRESS)
        assert result == FAUCET

    def test_resolve_faucet_mixed_case(self):
        """Test resolving 'FaUcEt' (mixed case) to FAUCET constant."""
        result = resolve_wallet_name("FaUcEt", DONATE_ADDRESS)
        assert result == FAUCET

    def test_resolve_ethereum_address(self):
        """Test that Ethereum addresses pass through unchanged."""
        result = resolve_wallet_name(TEST_ADDRESS_1, DONATE_ADDRESS)
        assert result == TEST_ADDRESS_1

    def test_resolve_ethereum_address_with_whitespace(self):
        """Test Ethereum address with whitespace is trimmed."""
        result = resolve_wallet_name(f"  {TEST_ADDRESS_1}  ", DONATE_ADDRESS)
        assert result == TEST_ADDRESS_1

    def test_resolve_invalid_name(self):
        """Test that invalid names raise ValueError."""
        with pytest.raises(ValueError, match="Invalid wallet identifier"):
            resolve_wallet_name("invalid_name", DONATE_ADDRESS)

    def test_resolve_invalid_address_format(self):
        """Test that invalid Ethereum address format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid wallet identifier"):
            resolve_wallet_name("0xINVALID", DONATE_ADDRESS)

    def test_resolve_short_address(self):
        """Test that short address raises ValueError."""
        with pytest.raises(ValueError, match="Invalid wallet identifier"):
            resolve_wallet_name("0x123", DONATE_ADDRESS)


class TestParseWeightedWallets:
    """Tests for parse_weighted_wallets function."""

    def test_single_wallet_no_weight(self):
        """Test single wallet without weight."""
        result = parse_weighted_wallets(TEST_ADDRESS_1, DONATE_ADDRESS)
        assert result == [(TEST_ADDRESS_1, 1)]

    def test_single_named_wallet(self):
        """Test single named wallet."""
        result = parse_weighted_wallets("donate", DONATE_ADDRESS)
        assert result == [(DONATE_ADDRESS, 1)]

    def test_single_wallet_with_weight(self):
        """Test single wallet with explicit weight."""
        result = parse_weighted_wallets(f"{TEST_ADDRESS_1}:100", DONATE_ADDRESS)
        assert result == [(TEST_ADDRESS_1, 100)]

    def test_multiple_wallets_with_weights(self):
        """Test multiple wallets with weights."""
        wallet_string = f"{TEST_ADDRESS_1}:100,{TEST_ADDRESS_2}:50"
        result = parse_weighted_wallets(wallet_string, DONATE_ADDRESS)
        assert result == [(TEST_ADDRESS_1, 100), (TEST_ADDRESS_2, 50)]

    def test_mixed_named_and_address_wallets(self):
        """Test mix of named wallets and addresses."""
        wallet_string = f"{TEST_ADDRESS_1}:100,faucet:1,donate:10"
        result = parse_weighted_wallets(wallet_string, DONATE_ADDRESS)
        expected = [
            (TEST_ADDRESS_1, 100),
            (FAUCET, 1),  # faucet resolves to FAUCET constant
            (DONATE_ADDRESS, 10),  # donate resolves to donate_address parameter
        ]
        assert result == expected

    def test_wallets_without_explicit_weights(self):
        """Test wallets in list without explicit weights default to 1."""
        wallet_string = f"{TEST_ADDRESS_1},{TEST_ADDRESS_2}"
        result = parse_weighted_wallets(wallet_string, DONATE_ADDRESS)
        assert result == [(TEST_ADDRESS_1, 1), (TEST_ADDRESS_2, 1)]

    def test_mixed_weights_and_no_weights(self):
        """Test mix of wallets with and without weights."""
        wallet_string = f"{TEST_ADDRESS_1}:100,{TEST_ADDRESS_2}"
        result = parse_weighted_wallets(wallet_string, DONATE_ADDRESS)
        assert result == [(TEST_ADDRESS_1, 100), (TEST_ADDRESS_2, 1)]

    def test_whitespace_handling(self):
        """Test that whitespace is properly handled."""
        wallet_string = f"  {TEST_ADDRESS_1} : 100 , {TEST_ADDRESS_2} : 50  "
        result = parse_weighted_wallets(wallet_string, DONATE_ADDRESS)
        assert result == [(TEST_ADDRESS_1, 100), (TEST_ADDRESS_2, 50)]

    def test_empty_string_raises_error(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_weighted_wallets("", DONATE_ADDRESS)

    def test_whitespace_only_raises_error(self):
        """Test whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_weighted_wallets("   ", DONATE_ADDRESS)

    def test_invalid_weight_format(self):
        """Test invalid weight format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid weight"):
            parse_weighted_wallets(f"{TEST_ADDRESS_1}:abc", DONATE_ADDRESS)

    def test_zero_weight_raises_error(self):
        """Test zero weight raises ValueError."""
        with pytest.raises(ValueError, match="Weight must be positive"):
            parse_weighted_wallets(f"{TEST_ADDRESS_1}:0", DONATE_ADDRESS)

    def test_negative_weight_raises_error(self):
        """Test negative weight raises ValueError."""
        with pytest.raises(ValueError, match="Weight must be positive"):
            parse_weighted_wallets(f"{TEST_ADDRESS_1}:-10", DONATE_ADDRESS)

    def test_invalid_wallet_in_list(self):
        """Test invalid wallet in list raises ValueError."""
        with pytest.raises(ValueError, match="Invalid wallet identifier"):
            parse_weighted_wallets(f"{TEST_ADDRESS_1}:100,invalid_wallet:50", DONATE_ADDRESS)


class TestSelectWalletForNode:
    """Tests for select_wallet_for_node function."""

    def test_single_wallet_always_returns_same(self):
        """Test single wallet always returns that wallet."""
        for _ in range(10):
            result = select_wallet_for_node(TEST_ADDRESS_1, DONATE_ADDRESS)
            assert result == TEST_ADDRESS_1

    def test_single_named_wallet(self):
        """Test single named wallet resolves correctly."""
        result = select_wallet_for_node("donate", DONATE_ADDRESS)
        assert result == DONATE_ADDRESS

    def test_weighted_selection_returns_valid_wallet(self):
        """Test weighted selection returns one of the valid wallets."""
        wallet_string = f"{TEST_ADDRESS_1}:100,{TEST_ADDRESS_2}:50"
        result = select_wallet_for_node(wallet_string, DONATE_ADDRESS)
        assert result in [TEST_ADDRESS_1, TEST_ADDRESS_2]

    def test_deterministic_with_seed(self):
        """Test selection is deterministic with same seed."""
        wallet_string = f"{TEST_ADDRESS_1}:100,{TEST_ADDRESS_2}:50"

        result1 = select_wallet_for_node(wallet_string, DONATE_ADDRESS, seed=42)
        result2 = select_wallet_for_node(wallet_string, DONATE_ADDRESS, seed=42)

        assert result1 == result2

    def test_distribution_respects_weights(self):
        """Test that distribution roughly respects weights over many selections."""
        wallet_string = f"{TEST_ADDRESS_1}:90,{TEST_ADDRESS_2}:10"

        counts = {TEST_ADDRESS_1: 0, TEST_ADDRESS_2: 0}

        # Run many selections
        for i in range(1000):
            result = select_wallet_for_node(wallet_string, DONATE_ADDRESS, seed=i)
            counts[result] += 1

        # Check that ADDRESS_1 appears roughly 9x more than ADDRESS_2
        # Using generous bounds to account for randomness
        ratio = counts[TEST_ADDRESS_1] / counts[TEST_ADDRESS_2]
        assert 5 < ratio < 15, f"Expected ratio ~9, got {ratio}"

    def test_equal_weights_distribution(self):
        """Test equal weights produce roughly equal distribution."""
        wallet_string = f"{TEST_ADDRESS_1}:1,{TEST_ADDRESS_2}:1"

        counts = {TEST_ADDRESS_1: 0, TEST_ADDRESS_2: 0}

        # Run many selections
        for i in range(1000):
            result = select_wallet_for_node(wallet_string, DONATE_ADDRESS, seed=i)
            counts[result] += 1

        # Check roughly equal (within 30%)
        ratio = counts[TEST_ADDRESS_1] / counts[TEST_ADDRESS_2]
        assert 0.7 < ratio < 1.3, f"Expected ratio ~1, got {ratio}"

    def test_named_wallets_in_weighted_list(self):
        """Test named wallets work in weighted lists."""
        wallet_string = f"{TEST_ADDRESS_1}:100,faucet:1"
        result = select_wallet_for_node(wallet_string, DONATE_ADDRESS)
        assert result in [TEST_ADDRESS_1, FAUCET]  # faucet resolves to FAUCET constant

    def test_invalid_wallet_string_raises_error(self):
        """Test invalid wallet string raises ValueError."""
        with pytest.raises(ValueError):
            select_wallet_for_node("invalid_wallet", DONATE_ADDRESS)


class TestValidateRewardsAddress:
    """Tests for validate_rewards_address function."""

    def test_valid_single_address(self):
        """Test validation of single valid address."""
        is_valid, error = validate_rewards_address(TEST_ADDRESS_1, DONATE_ADDRESS)
        assert is_valid is True
        assert error is None

    def test_valid_named_wallet(self):
        """Test validation of named wallet."""
        is_valid, error = validate_rewards_address("donate", DONATE_ADDRESS)
        assert is_valid is True
        assert error is None

    def test_valid_weighted_list(self):
        """Test validation of weighted wallet list."""
        wallet_string = f"{TEST_ADDRESS_1}:100,faucet:1,donate:10"
        is_valid, error = validate_rewards_address(wallet_string, DONATE_ADDRESS)
        assert is_valid is True
        assert error is None

    def test_invalid_address_format(self):
        """Test validation fails for invalid address."""
        is_valid, error = validate_rewards_address("0xINVALID", DONATE_ADDRESS)
        assert is_valid is False
        assert error is not None
        assert "Invalid wallet identifier" in error

    def test_invalid_weight_format(self):
        """Test validation fails for invalid weight."""
        is_valid, error = validate_rewards_address(f"{TEST_ADDRESS_1}:abc", DONATE_ADDRESS)
        assert is_valid is False
        assert error is not None

    def test_empty_string(self):
        """Test validation fails for empty string."""
        is_valid, error = validate_rewards_address("", DONATE_ADDRESS)
        assert is_valid is False
        assert error is not None
