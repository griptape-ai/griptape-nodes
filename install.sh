#!/bin/sh
set -e

# --------- styling helpers ---------
if [ -t 1 ]; then
  BOLD="\033[1m"
  CYAN="\033[36m"
  GREEN="\033[32m"
  RED="\033[31m"
  RESET="\033[0m"
else
  BOLD="" CYAN="" GREEN="" RED="" RESET=""
fi
cecho() { printf "%b%s%b\n" "$1" "$2" "$RESET"; } # colour echo
# -----------------------------------

# Check if uv is already installed
if command -v uv >/dev/null 2>&1; then
  cecho "$CYAN" "uv is already installed. Using existing installation..."
  UV_PATH=$(command -v uv)
else
  cecho "$CYAN" "Installing uv..."
  export UV_UNMANAGED_INSTALL="$HOME/.local/share/griptape_nodes/bin"
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  UV_PATH="$HOME/.local/share/griptape_nodes/bin/uv"
fi

cecho "$GREEN$BOLD" "uv installed successfully!"

# Verify uv installation
if [ ! -f "$UV_PATH" ]; then
  cecho "$RED" "Error: uv installation failed at expected path: $UV_PATH"
  exit 1
fi

echo ""
cecho "$CYAN$BOLD" "Installing Griptape Nodes Engine..."
echo ""
"$UV_PATH" tool update-shell
"$UV_PATH" tool install --force --python python3.12 griptape-nodes >/dev/null

cecho "$GREEN$BOLD" "**************************************"
cecho "$GREEN$BOLD" "*      Installation complete!        *"
cecho "$GREEN$BOLD" "*  Run 'griptape-nodes' (or 'gtn')   *"
cecho "$GREEN$BOLD" "*      to start the engine.          *"
cecho "$GREEN$BOLD" "**************************************"
