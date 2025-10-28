#!/bin/bash
# Run tests on macOS (skip Linux-only tests)

set -e

cd "$(dirname "$0")/.."

# Set test mode to prevent config.py from creating directories on import
export WNM_TEST_MODE=1

echo "Running macOS tests..."
pytest tests/ -v -m "not linux_only" --cov=src/wnm --cov-report=term-missing

echo ""
echo "macOS test suite complete!"
