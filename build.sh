#!/bin/sh
set -eu

cd "$(dirname "$0")"
rm -rf "$(pwd)/site-packages"
rm -rf "$(pwd)/.wheels"
mkdir -p "$(pwd)/.wheels"

# crcmod ships as source. Build it without its optional native extension so the
# wheel stays platform-independent instead of accidentally embedding a macOS
# binary while preparing the Linux veFaaS bundle.
CC=/usr/bin/false .venv312/bin/python -m pip wheel \
  --no-cache-dir \
  --no-deps \
  --wheel-dir "$(pwd)/.wheels" \
  crcmod==1.7

uv pip install \
  --index-url=https://mirrors.ivolces.com/pypi/simple \
  --extra-index-url=https://pypi.org/simple \
  --find-links="$(pwd)/.wheels" \
  --python-platform=x86_64-unknown-linux-gnu \
  --python-version=3.12 \
  --requirement requirements.txt \
  --target site-packages
