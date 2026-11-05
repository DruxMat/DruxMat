#!/bin/sh
set -eu
DATA_DIR="${DRUXMAT_DATA_DIR:-/data}"
mkdir -p "$DATA_DIR"
# A Railway volume is mounted as root. Set ownership before dropping privileges.
chown -R druxmat:druxmat "$DATA_DIR"
exec gosu druxmat "$@"
