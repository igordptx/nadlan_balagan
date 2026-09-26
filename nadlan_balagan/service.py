"""One browser worker and a UTC daily scheduler."""

from datetime import datetime, time as dt_time, timedelta, timezone
import logging
from pathlib import Path
from queue import Queue
import threading
import time

from .browser import run_search
from .config import DATA_DIR, SEARCH_DIR, SearchConfig, Settings, load_searches
from .storage import Storage


LOG = logging.getLogger(__name__)
UTC = timezone.utc


def next_8_utc(now: datetime) -> datetime:
    now = now.astimezone(UTC)
    today = datetime.combine(now.date(), dt_time(8), UTC)
    return today if now < today else today + timedelta(days=1)


class Service:
    def __init__(self, settings: Settings, storage: Storage | None = None, search_dir: Path = SEARCH_DIR) -> None:
        self.settings = settings
        self.storage = storage or Storage()
        self.search_dir = search_dir
        self._queue: Queue[tuple[str, list[str]]] = Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._current: dict | None = None
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._work, name="nadlan-worker", daemon=True)
        self._scheduler = threading.Thread(target=self._schedule, name="nadlan-scheduler", daemon=True)

    def start(self) -> None:
        self.storage.recover_interrupted()
        self._worker.start()
        self._scheduler.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(("", []))
        self._worker.join(timeout=5)
        self._scheduler.join(timeout=5)

    def status(self) -> dict:
        with self._lock:
            return {"pending": self._pending, "current": self._current}

    def submit_manual(self, search_id: str | None = None) -> tuple[bool, str]:
        searches, errors = load_searches(self.search_dir)
        if search_id:
            search = searches.get(search_id)
            if not search or not search.enabled:
                return False, f"Search {search_id!r} is missing or disabled"
            ids = [search_id]
        else:
            ids = [item.id for item in searches.values() if item.enabled]
        if not ids:
            return False, "No enabled searches are configured"
        with self._lock:
            if self._pending:
                return False, "A search batch is already running or queued"
            batch_id = self.storage.create_batch("manual")
            self._pending += 1
            self._queue.put((batch_id, ids))
        if errors:
            LOG.warning("Config errors: %s", "; ".join(errors))
        return True, batch_id

    def submit_scheduled(self, day: str) -> bool:
        with self._lock:
            if self.storage.scheduled_attempt_exists(day):
                return False
            searches, errors = load_searches(self.search_dir)
            ids = [item.id for item in searches.values() if item.enabled]
            batch_id = self.storage.create_batch("scheduled", day)
            self._pending += 1
            self._queue.put((batch_id, ids))
        if errors:
            LOG.warning("Config errors: %s", "; ".join(errors))
        LOG.info("Scheduled batch %s for %s with %d searches", batch_id, day, len(ids))
        return True

    def _schedule(self) -> None:
        while not self._stop.is_set():
            now = datetime.now(UTC)
            today_at_8 = datetime.combine(now.date(), dt_time(8), UTC)
            if now >= today_at_8:
                try:
                    self.submit_scheduled(now.date().isoformat())
                except Exception:
                    LOG.exception("Could not enqueue scheduled batch")
            wait = max(0.5, (next_8_utc(now) - now).total_seconds())
            self._stop.wait(min(wait, 60))

    def _work(self) -> None:
        while not self._stop.is_set():
            batch_id, ids = self._queue.get()
            if not batch_id:
                self._queue.task_done()
                break
            try:
                self._run_batch(batch_id, ids)
            except Exception:
                LOG.exception("Batch %s failed unexpectedly", batch_id)
                self.storage.set_batch_status(batch_id, "failed")
            finally:
                with self._lock:
                    self._pending -= 1
                    self._current = None
                self._queue.task_done()

    def _run_batch(self, batch_id: str, ids: list[str]) -> None:
        self.storage.set_batch_status(batch_id, "running")
        failures = 0
        if not ids:
            self.storage.set_batch_status(batch_id, "failed")
            LOG.error("Batch %s has no enabled searches", batch_id)
            return
        for index, search_id in enumerate(ids):
            if self._stop.is_set():
                self.storage.set_batch_status(batch_id, "interrupted")
                return
            searches, errors = load_searches(self.search_dir)
            search: SearchConfig | None = searches.get(search_id)
            if search is None or not search.enabled:
                failures += 1
                LOG.error("Search %s missing or disabled; config errors: %s", search_id, errors)
                continue
            run_id = self.storage.start_run(batch_id, search)
            with self._lock:
                self._current = {"batch_id": batch_id, "search_id": search_id, "started_at": datetime.now(UTC).isoformat(timespec="seconds")}
            directory = DATA_DIR / "runs" / batch_id / run_id
            try:
                result = run_search(search, self.settings, directory)
                self.storage.finish_run(run_id, result)
                LOG.info("Search %s completed: %d rows on %d pages", search_id, result.reported_count, result.page_count)
            except Exception as exc:
                failures += 1
                self.storage.fail_run(run_id, str(exc))
                LOG.exception("Search %s failed", search_id)
            if index + 1 < len(ids) and not self._stop.is_set():
                self._stop.wait(self.settings.delay_seconds)
        self.storage.set_batch_status(batch_id, "success" if failures == 0 else "partial" if failures < len(ids) else "failed")
