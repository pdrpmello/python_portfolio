"""Testes das regras de disponibilidade (PRD §6, ADR-0004)."""
import unittest
from datetime import date, time

from availability import (
    AvailabilityRules,
    apply_turnaround_buffer,
    filter_bookable_periods,
    operating_window,
    subtract_periods,
)
from models import TimePeriod

# Datas fixas de referência (julho/2026): 13=segunda, 18=sábado, 19=domingo.
MONDAY = date(2026, 7, 13)
SATURDAY = date(2026, 7, 18)
SUNDAY = date(2026, 7, 19)
SUNRISE = time(5, 45)
SUNSET = time(17, 30)


class OperatingWindowTest(unittest.TestCase):
    def test_weekday_closes_at_0930(self):
        window = operating_window(MONDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (SUNRISE, time(9, 30)))

    def test_saturday_closes_at_sunset(self):
        window = operating_window(SATURDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (SUNRISE, SUNSET))

    def test_sunday_closes_at_noon(self):
        window = operating_window(SUNDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (SUNRISE, time(12, 0)))

    def test_weekday_sunset_before_0930_wins(self):
        window = operating_window(MONDAY, time(5, 0), time(9, 0))
        self.assertEqual(window.end, time(9, 0))

    def test_no_window_when_sunrise_after_close(self):
        self.assertIsNone(operating_window(MONDAY, time(10, 0), SUNSET))


class TurnaroundBufferTest(unittest.TestCase):
    def test_expands_both_sides(self):
        buffered = apply_turnaround_buffer(
            [TimePeriod(start=time(8, 0), end=time(9, 0))], 30
        )
        self.assertEqual(buffered, (TimePeriod(start=time(7, 30), end=time(9, 30)),))

    def test_merges_neighbors_joined_by_buffer(self):
        buffered = apply_turnaround_buffer(
            [
                TimePeriod(start=time(6, 0), end=time(7, 0)),
                TimePeriod(start=time(7, 30), end=time(8, 30)),
            ],
            30,
        )
        self.assertEqual(buffered, (TimePeriod(start=time(5, 30), end=time(9, 0)),))

    def test_merges_overlapping_input(self):
        buffered = apply_turnaround_buffer(
            [
                TimePeriod(start=time(6, 0), end=time(8, 0)),
                TimePeriod(start=time(7, 0), end=time(7, 30)),
            ],
            0,
        )
        self.assertEqual(buffered, (TimePeriod(start=time(6, 0), end=time(8, 0)),))

    def test_clamps_at_day_bounds(self):
        buffered = apply_turnaround_buffer(
            [TimePeriod(start=time(0, 10), end=time(23, 40))], 30
        )
        self.assertEqual(buffered, (TimePeriod(start=time(0, 0), end=time(23, 59)),))

    def test_empty_input(self):
        self.assertEqual(apply_turnaround_buffer([], 30), ())


class SubtractPeriodsTest(unittest.TestCase):
    WINDOW = TimePeriod(start=time(6, 0), end=time(12, 0))

    def test_no_busy_returns_whole_window(self):
        self.assertEqual(
            subtract_periods(self.WINDOW, []),
            (TimePeriod(start=time(6, 0), end=time(12, 0)),),
        )

    def test_busy_in_middle_splits_window(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(8, 0), end=time(9, 0))]
        )
        self.assertEqual(
            free,
            (
                TimePeriod(start=time(6, 0), end=time(8, 0)),
                TimePeriod(start=time(9, 0), end=time(12, 0)),
            ),
        )

    def test_busy_covering_window_leaves_nothing(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(5, 0), end=time(13, 0))]
        )
        self.assertEqual(free, ())

    def test_busy_outside_window_ignored(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(13, 0), end=time(14, 0))]
        )
        self.assertEqual(free, (TimePeriod(start=time(6, 0), end=time(12, 0)),))

    def test_busy_crossing_window_edge_clipped(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(5, 0), end=time(7, 0))]
        )
        self.assertEqual(free, (TimePeriod(start=time(7, 0), end=time(12, 0)),))


class FilterBookableTest(unittest.TestCase):
    def test_partition_by_min_duration(self):
        long_period = TimePeriod(start=time(6, 0), end=time(8, 0))
        short_period = TimePeriod(start=time(9, 0), end=time(9, 20))
        bookable, too_short = filter_bookable_periods([long_period, short_period], 60)
        self.assertEqual(bookable, (long_period,))
        self.assertEqual(too_short, (short_period,))

    def test_exactly_min_is_bookable(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 0))
        bookable, too_short = filter_bookable_periods([period], 60)
        self.assertEqual(bookable, (period,))
        self.assertEqual(too_short, ())


class RulesDefaultsTest(unittest.TestCase):
    def test_defaults(self):
        rules = AvailabilityRules()
        self.assertEqual(rules.turnaround_minutes, 30)
        self.assertEqual(rules.min_flight_minutes, 60)
        self.assertEqual(rules.max_flight_minutes, 120)


if __name__ == "__main__":
    unittest.main()
