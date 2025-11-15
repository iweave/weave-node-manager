# AntctlManager Implementation Plan

## Executive Summary

This document outlines the plan to integrate `antctl` as a new process manager option in the Weave Node Manager (wnm) system. The AntctlManager will wrap the `antctl` CLI tool, allowing wnm to delegate node lifecycle management to antctl while maintaining wnm's decision engine and resource monitoring capabilities.

## Design Decisions

### 1. Integration Approach
**Decision**: AntctlManager will be an **additional option** alongside existing managers (SystemdManager, LaunchdManager, SetsidManager, DockerManager)

**Rationale**:
- Provides flexibility for users to choose their preferred backend
- Allows gradual migration without breaking existing deployments
- Enables platform-specific manager selection

### 2. Node Numbering Strategy
**Decision**: Parse antctl service names to extract node numbers

**Implementation**:
- antctl creates services named `antnode1`, `antnode2`, etc.
- wnm will parse the number from the service name and use it as the database `node.id`
- Accept gaps in numbering when nodes are removed (antctl doesn't reuse numbers)
- Store the full service name (e.g., "antnode1") in `node.service` field

**Multi-Container Handling**:
- Multiple Docker containers can each have `antnode1`, `antnode2`, etc.
- Distinguish using the `node.container_id` foreign key (already in schema)
- Use `NodeProcess.external_node_id` to store the antctl service name
- Uniqueness constraint: (container_id, service_name) pair

### 3. Path Configuration
**Decision**: Override antctl's default paths to match wnm's platform-specific conventions

**Rationale**:
- wnm already uses antctl's default paths by platform
- Maintains consistency with existing wnm deployments
- Allows wnm to control directory structure

**Path Overrides** (via antctl flags):
- `--data-dir-path`: Override with wnm's `node.root_dir`
- `--log-dir-path`: Override with wnm's log directory
- `--antnode-path`: Override with wnm's binary management

### 4. Migration Strategy
**Decision**: No automatic migration from existing managers

**Rationale**:
- We do not support migrating between process_managers.
- We will have the option of importing/migrating from an existing antctl cluster that was defined with metrics ports enabled. This existing cluster information can be collected by using the json format of the 'antctl status --details' command.

## Architecture

### Class Structure

```python
class AntctlManager(ProcessManager):
    """Manage nodes via antctl CLI wrapper"""

    def __init__(self, session_factory=None, firewall_type=None, mode=None):
        # mode can be "user" or "sudo" (with sudo)
        # Determines if antctl is run with sudo

    def create_node(self, node: Node, binary_path: str) -> Optional[NodeProcess]:
        # Use: antctl add --count 1 [--data-dir-path] [--log-dir-path] ...
        # Parse output to extract service_name
        # Return NodeProcess with external_node_id = service_name

    def start_node(self, node: Node) -> bool:
        # Use: antctl start --service-name {node.service}

    def stop_node(self, node: Node) -> bool:
        # Use: antctl stop --service-name {node.service}

    def restart_node(self, node: Node) -> bool:
        # Use: antctl stop then start (no direct restart command)

    def get_status(self, node: Node) -> NodeProcess:
        # Minimal stub - never actually called by executor
        # Just check metrics port via read_node_metadata()
        # Return NodeProcess with status based on metrics port response

    def remove_node(self, node: Node) -> bool:
        # Use: antctl stop --service-name {node.service}
        # Then: antctl remove --service-name {node.service}

    def survey_nodes(self, machine_config) -> list:
        # Use: antctl status --json
        # Parse all nodes and return list for database initialization

    def teardown_cluster(self) -> bool:
        # Use: antctl reset --force (or teardown equivalent)
        # Provides efficient bulk cleanup

    # Helper methods
    def _run_antctl(self, args: list, capture_output: bool = True) -> subprocess.CompletedProcess:
        # Execute antctl command with proper error handling
        # Handle sudo mode if self.use_sudo is True

    def _parse_status_json(self, json_output: str) -> list:
        # Parse antctl status --json output
        # Extract node details into structured format

    def _extract_service_name_from_output(self, output: str) -> str:
        # Parse antctl add output to find the created service name
        # Example: "Service antnode1 created successfully"

    def _get_next_available_service_name(self) -> str:
        # Query antctl status to find next available antnode number
        # Handle gaps in numbering
```

### Database Schema Usage

**Node table fields** (already exist):
- `id`: wnm's node number (parsed from antctl's "antnodeX")
- `service`: antctl service name ("antnode1", "antnode2", etc.)
- `container_id`: Foreign key to Container table (for multi-container scenarios)
- `manager_type`: Set to "antctl"
- `root_dir`, `port`, `metrics_port`: Override antctl defaults
- `binary`: Path to antnode binary
- `status`: RUNNING, STOPPED, etc. (mapped from antctl status)

**Container table** (for multi-container deployments):
- `container_id`: Docker container ID
- Allows multiple containers to each have "antnode1", "antnode2"
- Nodes are distinguished by (container_id, service) pair

### Antctl Command Mapping

| wnm Operation | Antctl Command | Notes |
|--------------|----------------|-------|
| `create_node()` | `antctl add --count 1 --data-dir-path {path} --log-dir-path {path} --port {port} --metrics-port {metrics_port} --no-upnp --rewards-address {wallet}` | Creates and starts node |
| `start_node()` | `antctl start --service-name {service}` | Starts stopped node |
| `stop_node()` | `antctl stop --service-name {service}` | Stops running node |
| `remove_node()` | `antctl stop --service-name {service} && antctl remove --service-name {service}` | Stop then remove |
| `survey_nodes()` | `antctl status --json` | Discover all nodes |
| `get_status()` | **N/A - uses metrics port** | Never called; checks metrics port via `read_node_metadata()` |
| `teardown_cluster()` | `antctl reset --force` | Bulk cleanup |

### Status Mapping

Map antctl status strings to wnm status constants:

```python
ANTCTL_STATUS_MAP = {
    "Running": RUNNING,
    "Stopped": STOPPED,
    "Added": STOPPED,  # Not yet started
    "Removed": DEAD,   # Marked for cleanup
}
```

## Implementation Steps

### Phase 1: Core AntctlManager Class
1. Create `src/wnm/process_managers/antctl_manager.py`
2. Implement `__init__()` with sudo/user mode support
3. Implement `_run_antctl()` helper for command execution
4. Implement basic error handling and logging

### Phase 2: Node Discovery
1. Implement `survey_nodes()` using `antctl status --json`
2. Parse JSON output to extract node details
3. Map antctl fields to wnm Node schema:
   - `service_name` → `node.service`
   - `number` → `node.id`
   - `data_dir_path` → `node.root_dir`
   - `metrics_port` → `node.metrics_port`
   - `node_port` → `node.port`
   - `status` → `node.status` (using ANTCTL_STATUS_MAP)
   - `peer_id` → `node.peer_id`
   - `version` → `node.version`

### Phase 3: Node Lifecycle Operations
1. Implement `create_node()`:
   - Build antctl command with path overrides
   - Execute `antctl add --count 1 ...`
   - Parse output to get service_name
   - Verify node was created via status check
   - Return NodeProcess with external_node_id=service_name
   - Open firewall if applicable

2. Implement `start_node()`:
   - Execute `antctl start --service-name {service}`
   - Verify status changed to Running

3. Implement `stop_node()`:
   - Execute `antctl stop --service-name {service}`
   - Verify status changed to Stopped


### Phase 4: Status Monitoring
**NOTE**: The `get_status()` method is required by the ProcessManager interface but **NOT actually called** by the executor.
The executor determines status by calling `read_node_metadata()` directly on the metrics port.

1. Implement `get_status()` as minimal stub:
   - Required by ProcessManager abstract base class
   - Never actually called by executor
   - Simple implementation: Just try to hit the metrics port via `read_node_metadata()`
   - Return NodeProcess with status=RUNNING if metrics port responds, STOPPED otherwise
   - **Do NOT call `antctl status` - unnecessary overhead**

2. Status is actually determined by executor via:
   - `read_node_metadata(node.host, node.metrics_port)` - existing function
   - No changes needed to metrics collection - works same as all other managers

### Phase 5: Node Removal
1. Implement `remove_node()`:
   - Stop node if running
   - Execute `antctl remove --service-name {service}`
   - Verify node removed from antctl status
   - Clean up firewall rules (if applicable)

### Phase 6: Cluster Operations
1. Implement `teardown_cluster()`:
   - Execute `antctl reset --force` or equivalent
   - Verify all nodes removed
   - Return True to indicate successful bulk teardown

### Phase 7: Factory Integration
1. Update `src/wnm/process_managers/factory.py`:
   - Import AntctlManager
   - Add "antctl" to managers dict
   - Update get_default_manager_type() if desired

2. don't add autodetection for antctl

### Phase 8: Configuration
1. Add `--process_manager antctl+user` CLI option support
2. Allow mode selection: `antctl+user` or `antctl+sudo`
3. Update initialization to detect and use antctl

### Phase 9: Testing
1. Unit tests for AntctlManager methods
2. Integration tests:
   - Create, start, stop, remove nodes
   - Survey existing nodes
   - Status monitoring
   - Multi-container scenarios
3. Platform testing:
   - Linux (user mode and system mode)
   - macOS (user mode)

## Special Considerations

### 1. Antctl Service Numbering
- Antctl decides service names (antnode1, antnode2, etc.)
- When node is removed, the number is NOT reused (creates gaps)
- Example: Remove antnode2, next node will be antnode4 (not antnode2)
- wnm must handle non-sequential node IDs

### 2. Multi-Container Scenarios
- Each container runs its own antctl instance
- Service names are container-scoped (each container has antnode1, antnode2)
- Distinguish using `node.container_id` foreign key
- When calling antctl, ensure commands target correct container context

### 3. Path Overrides
- Always specify `--data-dir-path` to match wnm's `node.root_dir`
- Always specify `--log-dir-path` to match wnm's log conventions
- Always specify `--antnode-path` if managing binary separately

### 4. Metrics Collection
- Antctl exposes metrics_port in JSON output
- wnm can continue using existing `read_node_metrics()` function
- No changes needed to metrics collection logic

### 5. Binary Management
- Antctl can download and manage binaries
- wnm may want to override with `--antnode-path` to maintain control
- Upgrades can use `antctl upgrade` or wnm's existing upgrade logic

### 6. Error Handling
- Parse antctl stderr for error messages
- Handle cases where antctl is not installed
- Gracefully handle permission errors (sudo mode)
- Detect and report antctl version compatibility

## API Examples

### Creating a Node
```python
# wnm decides node configuration
node = Node(
    id=5,  # Will request antnode5 or next available
    service="antnode5",
    root_dir="/home/user/.local/share/autonomi/node/antnode5",
    port=55005,
    metrics_port=13005,
    wallet="0x00455d78f850b0358E8cea5be24d415E01E107CF",
    # ... other fields
)

# AntctlManager creates it
manager = AntctlManager(session_factory=S)
result = manager.create_node(node, binary_path="/home/user/.local/bin/antnode")

# result.external_node_id = "antnode5" (parsed from antctl output)
```

### Surveying Existing Nodes
```python
manager = AntctlManager()
nodes = manager.survey_nodes(machine_config)

# Returns list of dicts:
# [
#   {
#     'id': 1,
#     'service': 'antnode1',
#     'status': 'RUNNING',
#     'root_dir': '/home/user/.local/share/autonomi/node/antnode1',
#     'port': 55555,
#     'metrics_port': 13555,
#     # ... other fields parsed from JSON
#   },
#   ...
# ]
```

### Multi-Container Usage
```python
# Container 1
container1 = Container(container_id="abc123", ...)
node1 = Node(id=1, service="antnode1", container_id=container1.id, ...)

# Container 2 (can also have antnode1)
container2 = Container(container_id="def456", ...)
node2 = Node(id=2, service="antnode1", container_id=container2.id, ...)

# Both are uniquely identified by (container_id, service) pair
```

## Testing Strategy

### Unit Tests
```python
# tests/test_antctl_manager.py
def test_create_node():
    # Mock antctl command execution
    # Verify correct arguments passed
    # Verify NodeProcess returned with correct external_node_id

def test_parse_status_json():
    # Test JSON parsing with sample antctl output
    # Verify field mapping

def test_status_mapping():
    # Test antctl status → wnm status mapping
```

### Integration Tests
```python
def test_full_lifecycle():
    # Create node
    # Verify it's running
    # Stop node
    # Verify it's stopped
    # Remove node
    # Verify it's gone

def test_survey_and_import():
    # Create nodes via antctl directly
    # Survey them via AntctlManager
    # Verify all nodes discovered
```

### Platform Tests
Test that **AntctlManager** correctly integrates with antctl on both platforms:
- **Linux**: Test wnm→antctl integration in both `antctl+user` and `antctl+sudo` modes
- **macOS**: Test wnm→antctl integration in `antctl+user` mode
- Verify that wnm correctly calls antctl commands and parses responses on each platform
- Note: We don't care what process manager antctl uses internally - that's antctl's concern


## Dependencies

### Required
- `antctl` installed via `antup antctl`
- `antctl` available in PATH (`~/.local/bin/antctl`)

### Optional
- `sudo` access for system-level services (mode="sudo")

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Antctl not installed | Check for antctl in PATH during initialization, provide clear error message |
| Service name conflicts | Use container_id to disambiguate in multi-container scenarios |
| Numbering gaps | Accept gaps, don't try to fill them (antctl limitation) |
| Path override failures | Validate paths before creating nodes, fail fast with clear errors |
| Status parsing errors | Robust JSON parsing with fallback to UNKNOWN status |
| antctl version changes | Document required antctl version, add version detection |

## Success Criteria

1. AntctlManager implements all ProcessManager interface methods
2. Can create, start, stop, upgrade and remove nodes via antctl
3. Status monitoring works correctly
4. Multi-container scenarios handled properly
5. Tests pass on Linux and macOS
6. Documentation complete
7. No breaking changes to existing managers

## Future Enhancements


3. **Upgrade integration**: Use `antctl upgrade` for node binary upgrades

5. **Performance optimization**: Batch status queries for multiple nodes
6. **Container orchestration**: Enhanced multi-container support with Docker API

## Questions for Review

1. Should we make antctl the default manager if it's installed?
    no
2. How should we handle antctl version compatibility?
    we have to accept that antctl can have a breaking change that will require an update to wnm to continue. hopefully --start_args will allow some flexibility in changes.
3. Should we support `antctl reset` vs `antctl teardown`? (different commands)
    we use teardown for wnm, this translates to `antctl reset` in the process_manager
4. Should we validate antctl is installed during wnm initialization?
    sure
5. How to handle the case where user manually adds/removes nodes via antctl outside of wnm?
    hopefully dead nodes detect removals, don't handle the case that a user creates a node out of band. The solution is to delete the database and reimport the active antctl nodes to get back to a known state with a new --init

## Next Steps

1. Review this plan with the team
2. Get approval on design decisions
3. Create feature branch: `feature/antctl-manager`
4. Implement Phase 1-3 (core functionality)
5. Create PR for initial review
6. Iterate based on feedback
7. Complete remaining phases
8. Final testing and documentation