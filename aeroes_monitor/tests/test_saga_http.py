"""Testes da aquisição HTTP com sessão requests fake (sem rede nem browser)."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

import saga_http

BASE_URL = "https://saga.example/login"
SCHEDULE_URL = "https://saga.example/schedules/personal"

LOGIN_HTML = (
    '<form method="post" action="/login">'
    '<input type="hidden" name="_token" value="TOK123">'
    '<input name="email"><input name="password"></form>'
)
DASHBOARD_HTML = '<div id="navbarDropdownProfile">Perfil</div>'
SCHEDULE_HTML = (
    "<html><body><script>\n"
    'const allSchedules = [{"start_at_raw":"2026-07-09 07:00:00",'
    '"end_at_raw":"2026-07-09 08:00:00","status":"CONFIRMED",'
    '"aircraft":{"registration":"PP-AYB"},"student":{"nickname":"Ana"}}];\n'
    "</script></body></html>"
)
SUN_XML = "<aisweb><day><sunrise>09:17</sunrise><sunset>20:15</sunset></day></aisweb>"


def _config(max_days=2):
    return SimpleNamespace(
        saga=SimpleNamespace(
            base_url=BASE_URL, schedule_url=SCHEDULE_URL, request_timeout_seconds=5
        ),
        credentials=SimpleNamespace(username="piloto@example.com", password="s3cr3t"),
        aircraft={"PP-AYB": "C152"},
        monitor=SimpleNamespace(max_days=max_days),
    )


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class FakeSession:
    """Sessão scriptada: responde por URL; registra chamadas."""

    def __init__(self, login_get=LOGIN_HTML, login_post=DASHBOARD_HTML,
                 schedule=SCHEDULE_HTML, sun=(SUN_XML, 200)):
        self.headers = {}
        self.calls = []
        self._login_get = login_get
        self._login_post = login_post
        self._schedule = schedule
        self._sun = sun

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        if url == BASE_URL:
            return FakeResponse(self._login_get)
        if url == SCHEDULE_URL:
            return FakeResponse(self._schedule)
        if url.endswith(saga_http.SUN_ENDPOINT):
            text, status = self._sun
            return FakeResponse(text, status)
        raise AssertionError(f"GET inesperado: {url}")

    def post(self, url, data=None, timeout=None, allow_redirects=True):
        self.calls.append(("POST", url, data))
        return FakeResponse(self._login_post)


def _run(session, config=None, today=date(2026, 7, 9)):
    with mock.patch("saga_http.requests.Session", return_value=session), \
         mock.patch("saga_http.local_today", return_value=today):
        return saga_http.scan(config or _config())


class ScanHappyPathTest(unittest.TestCase):
    def test_builds_days_from_all_schedules(self):
        result = _run(FakeSession())
        self.assertEqual(len(result.days), 2)
        self.assertEqual(result.days[0].day, date(2026, 7, 9))
        # 09:17Z -> 06:17 local.
        self.assertEqual(result.days[0].sunrise.strftime("%H:%M"), "06:17")
        self.assertIn("PP-AYB", [r.name for r in result.days[0].resources])

    def test_token_captured_and_posted_in_order(self):
        session = FakeSession()
        _run(session)
        self.assertEqual([c[0] for c in session.calls], ["GET", "POST", "GET", "GET"])
        post = next(c for c in session.calls if c[0] == "POST")
        self.assertEqual(post[2]["_token"], "TOK123")
        self.assertEqual(post[2]["email"], "piloto@example.com")

    def test_user_agent_is_set(self):
        session = FakeSession()
        _run(session)
        self.assertIn("Chrome", session.headers["User-Agent"])


class ScanLoginErrorTest(unittest.TestCase):
    def test_missing_token_raises_with_html(self):
        with self.assertRaises(saga_http.LoginError) as ctx:
            _run(FakeSession(login_get="<form>sem token</form>"))
        self.assertIsNotNone(ctx.exception.page_html)

    def test_post_still_shows_login_form_raises(self):
        with self.assertRaises(saga_http.LoginError):
            _run(FakeSession(login_post=LOGIN_HTML))

    def test_schedule_page_bounces_to_login_raises(self):
        with self.assertRaises(saga_http.LoginError):
            _run(FakeSession(schedule=LOGIN_HTML))


class ScanScheduleErrorTest(unittest.TestCase):
    def test_missing_all_schedules_raises_with_html(self):
        with self.assertRaises(saga_http.ScanHttpError) as ctx:
            _run(FakeSession(schedule="<html>sem variavel</html>"))
        self.assertIn("allSchedules", str(ctx.exception))
        self.assertIsNotNone(ctx.exception.page_html)

    def test_invalid_json_raises(self):
        with self.assertRaises(saga_http.ScanHttpError):
            _run(FakeSession(schedule="<script>const allSchedules = [nope];</script>"))


class ScanSunRecoverableTest(unittest.TestCase):
    def test_sun_http_error_is_recoverable(self):
        result = _run(FakeSession(sun=("", 500)))
        self.assertEqual(result.days, ())
        self.assertEqual(len(result.errors), 1)
        self.assertIn("sol", result.errors[0].message.lower())

    def test_sun_garbage_xml_is_recoverable(self):
        result = _run(FakeSession(sun=("<html>erro</html>", 200)))
        self.assertEqual(result.days, ())
        self.assertEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()
