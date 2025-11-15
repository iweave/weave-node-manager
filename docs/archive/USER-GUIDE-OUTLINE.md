# Weave Node Manager - User Guide & Reference Manual Outline

## Revision Notes
- **macOS is a fully supported production platform** (not just development)
- **Current:** macOS uses --relay mode (no firewall management required)
- **Future:** When relay mode is deprecated, macOS will require pfctl access (system privileges)

---

## Part 1: Getting Started

### 1.1 Introduction
- What is Weave Node Manager?
- Key features and capabilities
- When to use wnm vs anm
- Platform support overview (Linux, macOS)
- Alpha software disclaimer

### 1.2 Prerequisites
- Python version requirements (3.12.3+)
- System requirements (CPU, memory, disk)
- Platform-specific prerequisites
  - Linux: systemd or user-level access
  - **macOS: launchd support, currently uses --relay mode**
  - **macOS future: Will require pfctl access (system privileges) when relay mode is deprecated**
- Autonomi network basics

### 1.3 Quick Start Guide
- **Option A: macOS**
  - Installing antup
  - Installing wnm from PyPI
  - First-time initialization
  - **Understanding --relay mode (current)**
  - **Future: pfctl firewall setup (when relay deprecated)**

- **Option B: Linux User-Level (Recommended)**
  - Installing prerequisites
  - Installing wnm
  - Configuration and initialization

- **Option C: Linux Root-Level (Production)**
  - System setup
  - Migrating from anm
  - Production deployment

### 1.4 First Run Tutorial
- Understanding the initialization process
- Setting up rewards address
- Dry-run mode walkthrough
- Monitoring your first node
- Setting up cron for automated management

---

## Part 2: Core Concepts

### 2.1 How Weave Node Manager Works
- The execution cycle (one action per run)
- Lock file mechanism
- Decision engine overview
- Node lifecycle states

### 2.2 Node Lifecycle
- Node states (RUNNING, STOPPED, UPGRADING, RESTARTING, REMOVING, DEAD, DISABLED)
- State transitions
- Node creation process
- Node removal process
- Upgrade workflow

### 2.3 Resource Management
- Resource threshold system
- CPU monitoring and thresholds
- Memory monitoring and thresholds
- Disk space monitoring
- Network I/O tracking
- Load average considerations
- How wnm decides to add/remove nodes

### 2.4 Platform-Specific Behavior
- Process management approaches
  - systemd (Linux root)
  - launchd (macOS)
  - setsid (Linux user)
- **Firewall management**
  - **UFW (Linux)**
  - **Null/None (macOS with --relay mode - current)**
  - **pfctl (macOS - future when relay deprecated)**
- **Relay mode explanation and limitations**
- **Future macOS firewall requirements**
- Path conventions per platform
- Binary management and per-node copies

---

## Part 3: Configuration

### 3.1 Configuration System Overview
- Configuration priority layers
- Configuration sources (CLI, env vars, files, database, defaults)
- Platform-specific config file locations

### 3.2 Resource Thresholds
- `--cpu_less_than` / `--cpu_remove`
- `--mem_less_than` / `--mem_remove`
- `--hd_less_than` / `--hd_remove`
- `--desired_load_average` / `--max_load_average_allowed`
- `--io_less_than` / `--io_remove`
- Tuning recommendations for different hardware

### 3.3 Node Management Settings
- `--node_cap` - Maximum nodes
- `--node_storage` - Data directory
- Delay settings (start, restart, upgrade, remove)
- Port configuration (node ports, metrics ports)

### 3.4 Wallet Configuration
- Single wallet setup
- Named wallets (faucet, donate)
- Weighted distribution across multiple wallets
- Examples and use cases
- Changing wallet configuration

### 3.5 Network Settings
- Port ranges and assignment
- **--relay mode flag (macOS current requirement)**
- Bootstrap peers
- Network timeouts
- Bootstrap cache management

### 3.6 Advanced Configuration
- Database path customization
- Logging configuration
- Dry-run mode
- Force survey and other debugging options

---

## Part 4: Common Usage Scenarios

### 4.1 Daily Operations
- Running wnm manually
- Setting up cron for automation (all platforms)
- Monitoring node health
- Viewing node status reports
- Understanding wnm output

### 4.2 Node Management Tasks
- Adding nodes manually
- Removing specific nodes
- Upgrading nodes
- Restarting problematic nodes
- Disabling node management

### 4.3 Configuration Changes
- Adjusting resource thresholds
- Changing node capacity
- Updating rewards address
- Modifying wallet distribution

### 4.4 Troubleshooting Common Issues
- Nodes not starting
- High resource usage
- Port conflicts
- **macOS relay mode issues**
- Upgrade failures
- Database corruption recovery
- Lock file issues

### 4.5 Migration Scenarios
- Migrating from anm to wnm (Linux)
- **Preparing for post-relay macOS (future)**
- Backup and restore procedures

---

## Part 5: Advanced Topics

### 5.1 Database Schema
- Machine table reference
- Node table reference
- Direct database queries (for advanced users)

### 5.2 Process Manager Details
- SystemdManager implementation
- LaunchdManager implementation
- SetsidManager implementation
- DockerManager (testing only)

### 5.3 Reports and Monitoring
- node-status report format
- node-status-details report format
- Custom reporting queries
- Integration with external monitoring

### 5.4 Development and Testing
- Setting up development environment
- Running tests (macOS native, Linux Docker)
- Docker development workflow
- Contributing guidelines

### 5.5 Security Considerations
- Rewards address security
- File permissions
- Network exposure
- **Firewall configuration (platform-specific)**
- **macOS: Current relay mode vs future pfctl requirements**

---

## Part 6: Command-Line Reference

### 6.1 Command-Line Options (Complete List)
Alphabetical reference of all CLI options with:
- Option name and aliases
- Environment variable equivalent
- Description
- Default value
- Valid values/ranges
- Platform applicability
- **--relay flag details**
- Examples

### 6.2 Exit Codes
- Success codes
- Error codes
- What they mean and how to handle them

### 6.3 Environment Variables
- Complete list
- Platform-specific variables
- Testing/development variables

---

## Part 7: Appendices

### A. Platform-Specific Details
- macOS paths and conventions (production)
- Linux root paths and conventions
- Linux user paths and conventions
- Process management comparison table
- **Firewall management comparison (UFW, null, future pfctl)**
- **Relay mode vs non-relay comparison**

### B. Configuration File Examples
- Minimal configuration
- Production configuration (macOS and Linux)
- Development configuration
- Multi-wallet configuration
- **macOS relay mode configuration**

### C. Troubleshooting Matrix
- Problem → Symptoms → Solutions table
- Common error messages and fixes
- **Platform-specific issues (including relay mode)**

### D. FAQ
- General questions
- Platform-specific questions (macOS production clarity)
- Migration questions
- Performance questions
- **Relay mode and future changes FAQ**

### E. Glossary
- Technical terms
- Autonomi network terms
- wnm-specific terminology
- **Relay mode definition**

### F. Resources
- GitHub repository
- Issue tracker
- Community links
- Autonomi network documentation

---

## Progress Tracking

Use the todo list (TodoWrite tool) to track completion of each section.
Total sections: 31
