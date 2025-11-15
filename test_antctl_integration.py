#!/usr/bin/env python3
"""
Integration test for AntctlManager with real antctl installation.

This script tests the AntctlManager against a real antctl installation.
Run this manually to verify the implementation works correctly.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Set test mode to skip DB init during import
os.environ["WNM_TEST_MODE"] = "1"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from wnm.process_managers.antctl_manager import AntctlManager
from wnm.common import RUNNING, STOPPED, DEAD

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')


def test_antctl_installation():
    """Test that antctl is installed and accessible"""
    print("\n=== Testing antctl installation ===")
    manager = AntctlManager(mode="user")

    try:
        result = manager._run_antctl(["--version"])
        print(f"✓ antctl is installed: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("✗ antctl not found in PATH")
        return False
    except Exception as e:
        print(f"✗ Error running antctl: {e}")
        return False


def test_status_json_parsing():
    """Test parsing of antctl status --json output"""
    print("\n=== Testing status JSON parsing ===")
    manager = AntctlManager(mode="user")

    try:
        result = manager._run_antctl(["status", "--json"])
        nodes_data = json.loads(result.stdout)
        print(f"✓ Successfully parsed JSON status output")
        print(f"  Found {len(nodes_data.get('nodes', []))} nodes")

        # Print first node details if available
        if nodes_data.get("nodes"):
            node = nodes_data["nodes"][0]
            print(f"\n  First node details:")
            print(f"    Service name: {node.get('service_name')}")
            print(f"    Status: {node.get('status')}")
            print(f"    Data dir: {node.get('data_dir_path')}")
            print(f"    Log dir: {node.get('log_dir_path')}")
            print(f"    Node port: {node.get('node_port')}")
            print(f"    Metrics port: {node.get('metrics_port')}")
            print(f"    Rewards address: {node.get('rewards_address')}")
            print(f"    Version: {node.get('version')}")

        return True
    except Exception as e:
        print(f"✗ Error parsing status JSON: {e}")
        return False


def test_survey_nodes():
    """Test survey_nodes() method"""
    print("\n=== Testing survey_nodes() ===")
    manager = AntctlManager(mode="user")

    # Create a mock machine_config
    class MockMachineConfig:
        host = "127.0.0.1"

    machine_config = MockMachineConfig()

    try:
        nodes = manager.survey_nodes(machine_config)
        print(f"✓ survey_nodes() returned {len(nodes)} nodes")

        if nodes:
            for i, node in enumerate(nodes, 1):
                print(f"\n  Node {i}:")
                print(f"    service: {node.get('service')}")
                print(f"    node_name: {node.get('node_name')}")
                print(f"    status: {node.get('status')}")
                print(f"    root_dir: {node.get('root_dir')}")
                print(f"    log_dir: {node.get('log_dir')}")
                print(f"    port: {node.get('port')}")
                print(f"    metrics_port: {node.get('metrics_port')}")
                print(f"    wallet: {node.get('wallet')}")
                print(f"    manager_type: {node.get('manager_type')}")

        return True
    except Exception as e:
        print(f"✗ Error in survey_nodes(): {e}")
        import traceback
        traceback.print_exc()
        return False


def test_service_name_extraction():
    """Test _extract_service_name_from_output()"""
    print("\n=== Testing service name extraction ===")
    manager = AntctlManager(mode="user")

    # Test with various output formats
    test_cases = [
        ("Service antnode1 added successfully", "antnode1"),
        ("Added antnode2", "antnode2"),
        ("antnode3 created", "antnode3"),
        ("Created service: antnode10", "antnode10"),
        ("No service name here", None),
    ]

    all_passed = True
    for output, expected in test_cases:
        result = manager._extract_service_name_from_output(output)
        if result == expected:
            print(f"✓ '{output}' -> '{result}'")
        else:
            print(f"✗ '{output}' -> '{result}' (expected '{expected}')")
            all_passed = False

    return all_passed


def test_factory_integration():
    """Test that AntctlManager can be created via factory"""
    print("\n=== Testing factory integration ===")

    from wnm.process_managers.factory import get_process_manager

    try:
        # Test antctl+user
        manager = get_process_manager("antctl+user")
        print(f"✓ Created AntctlManager via factory (antctl+user)")
        print(f"  use_sudo: {manager.use_sudo}")

        # Test antctl+sudo
        manager = get_process_manager("antctl+sudo")
        print(f"✓ Created AntctlManager via factory (antctl+sudo)")
        print(f"  use_sudo: {manager.use_sudo}")

        return True
    except Exception as e:
        print(f"✗ Error creating manager via factory: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests"""
    print("=" * 60)
    print("AntctlManager Integration Tests")
    print("=" * 60)

    tests = [
        ("Antctl Installation", test_antctl_installation),
        ("Status JSON Parsing", test_status_json_parsing),
        ("Survey Nodes", test_survey_nodes),
        ("Service Name Extraction", test_service_name_extraction),
        ("Factory Integration", test_factory_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n✗ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())