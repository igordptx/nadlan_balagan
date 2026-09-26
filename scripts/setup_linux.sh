#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python_cmd=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    python_cmd="$candidate"
    break
  fi
done
if [[ -z "$python_cmd" ]]; then
  echo "Python 3.11+ is required. Install it with your distribution package manager, then rerun this script." >&2
  exit 1
fi

if ! command -v tesseract >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y tesseract tesseract-langpack-eng
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm tesseract tesseract-data-eng
  else
    echo "Install Tesseract OCR with your distribution package manager, then rerun." >&2
    exit 1
  fi
fi

if ! "$python_cmd" -m venv .venv; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y "${python_cmd}-venv"
    "$python_cmd" -m venv .venv
  else
    echo "Install the venv package for $python_cmd, then rerun this script." >&2
    exit 1
  fi
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
export PLAYWRIGHT_BROWSERS_PATH="$project_root/.browsers"
if command -v apt-get >/dev/null 2>&1; then
  .venv/bin/python -m playwright install --with-deps chromium
else
  .venv/bin/python -m playwright install chromium
fi
"$project_root/scripts/sanity_linux.sh"
echo "Start with: $project_root/.venv/bin/python -m nadlan_balagan serve"
