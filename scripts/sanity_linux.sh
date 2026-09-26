#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
.venv/bin/python -m nadlan_balagan check
.venv/bin/python -m unittest discover -s tests -v
echo "Linux sanity checks passed."
