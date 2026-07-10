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
    def test_weekday_closes_at_0930_and_start_rounds_up(self):
        window = operating_window(MONDAY, SUNRISE, SUNSET)  # 05:45 → 06:00
        self.assertEqual((window.start, window.end), (time(6, 0), time(9, 30)))

    def test_start_already_on_grid_unchanged(self):
        self.assertEqual(operating_window(MONDAY, time(6, 0), SUNSET).start, time(6, 0))

    def test_start_rounding_examples_from_spec(self):
        self.assertEqual(operating_window(MONDAY, time(6, 17), SUNSET).start, time(6, 30))
        self.assertEqual(operating_window(MONDAY, time(5, 47), SUNSET).start, time(6, 0))
        self.assertEqual(operating_window(MONDAY, time(5, 5), SUNSET).start, time(5, 30))

    def test_saturday_closes_at_sunset_rounded_down(self):
        window = operating_window(SATURDAY, SUNRISE, time(17, 23))
        self.assertEqual((window.start, window.end), (time(6, 0), time(17, 0)))
        self.assertEqual(operating_window(SATURDAY, SUNRISE, time(17, 45)).end, time(17, 30))
        self.assertEqual(operating_window(SATURDAY, SUNRISE, time(17, 30)).end, time(17, 30))

    def test_sunday_closes_at_noon(self):
        window = operating_window(SUNDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (time(6, 0), time(12, 0)))

    def test_weekday_sunset_before_0930_wins(self):
        window = operating_window(MONDAY, time(5, 0), time(9, 0))
        self.assertEqual(window.end, time(9, 0))

    def test_no_window_when_sunrise_after_close(self):
        self.assertIsNone(operating_window(MONDAY, time(10, 0), SUNSET))

    def test_no_window_when_rounding_collapses(self):
        # nascer 09:05 arredonda para 09:30 == fechamento de segunda ⇒ sem janela
        self.assertIsNone(operating_window(MONDAY, time(9, 5), SUNSET))


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


from availability import classify_day_periods, enrich_day_schedule
from models import DaySchedule, PeriodStatus, ResourceSchedule


class ClassifyDayPeriodsTest(unittest.TestCase):
    WINDOW = TimePeriod(start=time(6, 0), end=time(9, 30))
    RULES = AvailabilityRules(
        turnaround_minutes=30, min_flight_minutes=60, max_flight_minutes=120
    )

    def test_empty_schedule_is_one_available_block(self):
        entries = classify_day_periods(self.WINDOW, [], self.RULES)
        self.assertEqual(len(entries), 1)
        self.assertIs(entries[0].status, PeriodStatus.AVAILABLE)
        self.assertEqual(entries[0].reason, "livre")
        self.assertEqual(
            (entries[0].period.start, entries[0].period.end), (time(6, 0), time(9, 30))
        )

    def test_busy_with_label_and_free_gap(self):
        # Voo 06:00–07:00: com buffer de 30min o vão livre começa 07:30.
        # 07:30–09:30 = 2h ≥ 1h → 🟢.
        entries = classify_day_periods(
            self.WINDOW,
            [TimePeriod(start=time(6, 0), end=time(7, 0), label="João")],
            self.RULES,
        )
        self.assertEqual(len(entries), 2)
        self.assertIs(entries[0].status, PeriodStatus.BUSY)
        self.assertEqual(entries[0].reason, "reservado (João)")
        self.assertEqual(
            (entries[0].period.start, entries[0].period.end), (time(6, 0), time(7, 0))
        )
        self.assertIs(entries[1].status, PeriodStatus.AVAILABLE)
        self.assertEqual(
            (entries[1].period.start, entries[1].period.end),
            (time(7, 30), time(9, 30)),
        )

    def test_short_gap_reported_busy(self):
        # Voos 06:00–07:00 e 08:30–09:30 bufferizados deixam 07:30–08:00
        # (30min < 60min) → 🔴 "vão curto".
        entries = classify_day_periods(
            self.WINDOW,
            [
                TimePeriod(start=time(6, 0), end=time(7, 0)),
                TimePeriod(start=time(8, 30), end=time(9, 30)),
            ],
            self.RULES,
        )
        reasons = [e.reason for e in entries]
        self.assertIn("vão curto (30min < 60min)", reasons)
        short = next(e for e in entries if "vão curto" in e.reason)
        self.assertIs(short.status, PeriodStatus.BUSY)
        self.assertEqual(
            (short.period.start, short.period.end), (time(7, 30), time(8, 0))
        )

    def test_busy_outside_window_dropped_from_timeline(self):
        entries = classify_day_periods(
            self.WINDOW,
            [TimePeriod(start=time(14, 0), end=time(15, 0))],
            self.RULES,
        )
        self.assertTrue(all(e.status is PeriodStatus.AVAILABLE for e in entries))

    def test_busy_crossing_window_edge_clipped(self):
        entries = classify_day_periods(
            self.WINDOW,
            [TimePeriod(start=time(5, 0), end=time(6, 30))],
            self.RULES,
        )
        busy = [e for e in entries if e.status is PeriodStatus.BUSY and e.reason.startswith("reservado")]
        self.assertEqual(
            (busy[0].period.start, busy[0].period.end), (time(6, 0), time(6, 30))
        )

    def test_timeline_sorted_by_start(self):
        entries = classify_day_periods(
            self.WINDOW,
            [
                TimePeriod(start=time(8, 0), end=time(9, 0)),
                TimePeriod(start=time(6, 0), end=time(6, 30)),
            ],
            self.RULES,
        )
        starts = [e.period.start for e in entries]
        self.assertEqual(starts, sorted(starts))


class EnrichDayScheduleTest(unittest.TestCase):
    RULES = AvailabilityRules()

    def test_enriches_all_resources_on_monday(self):
        day = DaySchedule(
            day=MONDAY,
            sunrise=SUNRISE,
            sunset=SUNSET,
            resources=(
                ResourceSchedule(name="PT-ABC", model="C-152"),
                ResourceSchedule(name="Stand By"),
            ),
        )
        enriched = enrich_day_schedule(day, self.RULES)
        self.assertEqual(enriched.day, MONDAY)
        self.assertEqual(
            (enriched.window.start, enriched.window.end), (time(6, 0), time(9, 30))
        )
        self.assertEqual(len(enriched.resources), 2)
        self.assertEqual(enriched.resources[0].resource_name, "PT-ABC")
        self.assertEqual(enriched.resources[0].resource_model, "C-152")
        self.assertIs(
            enriched.resources[0].periods[0].status, PeriodStatus.AVAILABLE
        )

    def test_day_without_window(self):
        day = DaySchedule(
            day=MONDAY,
            sunrise=time(10, 0),
            sunset=SUNSET,
            resources=(ResourceSchedule(name="PT-ABC", model="C-152"),),
        )
        enriched = enrich_day_schedule(day, self.RULES)
        self.assertIsNone(enriched.window)
        self.assertEqual(enriched.resources[0].periods, ())


if __name__ == "__main__":
    unittest.main()
