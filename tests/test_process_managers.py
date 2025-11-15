"""Tests for process managers (systemd, docker, setsid, etc.)"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from wnm.common import DEAD, RUNNING, STOPPED
from wnm.models import Node
from wnm.process_managers import (
    DockerManager,
    LaunchdManager,
    SetsidManager,
    SystemdManager,
    get_default_manager_type,
    get_process_manager,
)
from wnm.process_managers.base import NodeProcess


@pytest.fixture
def mock_node():
    """Create a mock node for testing"""
    node = Mock(spec=Node)
    node.id = 1
    node.node_name = "0001"
    node.service = "antnode0001.service"
    node.root_dir = "/tmp/test_node/antnode0001"
    node.port = 55001
    node.metrics_port = 13001
    node.wallet = "0x1234567890abcdef"
    node.network = "evm-arbitrum-one"
    node.environment = ""
    node.binary = "/tmp/test_node/antnode0001/antnode"
    return node


class TestProcessManagerFactory:
    """Tests for ProcessManager factory"""

    def test_get_systemd_manager(self):
        """Test getting SystemdManager from factory"""
        manager = get_process_manager("systemd")
        assert isinstance(manager, SystemdManager)

    def test_get_docker_manager(self):
        """Test getting DockerManager from factory"""
        manager = get_process_manager("docker")
        assert isinstance(manager, DockerManager)

    def test_get_setsid_manager(self):
        """Test getting SetsidManager from factory"""
        manager = get_process_manager("setsid")
        assert isinstance(manager, SetsidManager)

    def test_get_launchd_manager(self):
        """Test getting LaunchdManager from factory"""
        manager = get_process_manager("launchd")
        assert isinstance(manager, LaunchdManager)

    def test_get_antctl_manager(self):
        """Test getting AntctlManager from factory"""
        from wnm.process_managers.antctl_manager import AntctlManager

        manager = get_process_manager("antctl+user")
        assert isinstance(manager, AntctlManager)
        assert manager.use_sudo is False

        manager = get_process_manager("antctl+sudo")
        assert isinstance(manager, AntctlManager)
        assert manager.use_sudo is True

    def test_unknown_manager_type(self):
        """Test error handling for unknown manager type"""
        with pytest.raises(ValueError, match="Unsupported manager type"):
            get_process_manager("unknown")

    def test_get_default_manager_type(self):
        """Test getting default manager type"""
        manager_type = get_default_manager_type()
        assert manager_type in ["systemd", "setsid", "docker", "launchd"]


class TestSystemdManager:
    """Tests for SystemdManager"""

    @patch("subprocess.run")
    def test_start_node(self, mock_run, mock_node):
        """Test starting a systemd node"""
        mock_run.return_value = Mock(returncode=0, stdout="")
        manager = SystemdManager()
        result = manager.start_node(mock_node)
        assert result is True
        # Verify systemctl start was called
        assert any("systemctl" in str(call) for call in mock_run.call_args_list)

    @patch("subprocess.run")
    def test_stop_node(self, mock_run, mock_node):
        """Test stopping a systemd node"""
        mock_run.return_value = Mock(returncode=0)
        manager = SystemdManager()
        result = manager.stop_node(mock_node)
        assert result is True
        # Verify systemctl stop was called
        assert any("systemctl" in str(call) for call in mock_run.call_args_list)

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_get_status_running(self, mock_isdir, mock_run, mock_node):
        """Test getting systemd node status when running"""
        mock_isdir.return_value = True
        mock_run.return_value = Mock(
            returncode=0, stdout="MainPID=1234\nActiveState=active\n"
        )
        manager = SystemdManager()
        status = manager.get_status(mock_node)
        assert isinstance(status, NodeProcess)
        assert status.node_id == 1
        assert status.status == RUNNING
        assert status.pid == 1234

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_get_status_stopped(self, mock_isdir, mock_run, mock_node):
        """Test getting systemd node status when stopped"""
        mock_isdir.return_value = True
        mock_run.return_value = Mock(
            returncode=0, stdout="MainPID=0\nActiveState=inactive\n"
        )
        manager = SystemdManager()
        status = manager.get_status(mock_node)
        assert status.status == STOPPED
        assert status.pid is None

    @patch("subprocess.run")
    def test_remove_node(self, mock_run, mock_node):
        """Test removing a systemd node"""
        mock_run.return_value = Mock(returncode=0)
        manager = SystemdManager()
        result = manager.remove_node(mock_node)
        assert result is True
        # Verify cleanup commands were called
        assert mock_run.call_count >= 2  # stop + rm + daemon-reload

    def test_enable_firewall_port(self):
        """Test enabling firewall port delegates to firewall manager"""
        manager = SystemdManager()
        # Mock the firewall manager
        manager.firewall = Mock()
        manager.firewall.enable_port = Mock(return_value=True)

        result = manager.enable_firewall_port(55001)

        assert result is True
        manager.firewall.enable_port.assert_called_once_with(55001, "udp", None)

    @patch("subprocess.run")
    def test_disable_firewall_port(self, mock_run):
        """Test disabling firewall port"""
        mock_run.return_value = Mock(returncode=0)
        manager = SystemdManager()
        result = manager.disable_firewall_port(55001)
        assert result is True


class TestDockerManager:
    """Tests for DockerManager"""

    @patch("subprocess.run")
    def test_start_container(self, mock_run, mock_node):
        """Test starting a Docker container"""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = DockerManager()
        result = manager.start_node(mock_node)
        assert result is True
        # Verify docker start was called
        assert any("docker" in str(call) for call in mock_run.call_args_list)

    @patch("subprocess.run")
    def test_stop_container(self, mock_run, mock_node):
        """Test stopping a Docker container"""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = DockerManager()
        result = manager.stop_node(mock_node)
        assert result is True
        # Verify docker stop was called
        assert any("docker" in str(call) for call in mock_run.call_args_list)

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_get_status_running(self, mock_isdir, mock_run, mock_node):
        """Test getting Docker container status when running"""
        mock_isdir.return_value = True
        mock_run.return_value = Mock(
            returncode=0, stdout="running|1234|abc123def456\n", stderr=""
        )
        manager = DockerManager()
        status = manager.get_status(mock_node)
        assert status.status == RUNNING
        assert status.pid == 1234
        assert status.container_id == "abc123def456"

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_get_status_stopped(self, mock_isdir, mock_run, mock_node):
        """Test getting Docker container status when stopped"""
        mock_isdir.return_value = True
        # Container doesn't exist (CalledProcessError, not Exception)
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "docker")
        manager = DockerManager()
        status = manager.get_status(mock_node)
        assert status.status == STOPPED

    @patch("subprocess.run")
    def test_remove_container(self, mock_run, mock_node):
        """Test removing a Docker container"""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = DockerManager()
        with patch("shutil.rmtree"):  # Mock directory removal
            result = manager.remove_node(mock_node)
        assert result is True

    def test_firewall_operations_noop(self):
        """Test that firewall operations are no-op for Docker"""
        manager = DockerManager()
        assert manager.enable_firewall_port(55001) is True
        assert manager.disable_firewall_port(55001) is True


class TestSetsidManager:
    """Tests for SetsidManager"""

    def test_pid_file_path(self, mock_node):
        """Test PID file path generation"""
        manager = SetsidManager()
        pid_file = manager._get_pid_file(mock_node)
        assert str(pid_file) == f"{mock_node.root_dir}/node.pid"

    @patch("psutil.pid_exists")
    def test_write_read_pid_file(self, mock_pid_exists, mock_node):
        """Test PID file creation and reading"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_node.root_dir = tmpdir
            manager = SetsidManager()

            # Write PID
            manager._write_pid_file(mock_node, 12345)

            # Mock that PID exists
            mock_pid_exists.return_value = True

            # Read it back
            pid = manager._read_pid_file(mock_node)
            assert pid == 12345

            # Verify file was created
            pid_file = Path(tmpdir) / "node.pid"
            assert pid_file.exists()

    @patch("wnm.process_managers.setsid_manager.subprocess.Popen")
    @patch("wnm.process_managers.setsid_manager.psutil.process_iter")
    @patch("wnm.process_managers.setsid_manager.shutil.which")
    def test_start_node(self, mock_which, mock_process_iter, mock_popen, mock_node):
        """Test starting a setsid node"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_node.root_dir = tmpdir

            # Create mock binary
            binary = Path(tmpdir) / "antnode"
            binary.touch()
            binary.chmod(0o755)

            # Mock which to return None (ufw not available)
            mock_which.return_value = None

            # Mock process
            mock_process = Mock()
            mock_process.poll.return_value = None  # Process is running
            mock_process.pid = 99999
            mock_popen.return_value = mock_process

            # Mock process_iter to find our process
            mock_proc_info = Mock()
            mock_proc_info.info = {
                "pid": 12345,
                "cmdline": ["antnode", "--port", str(mock_node.port)],
            }
            mock_process_iter.return_value = [mock_proc_info]

            manager = SetsidManager()
            result = manager.start_node(mock_node)
            assert result is True

    @patch("wnm.process_managers.setsid_manager.psutil.Process")
    @patch("wnm.process_managers.setsid_manager.psutil.pid_exists")
    @patch("wnm.process_managers.setsid_manager.shutil.which")
    def test_stop_node(
        self, mock_which, mock_pid_exists, mock_process_class, mock_node
    ):
        """Test stopping a setsid node"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_node.root_dir = tmpdir

            # Mock which to return None (ufw not available)
            mock_which.return_value = None

            # Create PID file and mock that PID exists
            manager = SetsidManager()
            manager._write_pid_file(mock_node, 12345)
            mock_pid_exists.return_value = True

            # Mock process
            mock_process = Mock()
            mock_process.wait = Mock()
            mock_process_class.return_value = mock_process

            result = manager.stop_node(mock_node)
            assert result is True
            mock_process.terminate.assert_called_once()

    @patch("psutil.pid_exists")
    @patch("os.path.isdir")
    def test_get_status(self, mock_isdir, mock_pid_exists, mock_node):
        """Test getting setsid node status"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_node.root_dir = tmpdir
            mock_isdir.return_value = True

            manager = SetsidManager()

            # No PID file = stopped
            status = manager.get_status(mock_node)
            assert status.status == STOPPED

            # Create PID file
            manager._write_pid_file(mock_node, 12345)
            mock_pid_exists.return_value = False  # Process doesn't exist

            status = manager.get_status(mock_node)
            assert status.status == STOPPED

    def test_firewall_operations_best_effort(self):
        """Test that firewall operations are best-effort for setsid"""
        manager = SetsidManager()
        # Should not raise even if firewall commands fail
        assert manager.enable_firewall_port(55001) is True
        assert manager.disable_firewall_port(55001) is True


class TestLaunchdManager:
    """Tests for LaunchdManager (macOS launchd)"""

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.makedirs")
    @patch("shutil.copy2")
    @patch("os.chmod")
    @patch("builtins.open", create=True)
    def test_create_node(
        self,
        mock_open,
        mock_chmod,
        mock_copy,
        mock_makedirs,
        mock_exists,
        mock_run,
        mock_node,
    ):
        """Test creating a launchd node"""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        mock_open.return_value.__enter__ = Mock()
        mock_open.return_value.__exit__ = Mock()

        manager = LaunchdManager()
        result = manager.create_node(mock_node, "/usr/local/bin/antnode")

        assert result is not None
        assert isinstance(result, NodeProcess)
        assert result.node_id == mock_node.id
        # Verify launchctl load was called
        assert any(
            "launchctl" in str(call) and "load" in str(call)
            for call in mock_run.call_args_list
        )
        # Verify plist file was written
        mock_open.assert_called()

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_start_node(self, mock_exists, mock_run, mock_node):
        """Test starting a launchd node"""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        manager = LaunchdManager()
        result = manager.start_node(mock_node)

        assert result is True
        # Verify launchctl load was called
        assert any(
            "launchctl" in str(call) and "load" in str(call)
            for call in mock_run.call_args_list
        )

    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_stop_node(self, mock_exists, mock_run, mock_node):
        """Test stopping a launchd node"""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        manager = LaunchdManager()
        result = manager.stop_node(mock_node)

        assert result is True
        # Verify launchctl unload was called
        assert any(
            "launchctl" in str(call) and "unload" in str(call)
            for call in mock_run.call_args_list
        )

    @patch("subprocess.run")
    def test_restart_node(self, mock_run, mock_node):
        """Test restarting a launchd node"""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        manager = LaunchdManager()
        result = manager.restart_node(mock_node)

        assert result is True
        # Verify launchctl kickstart was called
        assert any(
            "launchctl" in str(call) and "kickstart" in str(call)
            for call in mock_run.call_args_list
        )

    @patch("subprocess.run")
    @patch("os.getuid")
    def test_get_status_running(self, mock_getuid, mock_run, mock_node):
        """Test getting launchd node status when running"""
        mock_getuid.return_value = 501
        mock_run.return_value = Mock(
            returncode=0, stdout='"PID" = 12345;\n"LastExitStatus" = 0;\n', stderr=""
        )

        manager = LaunchdManager()
        status = manager.get_status(mock_node)

        assert isinstance(status, NodeProcess)
        assert status.node_id == 1
        assert status.status == RUNNING
        assert status.pid == 12345

    @patch("subprocess.run")
    @patch("os.getuid")
    def test_get_status_stopped(self, mock_getuid, mock_run, mock_node):
        """Test getting launchd node status when stopped"""
        mock_getuid.return_value = 501
        mock_run.return_value = Mock(
            returncode=0, stdout='"LastExitStatus" = 0;\n', stderr=""
        )

        manager = LaunchdManager()
        status = manager.get_status(mock_node)

        assert status.status == STOPPED
        assert status.pid is None

    @patch("subprocess.run")
    @patch("os.getuid")
    def test_get_status_not_found(self, mock_getuid, mock_run, mock_node):
        """Test getting status when service not found"""
        mock_getuid.return_value = 501
        mock_run.return_value = Mock(
            returncode=1, stdout="", stderr="Could not find service"
        )

        manager = LaunchdManager()
        status = manager.get_status(mock_node)

        assert status.status == STOPPED
        assert status.pid is None

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("shutil.rmtree")
    def test_remove_node(
        self, mock_rmtree, mock_remove, mock_exists, mock_run, mock_node
    ):
        """Test removing a launchd node"""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        manager = LaunchdManager()
        result = manager.remove_node(mock_node)

        assert result is True
        # Verify unload was called
        assert any(
            "launchctl" in str(call) and "unload" in str(call)
            for call in mock_run.call_args_list
        )
        # Verify cleanup
        mock_remove.assert_called()  # plist file removed
        assert mock_rmtree.call_count >= 1  # directories removed

    def test_plist_generation(self, mock_node):
        """Test that plist XML is generated correctly"""
        manager = LaunchdManager()
        plist_content = manager._generate_plist_content(mock_node, "/path/to/antnode")

        # Verify plist contains required keys
        assert "com.autonomi.antnode-1" in plist_content
        assert "ProgramArguments" in plist_content
        assert "RunAtLoad" in plist_content
        assert "KeepAlive" in plist_content
        assert str(mock_node.port) in plist_content
        assert str(mock_node.metrics_port) in plist_content
        assert mock_node.wallet in plist_content
        assert mock_node.network in plist_content
        # Verify --enable-metrics-server flag is NOT present
        assert "--enable-metrics-server" not in plist_content

    def test_service_label_generation(self, mock_node):
        """Test service label generation"""
        manager = LaunchdManager()
        label = manager._get_service_label(mock_node)
        assert label == "com.autonomi.antnode-1"

    @patch("os.getuid")
    def test_service_domain_generation(self, mock_getuid):
        """Test service domain generation"""
        mock_getuid.return_value = 501
        manager = LaunchdManager()
        domain = manager._get_service_domain()
        assert domain == "gui/501"

    def test_plist_path_generation(self, mock_node):
        """Test plist path generation"""
        manager = LaunchdManager()
        plist_path = manager._get_plist_path(mock_node)
        assert plist_path.endswith("/Library/LaunchAgents/com.autonomi.antnode-1.plist")

    def test_firewall_operations_best_effort(self):
        """Test that firewall operations work (use null firewall on macOS)"""
        manager = LaunchdManager()
        # Should not raise - macOS uses null firewall by default
        assert manager.enable_firewall_port(55001) is True
        assert manager.disable_firewall_port(55001) is True


class TestAntctlManager:
    """Tests for AntctlManager"""

    @patch("subprocess.run")
    def test_start_node(self, mock_run, mock_node):
        """Test starting an antctl node"""
        from wnm.process_managers.antctl_manager import AntctlManager

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = AntctlManager(mode="user")
        result = manager.start_node(mock_node)
        assert result is True
        # Verify antctl start was called
        assert any("antctl" in str(call) for call in mock_run.call_args_list)

    @patch("subprocess.run")
    def test_stop_node(self, mock_run, mock_node):
        """Test stopping an antctl node"""
        from wnm.process_managers.antctl_manager import AntctlManager

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = AntctlManager(mode="user")
        result = manager.stop_node(mock_node)
        assert result is True
        # Verify antctl stop was called
        assert any("antctl" in str(call) for call in mock_run.call_args_list)

    @patch("subprocess.run")
    def test_restart_node(self, mock_run, mock_node):
        """Test restarting an antctl node"""
        from wnm.process_managers.antctl_manager import AntctlManager

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = AntctlManager(mode="user")
        result = manager.restart_node(mock_node)
        assert result is True
        # Should call both stop and start
        assert mock_run.call_count >= 2

    @patch("subprocess.run")
    @patch("os.path.isdir")
    def test_get_status(self, mock_isdir, mock_run, mock_node):
        """Test getting antctl node status"""
        from wnm.process_managers.antctl_manager import AntctlManager
        from wnm.utils import read_node_metadata

        mock_isdir.return_value = True
        manager = AntctlManager(mode="user")

        with patch("wnm.process_managers.antctl_manager.read_node_metadata") as mock_read:
            # Node is stopped
            mock_read.return_value = {"status": STOPPED}
            status = manager.get_status(mock_node)
            assert status.status == STOPPED

    @patch("subprocess.run")
    def test_remove_node(self, mock_run, mock_node):
        """Test removing an antctl node"""
        from wnm.process_managers.antctl_manager import AntctlManager

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = AntctlManager(mode="user")
        result = manager.remove_node(mock_node)
        assert result is True
        # Verify antctl remove was called
        assert any("remove" in str(call) for call in mock_run.call_args_list)

    def test_service_name_extraction(self):
        """Test parsing antctl command output for service names"""
        from wnm.process_managers.antctl_manager import AntctlManager

        manager = AntctlManager(mode="user")

        # Test successful extraction
        output = "Service antnode1 created successfully"
        service_name = manager._extract_service_name_from_output(output)
        assert service_name == "antnode1"

        # Test with different format
        output = "Added antnode42"
        service_name = manager._extract_service_name_from_output(output)
        assert service_name == "antnode42"

        # Test failure case
        output = "No service name here"
        service_name = manager._extract_service_name_from_output(output)
        assert service_name is None

    @patch("subprocess.run")
    def test_survey_nodes(self, mock_run):
        """Test surveying nodes with antctl status --json"""
        from wnm.process_managers.antctl_manager import AntctlManager

        # Mock JSON output from antctl status
        json_output = {
            "nodes": [
                {
                    "service_name": "antnode1",
                    "status": "Running",
                    "data_dir_path": "/path/to/node1",
                    "log_dir_path": "/path/to/node1/logs",
                    "node_port": 55001,
                    "metrics_port": 13001,
                    "rewards_address": "0x1234",
                    "peer_id": "abc123",
                    "version": "0.4.7",
                    "antnode_path": "/path/to/antnode",
                    "network": "evm-arbitrum-one",
                }
            ],
            "daemon": None,
        }

        mock_run.return_value = Mock(
            returncode=0, stdout=json.dumps(json_output), stderr=""
        )

        manager = AntctlManager(mode="user")

        # Create mock machine_config
        class MockMachineConfig:
            host = "127.0.0.1"

        machine_config = MockMachineConfig()
        nodes = manager.survey_nodes(machine_config)

        assert len(nodes) == 1
        assert nodes[0]["service"] == "antnode1"
        assert nodes[0]["root_dir"] == "/path/to/node1"
        assert nodes[0]["log_dir"] == "/path/to/node1/logs"
        assert nodes[0]["port"] == 55001
        assert nodes[0]["metrics_port"] == 13001
        assert nodes[0]["manager_type"] == "antctl"

    @patch("subprocess.run")
    def test_teardown_cluster(self, mock_run):
        """Test tearing down cluster with antctl reset"""
        from wnm.process_managers.antctl_manager import AntctlManager

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        manager = AntctlManager(mode="user")
        result = manager.teardown_cluster()
        assert result is True
        # Verify antctl reset was called
        assert any("reset" in str(call) and "--force" in str(call) for call in mock_run.call_args_list)

    def test_mode_selection(self):
        """Test user vs sudo mode selection"""
        from wnm.process_managers.antctl_manager import AntctlManager

        # User mode
        manager = AntctlManager(mode="user")
        assert manager.use_sudo is False
        assert manager.antctl_cmd == ["antctl"]

        # Sudo mode
        manager = AntctlManager(mode="sudo")
        assert manager.use_sudo is True
        assert manager.antctl_cmd == ["sudo", "antctl"]

        # Default (user mode)
        manager = AntctlManager()
        assert manager.use_sudo is False
