#!/bin/sh
set -eu

cd "$(dirname "$0")"
if [ -d site-packages ]; then
  export PYTHONPATH="$(pwd)/site-packages${PYTHONPATH:+:$PYTHONPATH}"
fi
exec python -m backend.server
