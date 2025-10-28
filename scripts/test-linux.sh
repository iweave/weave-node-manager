#!/bin/bash
# Run tests on Linux in Docker (skip macOS-only tests)

set -e

cd "$(dirname "$0")/.."

echo "Running Linux tests in Docker..."
docker compose -f tests/docker/docker-compose.test.yml build wnm-test
docker compose -f tests/docker/docker-compose.test.yml run --rm -e WNM_TEST_MODE=1 wnm-test pytest tests/ -v -m "not macos_only" --cov=src/wnm --cov-report=term-missing

echo ""
echo "Linux test suite complete!"
