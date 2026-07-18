import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB = os.path.join(ROOT, "web")
for path in (ROOT, WEB):
    if path not in sys.path:
        sys.path.insert(0, path)

import app as web_app


class DashboardHelperTests(unittest.TestCase):
    def test_asset_version_prefers_explicit_env_value(self):
        old = os.environ.get("TDM_WEB_ASSET_VERSION")
        os.environ["TDM_WEB_ASSET_VERSION"] = "test-version-123"
        try:
            self.assertEqual(web_app.get_asset_version(), "test-version-123")
        finally:
            if old is None:
                os.environ.pop("TDM_WEB_ASSET_VERSION", None)
            else:
                os.environ["TDM_WEB_ASSET_VERSION"] = old

    def test_build_active_drop_payload_includes_id_and_progress_health(self):
        drop = SimpleNamespace(
            id="drop-1",
            name="Drop One",
            current_minutes=42,
            required_minutes=90,
            remaining_minutes=48,
            progress_percentage=47,
            progress=42 / 90,
            campaign=SimpleNamespace(name="Campaign", game=SimpleNamespace(name="Game")),
            benefits=[],
        )
        now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        payload = web_app.build_active_drop_payload(drop, "gql", now=now)
        self.assertEqual(payload["drop_id"], "drop-1")
        self.assertEqual(payload["current_minutes"], 42)
        self.assertEqual(payload["progress_health"]["state"], "ok")
        self.assertEqual(payload["progress_health"]["last_progress_change_at"], now.isoformat())

    def test_progress_health_warns_when_progress_stale(self):
        now = datetime(2026, 7, 18, 12, 10, tzinfo=timezone.utc)
        old = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        health = web_app.get_progress_health("drop-1", 10, 90, now=now, previous={
            "drop_id": "drop-1",
            "current_minutes": 10,
            "updated_at": old,
        })
        self.assertEqual(health["state"], "stale")
        self.assertGreaterEqual(health["minutes_since_progress_change"], 10)
        self.assertIn("Progress has not changed", health["message"])


if __name__ == "__main__":
    unittest.main()
