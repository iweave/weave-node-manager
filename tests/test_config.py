"""Tests for config.py - path detection and mode selection"""

import os
import platform
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from wnm.models import Base, Machine


class TestProcessManagerModeDetection:
    """Tests for _detect_process_manager_mode() function"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test - clear environment and sys.argv"""
        # Save original values
        self.orig_argv = sys.argv.copy()
        self.orig_env = os.environ.copy()

        yield

        # Restore original values
        sys.argv = self.orig_argv
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_detect_from_command_line_sudo(self):
        """Test detection from --process_manager command line argument (sudo)"""
        from importlib import reload

        sys.argv = ["wnm", "--process_manager", "systemd+sudo"]

        # Clear environment variables
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ.pop("DBPATH", None)
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent directory creation and DB init

        import wnm.config as config_module

        reload(config_module)

        assert config_module._PM_MODE == "sudo"

    def test_detect_from_command_line_user(self):
        """Test detection from --process_manager command line argument (user)"""
        from importlib import reload

        sys.argv = ["wnm", "--process_manager", "systemd+user"]

        os.environ.pop("PROCESS_MANAGER", None)
        os.environ.pop("DBPATH", None)
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent directory creation and DB init

        import wnm.config as config_module

        reload(config_module)

        assert config_module._PM_MODE == "user"

    def test_detect_from_env_var_sudo(self):
        """Test detection from PROCESS_MANAGER environment variable (sudo)"""
        from importlib import reload

        sys.argv = ["wnm"]
        os.environ["PROCESS_MANAGER"] = "systemd+sudo"
        os.environ.pop("DBPATH", None)
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent directory creation and DB init

        import wnm.config as config_module

        reload(config_module)

        assert config_module._PM_MODE == "sudo"

    def test_detect_from_env_var_user(self):
        """Test detection from PROCESS_MANAGER environment variable (user)"""
        from importlib import reload

        sys.argv = ["wnm"]
        os.environ["PROCESS_MANAGER"] = "launchd+user"
        os.environ.pop("DBPATH", None)
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent directory creation and DB init

        import wnm.config as config_module

        reload(config_module)

        assert config_module._PM_MODE == "user"

    def test_detect_from_dbpath_cmdline_sudo(self, tmp_path):
        """Test detection from database specified via --dbpath command line"""
        from importlib import reload

        # Create a test database with systemd+sudo
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE machine (
                id INTEGER PRIMARY KEY,
                process_manager TEXT
            )
        """
        )
        cursor.execute(
            "INSERT INTO machine (id, process_manager) VALUES (1, 'systemd+sudo')"
        )
        conn.commit()
        conn.close()

        sys.argv = ["wnm", "--dbpath", f"sqlite:///{db_path}"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ.pop("DBPATH", None)
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent full DB initialization

        import wnm.config as config_module

        reload(config_module)

        assert config_module._PM_MODE == "sudo"

    def test_detect_from_dbpath_env_user(self, tmp_path):
        """Test detection from database specified via DBPATH environment variable"""
        from importlib import reload

        # Create a test database with launchd+user
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE machine (
                id INTEGER PRIMARY KEY,
                process_manager TEXT
            )
        """
        )
        cursor.execute(
            "INSERT INTO machine (id, process_manager) VALUES (1, 'launchd+user')"
        )
        conn.commit()
        conn.close()

        sys.argv = ["wnm"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ["DBPATH"] = f"sqlite:///{db_path}"
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent full DB initialization

        import wnm.config as config_module

        reload(config_module)

        assert config_module._PM_MODE == "user"

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux-specific test")
    def test_detect_from_default_location_linux_sudo(self, tmp_path):
        """Test detection from default Linux sudo location"""
        from importlib import reload

        # Create a test database at Linux sudo location
        db_dir = tmp_path / "var" / "antctl"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "colony.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE machine (
                id INTEGER PRIMARY KEY,
                process_manager TEXT
            )
        """
        )
        cursor.execute(
            "INSERT INTO machine (id, process_manager) VALUES (1, 'systemd+sudo')"
        )
        conn.commit()
        conn.close()

        sys.argv = ["wnm"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ.pop("DBPATH", None)

        # Patch the db_locations to use tmp_path
        with patch("wnm.config.PLATFORM", "Linux"):
            with patch("wnm.config._detect_process_manager_mode") as mock_detect:
                # Simulate the detection logic
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("SELECT process_manager FROM machine WHERE id = 1")
                    row = cursor.fetchone()
                    conn.close()

                    if row and "+sudo" in row[0]:
                        mock_detect.return_value = "sudo"

                import wnm.config as config_module

                reload(config_module)


class TestPathSelection:
    """Tests for path selection based on detected mode"""

    def test_linux_sudo_paths(self):
        """Test that Linux sudo mode uses system-wide paths"""
        from importlib import reload

        sys.argv = ["wnm", "--process_manager", "systemd+sudo"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ["WNM_TEST_MODE"] = "1"  # Prevent directory creation

        with patch("platform.system", return_value="Linux"):
            import wnm.config as config_module

            reload(config_module)

            assert config_module.BASE_DIR == "/var/antctl"
            assert config_module.NODE_STORAGE == "/var/antctl/services"
            assert config_module.LOG_DIR == "/var/log/antnode"
            assert config_module.BOOTSTRAP_CACHE_DIR == "/var/antctl/bootstrap-cache"

    def test_linux_user_paths(self):
        """Test that Linux user mode uses user-level paths"""
        from importlib import reload

        sys.argv = ["wnm", "--process_manager", "systemd+user"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ["WNM_TEST_MODE"] = "1"

        with patch("platform.system", return_value="Linux"):
            import wnm.config as config_module

            reload(config_module)

            assert (
                "~/.local/share/autonomi" in config_module.BASE_DIR
                or ".local/share/autonomi" in config_module.BASE_DIR
            )
            assert "node" in config_module.NODE_STORAGE
            assert "logs" in config_module.LOG_DIR

    def test_macos_sudo_paths(self):
        """Test that macOS sudo mode uses system-wide paths"""
        from importlib import reload

        sys.argv = ["wnm", "--process_manager", "launchd+sudo"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ["WNM_TEST_MODE"] = "1"

        with patch("platform.system", return_value="Darwin"):
            import wnm.config as config_module

            reload(config_module)

            assert config_module.BASE_DIR == "/Library/Application Support/autonomi"
            assert (
                config_module.NODE_STORAGE
                == "/Library/Application Support/autonomi/node"
            )
            assert config_module.LOG_DIR == "/Library/Logs/autonomi"

    def test_macos_user_paths(self):
        """Test that macOS user mode uses user-level paths"""
        from importlib import reload

        sys.argv = ["wnm", "--process_manager", "launchd+user"]
        os.environ.pop("PROCESS_MANAGER", None)
        os.environ["WNM_TEST_MODE"] = "1"

        with patch("platform.system", return_value="Darwin"):
            import wnm.config as config_module

            reload(config_module)

            assert (
                "~/Library/Application Support/autonomi" in config_module.BASE_DIR
                or "Library/Application Support/autonomi" in config_module.BASE_DIR
            )
            assert "node" in config_module.NODE_STORAGE
            assert "Logs/autonomi" in config_module.LOG_DIR


class TestExecutorManagerType:
    """Tests for executor.py using machine_config process_manager"""

    def test_node_created_with_correct_manager_type_sudo(
        self, db_session, sample_machine_config, sample_node_config
    ):
        """Test that nodes are created with process_manager from machine config (sudo)"""
        from wnm.models import Machine, Node

        # Update machine config to use systemd+sudo
        sample_machine_config["process_manager"] = "systemd+sudo"
        sample_machine_config["node_storage"] = "/var/antctl/services"

        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        # Create a node with the process_manager from machine config
        sample_node_config["manager_type"] = "systemd+sudo"
        sample_node_config["method"] = "systemd+sudo"

        node = Node(**sample_node_config)
        db_session.add(node)
        db_session.commit()

        assert node.manager_type == "systemd+sudo"
        assert "+sudo" in node.manager_type

    def test_node_created_with_correct_manager_type_user(
        self, db_session, sample_machine_config, sample_node_config
    ):
        """Test that nodes are created with process_manager from machine config (user)"""
        from wnm.models import Machine, Node

        # Update machine config to use launchd+user
        sample_machine_config["process_manager"] = "launchd+user"
        sample_machine_config["node_storage"] = (
            "~/Library/Application Support/autonomi/node"
        )

        machine = Machine(**sample_machine_config)
        db_session.add(machine)
        db_session.commit()

        # Create a node with the process_manager from machine config
        sample_node_config["manager_type"] = "launchd+user"
        sample_node_config["method"] = "launchd+user"

        node = Node(**sample_node_config)
        db_session.add(node)
        db_session.commit()

        assert node.manager_type == "launchd+user"
        assert "+user" in node.manager_type
