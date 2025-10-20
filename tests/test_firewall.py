"""
Tests for firewall managers.

Tests the firewall abstraction layer, including UFW and null implementations.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from wnm.firewall import NullFirewall, UFWManager, get_firewall_manager
from wnm.firewall.factory import get_default_firewall_type


class TestNullFirewall:
    """Tests for NullFirewall (no-op implementation)"""

    def test_enable_port(self):
        """Test enabling port is a no-op"""
        firewall = NullFirewall()
        assert firewall.enable_port(55001) is True
        assert firewall.enable_port(55002, protocol="tcp") is True
        assert firewall.enable_port(55003, comment="test") is True

    def test_disable_port(self):
        """Test disabling port is a no-op"""
        firewall = NullFirewall()
        assert firewall.disable_port(55001) is True
        assert firewall.disable_port(55002, protocol="tcp") is True

    def test_is_enabled(self):
        """Test firewall is never enabled"""
        firewall = NullFirewall()
        assert firewall.is_enabled() is False

    def test_is_available(self):
        """Test firewall is always available"""
        firewall = NullFirewall()
        assert firewall.is_available() is True


class TestUFWManager:
    """Tests for UFWManager (Ubuntu firewall)"""

    @patch("shutil.which")
    def test_is_available_true(self, mock_which):
        """Test UFW is available when ufw command exists"""
        mock_which.return_value = "/usr/sbin/ufw"
        firewall = UFWManager()
        assert firewall.is_available() is True
        mock_which.assert_called_once_with("ufw")

    @patch("shutil.which")
    def test_is_available_false(self, mock_which):
        """Test UFW is not available when ufw command doesn't exist"""
        mock_which.return_value = None
        firewall = UFWManager()
        assert firewall.is_available() is False
        mock_which.assert_called_once_with("ufw")

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_is_enabled_true(self, mock_which, mock_run):
        """Test UFW is enabled when status shows active"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Status: active\nLogging: on"
        )

        firewall = UFWManager()
        assert firewall.is_enabled() is True

        mock_run.assert_called_once_with(
            ["sudo", "ufw", "status"], check=True, capture_output=True, text=True
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_is_enabled_false(self, mock_which, mock_run):
        """Test UFW is disabled when status shows inactive"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Status: inactive\nLogging: off"
        )

        firewall = UFWManager()
        assert firewall.is_enabled() is False

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_enable_port_success(self, mock_which, mock_run):
        """Test enabling a port successfully"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(returncode=0)

        firewall = UFWManager()
        assert firewall.enable_port(55001) is True

        mock_run.assert_called_once_with(
            ["sudo", "ufw", "allow", "55001/udp"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_enable_port_with_comment(self, mock_which, mock_run):
        """Test enabling a port with a comment"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(returncode=0)

        firewall = UFWManager()
        assert firewall.enable_port(55001, comment="antnode1") is True

        mock_run.assert_called_once_with(
            ["sudo", "ufw", "allow", "55001/udp", "comment", "antnode1"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_enable_port_tcp(self, mock_which, mock_run):
        """Test enabling a TCP port"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(returncode=0)

        firewall = UFWManager()
        assert firewall.enable_port(55001, protocol="tcp") is True

        mock_run.assert_called_once_with(
            ["sudo", "ufw", "allow", "55001/tcp"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_enable_port_not_available(self, mock_which, mock_run):
        """Test enabling a port when UFW is not available"""
        mock_which.return_value = None

        firewall = UFWManager()
        assert firewall.enable_port(55001) is False

        # Should not call subprocess.run
        mock_run.assert_not_called()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_enable_port_failure(self, mock_which, mock_run):
        """Test handling failure when enabling port"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.side_effect = Exception("Permission denied")

        firewall = UFWManager()
        assert firewall.enable_port(55001) is False

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_disable_port_success(self, mock_which, mock_run):
        """Test disabling a port successfully"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(returncode=0)

        firewall = UFWManager()
        assert firewall.disable_port(55001) is True

        mock_run.assert_called_once_with(
            ["sudo", "ufw", "delete", "allow", "55001/udp"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_disable_port_tcp(self, mock_which, mock_run):
        """Test disabling a TCP port"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(returncode=0)

        firewall = UFWManager()
        assert firewall.disable_port(55001, protocol="tcp") is True

        mock_run.assert_called_once_with(
            ["sudo", "ufw", "delete", "allow", "55001/tcp"],
            check=True,
            capture_output=True,
            text=True,
        )

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_disable_port_not_available(self, mock_which, mock_run):
        """Test disabling a port when UFW is not available"""
        mock_which.return_value = None

        firewall = UFWManager()
        assert firewall.disable_port(55001) is False

        # Should not call subprocess.run
        mock_run.assert_not_called()

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_disable_port_failure(self, mock_which, mock_run):
        """Test handling failure when disabling port"""
        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.side_effect = Exception("Permission denied")

        firewall = UFWManager()
        assert firewall.disable_port(55001) is False


class TestFirewallFactory:
    """Tests for firewall factory functions"""

    @patch("wnm.firewall.factory.UFWManager")
    def test_get_firewall_manager_ufw(self, mock_ufw_class):
        """Test creating UFW manager explicitly"""
        mock_ufw = MagicMock()
        mock_ufw_class.return_value = mock_ufw

        result = get_firewall_manager("ufw")

        assert result == mock_ufw
        mock_ufw_class.assert_called_once()

    def test_get_firewall_manager_null(self):
        """Test creating null firewall explicitly"""
        result = get_firewall_manager("null")
        assert isinstance(result, NullFirewall)

    def test_get_firewall_manager_disabled_alias(self):
        """Test 'disabled' is an alias for 'null'"""
        result = get_firewall_manager("disabled")
        assert isinstance(result, NullFirewall)

    def test_get_firewall_manager_invalid(self):
        """Test error on invalid firewall type"""
        with pytest.raises(ValueError, match="Unknown firewall type"):
            get_firewall_manager("invalid_type")

    @patch.dict(os.environ, {"WNM_FIREWALL_DISABLED": "1"})
    def test_default_firewall_disabled_env_var(self):
        """Test firewall disabled via environment variable"""
        result = get_default_firewall_type()
        assert result == "null"

    @patch.dict(os.environ, {"WNM_FIREWALL_DISABLED": "true"})
    def test_default_firewall_disabled_env_var_true(self):
        """Test firewall disabled via environment variable (true)"""
        result = get_default_firewall_type()
        assert result == "null"

    @patch.dict(os.environ, {"WNM_FIREWALL_DISABLED": "yes"})
    def test_default_firewall_disabled_env_var_yes(self):
        """Test firewall disabled via environment variable (yes)"""
        result = get_default_firewall_type()
        assert result == "null"

    @patch("wnm.firewall.factory.UFWManager")
    def test_default_firewall_ufw_available(self, mock_ufw_class):
        """Test default firewall detects UFW when available"""
        mock_ufw = MagicMock()
        mock_ufw.is_available.return_value = True
        mock_ufw_class.return_value = mock_ufw

        result = get_default_firewall_type()
        assert result == "ufw"

    @patch("wnm.firewall.factory.UFWManager")
    def test_default_firewall_ufw_not_available(self, mock_ufw_class):
        """Test default firewall falls back to null when UFW not available"""
        mock_ufw = MagicMock()
        mock_ufw.is_available.return_value = False
        mock_ufw_class.return_value = mock_ufw

        result = get_default_firewall_type()
        assert result == "null"

    @patch("wnm.firewall.factory.UFWManager")
    def test_get_firewall_manager_auto_detect(self, mock_ufw_class):
        """Test auto-detection when firewall_type is None"""
        mock_ufw = MagicMock()
        mock_ufw.is_available.return_value = True
        mock_ufw_class.return_value = mock_ufw

        # Should auto-detect and return UFW
        result = get_firewall_manager(None)
        assert result == mock_ufw


class TestProcessManagerFirewallIntegration:
    """Tests for process manager integration with firewall abstraction"""

    def test_process_manager_has_firewall(self):
        """Test that process managers receive a firewall instance"""
        from wnm.process_managers import SystemdManager

        manager = SystemdManager()
        assert hasattr(manager, "firewall")
        assert manager.firewall is not None

    def test_process_manager_firewall_null(self):
        """Test process manager can be configured with null firewall"""
        from wnm.process_managers import SystemdManager

        manager = SystemdManager(firewall_type="null")
        assert isinstance(manager.firewall, NullFirewall)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_process_manager_firewall_ufw(self, mock_which, mock_run):
        """Test process manager can be configured with UFW"""
        from wnm.process_managers import SystemdManager

        mock_which.return_value = "/usr/sbin/ufw"

        manager = SystemdManager(firewall_type="ufw")
        assert isinstance(manager.firewall, UFWManager)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_systemd_enable_firewall_port(self, mock_which, mock_run):
        """Test SystemdManager can enable firewall port through abstraction"""
        from wnm.process_managers import SystemdManager

        mock_which.return_value = "/usr/sbin/ufw"
        mock_run.return_value = MagicMock(returncode=0)

        manager = SystemdManager(firewall_type="ufw")
        result = manager.enable_firewall_port(55001)

        assert result is True
        # Verify ufw command was called
        assert any("ufw" in str(call) for call in mock_run.call_args_list)

    def test_docker_manager_uses_null_firewall(self):
        """Test DockerManager defaults to null firewall"""
        from wnm.process_managers import DockerManager

        manager = DockerManager()
        assert isinstance(manager.firewall, NullFirewall)

    def test_setsid_manager_can_use_ufw(self):
        """Test SetsidManager can use UFW when available"""
        from wnm.process_managers import SetsidManager

        manager = SetsidManager(firewall_type="ufw")
        assert isinstance(manager.firewall, UFWManager)
