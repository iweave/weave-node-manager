#!/bin/bash
# Start interactive development shell in Docker container

set -e

cd "$(dirname "$0")/.."

echo "Building development container..."
docker compose -f tests/docker/docker-compose.test.yml build wnm-dev

echo "Starting development shell..."
echo "You are now in a Linux environment with systemd, ufw, and all dependencies."
echo ""
echo "Useful commands:"
echo "  python3 -m wnm              # Run WNM"
echo "  pytest -v                   # Run tests"
echo "  pytest tests/test_models.py # Run specific test file"
echo "  black src/                  # Format code"
echo "  isort src/                  # Sort imports"
echo ""

docker compose -f tests/docker/docker-compose.test.yml run --rm wnm-dev
