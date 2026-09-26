"""Command-line entry point for the server, one-off runs, and sanity checks."""

import argparse
from dataclasses import replace
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import sys

from waitress.server import create_server

from .config import DATA_DIR, ROOT, load_searches, load_settings
from .ocr import read_four_digits, tesseract_binary
from .service import Service
from .storage import Storage
from .web import create_app


def setup_logging() -> None:
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(), RotatingFileHandler(log_dir / "service.log", maxBytes=2_000_000, backupCount=3)]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)


def check_environment(*, strict_config: bool = True) -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required")
    binary = tesseract_binary()
    subprocess.run([binary, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    fixture = ROOT / "tests" / "fixtures" / "ocr_1234.png"
    if read_four_digits(fixture) != "1234":
        raise RuntimeError("Tesseract failed the four-digit OCR sanity image")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content("<title>nadlan sanity</title>")
            if page.title() != "nadlan sanity":
                raise RuntimeError("Chromium sanity page failed")
        finally:
            browser.close()
    searches, errors = load_searches()
    if errors and strict_config:
        raise RuntimeError("Invalid search files: " + "; ".join(errors))
    if errors:
        logging.warning("Invalid search files: %s", "; ".join(errors))
    Storage()
    print(f"Sanity OK: Python {sys.version.split()[0]}, Tesseract OCR, Chromium, {len(searches)} search config(s), SQLite")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled Nadlan searches and local dashboard")
    command = parser.add_subparsers(dest="command", required=True)
    serve_command = command.add_parser("serve", help="Run dashboard and daily scheduler")
    serve_command.add_argument("--port", type=int, help="Override settings.toml port for this run")
    command.add_parser("check", help="Check Python, OCR, browser, configs, and database")
    once = command.add_parser("run-once", help="Run enabled searches now and exit")
    once.add_argument("--search", help="Run one search id instead of all enabled searches")
    args = parser.parse_args()
    setup_logging()
    if args.command == "check":
        check_environment()
        return
    settings = load_settings()
    if args.command == "serve" and args.port is not None:
        if not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
        settings = replace(settings, port=args.port)
    service = Service(settings)
    if args.command == "run-once":
        service.storage.recover_interrupted()
        accepted, message = service.submit_manual(args.search)
        if not accepted:
            raise RuntimeError(message)
        service._worker.start()
        service._queue.join()
        batch = service.storage.recent_batches(1)[0]
        if batch["status"] != "success":
            raise RuntimeError(f"Batch finished with status {batch['status']}; check {DATA_DIR / 'logs' / 'service.log'}")
        print(f"Batch {message} completed successfully")
        return
    check_environment(strict_config=False)
    app = create_app(service)
    server = create_server(app, host="127.0.0.1", port=settings.port, threads=4)
    service.start()
    print(f"Dashboard: http://127.0.0.1:{settings.port}", flush=True)
    try:
        server.run()
    finally:
        service.stop()
        server.close()


if __name__ == "__main__":
    main()
