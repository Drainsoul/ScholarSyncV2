#!/bin/sh
# Give this codespace its own secret key, once. The public explore key in compose.yaml is for
# localhost only, and settings refuse it inside a codespace (docs/SETUP.md).
# The file is git-ignored; compose reads it with --env-file on every start (devcontainer.json).
set -eu
KEY_FILE="$(dirname "$0")/explore.env"
if [ ! -s "$KEY_FILE" ]; then
  umask 077
  printf 'EXPLORE_SECRET_KEY=codespace-%s\n' \
    "$(head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n')" > "$KEY_FILE"
fi
