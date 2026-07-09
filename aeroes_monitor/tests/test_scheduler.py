"""Testes da varredura multi-dia com métodos internos mockados."""
import unittest
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest import mock

from models import DaySchedule, ScanResult
from scheduler import MAX_CONSECUTIVE_FAILURES, ScheduleScanner

SELECTORS = {
    "schedule_container": (".schedule",),
    "schedule_date": (".date",),
    "next_day_button": (".next",),
    "sunrise_text": (".sunrise",),
    "sunset_text": (".sunset",),
    "resource_row": (".row",),
    "resource_name": (".name",),
    "event_item": (".event",),
    "login_form": ("form.login",),
    "logged_in_marker": (".user-menu",),
    "login_username": ("#user",),
    "login_password": ("#pass",),
    "login_submit": ("#submit",),
}


def _config(max_days=3):
    return SimpleNamespace(
        monitor=SimpleNamespace(max_days=max_days),
        selenium=SimpleNamespace(schedule_url="", element_timeout_seconds=1),
        selectors=SELECTORS,
        aircraft={"PT-ABC": "C-152"},
        credentials=SimpleNamespace(username="u", password="p"),
    )


def _day(index):
    return DaySchedule(
        day=date(2026, 7, 14) + timedelta(days=index),
        sunrise=time(5, 45),
        sunset=time(17, 30),
        resources=(),
    )


def _scanner(max_days=3):
    return ScheduleScanner(driver=mock.Mock(), config=_config(max_days))


class ScanLoopTest(unittest.TestCase):
    def test_happy_path_scans_all_days(self):
        scanner = _scanner(max_days=3)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(scanner, "_scan_single_day", side_effect=[_day(0), _day(1), _day(2)]), \
             mock.patch.object(scanner, "_advance_day", return_value=True) as advance, \
             mock.patch("scheduler.read_text_from_selectors", return_value="14/07/2026"):
            result = scanner.scan()
        self.assertIsInstance(result, ScanResult)
        self.assertEqual(len(result.days), 3)
        self.assertEqual(result.errors, ())
        self.assertEqual(advance.call_count, 2)  # não avança após o último dia

    def test_single_day_failure_is_recoverable(self):
        scanner = _scanner(max_days=3)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(
                 scanner,
                 "_scan_single_day",
                 side_effect=[_day(0), ValueError("sol ausente"), _day(2)],
             ), \
             mock.patch.object(scanner, "_advance_day", return_value=True), \
             mock.patch("scheduler.read_text_from_selectors", return_value="15/07/2026"):
            result = scanner.scan()
        self.assertEqual(len(result.days), 2)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].day_index, 1)
        self.assertIn("sol ausente", result.errors[0].message)

    def test_consecutive_failures_truncate_scan(self):
        scanner = _scanner(max_days=10)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(scanner, "_scan_single_day", side_effect=ValueError("boom")), \
             mock.patch.object(scanner, "_advance_day", return_value=True) as advance, \
             mock.patch("scheduler.read_text_from_selectors", return_value=""):
            result = scanner.scan()
        self.assertEqual(result.days, ())
        # 3 erros de dia + 1 erro de truncamento.
        self.assertEqual(len(result.errors), MAX_CONSECUTIVE_FAILURES + 1)
        self.assertIn("falhas consecutivas", result.errors[-1].message)
        self.assertEqual(advance.call_count, MAX_CONSECUTIVE_FAILURES - 1)

    def test_advance_failure_truncates_with_partial_result(self):
        scanner = _scanner(max_days=5)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(scanner, "_scan_single_day", return_value=_day(0)), \
             mock.patch.object(scanner, "_advance_day", return_value=False), \
             mock.patch("scheduler.read_text_from_selectors", return_value="14/07/2026"):
            result = scanner.scan()
        self.assertEqual(len(result.days), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("avançar", result.errors[0].message)


class EnsureSessionTest(unittest.TestCase):
    def test_relogin_when_back_at_login_page(self):
        scanner = _scanner()
        with mock.patch("scheduler.is_login_page", return_value=True), \
             mock.patch("scheduler.login") as do_login, \
             mock.patch.object(scanner, "_open_schedule") as reopen:
            scanner._ensure_session()
        do_login.assert_called_once()
        reopen.assert_called_once()

    def test_noop_when_session_alive(self):
        scanner = _scanner()
        with mock.patch("scheduler.is_login_page", return_value=False), \
             mock.patch("scheduler.login") as do_login:
            scanner._ensure_session()
        do_login.assert_not_called()


class ResolveDateTest(unittest.TestCase):
    def test_parses_label(self):
        scanner = _scanner()
        self.assertEqual(scanner._resolve_date(0, "Segunda, 14/07/2026"), date(2026, 7, 14))

    def test_fallback_from_last_parsed(self):
        scanner = _scanner()
        scanner._resolve_date(0, "14/07/2026")
        self.assertEqual(scanner._resolve_date(2, "sem data"), date(2026, 7, 16))

    def test_fallback_from_today_when_never_parsed(self):
        scanner = _scanner()
        expected = date.today() + timedelta(days=1)
        self.assertEqual(scanner._resolve_date(1, "???"), expected)


class ReadSunTimesTest(unittest.TestCase):
    def test_reads_from_selector_text(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value="Nascer do sol: 05:45"):
            self.assertEqual(scanner._read_sunrise(""), time(5, 45))

    def test_single_time_in_dedicated_element(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value="05:45"):
            self.assertEqual(scanner._read_sunrise(""), time(5, 45))

    def test_falls_back_to_page_text(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value=None):
            self.assertEqual(
                scanner._read_sunset("Pôr do sol: 17:30"), time(17, 30)
            )

    def test_raises_when_absent(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value=None):
            with self.assertRaises(ValueError):
                scanner._read_sunrise("página sem informação de sol")


if __name__ == "__main__":
    unittest.main()
