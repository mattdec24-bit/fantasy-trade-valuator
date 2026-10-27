#!/bin/sh
# Run from any working directory; no credentials belong in shell arguments.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Probe every candidate, including later PATH entries with the same name.
# An older system python3 must not mask an installed supported interpreter.
for candidate in python3 python3.15 python3.14 python3.13 python3.12 python3.11 python; do
    saved_ifs=$IFS
    IFS=:
    for directory in $PATH; do
        IFS=$saved_ifs
        interpreter="${directory:-.}/$candidate"
        if [ -x "$interpreter" ] && "$interpreter" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
            exec "$interpreter" scripts/local.py "$@"
        fi
    done
    IFS=$saved_ifs
done
echo 'Install Python 3.11+ and Docker with Compose, then run this launcher again.' >&2
exit 1
