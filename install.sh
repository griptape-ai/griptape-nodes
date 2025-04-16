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
echo "Downloading Griptape Nodes..."
echo ""

# Download the latest release tarball for griptape-nodes
curl -L https://github.com/griptape-ai/griptape-nodes/archive/refs/tags/latest.tar.gz -o griptape-nodes-latest.tar.gz

echo ""
echo "Installing Griptape Nodes Engine from the tarball..."
echo ""
uv tool install --force --python python3.13 ./griptape-nodes-latest.tar.gz

echo ""
echo "Installing Griptape Nodes Library + Workflows..."
echo ""

# Extract from the same tarball to get library/workflow files
TMP_DIR="$(mktemp -d)"
tar -xzf griptape-nodes-latest.tar.gz -C "$TMP_DIR"

# Name of the extracted directory (e.g., griptape-nodes-latest)
NODE_DIR="$(find "$TMP_DIR" -maxdepth 1 -type d -name 'griptape-nodes*' | head -n 1)"

XDG_DATA_HOME="$HOME/.local/share"
mkdir -p "$XDG_DATA_HOME/griptape_nodes"

cp -R "$NODE_DIR/nodes" "$XDG_DATA_HOME/griptape_nodes/nodes"
cp -R "$NODE_DIR/workflows" "$XDG_DATA_HOME/griptape_nodes/workflows"

rm -rf "$TMP_DIR"
rm griptape-nodes-latest.tar.gz

echo "**************************************"
echo "*      Installation complete!        *"
echo "*  Run 'griptape-nodes' (or 'gtn')   *"
echo "*      to start the engine.          *"
echo "**************************************"
