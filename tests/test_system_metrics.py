"""Tests for platform-specific system metrics"""

import platform
import re
from unittest.mock import Mock, patch

import pytest

from wnm.config import load_anm_config, define_machine


class TestSystemStartTime:
    """Tests for system start time detection"""

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    @patch("subprocess.run")
    def test_macos_system_start_time(self, mock_run):
        """Test system start time detection on macOS using sysctl"""
        # Mock sysctl kern.boottime output
        mock_run.return_value = Mock(
            returncode=0,
            stdout="{ sec = 1234567890, usec = 123456 }".encode("utf-8")
        )

        # Import and call the function that uses system start time
        from wnm.utils import get_machine_metrics

        # Create a minimal mock for S() session
        mock_s = Mock()
        mock_session = Mock()
        mock_session.execute.return_value.all.return_value = []
        mock_s.return_value.__enter__ = Mock(return_value=mock_session)
        mock_s.return_value.__exit__ = Mock(return_value=None)

        # Mock psutil functions
        with patch("wnm.utils.psutil.cpu_percent") as mock_cpu:
            with patch("wnm.utils.psutil.virtual_memory") as mock_mem:
                with patch("wnm.utils.psutil.disk_usage") as mock_disk:
                    with patch("wnm.utils.psutil.disk_io_counters") as mock_io:
                        with patch("wnm.utils.os.getloadavg") as mock_load:
                            with patch("wnm.utils.shutil.which") as mock_which:
                                with patch("wnm.utils.psutil.net_io_counters") as mock_net_io:
                                    # Setup mocks
                                    mock_cpu.return_value = 25.0
                                    mock_mem.return_value = Mock(percent=50.0)
                                    mock_disk.return_value = Mock(percent=60.0, total=1000000000000)
                                    mock_io.return_value = Mock(read_bytes=1000, write_bytes=2000)
                                    mock_net_io.return_value = Mock(bytes_sent=1000, bytes_recv=2000)
                                    mock_load.return_value = (1.0, 1.5, 2.0)
                                    mock_which.return_value = "/usr/local/bin/antnode"

                                    # Call the function with S as parameter
                                    metrics = get_machine_metrics(mock_s, "/tmp/test", 90, 1000000000)

                                    # Verify system_start was parsed correctly
                                    assert metrics["system_start"] == 1234567890
                                    assert mock_run.called
                                    # Verify it called sysctl, not uptime (check first call)
                                    first_call_args = mock_run.call_args_list[0][0][0]
                                    assert "sysctl" in first_call_args

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
    @patch("subprocess.run")
    def test_linux_system_start_time(self, mock_run):
        """Test system start time detection on Linux using uptime --since"""
        # Mock uptime --since output
        mock_run.return_value = Mock(
            returncode=0,
            stdout="2024-01-15 10:30:45\n".encode("utf-8")
        )

        from wnm.utils import get_machine_metrics

        # Create a minimal mock for S() session
        mock_s = Mock()
        mock_session = Mock()
        mock_session.execute.return_value.all.return_value = []
        mock_s.return_value.__enter__ = Mock(return_value=mock_session)
        mock_s.return_value.__exit__ = Mock(return_value=None)

        # Mock psutil functions
        with patch("wnm.utils.psutil.cpu_percent") as mock_cpu:
            with patch("wnm.utils.psutil.virtual_memory") as mock_mem:
                with patch("wnm.utils.psutil.disk_usage") as mock_disk:
                    with patch("wnm.utils.psutil.disk_io_counters") as mock_io:
                        with patch("wnm.utils.os.getloadavg") as mock_load:
                            with patch("wnm.utils.shutil.which") as mock_which:
                                with patch("wnm.utils.psutil.net_io_counters") as mock_net_io:
                                    # Setup mocks
                                    mock_cpu.return_value = 25.0
                                    mock_mem.return_value = Mock(percent=50.0)
                                    mock_disk.return_value = Mock(percent=60.0, total=1000000000000)
                                    mock_io.return_value = Mock(read_bytes=1000, write_bytes=2000)
                                    mock_net_io.return_value = Mock(bytes_sent=1000, bytes_recv=2000)
                                    mock_load.return_value = (1.0, 1.5, 2.0)
                                    mock_which.return_value = "/usr/local/bin/antnode"

                                    # Call the function with S as parameter
                                    metrics = get_machine_metrics(mock_s, "/tmp/test", 90, 1000000000)

                                    # Verify system_start was parsed correctly
                                    assert metrics["system_start"] > 0
                                    assert mock_run.called
                                    # Verify it called uptime, not sysctl (check first call)
                                    first_call_args = mock_run.call_args_list[0][0][0]
                                    assert "uptime" in first_call_args


class TestCPUCount:
    """Tests for CPU count detection"""

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_macos_cpu_count(self):
        """Test CPU count detection on macOS using os.cpu_count()"""
        from wnm.config import load_anm_config

        # Create mock options with required attributes
        mock_options = Mock()
        mock_options.rewards_address = "0x1234567890123456789012345678901234567890"

        # Mock the config file not existing
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False

            # Call the function
            anm_config = load_anm_config(mock_options)

            # Verify CPU count is set and positive
            assert "cpu_count" in anm_config
            assert anm_config["cpu_count"] > 0
            # On macOS, should use os.cpu_count()
            import os
            assert anm_config["cpu_count"] == (os.cpu_count() or 1)

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
    def test_linux_cpu_count(self):
        """Test CPU count detection on Linux using sched_getaffinity"""
        from wnm.config import load_anm_config
        import os

        # Create mock options with required attributes
        mock_options = Mock()
        mock_options.rewards_address = "0x1234567890123456789012345678901234567890"

        # Mock the config file not existing
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False

            # Call the function
            anm_config = load_anm_config(mock_options)

            # Verify CPU count is set and positive
            assert "cpu_count" in anm_config
            assert anm_config["cpu_count"] > 0
            # On Linux, should use sched_getaffinity
            assert anm_config["cpu_count"] == len(os.sched_getaffinity(0))

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_macos_define_machine_cpu_count(self):
        """Test CPU count in define_machine on macOS"""
        from wnm import config
        import os

        # Create mock options with required rewards_address
        mock_options = Mock()
        mock_options.rewards_address = "0x1234567890abcdef1234567890abcdef12345678"
        mock_options.donate_address = "0x00455d78f850b0358E8cea5be24d415E01E107CF"
        mock_options.node_cap = 20
        mock_options.cpu_less_than = 80
        mock_options.mem_less_than = 80
        mock_options.hd_less_than = 80
        mock_options.cpu_remove = 85
        mock_options.mem_remove = 85
        mock_options.hd_remove = 85
        mock_options.desired_load_average = 2.0
        mock_options.max_load_average_allowed = 4.0
        mock_options.port_start = 55
        mock_options.node_storage = "/tmp/test"
        mock_options.network = "evm-arbitrum-one"
        mock_options.relay = False

        # Mock the database session to capture the machine dict
        captured_machine = {}
        with patch.object(config, 'S') as mock_S:
            mock_session = Mock()
            mock_S.return_value.__enter__.return_value = mock_session
            mock_S.return_value.__exit__.return_value = None

            def capture_machine(insert_obj, values):
                captured_machine.update(values[0])
                return Mock()

            mock_session.execute.side_effect = capture_machine
            mock_session.commit = Mock()

            # Call the function
            result = config.define_machine(mock_options)

        # Verify function returned True
        assert result is True

        # Verify CPU count in captured machine dict
        assert captured_machine["cpu_count"] > 0
        # On macOS, should use os.cpu_count()
        assert captured_machine["cpu_count"] == (os.cpu_count() or 1)

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
    def test_linux_define_machine_cpu_count(self):
        """Test CPU count in define_machine on Linux"""
        from wnm import config
        import os

        # Create mock options with required rewards_address
        mock_options = Mock()
        mock_options.rewards_address = "0x1234567890abcdef1234567890abcdef12345678"
        mock_options.donate_address = "0x00455d78f850b0358E8cea5be24d415E01E107CF"
        mock_options.node_cap = 20
        mock_options.cpu_less_than = 80
        mock_options.mem_less_than = 80
        mock_options.hd_less_than = 80
        mock_options.cpu_remove = 85
        mock_options.mem_remove = 85
        mock_options.hd_remove = 85
        mock_options.desired_load_average = 2.0
        mock_options.max_load_average_allowed = 4.0
        mock_options.port_start = 55
        mock_options.node_storage = "/tmp/test"
        mock_options.network = "evm-arbitrum-one"
        mock_options.relay = False

        # Mock the database session to capture the machine dict
        captured_machine = {}
        with patch.object(config, 'S') as mock_S:
            mock_session = Mock()
            mock_S.return_value.__enter__.return_value = mock_session
            mock_S.return_value.__exit__.return_value = None

            def capture_machine(insert_obj, values):
                captured_machine.update(values[0])
                return Mock()

            mock_session.execute.side_effect = capture_machine
            mock_session.commit = Mock()

            # Call the function
            result = config.define_machine(mock_options)

        # Verify function returned True
        assert result is True

        # Verify CPU count in captured machine dict
        assert captured_machine["cpu_count"] > 0
        # On Linux, should use sched_getaffinity
        assert captured_machine["cpu_count"] == len(os.sched_getaffinity(0))


class TestSystemMetricsIntegration:
    """Integration tests for system metrics on current platform"""

    def test_system_metrics_collection(self):
        """Test that system metrics can be collected on current platform"""
        from wnm.utils import get_machine_metrics

        # Create a minimal mock for S() session
        mock_s = Mock()
        mock_session = Mock()
        mock_session.execute.return_value.all.return_value = []
        mock_s.return_value.__enter__ = Mock(return_value=mock_session)
        mock_s.return_value.__exit__ = Mock(return_value=None)

        # Mock shutil.which to avoid sys.exit
        with patch("wnm.utils.shutil.which") as mock_which:
            mock_which.return_value = "/usr/local/bin/antnode"

            # Call the function with actual system calls and S as parameter
            metrics = get_machine_metrics(mock_s, "/tmp/test", 90, 1000000000)

            # Verify all expected metrics are present
            assert "system_start" in metrics
            assert metrics["system_start"] >= 0
            assert "used_cpu_percent" in metrics
            assert "used_mem_percent" in metrics
            assert "used_hd_percent" in metrics

    def test_cpu_count_detection(self):
        """Test that CPU count detection works on current platform"""
        from wnm.config import load_anm_config

        # Create mock options with required attributes
        mock_options = Mock()
        mock_options.rewards_address = "0x1234567890123456789012345678901234567890"

        # Mock the config file not existing
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False

            # Call the function
            anm_config = load_anm_config(mock_options)

            # Verify CPU count is set and positive
            assert "cpu_count" in anm_config
            assert anm_config["cpu_count"] > 0
            # Should work on any platform
            assert isinstance(anm_config["cpu_count"], int)
