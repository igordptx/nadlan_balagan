"""SQLite run history; every database path stays under the repository root."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .config import DATA_DIR, SearchConfig
from .browser import BrowserResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: Path = DATA_DIR / "nadlan.sqlite3") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    scheduled_date TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    search_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    row_count INTEGER,
                    page_count INTEGER,
                    columns_json TEXT,
                    rows_json TEXT,
                    csv_path TEXT,
                    result_url TEXT,
                    error TEXT,
                    FOREIGN KEY(batch_id) REFERENCES batches(id)
                );
                CREATE INDEX IF NOT EXISTS runs_search_status ON runs(search_id, status, finished_at);
            """)

    def recover_interrupted(self) -> None:
        with self.connect() as db:
            db.execute("UPDATE batches SET status='interrupted', finished_at=? WHERE status IN ('queued','running')", (utc_now(),))
            db.execute("UPDATE runs SET status='interrupted', finished_at=?, error='Service stopped during this run' WHERE status='running'", (utc_now(),))

    def scheduled_attempt_exists(self, day: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM batches WHERE trigger='scheduled' AND scheduled_date=? AND status!='interrupted' LIMIT 1",
                (day,),
            ).fetchone()
        return row is not None

    def create_batch(self, trigger: str, scheduled_date: str | None = None) -> str:
        batch_id = uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO batches (id, trigger, scheduled_date, status, created_at) VALUES (?,?,?,?,?)",
                (batch_id, trigger, scheduled_date, "queued", utc_now()),
            )
        return batch_id

    def set_batch_status(self, batch_id: str, status: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE batches SET status=?, finished_at=? WHERE id=?",
                (status, utc_now() if status not in ("queued", "running") else None, batch_id),
            )

    def start_run(self, batch_id: str, search: SearchConfig) -> str:
        run_id = uuid4().hex
        from dataclasses import asdict
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs (id,batch_id,search_id,title,config_json,status,started_at) VALUES (?,?,?,?,?,?,?)",
                (run_id, batch_id, search.id, search.title, json.dumps(asdict(search), ensure_ascii=False), "running", utc_now()),
            )
        return run_id

    def finish_run(self, run_id: str, result: BrowserResult) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE runs SET status='success', finished_at=?, row_count=?, page_count=?,
                   columns_json=?, rows_json=?, csv_path=?, result_url=? WHERE id=?""",
                (utc_now(), result.reported_count, result.page_count,
                 json.dumps(result.columns, ensure_ascii=False), json.dumps(result.rows, ensure_ascii=False),
                 str(result.csv_path), result.url, run_id),
            )

    def fail_run(self, run_id: str, error: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?",
                (utc_now(), error[:2000], run_id),
            )

    def latest(self, search_id: str, status: str | None = None) -> dict | None:
        sql = "SELECT * FROM runs WHERE search_id=?"
        params: list[str] = [search_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY started_at DESC, rowid DESC LIMIT 1"
        with self.connect() as db:
            row = db.execute(sql, params).fetchone()
        return dict(row) if row else None

    def recent_batches(self, limit: int = 10) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM batches ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
