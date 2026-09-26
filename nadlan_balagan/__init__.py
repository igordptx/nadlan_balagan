"""Scheduled real-estate searches and local results dashboard."""

import os
from pathlib import Path


# Keep Playwright's downloaded browser within this checkout on both platforms.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parent.parent / ".browsers"))
