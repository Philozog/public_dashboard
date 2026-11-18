#!/bin/bash
# Double-click to install (first time only) and start AP Terminal.
cd "$(dirname "$0")" || exit 1
exec ./start-linux.sh
