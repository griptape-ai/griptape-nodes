#!/bin/bash

# Test script to validate that each node class in the advanced media library can be loaded successfully
# Uses pytest to run smoke tests for dynamic node loading

set -e  # Exit on first error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_ACTIVATE="${SCRIPT_DIR}/.venv/bin/activate"
TEST_FILE="${SCRIPT_DIR}/test_node_loading.py"

echo "=== Griptape Nodes Advanced Media Library - Node Loading Test ==="
echo "Script directory: ${SCRIPT_DIR}"
echo "Test file: ${TEST_FILE}"
echo "Virtual environment: ${VENV_ACTIVATE}"
echo ""

# Check if test file exists
if [[ ! -f "${TEST_FILE}" ]]; then
    echo "ERROR: Test file not found at ${TEST_FILE}"
    exit 1
fi

# Check if virtual environment exists
if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    echo "ERROR: Virtual environment activation file not found at ${VENV_ACTIVATE}"
    echo "Please create a virtual environment with: python -m venv .venv"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "${VENV_ACTIVATE}"

# Verify Python is using the virtual environment
echo "Using Python: $(which python)"
echo "Python version: $(python --version)"
echo ""

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo "ERROR: pytest not found in virtual environment"
    echo "Please install pytest with: pip install pytest"
    exit 1
fi

echo "Using pytest: $(which pytest)"
echo "Pytest version: $(pytest --version)"
echo ""

# Add the library base directory to Python path
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Run pytest with minimal output, showing only print statements and failures
echo "Running pytest smoke tests for node loading..."
echo ""

# Run the tests with -s to show print output and -q for quiet mode
if pytest -s -q -x "${TEST_FILE}"; then
    echo ""
    echo "✅ ALL NODE LOADING TESTS PASSED!"
    echo "=== Test completed successfully! ==="
    exit 0
else
    echo ""
    echo "❌ NODE LOADING TESTS FAILED!"
    echo "Check the error output above for details."
    echo "=== Test failed! ==="
    exit 1
fi