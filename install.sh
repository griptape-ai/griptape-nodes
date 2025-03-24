#!/bin/sh

echo ""
echo "Installing uv..."
echo ""
curl -LsSf https://astral.sh/uv/install.sh | sh

echo ""
echo "Installing griptape nodes engine..."
echo ""
# Install griptape-nodes using the newly installed uv
uv tool install --force --python python3.12 --from git+https://github.com/griptape-ai/griptape-nodes@latest griptape_nodes

echo ""
echo "Installation complete, run:"
echo "griptape-nodes"
echo ""
