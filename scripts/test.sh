#!/bin/bash
# Run tests in Docker container

set -e

cd "$(dirname "$0")/.."

echo "Building test container..."
docker compose -f tests/docker/docker-compose.test.yml build wnm-test

echo "Running tests..."
docker compose -f tests/docker/docker-compose.test.yml run --rm wnm-test "$@"
