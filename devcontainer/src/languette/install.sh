#!/bin/sh
# The devcontainer feature's build step, run as root: python3 3.11 or newer
# and shfmt where apt can bring them, then languette from PyPI, pinned to this
# release, on PATH for every user. The wiring needs the container's own user
# and network, so it is the feature's postCreateCommand, `languette install`.
set -eu

version=0.0.14 # x-release-please-version
venv=/usr/local/lib/languette

python_ok() {
    command -v python3 >/dev/null 2>&1 && python3 -c 'import sys, venv; sys.exit(sys.version_info < (3, 11))' 2>/dev/null
}

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q
    python_ok || apt-get install -y -q --no-install-recommends python3 python3-venv
    # The parser the guards trust most; without it they read commands a rung lower.
    command -v shfmt >/dev/null 2>&1 || apt-get install -y -q --no-install-recommends shfmt || true
    rm -rf /var/lib/apt/lists/*
fi

if ! python_ok; then
    echo "languette: needs python3 3.11 or newer with venv; add ghcr.io/devcontainers/features/python before this feature" >&2
    exit 1
fi

python3 -m venv "$venv"
"$venv/bin/pip" install --no-cache-dir --disable-pip-version-check -q "languette==$version"
ln -sf "$venv/bin/languette" /usr/local/bin/languette
languette --help >/dev/null
