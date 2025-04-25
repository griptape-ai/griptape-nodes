#!/bin/sh

set -e

echo ""
echo "Installing uv..."
echo ""
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify uv is on the user's PATH
if ! command -v uv >/dev/null 2>&1; then
  echo "Error: Griptape Nodes dependency 'uv' was installed but requires the terminal instance to be restarted to be run."
  echo "Please close this terminal instance, open a new terminal instance, and then run the install command you performed earlier."
  exit 1
fi

echo ""
echo "Installing Griptape Nodes Engine..."
echo ""
uv tool install --force --python python3.12 git+https://github.com/griptape-ai/griptape-nodes

echo "**************************************"
echo "*      Installation complete!        *"
echo "*  Run 'griptape-nodes' (or 'gtn')   *"
echo "*      to start the engine.          *"
echo "**************************************"
