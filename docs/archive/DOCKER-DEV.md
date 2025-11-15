# Docker Development Environment

**Note:** This Docker environment is primarily for Linux-specific testing (systemd, UFW firewall).

**macOS users can run tests natively** using `./scripts/test-macos.sh` - Docker is optional for macOS users who want to test Linux-specific functionality.

Since WNM now supports both Linux and macOS, we use Docker containers for Linux-specific development and testing on macOS host machines.

## Quick Start

### Run Tests
```bash
./scripts/test.sh
```

This builds the test container and runs the full pytest suite.

### Interactive Development Shell
```bash
./scripts/dev.sh
```

This starts an interactive bash shell inside a Debian container with:
- Python 3.12
- systemd
- ufw (firewall)
- All dependencies from requirements.txt and requirements-dev.txt
- Your source code mounted as volumes (changes sync automatically)

## Development Workflow

### 1. Start the development container
```bash
./scripts/dev.sh
```

### 2. Inside the container, you can:

**Run the application:**
```bash
python3 -m wnm --dry_run
```

**Run tests:**
```bash
# All tests
pytest -v

# Specific test file
pytest tests/test_models.py -v

# With coverage
pytest --cov=wnm --cov-report=term-missing

# Specific test
pytest tests/test_models.py::TestMachine::test_create_machine -v
```

**Format code:**
```bash
black src/
isort src/
```

**Check systemd:**
```bash
sudo systemctl status
```

**Check firewall:**
```bash
sudo ufw status
```

### 3. Exit the container
```bash
exit
```

Your changes are preserved in the mounted volumes and your local filesystem.

## Container Details

### User
- Default user: `ant`
- Has sudo privileges with NOPASSWD

### Directories
- `/app` - Working directory with mounted source code
- `/var/antctl` - Persistent volume for node data (survives container restarts)
- `/tmp/test_nodes` - Temporary test data

### Environment Variables
- `PYTHONPATH=/app/src` - Python can import `wnm` module
- `WNM_DEV_MODE=1` - Development mode flag
- `PYTHONUNBUFFERED=1` - See output immediately

## Docker Compose Services

The `tests/docker/docker-compose.test.yml` file defines:

### wnm-test
- Runs pytest and exits
- Read-only source mounts
- Used by `./scripts/test.sh`

### wnm-dev
- Interactive development environment
- Read-write source mounts
- Privileged mode for systemd
- Persistent database volume
- Used by `./scripts/dev.sh`

## Manual Docker Commands

If you prefer not to use the helper scripts:

### Build the image
```bash
docker compose -f tests/docker/docker-compose.test.yml build wnm-dev
```

### Run tests
```bash
docker compose -f tests/docker/docker-compose.test.yml run --rm wnm-test
```

### Start dev shell
```bash
docker compose -f tests/docker/docker-compose.test.yml run --rm wnm-dev
```

### Run custom command
```bash
docker compose -f tests/docker/docker-compose.test.yml run --rm wnm-dev pytest tests/test_models.py
```

## Troubleshooting

### Container won't start
```bash
# Clean up old containers
docker compose -f tests/docker/docker-compose.test.yml down

# Rebuild from scratch
docker compose -f tests/docker/docker-compose.test.yml build --no-cache wnm-dev
```

### Permission errors
The container runs as user `ant` (UID may differ from your macOS user). If you see permission errors with mounted volumes, this is expected Docker behavior.

### Systemd not working
The container needs `privileged: true` in docker-compose.yml for systemd to work. This is already configured.

## Testing Workflow

1. Write tests in `tests/` on your Mac using your favorite editor
2. Run `./scripts/test.sh` to execute tests in Linux container
3. Iterate until tests pass
4. Commit changes

## Native macOS Development

**If you're on macOS**, you can develop and test natively without Docker:

```bash
# Run tests natively
./scripts/test-macos.sh

# Run application
python3 -m wnm --dry_run

# Format code
black src/
isort src/
```

Tests marked with `@pytest.mark.linux_only` will be automatically skipped on macOS.

## Future Enhancements

- Docker-in-Docker support for testing container-based nodes
- Pre-commit hooks that run tests in Docker
- CI/CD integration with same Docker images
- Docker training for containerized node management (coming after macOS support completion)
