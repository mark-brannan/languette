#!/bin/bash
# The feature's test: in a container built with Claude Code and this feature,
# the doctor finds languette wired and exits 0, as it does after a hand install.
set -e

# shellcheck source=/dev/null
source dev-container-features-test-lib

check "languette is on PATH" languette --help
check "languette doctor finds no ✗" languette doctor

reportResults
