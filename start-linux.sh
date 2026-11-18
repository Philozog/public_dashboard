#!/bin/bash
# Run ./start-linux.sh to install (first time only) and start AP Terminal.
cd "$(dirname "$0")" || exit 1

fail() {
    echo
    echo "$1"
    read -r -p "Press Enter to close." _
    exit 1
}

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    command -v open >/dev/null 2>&1 && open "https://www.python.org/downloads/"
    fail "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/ then run this again."
fi

if [ ! -x .venv/bin/python ]; then
    echo "First run: setting up. This takes a few minutes, only once."
    "$PY" -m venv .venv || fail "Could not create the Python environment (on Debian/Ubuntu: sudo apt install python3-venv)."
fi

# Reinstall packages only when requirements.txt has changed.
if ! cmp -s requirements.txt .venv/installed-requirements.txt; then
    .venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
    .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt ||
        fail "Package install failed. See the message above."
    cp requirements.txt .venv/installed-requirements.txt
fi

.venv/bin/python main.py || fail "The dashboard stopped with an error. See the message above."
