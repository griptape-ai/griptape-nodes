#!/bin/bash
set -e

/griptape-nodes/.venv/bin/griptape-nodes init

exec "$@"
