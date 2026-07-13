"""Testes da aquisição via allSchedules com driver fake (sem browser)."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

from models import ScanResult
from scheduler import ScheduleScanner

SELECTORS = {
    "login_form": ("form.login",),
    "logged_in_marker": (".user-menu",),
    "login_username": ("#user",),
    "login_password": ("#pass",),
    "login_submit": ("#submit",),
}

SUN_XML = (
    "<aisweb><day><sunrise>09:17</sunrise><sunset>20:15</sunset></day></aisweb>"
)

RAW = [
    {
        "start_at_raw": "2026-07-09 07:00:00",
        "end_at_raw": "2026-07-09 08:00:00",
        "status": "CONFIRMED",
        "aircraft": {"registration": "PP-AYB"},
        "student": {"nickname": "Ana"},
    }
]


def _config(max_days=2, schedule_url="https://saga.example/schedules/personal"):
    return SimpleNamespace(
        monitor=SimpleNamespace(max_days=max_days),
        selenium=SimpleNamespace(
            base_url="https://saga.example/login",
            schedule_url=schedule_url,
            element_timeout_seconds=1,
        ),
        selectors=SELECTORS,
        aircraft={"PP-AYB": "Cessna 152"},
        credentials=SimpleNamespace(username="u", password="p"),
    )


class FakeDriver:
    """Driver mínimo: get() registra URLs; scripts respondem por roteiro."""

    def __init__(self, all_schedules=RAW, sun_response=SUN_XML, has_data=True):
        self.urls: list[str] = []
        self.all_schedules = all_schedules
        self.sun_response = sun_response
        self.has_data = has_data

    def get(self, url):
        self.urls.append(url)

    def execute_script(self, script, *args):
        if "typeof allSchedules" in script:
            return self.has_data
        if "return allSchedules" in script:
            return self.all_schedules
        raise AssertionError(f"script inesperado: {script}")

    def execute_async_script(self, script, *args):
        if self.sun_response is None:
            return {"status": -1, "body": "falha de rede"}
        return {"status": 200, "body": self.sun_response}

    def set_script_timeout(self, seconds):
        pass


def _scan(driver, config=None, today=date(2026, 7, 9)):
    scanner = ScheduleScanner(driver, config or _config())
    with mock.patch("scheduler.is_login_page", return_value=False), \
         mock.patch("scheduler.local_today", return_value=today):
        return scanner.scan()


class ScanTest(unittest.TestCase):
    def test_happy_path_builds_days_from_all_schedules(self):
        driver = FakeDriver()
        result = _scan(driver)
        self.assertIsInstance(result, ScanResult)
        self.assertEqual(len(result.days), 2)
        self.assertEqual(result.days[0].day, date(2026, 7, 9))
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        # 07:00 local vindo de start_at_raw; sol 09:17Z -> 06:17 local.
        self.assertEqual(result.days[0].sunrise.strftime("%H:%M"), "06:17")
        self.assertEqual(driver.urls, ["https://saga.example/schedules/personal"])

    def test_falls_back_to_base_url_without_schedule_url(self):
        driver = FakeDriver()
        _scan(driver, _config(schedule_url=""))
        self.assertEqual(driver.urls, ["https://saga.example/login"])

    def test_missing_all_schedules_is_fatal(self):
        driver = FakeDriver(has_data=False)
        with self.assertRaises(Exception) as ctx:
            _scan(driver)
        self.assertIn("allSchedules", str(ctx.exception))

    def test_non_list_all_schedules_is_fatal(self):
        driver = FakeDriver(all_schedules={"nada": 1})
        with self.assertRaises(ValueError):
            _scan(driver)

    def test_sun_failure_is_recoverable_error(self):
        driver = FakeDriver(sun_response=None)
        result = _scan(driver)
        self.assertEqual(result.days, ())
        self.assertEqual(len(result.errors), 1)
        self.assertIn("sol", result.errors[0].message.lower())

    def test_relogin_when_session_expired(self):
        driver = FakeDriver()
        scanner = ScheduleScanner(driver, _config())
        with mock.patch("scheduler.is_login_page", side_effect=[True, False]), \
             mock.patch("scheduler.login") as do_login:
            scanner.scan()
        do_login.assert_called_once()
        # get() da página da escala ocorre de novo após o relogin.
        self.assertEqual(len(driver.urls), 2)


if __name__ == "__main__":
    unittest.main()
