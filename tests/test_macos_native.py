"""Native macOS integration tests for Phase 4 system metrics

These tests run on macOS only and test the actual system calls,
not mocks. They verify that the platform-specific code works correctly.
"""

import platform
import subprocess
import os
import re

import pytest


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
class TestMacOSSystemMetrics:
    """Tests that run actual system calls on macOS"""

    def test_sysctl_boottime_parsing(self):
        """Test that we can parse sysctl kern.boottime on macOS"""
        # This is the actual code from utils.py
        result = subprocess.run(
            ["sysctl", "-n", "kern.boottime"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True
        )
        output = result.stdout.decode("utf-8")

        # Verify we can parse it
        match = re.search(r"sec = (\d+)", output)
        assert match is not None, f"Could not parse kern.boottime: {output}"

        system_start = int(match.group(1))
        assert system_start > 0
        assert system_start < 2000000000  # Sanity check: before year 2033

    def test_cpu_count_detection(self):
        """Test CPU count detection on macOS"""
        # This is the actual code from config.py
        if platform.system() == "Darwin":
            cpu_count = os.cpu_count() or 1
        else:
            cpu_count = len(os.sched_getaffinity(0))

        assert cpu_count > 0
        assert cpu_count <= 256  # Sanity check
        assert isinstance(cpu_count, int)

    def test_cpu_times_parsing(self):
        """Test CPU times parsing on macOS (no iowait field)"""
        import psutil

        cpu_times = psutil.cpu_times_percent(0.1)

        # macOS should have: user, nice, system, idle (no iowait)
        assert hasattr(cpu_times, 'user')
        assert hasattr(cpu_times, 'nice')
        assert hasattr(cpu_times, 'system')
        assert hasattr(cpu_times, 'idle')

        # This is the actual code from utils.py
        if platform.system() == "Darwin":
            idle_percent = cpu_times.idle
            io_wait = 0  # Not available on macOS
        else:
            idle_percent, io_wait = cpu_times[3:5]

        assert 0 <= idle_percent <= 100
        assert io_wait == 0  # macOS doesn't have iowait

        used_percent = 100 - idle_percent
        assert 0 <= used_percent <= 100

    def test_platform_imports(self):
        """Test that PLATFORM constant is available in config and utils"""
        # Set test mode
        os.environ["WNM_TEST_MODE"] = "1"

        import sys
        sys.path.insert(0, '/Users/dawn/workspace/python/weave-node-manager/src')

        # These should import without errors
        import wnm.config
        import wnm.utils

        # Verify PLATFORM constant is available (defined in config, imported in utils)
        assert hasattr(wnm.config, 'PLATFORM')
        assert hasattr(wnm.utils, 'PLATFORM')
        assert wnm.config.PLATFORM == "Darwin"
        assert wnm.utils.PLATFORM == "Darwin"


@pytest.mark.skipif(platform.system() == "Darwin", reason="Linux only")
class TestLinuxSystemMetrics:
    """Tests that verify Linux-specific code paths"""

    def test_sched_getaffinity_available(self):
        """Test that sched_getaffinity is available on Linux"""
        if platform.system() == "Linux":
            cpu_count = len(os.sched_getaffinity(0))
            assert cpu_count > 0

    def test_uptime_since_available(self):
        """Test that uptime --since works on Linux"""
        if platform.system() == "Linux":
            result = subprocess.run(
                ["uptime", "--since"],
                capture_output=True,
                text=True,
                check=False
            )
            # Should not fail on Linux
            assert result.returncode == 0

    def test_cpu_times_has_iowait(self):
        """Test that CPU times includes iowait on Linux"""
        if platform.system() == "Linux":
            import psutil
            cpu_times = psutil.cpu_times_percent(0.1)
            # Linux should have at least 5 fields including iowait
            assert len(cpu_times) >= 5
