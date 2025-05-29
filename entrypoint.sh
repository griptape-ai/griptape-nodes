#!/bin/bash
set -e

if [ "$GTN_INIT" = "true" ]; then
    /griptape-nodes/.venv/bin/griptape-nodes init
fi

exec "$@"
