from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from bs4 import BeautifulSoup

from nadlan_balagan.config import DATA_DIR, Settings
from nadlan_balagan.service import Service, next_8_utc
from nadlan_balagan.storage import Storage
from nadlan_balagan.web import create_app


class SchedulerTests(unittest.TestCase):
    def test_next_run_is_utc_not_local_time(self):
        israel = timezone(timedelta(hours=3))
        self.assertEqual(next_8_utc(datetime(2026, 9, 26, 10, 59, tzinfo=israel)).hour, 8)
        self.assertEqual(next_8_utc(datetime(2026, 9, 26, 11, 1, tzinfo=israel)).day, 27)

    def test_scheduled_batch_does_not_duplicate(self):
        DATA_DIR.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DATA_DIR) as folder:
            root = Path(folder)
            service = Service(Settings(), Storage(root / "test.sqlite3"), root)
            (root / "sample.toml").write_text('''id="sample"\ntitle="Sample"\n[location]\nkind="gush_range"\nfrom=1\nto=1\n[filters]\nproperty_type="דירת מגורים"\ntransaction_type="הכל"\nperiod="last_12_months"\n''', encoding="utf-8")
            self.assertTrue(service.submit_scheduled("2026-09-26"))
            self.assertFalse(service.submit_scheduled("2026-09-26"))
            service.storage.recover_interrupted()
            self.assertFalse(service.storage.scheduled_attempt_exists("2026-09-26"))

    def test_local_dashboard_and_csrf(self):
        DATA_DIR.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DATA_DIR) as folder:
            root = Path(folder)
            service = Service(Settings(), Storage(root / "test.sqlite3"), root)
            app = create_app(service)
            client = app.test_client()
            self.assertEqual(client.get("/health").status_code, 200)
            index = client.get("/")
            self.assertEqual(index.status_code, 200)
            self.assertEqual(client.post("/run", data={}).status_code, 403)
            (root / "sample.toml").write_text('''id="sample"\ntitle="Sample"\n[location]\nkind="gush_range"\nfrom=1\nto=1\n[filters]\nproperty_type="דירת מגורים"\ntransaction_type="הכל"\nperiod="last_12_months"\n''', encoding="utf-8")
            token = BeautifulSoup(client.get("/").data, "html.parser").select_one('input[name="csrf_token"]')["value"]
            response = client.post("/run", data={"csrf_token": token}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(service.status()["pending"], 1)
