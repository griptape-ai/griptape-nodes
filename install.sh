#!/bin/sh

echo ""
echo "Installing uv..."
echo ""
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify uv is on the user's PATH
if ! command -v uv >/dev/null 2>&1; then
  echo "Error: Griptape Nodes dependency 'uv' was installed, but requires the terminal to be restarted to be run."
  echo "Please close this terminal and open a new one, then run the install command you performed earlier."

  exit 1
fi

echo ""
echo "Installing Griptape Nodes Engine..."
echo ""
uv tool install --force --python python3.13 --from git+https://github.com/griptape-ai/griptape-nodes.git@latest griptape_nodes

# Install Griptape Nodes Library + Scripts
: "${XDG_DATA_HOME:="$HOME/.local/share"}"
REPO_NAME="griptape-nodes"

TMP_DIR="$(mktemp -d)"
cd "$TMP_DIR"

echo ""
echo "Installing Griptape Nodes Library..."
echo ""
git clone --depth 1 --branch latest https://github.com/griptape-ai/griptape-nodes.git

mkdir -p "$XDG_DATA_HOME/griptape_nodes"

cp -R $REPO_NAME/nodes/ "$XDG_DATA_HOME/griptape_nodes/nodes"
cp -R $REPO_NAME/scripts/ "$XDG_DATA_HOME/griptape_nodes/scripts"

cd - >/dev/null
rm -rf "$TMP_DIR"

echo "**************************************"
echo "*      Installation complete!        *"
echo "*  Run 'griptape-nodes' (or 'gtn')   *"
echo "*      to start the engine.          *"
echo "**************************************"
