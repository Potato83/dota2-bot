#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# 1. Validate dependencies
if ! command -v python3 &>/dev/null; then
    echo "[Error] python3 not found." >&2
    exit 1
fi

if ! command -v xdotool &>/dev/null; then
    echo "[Error] xdotool not found. Install it (e.g. sudo apt install xdotool)." >&2
    exit 1
fi

VER=$(python3 -c 'import sys; print(sys.version_info[:2] >= (3, 10))')
if [ "$VER" != "True" ]; then
    echo "[Error] Python 3.10+ is required." >&2
    exit 1
fi

# 2. Prepare Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[+] Creating virtual environment..."
    python3 -m venv .venv
fi

# 3. Trap exit to safely deactivate venv
trap 'deactivate 2>/dev/null || true' EXIT

# 4. Activate and install requirements
echo "[+] Activating venv and installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 5. Run bot passing all arguments
echo "[+] Starting bot..."
python dota_safe_bot.py "$@"
