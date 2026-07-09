"""Testes da orquestração (run_scan) e CLI com dependências mockadas."""
import unittest
from types import SimpleNamespace
from unittest import mock

from main import main, parse_args, run_scan
from models import ScanResult


def _config():
    return SimpleNamespace(
        credentials=SimpleNamespace(username="u", password="p"),
        discord=SimpleNamespace(webhook_url="https://discord.example/webhook"),
        monitor=SimpleNamespace(
            max_days=1,
            check_interval_seconds=3600,
            turnaround_minutes=30,
            min_flight_minutes=60,
            max_flight_minutes=120,
        ),
        selenium=SimpleNamespace(
            base_url="https://saga.example.com",
            schedule_url="",
            headless=True,
            page_load_timeout_seconds=5,
            element_timeout_seconds=5,
            debug_dir="debug",
        ),
        selectors={},
        aircraft={"PT-ABC": "C-152"},
        logging=SimpleNamespace(level="INFO", file=""),
    )


class ParseArgsTest(unittest.TestCase):
    def test_defaults(self):
        args = parse_args([])
        self.assertFalse(args.once)
        self.assertEqual(args.config, "config.ini")

    def test_once_and_custom_config(self):
        args = parse_args(["--once", "--config", "outro.ini"])
        self.assertTrue(args.once)
        self.assertEqual(args.config, "outro.ini")


class RunScanTest(unittest.TestCase):
    @mock.patch("main.ScheduleScanner")
    @mock.patch("main.login")
    @mock.patch("main.create_driver")
    @mock.patch("main.DiscordNotifier")
    def test_happy_path(self, notifier_cls, create_driver, do_login, scanner_cls):
        notifier = notifier_cls.return_value
        driver = create_driver.return_value
        scanner_cls.return_value.scan.return_value = ScanResult()
        self.assertTrue(run_scan(_config()))
        notifier.send_scan_started.assert_called_once()
        notifier.send_summary.assert_called_once()
        notifier.send_report.assert_called_once()
        notifier.send_error.assert_not_called()
        do_login.assert_called_once()
        driver.quit.assert_called_once()

    @mock.patch("main.save_debug_artifacts")
    @mock.patch("main.ScheduleScanner")
    @mock.patch("main.login", side_effect=RuntimeError("login quebrou"))
    @mock.patch("main.create_driver")
    @mock.patch("main.DiscordNotifier")
    def test_fatal_error_notifies_saves_artifacts_and_quits(
        self, notifier_cls, create_driver, do_login, scanner_cls, save_artifacts
    ):
        notifier = notifier_cls.return_value
        driver = create_driver.return_value
        self.assertFalse(run_scan(_config()))
        notifier.send_error.assert_called_once()
        self.assertIn("login quebrou", notifier.send_error.call_args.args[0])
        save_artifacts.assert_called_once()
        driver.quit.assert_called_once()
        scanner_cls.return_value.scan.assert_not_called()

    @mock.patch("main.create_driver", side_effect=RuntimeError("sem chrome"))
    @mock.patch("main.DiscordNotifier")
    def test_driver_creation_failure_still_notifies(self, notifier_cls, create_driver):
        notifier = notifier_cls.return_value
        self.assertFalse(run_scan(_config()))
        notifier.send_error.assert_called_once()

    @mock.patch("main.ScheduleScanner")
    @mock.patch("main.login")
    @mock.patch("main.create_driver")
    @mock.patch("main.DiscordNotifier")
    def test_quit_failure_does_not_break_result(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        create_driver.return_value.quit.side_effect = RuntimeError("já fechado")
        scanner_cls.return_value.scan.return_value = ScanResult()
        self.assertTrue(run_scan(_config()))


class MainExitCodesTest(unittest.TestCase):
    def test_missing_config_returns_2(self):
        self.assertEqual(main(["--once", "--config", "nao_existe_123.ini"]), 2)


if __name__ == "__main__":
    unittest.main()
