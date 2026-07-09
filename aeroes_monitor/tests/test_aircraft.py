"""Testes do parsing de agendas com elementos falsos (ADR-0007, F5)."""
import unittest
from datetime import time

from aircraft import STANDBY_NAME, AircraftService

SELECTORS = {
    "resource_row": (".row",),
    "resource_name": (".name",),
    "event_item": (".event",),
}
ALLOWLIST = {"PT-ABC": "Cessna 152", "PT-XYZ": "Cessna 172"}


class FakeElement:
    def __init__(self, text="", children=None):
        self.text = text
        self._children = children or {}

    def find_elements(self, by, selector):
        return self._children.get(selector, [])

    def is_displayed(self):
        return True


def _row(name, events=()):
    return FakeElement(
        text=name,
        children={
            ".name": [FakeElement(text=name)],
            ".event": [FakeElement(text=e) for e in events],
        },
    )


class FakeDriver:
    def __init__(self, rows):
        self._rows = rows

    def find_elements(self, by, selector):
        return self._rows if selector == ".row" else []


class BuildAircraftSchedulesTest(unittest.TestCase):
    def test_allowlisted_aircraft_with_events(self):
        driver = FakeDriver(
            [
                _row("PT-ABC — Cessna 152", ["06:00 - 07:00 João", "08:00 - 09:00"]),
                _row("PT-QQQ — fora da lista", ["06:00 - 07:00"]),
                _row("STAND BY", ["07:00 - 08:00"]),
            ]
        )
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        names = [s.name for s in schedules]
        self.assertEqual(names, ["PT-ABC", "PT-XYZ", STANDBY_NAME])

        pt_abc = schedules[0]
        self.assertEqual(pt_abc.model, "Cessna 152")
        self.assertEqual(len(pt_abc.busy_periods), 2)
        self.assertEqual(pt_abc.busy_periods[0].start, time(6, 0))
        self.assertEqual(pt_abc.busy_periods[0].label, "João")

        # PT-XYZ não tem linha → agenda vazia, mas presente (ADR-0007).
        self.assertEqual(schedules[1].busy_periods, ())

        standby = schedules[2]
        self.assertEqual(standby.model, "")
        self.assertEqual(len(standby.busy_periods), 1)

    def test_standby_always_emitted_even_if_absent(self):
        driver = FakeDriver([_row("PT-ABC", [])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(schedules[-1].name, STANDBY_NAME)
        self.assertEqual(schedules[-1].busy_periods, ())

    def test_case_insensitive_registration_match(self):
        driver = FakeDriver([_row("pt-abc (Cessna)", ["06:00 - 07:00"])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(len(schedules[0].busy_periods), 1)

    def test_unparseable_event_ignored(self):
        driver = FakeDriver([_row("PT-ABC", ["manutenção sem horário", "06:00 - 07:00"])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(len(schedules[0].busy_periods), 1)

    def test_events_sorted_by_start(self):
        driver = FakeDriver([_row("PT-ABC", ["08:00 - 09:00", "06:00 - 07:00"])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        starts = [p.start for p in schedules[0].busy_periods]
        self.assertEqual(starts, sorted(starts))

    def test_row_name_fallback_to_row_text_first_line(self):
        row = FakeElement(
            text="Stand-by\n07:00 - 08:00",
            children={".name": [], ".event": [FakeElement(text="07:00 - 08:00")]},
        )
        schedules = AircraftService(FakeDriver([row]), SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(len(schedules[-1].busy_periods), 1)


if __name__ == "__main__":
    unittest.main()
