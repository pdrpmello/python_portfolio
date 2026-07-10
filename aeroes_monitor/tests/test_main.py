"""Testes da orquestração (run_scan) e CLI com dependências mockadas."""
import tempfile
import unittest
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from main import main, parse_args, run_scan
from models import DaySchedule, ResourceSchedule, ScanResult, TimePeriod
from notifications import NotifyState, load_state, save_state


def _config():
    return SimpleNamespace(
        credentials=SimpleNamespace(username="u", password="p"),
        discord=SimpleNamespace(webhook_url="https://discord.example/webhook"),
        monitor=SimpleNamespace(
            max_days=1,
            check_interval_seconds=900,
            turnaround_minutes=30,
            min_flight_minutes=60,
            max_flight_minutes=120,
        ),
        selenium=SimpleNamespace(
            base_url="https://saga.example.com",
            schedule_url="https://saga.example.com/schedules/personal",
            headless=True,
            page_load_timeout_seconds=5,
            element_timeout_seconds=5,
            debug_dir="debug",
        ),
        selectors={},
        aircraft={"PT-ABC": "C-152"},
        logging=SimpleNamespace(level="INFO", file=""),
    )


def _scan_result(busy=()):
    """Um sábado com janela ampla: sem ocupação ⇒ 1 janela 🟢 o dia todo."""
    return ScanResult(
        days=(
            DaySchedule(
                day=date(2026, 7, 11),  # sábado
                sunrise=time(6, 0),
                sunset=time(17, 0),
                resources=(
                    ResourceSchedule(
                        name="PT-ABC", model="C-152", busy_periods=tuple(busy)
                    ),
                ),
            ),
        ),
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


@mock.patch("main.ScheduleScanner")
@mock.patch("main.login")
@mock.patch("main.create_driver")
@mock.patch("main.DiscordNotifier")
class RunScanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_path = Path(self._tmp.name) / "state.json"

    def test_first_run_sends_baseline_and_saves_state(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_summary.assert_called_once()
        notifier.send_report.assert_called_once()
        notifier.send_message.assert_not_called()
        state = load_state(self.state_path)
        self.assertTrue(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)

    def test_no_changes_is_silent(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline
        notifier.reset_mock()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_summary.assert_not_called()
        notifier.send_report.assert_not_called()
        notifier.send_message.assert_not_called()
        notifier.send_error.assert_not_called()

    def test_new_window_notifies_openings_only(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        # Baseline com o dia inteiro ocupado ⇒ nenhuma janela.
        scanner_cls.return_value.scan.return_value = _scan_result(
            busy=(TimePeriod(start=time(6, 0), end=time(17, 0)),)
        )
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        # Cancelaram tudo ⇒ abre janela nova.
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_message.assert_called_once()
        self.assertIn("Abriu horário", notifier.send_message.call_args.args[0])
        notifier.send_summary.assert_not_called()
        notifier.send_report.assert_not_called()

    def test_error_notifies_only_on_transition(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline ok
        notifier.reset_mock()
        scanner_cls.return_value.scan.side_effect = RuntimeError("SAGA fora do ar")
        with mock.patch("main.save_debug_artifacts"):
            self.assertFalse(run_scan(_config(), self.state_path))
            notifier.send_error.assert_called_once()  # transição ok→falha
            notifier.reset_mock()
            self.assertFalse(run_scan(_config(), self.state_path))
            notifier.send_error.assert_not_called()  # falha repetida: silêncio
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # janelas preservadas

    def test_recovery_notifies_and_diffs_against_preserved_windows(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        save_state(
            self.state_path,
            NotifyState(
                windows=frozenset({("2026-07-11", "PT-ABC", "06:00", "17:00")}),
                last_scan_ok=False,
            ),
        )
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        sent = [c.args[0] for c in notifier.send_message.call_args_list]
        self.assertTrue(any("voltou a funcionar" in m for m in sent))
        # Janela é a mesma do estado preservado ⇒ nenhum "Abriu horário".
        self.assertFalse(any("Abriu horário" in m for m in sent))

    def test_degraded_scan_counts_as_failure(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        from models import ScanError

        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        scanner_cls.return_value.scan.return_value = ScanResult(
            days=(), errors=(ScanError(day_index=0, day_label="sol", message="sem sol"),)
        )
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # preservadas

    def test_failure_without_state_notifies_but_keeps_baseline_pending(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.side_effect = RuntimeError("boom")
        with mock.patch("main.save_debug_artifacts"):
            self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        self.assertIsNone(load_state(self.state_path))  # baseline continua pendente

    def test_driver_quit_failure_does_not_break_result(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        create_driver.return_value.quit.side_effect = RuntimeError("já fechado")
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))


class MainExitCodesTest(unittest.TestCase):
    def test_missing_config_returns_2(self):
        self.assertEqual(main(["--once", "--config", "nao_existe_123.ini"]), 2)


if __name__ == "__main__":
    unittest.main()
