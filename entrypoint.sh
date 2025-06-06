#!/bin/bash
set -e

if [ "$GTN_INIT" = "true" ]; then
    /opt/venv/bin/griptape-nodes init --no-interactive
fi

exec "$@"
