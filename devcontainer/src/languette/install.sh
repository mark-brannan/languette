#!/bin/sh
# The devcontainer feature's build step, run as root: python3 3.11 or newer,
# shfmt and gh where apt can bring them, then languette from PyPI, pinned to this
# release, on PATH for every user. The wiring needs the container's own user
# and network, so it is the feature's postCreateCommand, `languette install`.
set -eu

version=0.0.25 # x-release-please-version
venv=/usr/local/lib/languette

python_ok() {
    command -v python3 >/dev/null 2>&1 && python3 -c 'import sys, ensurepip; sys.exit(sys.version_info < (3, 11))' 2>/dev/null
}

if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    # Update only when something is missing, so a base image that has it all builds offline.
    python_ok || need="python3 python3-venv"
    # The parser the guards trust most; without it they read commands a rung lower.
    command -v shfmt >/dev/null 2>&1 || extra="shfmt"
    # For the guards that ask GitHub; without it they ask the user instead.
    command -v gh >/dev/null 2>&1 || extra="${extra:-} gh"
    if [ -n "${need:-}${extra:-}" ]; then
        apt-get update -q
        [ -z "${need:-}" ] || apt-get install -y -q --no-install-recommends $need
        for pkg in ${extra:-}; do apt-get install -y -q --no-install-recommends "$pkg" || true; done
        rm -rf /var/lib/apt/lists/*
    fi
fi

if ! python_ok; then
    echo "languette: needs python3 3.11 or newer with venv; add ghcr.io/devcontainers/features/python before this feature" >&2
    exit 1
fi

python3 -m venv "$venv"
"$venv/bin/pip" install --no-cache-dir --disable-pip-version-check -q "languette==$version"
ln -sf "$venv/bin/languette" /usr/local/bin/languette
languette --help >/dev/null
