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
        saga=SimpleNamespace(
            base_url="https://saga.example.com/login",
            schedule_url="https://saga.example.com/schedules/personal",
            request_timeout_seconds=30,
            debug_dir="debug",
        ),
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


@mock.patch("main.saga_http")
@mock.patch("main.DiscordNotifier")
class RunScanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_path = Path(self._tmp.name) / "state.json"

    def test_first_run_sends_baseline_and_saves_state(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_report.assert_called_once()
        notifier.send_message.assert_not_called()
        state = load_state(self.state_path)
        self.assertTrue(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)
        self.assertEqual(state.days, frozenset({"2026-07-11"}))

    def test_no_changes_is_silent(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline
        notifier.reset_mock()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_report.assert_not_called()
        notifier.send_message.assert_not_called()
        notifier.send_error.assert_not_called()

    def test_new_window_notifies_openings_only(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result(
            busy=(TimePeriod(start=time(6, 0), end=time(17, 0)),)
        )
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        saga_http.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_message.assert_called_once()
        self.assertIn("Abriu horário", notifier.send_message.call_args.args[0])
        self.assertIn("PT-ABC C-152", notifier.send_message.call_args.args[0])
        notifier.send_report.assert_not_called()

    def test_error_notifies_only_on_transition(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline ok
        notifier.reset_mock()
        saga_http.scan.side_effect = RuntimeError("SAGA fora do ar")
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()  # transição ok→falha
        notifier.reset_mock()
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_not_called()  # falha repetida: silêncio
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # janelas preservadas

    def test_recovery_notifies_and_diffs_against_preserved_windows(
        self, notifier_cls, saga_http
    ):
        notifier = notifier_cls.return_value
        save_state(
            self.state_path,
            NotifyState(
                windows=frozenset({("2026-07-11", "PT-ABC", "06:00", "17:00")}),
                days=frozenset({"2026-07-11"}),
                last_scan_ok=False,
            ),
        )
        saga_http.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        sent = [c.args[0] for c in notifier.send_message.call_args_list]
        self.assertTrue(any("voltou a funcionar" in m for m in sent))
        self.assertFalse(any("Abriu horário" in m for m in sent))

    def test_degraded_scan_counts_as_failure(self, notifier_cls, saga_http):
        from models import ScanError

        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        saga_http.scan.return_value = ScanResult(
            days=(), errors=(ScanError(day_index=0, day_label="sol", message="sem sol"),)
        )
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # preservadas

    def test_failure_without_state_notifies_but_keeps_baseline_pending(
        self, notifier_cls, saga_http
    ):
        notifier = notifier_cls.return_value
        saga_http.scan.side_effect = RuntimeError("boom")
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        self.assertIsNone(load_state(self.state_path))  # baseline continua pendente

    def test_state_write_failure_does_not_propagate(self, notifier_cls, saga_http):
        """Contrato de run_scan: OSError persistente no save_state não estoura."""
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline com estado gravado
        with mock.patch(
            "main.save_state", side_effect=OSError("state.json travado pelo OneDrive")
        ):
            self.assertFalse(run_scan(_config(), self.state_path))

    def test_discord_outage_does_not_propagate(self, notifier_cls, saga_http):
        """Discord fora do ar: send_* falhando (inclusive no handler) não estoura."""
        notifier = notifier_cls.return_value
        notifier.send_report.side_effect = ConnectionError("discord fora do ar")
        notifier.send_error.side_effect = ConnectionError("discord fora do ar")
        saga_http.scan.return_value = _scan_result()
        self.assertFalse(run_scan(_config(), self.state_path))
        self.assertIsNone(load_state(self.state_path))  # baseline continua pendente

    def test_failure_with_page_html_saves_debug(self, notifier_cls, saga_http):
        """Exceção com page_html: HTML salvo em debug_dir para recalibração."""
        with tempfile.TemporaryDirectory() as dbg:
            cfg = _config()
            cfg.saga.debug_dir = dbg
            exc = RuntimeError("layout mudou")
            exc.page_html = "<html>falha</html>"
            saga_http.scan.side_effect = exc
            self.assertFalse(run_scan(cfg, self.state_path))
            files = list(Path(dbg).glob("*-fatal.html"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(encoding="utf-8"), "<html>falha</html>")


class MainExitCodesTest(unittest.TestCase):
    def test_missing_config_returns_2(self):
        self.assertEqual(main(["--once", "--config", "nao_existe_123.ini"]), 2)


class MainLoopTest(unittest.TestCase):
    def test_loop_survives_run_scan_exception(self):
        """Regressão de bug futuro em run_scan não pode matar o modo contínuo."""
        with mock.patch("main.load_config", return_value=_config()), mock.patch(
            "main.config_to_safe_dict", return_value={}
        ), mock.patch(
            "main.run_scan", side_effect=RuntimeError("bug inesperado")
        ) as scan, mock.patch("main.time.sleep", side_effect=KeyboardInterrupt) as slp:
            self.assertEqual(main([]), 0)
        scan.assert_called_once()
        slp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
