import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.environ.get(
    "APP_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
)
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

    def test_json_from_view_response_preserves_tuple_error_status(self):
        with web_app.app.app_context():
            data, status = web_app._json_from_view_response((web_app.jsonify({'error': 'boom'}), 503))
        self.assertEqual(status, 503)
        self.assertEqual(data, {'error': 'boom'})

    def test_json_from_view_response_uses_response_status_when_not_tuple(self):
        with web_app.app.app_context():
            response = web_app.jsonify({'ok': True})
            response.status_code = 202
            data, status = web_app._json_from_view_response(response)
        self.assertEqual(status, 202)
        self.assertEqual(data, {'ok': True})

    def test_wake_miner_after_auth_saves_and_fetches_inventory(self):
        calls = []
        twitch = SimpleNamespace(
            save=lambda force=False: calls.append(("save", force)),
            change_state=lambda state: calls.append(("state", state)),
        )
        old_loop = web_app.main_event_loop
        web_app.main_event_loop = None
        try:
            web_app.wake_miner_after_auth(twitch)
        finally:
            web_app.main_event_loop = old_loop
        self.assertEqual(calls, [("save", True), ("state", web_app.State.INVENTORY_FETCH)])

    def test_schedule_miner_state_uses_registered_event_loop_threadsafe(self):
        calls = []
        class FakeLoop:
            def is_closed(self):
                return False
            def call_soon_threadsafe(self, func, *args):
                calls.append(("scheduled", func, args))

        twitch = SimpleNamespace(change_state=lambda state: calls.append(("state", state)))
        old_loop = web_app.main_event_loop
        web_app.main_event_loop = FakeLoop()
        try:
            web_app.schedule_miner_state(twitch, web_app.State.INVENTORY_FETCH)
        finally:
            web_app.main_event_loop = old_loop

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "scheduled")
        self.assertEqual(calls[0][2], (web_app.State.INVENTORY_FETCH,))

    def test_health_payload_marks_login_required_before_twitch_auth(self):
        twitch = SimpleNamespace(
            _state=SimpleNamespace(name="IDLE"),
            _auth_state=SimpleNamespace(user_id=0, _logged_in=SimpleNamespace(is_set=lambda: False)),
            _session=None,
            inventory=[],
            channels={},
            websocket=SimpleNamespace(websockets=[]),
            watching_channel=SimpleNamespace(get_with_default=lambda default: None),
            get_active_drop=lambda channel: None,
        )
        old_instance = web_app.tdm_instance
        web_app.tdm_instance = twitch
        try:
            payload = web_app.build_health_payload(twitch)
            with web_app.app.test_client() as client:
                response = client.get('/health')
        finally:
            web_app.tdm_instance = old_instance

        self.assertEqual(payload["state"], "needs_login")
        self.assertFalse(payload["checks"]["twitch_login"])
        self.assertIn("Twitch login", payload["message"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["state"], "needs_login")

    def test_health_payload_reports_linked_and_earnable_campaigns(self):
        campaign = SimpleNamespace(
            active=True,
            linked=True,
            eligible=True,
            finished=False,
        )
        twitch = SimpleNamespace(
            _state=SimpleNamespace(name="CHANNEL_SWITCH"),
            _auth_state=SimpleNamespace(user_id=123, _logged_in=SimpleNamespace(is_set=lambda: True)),
            _session=object(),
            inventory=[campaign],
            channels={"chan": object()},
            websocket=SimpleNamespace(websockets=[SimpleNamespace(connected=True)]),
            watching_channel=SimpleNamespace(get_with_default=lambda default: None),
            get_active_drop=lambda channel: None,
        )
        payload = web_app.build_health_payload(twitch)
        self.assertEqual(payload["state"], "ready")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["counts"]["eligible_campaigns"], 1)
        self.assertEqual(payload["counts"]["earnable_campaigns"], 1)
        self.assertEqual(payload["counts"]["channels"], 1)


if __name__ == "__main__":
    unittest.main()
