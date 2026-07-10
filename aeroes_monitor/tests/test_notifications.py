"""Testes da política de notificação por diff (spec 2026-07-09)."""
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
    load_state,
    save_state,
)


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


class ExtractOpenWindowsTest(unittest.TestCase):
    def test_only_available_periods_become_keys(self):
        windows = extract_open_windows([_day()])
        self.assertEqual(
            windows, frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")})
        )


class DiffTest(unittest.TestCase):
    def test_new_windows_detected_sorted(self):
        old = frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")})
        new = old | {
            ("2026-07-12", "PT-JTK", "07:00", "09:00"),
            ("2026-07-11", "PP-AYB", "14:00", "16:00"),
        }
        self.assertEqual(
            diff_new_windows(old, new),
            (
                ("2026-07-11", "PP-AYB", "14:00", "16:00"),
                ("2026-07-12", "PT-JTK", "07:00", "09:00"),
            ),
        )

    def test_removed_windows_are_silent(self):
        old = frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")})
        self.assertEqual(diff_new_windows(old, frozenset()), ())


class StatePersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        state = NotifyState(
            windows=frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")}),
            last_scan_ok=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_state(path, state)
            self.assertEqual(load_state(path), state)

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_state(Path("nao_existe_state_9x8.json")))

    def test_corrupted_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{isso não é json", encoding="utf-8")
            self.assertIsNone(load_state(path))
            path.write_text('{"version": 99, "windows": []}', encoding="utf-8")
            self.assertIsNone(load_state(path))


if __name__ == "__main__":
    unittest.main()
