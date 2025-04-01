#!/bin/sh

CONFIG_FILE="$HOME/.config/griptape_nodes/griptape_nodes_config.json"
ENV_FILE="$HOME/.config/griptape_nodes/.env"
API_KEY="$1"

# If an API key was passed, attempt to write it to the config file
if [ -n "$API_KEY" ]; then
  # Ensure the config directory exists
  mkdir -p "$(dirname "$CONFIG_FILE")"

  # Check if the file already exists
  if [ -e "$CONFIG_FILE" ]; then
    echo "A config file already exists at '$CONFIG_FILE', overwriting..."
  fi
  # Write the API key to the config file
  echo '{
  "nodes": {
    "Griptape": {
        "GT_CLOUD_API_KEY": "$GT_CLOUD_API_KEY"
    }
  }
}' >"$CONFIG_FILE"

  echo 'GT_CLOUD_API_KEY="'"$API_KEY"'"' >"$ENV_FILE"
  echo "API key saved to $CONFIG_FILE"
else
  echo "No API key provided. Skipping config file creation."
fi

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

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo ""
echo "${GREEN}${BOLD}==========================================${NC}"
echo "${GREEN}${BOLD}✅ Installation complete!${NC}"
echo ""
echo "${BOLD}👉 Run '${RED}griptape-nodes${NC}${BOLD}' (or just '${RED}gtn${NC}${BOLD}') to start the engine.${NC}"
echo "${GREEN}${BOLD}==========================================${NC}"
echo ""
