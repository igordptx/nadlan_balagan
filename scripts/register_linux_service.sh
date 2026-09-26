#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="$project_root/data/service"
mkdir -p "$unit_dir"
unit="$unit_dir/nadlan-balagan.service"
cat > "$unit" <<EOF
[Unit]
Description=Nadlan Balagan local dashboard and daily searches
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$project_root
ExecStart=$project_root/.venv/bin/python -m nadlan_balagan serve
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user link "$unit"
systemctl --user daemon-reload
systemctl --user enable --now nadlan-balagan.service
echo "User service registered. Application files and data remain under $project_root."
