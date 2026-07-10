"""Testes da política de notificação por diff (specs 2026-07-09 e 2026-07-10)."""
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    TimePeriod,
)
from notifications import (
    NotifyState,
    diff_new_windows,
    extract_open_windows,
    extract_scanned_days,
    load_state,
    save_state,
)

W_MORNING = ("2026-07-11", "PP-AYB", "06:00", "09:30")


def _day(availables=((time(6, 0), time(9, 30)),)):
    periods = tuple(
        ClassifiedPeriod(
            period=TimePeriod(start=s, end=e),
            status=PeriodStatus.AVAILABLE,
            reason="livre",
        )
        for s, e in availables
    ) + (
        ClassifiedPeriod(
            period=TimePeriod(start=time(10, 0), end=time(11, 0)),
            status=PeriodStatus.BUSY,
            reason="reservado",
        ),
    )
    return DayAvailability(
        day=date(2026, 7, 11),
        sunrise=time(6, 0),
        sunset=time(17, 15),
        window=TimePeriod(start=time(6, 0), end=time(17, 15)),
        resources=(
            ResourceAvailability(
                resource_name="PP-AYB", resource_model="C152", periods=periods
            ),
        ),
    )


def _state(windows=(), days=("2026-07-11", "2026-07-12"), last_scan_ok=True):
    return NotifyState(
        windows=frozenset(windows), days=frozenset(days), last_scan_ok=last_scan_ok
    )


class ExtractTest(unittest.TestCase):
    def test_only_available_periods_become_keys(self):
        windows = extract_open_windows([_day()])
        self.assertEqual(windows, frozenset({W_MORNING}))

    def test_scanned_days_are_iso_dates(self):
        self.assertEqual(extract_scanned_days([_day()]), frozenset({"2026-07-11"}))


class DiffTest(unittest.TestCase):
    def test_new_windows_detected_sorted(self):
        previous = _state(windows={W_MORNING})
        current = frozenset(
            {
                W_MORNING,
                ("2026-07-12", "PT-JTK", "07:00", "09:00"),
                ("2026-07-11", "PP-AYB", "14:00", "16:00"),
            }
        )
        self.assertEqual(
            diff_new_windows(previous, current),
            (
                ("2026-07-11", "PP-AYB", "14:00", "16:00"),
                ("2026-07-12", "PT-JTK", "07:00", "09:00"),
            ),
        )

    def test_removed_windows_are_silent(self):
        self.assertEqual(diff_new_windows(_state(windows={W_MORNING}), frozenset()), ())

    def test_day_new_to_horizon_is_silent(self):
        previous = _state(windows={W_MORNING}, days=("2026-07-11",))
        current = frozenset({W_MORNING, ("2026-08-10", "PP-AYB", "06:00", "09:30")})
        self.assertEqual(diff_new_windows(previous, current), ())

    def test_scanned_day_without_windows_notifies_when_it_opens(self):
        """Dia lotado ontem (varrido, zero 🟢) que abre vaga: NOTIFICA."""
        previous = _state(windows=(), days=("2026-07-11",))
        self.assertEqual(
            diff_new_windows(previous, frozenset({W_MORNING})), (W_MORNING,)
        )

    def test_shrunken_window_is_silent(self):
        previous = _state(windows={W_MORNING})
        current = frozenset({("2026-07-11", "PP-AYB", "08:30", "09:30")})
        self.assertEqual(diff_new_windows(previous, current), ())

    def test_grown_window_notifies(self):
        previous = _state(windows={("2026-07-11", "PP-AYB", "08:00", "09:30")})
        self.assertEqual(
            diff_new_windows(previous, frozenset({W_MORNING})), (W_MORNING,)
        )

    def test_partially_shifted_window_notifies(self):
        previous = _state(windows={("2026-07-11", "PP-AYB", "06:00", "08:00")})
        current = frozenset({("2026-07-11", "PP-AYB", "07:00", "09:00")})
        self.assertEqual(
            diff_new_windows(previous, current),
            (("2026-07-11", "PP-AYB", "07:00", "09:00"),),
        )

    def test_containment_requires_same_day_and_resource(self):
        previous = _state(
            windows={
                ("2026-07-11", "PP-AYB", "06:00", "09:30"),
                ("2026-07-12", "PT-JTK", "06:00", "12:00"),
            }
        )
        current = frozenset(
            {
                ("2026-07-11", "PT-JTK", "07:00", "08:30"),  # outra aeronave
                ("2026-07-12", "PP-AYB", "07:00", "08:30"),  # outro dia
            }
        )
        self.assertEqual(
            diff_new_windows(previous, current),
            (
                ("2026-07-11", "PT-JTK", "07:00", "08:30"),
                ("2026-07-12", "PP-AYB", "07:00", "08:30"),
            ),
        )


class StatePersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        state = NotifyState(
            windows=frozenset({W_MORNING}),
            days=frozenset({"2026-07-11", "2026-07-12"}),
            last_scan_ok=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_state(path, state)
            self.assertEqual(load_state(path), state)

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_state(Path("nao_existe_state_9x8.json")))

    def test_v1_state_is_baseline(self):
        """Migração: state antigo (v1, sem days) vira baseline automática."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                '{"version": 1, "windows": [["2026-07-11", "PP-AYB", "06:00", "09:30"]],'
                ' "last_scan_ok": true}',
                encoding="utf-8",
            )
            with self.assertLogs("notifications", level="WARNING"):
                self.assertIsNone(load_state(path))

    def test_corrupted_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{isso não é json", encoding="utf-8")
            with self.assertLogs("notifications", level="WARNING"):
                self.assertIsNone(load_state(path))
            path.write_text('{"version": 99, "windows": []}', encoding="utf-8")
            with self.assertLogs("notifications", level="WARNING"):
                self.assertIsNone(load_state(path))

    def test_wrong_shape_json_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            for payload in ("null", "[]", "42", "true", '"texto"'):
                path.write_text(payload, encoding="utf-8")
                with self.assertLogs("notifications", level="WARNING"):
                    self.assertIsNone(load_state(path))
            bad_payloads = (
                # janela com 3 partes
                '{"version": 2, "windows": [["2026-07-11", "PP-AYB", "06:00"]],'
                ' "days": ["2026-07-11"], "last_scan_ok": true}',
                # janela com partes não-string
                '{"version": 2, "windows": [[1, 2, 3, 4]],'
                ' "days": ["2026-07-11"], "last_scan_ok": true}',
                # days não é lista
                '{"version": 2, "windows": [], "days": "2026-07-11",'
                ' "last_scan_ok": true}',
                # days com item não-string
                '{"version": 2, "windows": [], "days": [20260711],'
                ' "last_scan_ok": true}',
                # sem days
                '{"version": 2, "windows": [], "last_scan_ok": true}',
            )
            for payload in bad_payloads:
                path.write_text(payload, encoding="utf-8")
                with self.assertLogs("notifications", level="WARNING"):
                    self.assertIsNone(load_state(path))


if __name__ == "__main__":
    unittest.main()
