"""Testes das funções puras de dados do SAGA (sol e agendamentos)."""
import unittest
from datetime import date, time

from saga_data import parse_sun_xml, utc_time_to_local, PAGE_WINDOW_DAYS, STANDBY_NAME, build_day_schedules
from models import ScanResult

SUN_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><aisweb><day>'
    "<date>2026-07-09</date><sunrise>09:17</sunrise><sunset>20:15</sunset>"
    "<weekDay>4</weekDay><aero>SBVT</aero></day></aisweb>"
)


class ParseSunXmlTest(unittest.TestCase):
    def test_parses_sunrise_and_sunset(self):
        self.assertEqual(parse_sun_xml(SUN_XML), (time(9, 17), time(20, 15)))

    def test_missing_field_returns_none(self):
        xml = "<aisweb><day><sunrise>09:17</sunrise></day></aisweb>"
        self.assertIsNone(parse_sun_xml(xml))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_sun_xml("<html>Erro 500</html>"))
        self.assertIsNone(parse_sun_xml(""))
        self.assertIsNone(parse_sun_xml("não é xml"))


class UtcTimeToLocalTest(unittest.TestCase):
    def test_converts_utc_to_america_sao_paulo(self):
        # SBVT em julho: UTC-3 (Brasil sem horário de verão desde 2019).
        self.assertEqual(utc_time_to_local(time(9, 17), date(2026, 7, 9)), time(6, 17))
        self.assertEqual(utc_time_to_local(time(20, 15), date(2026, 7, 9)), time(17, 15))


def _raw(reg, start, end, status="CONFIRMED", student=None, icao="C152"):
    return {
        "start_at_raw": start,
        "end_at_raw": end,
        "status": status,
        "aircraft": {"registration": reg, "icao": icao},
        "student": {"nickname": student} if student else None,
    }


ALLOWLIST = {"PP-AYB": "Cessna 152", "PT-JTK": "Cessna 172"}
DAY = date(2026, 7, 9)
SUNRISE, SUNSET = time(6, 17), time(17, 15)


def _build(raw, max_days=2, allowlist=ALLOWLIST):
    return build_day_schedules(raw, allowlist, SUNRISE, SUNSET, DAY, max_days)


class BuildDaySchedulesTest(unittest.TestCase):
    def test_groups_by_day_and_registration(self):
        result = _build(
            [
                _raw("PP-AYB", "2026-07-09 07:00:00", "2026-07-09 08:00:00", student="Ana"),
                _raw("PT-JTK", "2026-07-10 09:00:00", "2026-07-10 10:30:00"),
            ]
        )
        self.assertIsInstance(result, ScanResult)
        self.assertEqual(len(result.days), 2)
        d0 = result.days[0]
        self.assertEqual(d0.day, DAY)
        self.assertEqual((d0.sunrise, d0.sunset), (SUNRISE, SUNSET))
        ayb = next(r for r in d0.resources if r.name == "PP-AYB")
        self.assertEqual(ayb.model, "Cessna 152")
        self.assertEqual(ayb.busy_periods[0].start, time(7, 0))
        self.assertEqual(ayb.busy_periods[0].label, "Ana")
        jtk_d1 = next(r for r in result.days[1].resources if r.name == "PT-JTK")
        self.assertEqual(jtk_d1.busy_periods[0].end, time(10, 30))

    def test_all_resources_present_even_on_empty_day(self):
        result = _build([])
        names = [r.name for r in result.days[0].resources]
        self.assertEqual(names, ["PP-AYB", "PT-JTK", STANDBY_NAME])
        self.assertTrue(all(r.busy_periods == () for r in result.days[0].resources))

    def test_canceled_and_unknown_registrations_ignored(self):
        result = _build(
            [
                _raw("PP-AYB", "2026-07-09 07:00:00", "2026-07-09 08:00:00", status="CANCELED"),
                _raw("XX-XXX", "2026-07-09 09:00:00", "2026-07-09 10:00:00"),
            ]
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(ayb.busy_periods, ())

    def test_standby_slot_maps_to_standby_resource(self):
        result = _build(
            [_raw("SLOT STAND-BY", "2026-07-09 06:00:00", "2026-07-09 07:00:00")]
        )
        standby = next(r for r in result.days[0].resources if r.name == STANDBY_NAME)
        self.assertEqual(standby.busy_periods[0].start, time(6, 0))

    def test_registration_matching_is_normalized(self):
        result = _build(
            [_raw("pp ayb", "2026-07-09 07:00:00", "2026-07-09 08:00:00")]
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(len(ayb.busy_periods), 1)

    def test_midnight_crossing_clipped_and_invalid_skipped(self):
        result = _build(
            [
                _raw("PP-AYB", "2026-07-09 22:00:00", "2026-07-10 01:00:00"),
                _raw("PT-JTK", "2026-07-09 10:00:00", "2026-07-09 10:00:00"),
                {"start_at_raw": None, "end_at_raw": None, "status": "CONFIRMED",
                 "aircraft": {"registration": "PP-AYB"}, "student": None},
            ]
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(ayb.busy_periods[0].end, time(23, 59))
        jtk = next(r for r in result.days[0].resources if r.name == "PT-JTK")
        self.assertEqual(jtk.busy_periods, ())

    def test_events_outside_window_ignored(self):
        result = _build(
            [_raw("PP-AYB", "2026-08-20 07:00:00", "2026-08-20 08:00:00")],
            max_days=2,
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(ayb.busy_periods, ())
        self.assertEqual(result.errors, ())

    def test_max_days_beyond_page_window_truncates_with_error(self):
        result = _build([], max_days=45)
        self.assertEqual(len(result.days), PAGE_WINDOW_DAYS)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("30", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
