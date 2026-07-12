"""Testes das dataclasses de domínio."""
import dataclasses
import unittest
from datetime import date, time

from models import (
    ClassifiedPeriod,
    DayAvailability,
    DaySchedule,
    PeriodStatus,
    ResourceAvailability,
    ResourceSchedule,
    ScanError,
    ScanResult,
    TimePeriod,
)


class TimePeriodTest(unittest.TestCase):
    def test_duration_minutes(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 30))
        self.assertEqual(period.duration_minutes(), 90)

    def test_start_must_precede_end(self):
        with self.assertRaises(ValueError):
            TimePeriod(start=time(8, 0), end=time(8, 0))
        with self.assertRaises(ValueError):
            TimePeriod(start=time(9, 0), end=time(8, 0))

    def test_is_frozen(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 0))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            period.start = time(5, 0)

    def test_default_label_empty(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 0))
        self.assertEqual(period.label, "")


class ContainerModelsTest(unittest.TestCase):
    def test_resource_schedule_defaults(self):
        resource = ResourceSchedule(name="PT-ABC")
        self.assertEqual(resource.model, "")
        self.assertEqual(resource.busy_periods, ())

    def test_day_schedule_holds_resources(self):
        resource = ResourceSchedule(name="Stand By")
        day = DaySchedule(
            day=date(2026, 7, 13),
            sunrise=time(5, 45),
            sunset=time(17, 30),
            resources=(resource,),
        )
        self.assertEqual(day.resources[0].name, "Stand By")

    def test_period_status_members(self):
        self.assertIn(PeriodStatus.AVAILABLE, PeriodStatus)
        self.assertIn(PeriodStatus.BUSY, PeriodStatus)

    def test_availability_models(self):
        entry = ClassifiedPeriod(
            period=TimePeriod(start=time(6, 0), end=time(7, 0)),
            status=PeriodStatus.AVAILABLE,
            reason="livre",
        )
        resource = ResourceAvailability(
            resource_name="PT-ABC", resource_model="C-152", periods=(entry,)
        )
        day = DayAvailability(
            day=date(2026, 7, 13),
            sunrise=time(5, 45),
            sunset=time(17, 30),
            window=TimePeriod(start=time(5, 45), end=time(12, 0)),
            resources=(resource,),
        )
        self.assertIs(day.resources[0].periods[0].status, PeriodStatus.AVAILABLE)

    def test_scan_result_defaults(self):
        result = ScanResult()
        self.assertEqual(result.days, ())
        self.assertEqual(result.errors, ())
        error = ScanError(day_index=2, day_label="16/07/2026", message="sem sol")
        self.assertEqual(error.day_index, 2)


if __name__ == "__main__":
    unittest.main()
