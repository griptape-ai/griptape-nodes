#!/bin/bash
set -e

if [ "$GTN_INIT" = "true" ]; then
    /app/.venv/bin/griptape-nodes init --no-interactive
fi

exec "$@"
