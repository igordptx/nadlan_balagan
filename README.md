# Nadlan Balagan

Nadlan Balagan runs saved searches on the Israel Tax Authority real-estate site, shows the latest results at **http://127.0.0.1:7777**, and schedules enabled searches for **08:00 UTC every day**. It uses Chromium through Playwright and Tesseract OCR to handle the site's four-digit image challenge.

The application supports Python 3.11+ on Windows and Linux. The setup scripts put the Python environment in `.venv/` and Chromium in `.browsers/`. Search results, the SQLite database, service logs, and generated service-unit files live in `data/`. These directories are excluded from Git. Tesseract is an operating-system dependency installed by the setup script; it is not bundled in this repository.

## Install and run on Linux

```bash
cd ~/nadlan_balagan
bash scripts/setup_linux.sh
.venv/bin/python -m nadlan_balagan serve
```

The setup script checks for Python 3.11+, installs Tesseract if needed (apt, dnf, or pacman), creates the virtual environment, installs the Python package, downloads Chromium, and runs the Linux sanity tests. Ubuntu/Debian receive Playwright's browser-library installation automatically. On other distributions, Chromium's libraries may need to be installed through that distribution's package manager.

To start the application when your Linux user session starts, run `bash scripts/register_linux_service.sh`. Check it with `systemctl --user status nadlan-balagan.service`. A user service normally runs while your user session is active; on a machine that must run unattended after logout, configure systemd lingering for your user separately.

## Install and run on Windows

From PowerShell in the project directory:

```powershell
.\scripts\setup_windows.ps1
.\.venv\Scripts\python.exe -m nadlan_balagan serve
```

The script uses WinGet to install Python 3.13 or Tesseract when needed, creates `.venv`, downloads Chromium to `.browsers`, and runs the Windows sanity tests. If Python was newly installed, open a new PowerShell window and rerun the setup script. If PowerShell blocks local scripts, run `Set-ExecutionPolicy -Scope Process Bypass` in that window first. To start the app at logon, run `.\scripts\register_windows_task.ps1`.

Both setup scripts require network access. System package installation may request administrator privileges. If Tesseract is installed in an unusual location, set the `NADLAN_TESSERACT` environment variable to its executable path before starting the app.

## Configure searches

Put one `.toml` file per search in `searches/`. The included `gush_30303.toml` is a working example:

```toml
id = "gush-30303"
title = "Apartments in gush 30303"
enabled = true

[location]
kind = "gush_range"
from = 30303
to = 30303

[filters]
property_type = "דירת מגורים"
transaction_type = "הכל"
period = "last_12_months"
```

Each field has a specific role:

| Field | What it controls |
| --- | --- |
| `id` | A unique, stable identifier for the search. Use lowercase letters, digits, hyphens, or underscores. Results remain associated with this ID even if you change `title`. |
| `title` | The name displayed on the dashboard. |
| `enabled` | Set `false` to keep the file without running it daily or through the dashboard. |
| `location.from`, `location.to` | Starting and ending gush numbers. Set them equal for one gush, or use a range. |
| `property_type` | The exact Hebrew label offered in the site's property dropdown; `דירת מגורים` is the verified example. |
| `transaction_type` | The exact label offered after choosing the property type; `הכל` is the verified example. Available choices can depend on `property_type`. |
| `period` | A rolling date window: `last_3_months`, `last_6_months`, `last_12_months`, or `last_36_months`. The site calculates dates at the time of each run. |

To add another search, copy the example to a new `.toml` file, change its `id`, and adjust the filters. Filenames may differ from IDs. For example, you can keep one file for gush 30303 over 12 months and another with a different ID and `period = "last_36_months"` to compare a longer window. Every enabled file is a separate search, run sequentially with the delay in `settings.toml`.

The initial release supports gush ranges and preset periods. It does not yet automate city autocomplete, parcel-specific searches, or custom start/end dates. Search files are reloaded before each batch, so editing a search does not require restarting the server. Invalid files are shown on the dashboard and do not prevent other valid searches from running. If the site does not offer a configured property or transaction label, that search fails with an error shown on the dashboard; other searches continue.

`settings.toml` sets the local port, delay between searches (default three seconds), headless mode, OCR attempt limit, and maximum result pages. The dashboard is deliberately bound to `127.0.0.1`; it is not accessible from other machines without additional networking configuration.

If port 7777 is occupied, change `settings.toml` or use `python -m nadlan_balagan serve --port 10000` for that run. Startup checks the port before queueing a scheduled search.

## Runs and results

Keep the service running for the 08:00 UTC schedule. If it starts after 08:00 and today's scheduled batch has not run, it runs once immediately. Manual runs do not replace the daily scheduled run. Scheduled and manual jobs share one worker and never run browser searches concurrently. The dashboard's **Run all now** and per-search buttons trigger manual jobs.

Each run records a status and keeps its files in `data/runs/<batch-id>/<run-id>/`. The dashboard displays the latest *successful* data alongside any more recent error. It preserves rows exactly as the site displays them, including repeated-looking rows. For results spanning multiple pages, it follows the site's pagination and checks that the collected row count matches the reported count. If pagination cannot be completed, that run fails rather than publishing partial data.

The project never writes search artifacts into the source folders or outside this checkout. Playwright's browser binaries, the SQLite database, logs, and captures all stay here. The only external changes made by optional autostart registration are operating-system task/service registration; the Linux service-unit file itself is generated under `data/service/`.

## Checks and one-off run

Linux:

```bash
bash scripts/sanity_linux.sh
.venv/bin/python -m nadlan_balagan run-once
```

Windows:

```powershell
.\scripts\sanity_windows.ps1
.\.venv\Scripts\python.exe -m nadlan_balagan run-once
```

Use `run-once --search gush-30303` to select one configured search. The sanity scripts test Python, Tesseract against a four-digit fixture, a local Chromium page, configuration loading, SQLite, and the unit tests without contacting the tax website. A live `run-once` checks the external site as well. The site can change its controls or block automated traffic, so a failed live run leaves diagnostics in that run's directory and the error in the dashboard.
