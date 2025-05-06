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

echo ""
cecho "$CYAN$BOLD" "Installing uv..."
echo ""
curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
cecho "$GREEN$BOLD" "uv installed successfully!"

# Verify uv is on the user's PATH
if ! command -v uv >/dev/null 2>&1; then
  cecho "$RED" "Error: Griptape Nodes dependency 'uv' was installed but requires the terminal instance to be restarted to be run."
  cecho "$RED" "Please close this terminal instance, open a new terminal instance, and then run the install command you performed earlier."
  exit 1
fi

echo ""
cecho "$CYAN$BOLD" "Installing Griptape Nodes Engine..."
echo ""
~/.local/bin/uv tool update-shell
~/.local/bin/uv tool install --force --python python3.12 griptape-nodes >/dev/null

cecho "$GREEN$BOLD" "**************************************"
cecho "$GREEN$BOLD" "*      Installation complete!        *"
cecho "$GREEN$BOLD" "*  Run 'griptape-nodes' (or 'gtn')   *"
cecho "$GREEN$BOLD" "*      to start the engine.          *"
cecho "$GREEN$BOLD" "**************************************"
