"""Testes do parsing puro de texto (utils.py)."""
import unittest
from datetime import date, time

from utils import (
    extract_period,
    extract_sunrise,
    extract_sunset,
    find_times,
    normalize_registration,
    parse_day_date,
    parse_time,
)


class ParseTimeTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_time("06:15"), time(6, 15))
        self.assertEqual(parse_time("6:15"), time(6, 15))
        self.assertEqual(parse_time("06h15"), time(6, 15))
        self.assertEqual(parse_time("Saída às 14:05 confirmada"), time(14, 5))

    def test_invalid(self):
        self.assertIsNone(parse_time("sem horário"))
        self.assertIsNone(parse_time("99:99"))
        self.assertIsNone(parse_time(""))


class FindTimesTest(unittest.TestCase):
    def test_finds_all_valid_times_in_order(self):
        text = "Nascer do sol: 05:45 · Pôr do sol: 17:30"
        self.assertEqual(find_times(text), [time(5, 45), time(17, 30)])

    def test_empty_when_no_times(self):
        self.assertEqual(find_times("nada aqui"), [])


class ExtractPeriodTest(unittest.TestCase):
    def test_hyphen_separator(self):
        period = extract_period("06:00 - 07:00 João Silva")
        self.assertEqual(period.start, time(6, 0))
        self.assertEqual(period.end, time(7, 0))
        self.assertEqual(period.label, "João Silva")

    def test_en_dash_separator(self):
        period = extract_period("06:00–07:00")
        self.assertEqual((period.start, period.end), (time(6, 0), time(7, 0)))
        self.assertEqual(period.label, "")

    def test_as_separator(self):
        period = extract_period("Reserva 06:00 às 07:30")
        self.assertEqual((period.start, period.end), (time(6, 0), time(7, 30)))
        self.assertEqual(period.label, "Reserva")

    def test_invalid_or_inverted(self):
        self.assertIsNone(extract_period("apenas texto"))
        self.assertIsNone(extract_period("08:00 - 07:00 invertido"))


class SunTimesTest(unittest.TestCase):
    def test_extract_sunrise_pt_br(self):
        self.assertEqual(extract_sunrise("Nascer do sol: 05:45"), time(5, 45))
        self.assertEqual(extract_sunrise("NASCER DO SOL 05h45"), time(5, 45))

    def test_extract_sunset_pt_br_with_accents(self):
        self.assertEqual(extract_sunset("Pôr do sol: 17:30"), time(17, 30))
        self.assertEqual(extract_sunset("por do sol 17:30"), time(17, 30))
        self.assertEqual(extract_sunset("Pôr-do-sol: 17:30"), time(17, 30))

    def test_combined_line_distinguishes_both(self):
        text = "Nascer do sol: 05:45 | Pôr do sol: 17:30"
        self.assertEqual(extract_sunrise(text), time(5, 45))
        self.assertEqual(extract_sunset(text), time(17, 30))

    def test_missing_returns_none(self):
        self.assertIsNone(extract_sunrise("Pôr do sol: 17:30"))
        self.assertIsNone(extract_sunset("Nascer do sol: 05:45"))


class ParseDayDateTest(unittest.TestCase):
    def test_plain_date(self):
        self.assertEqual(parse_day_date("14/07/2026"), date(2026, 7, 14))

    def test_date_with_weekday_prefix(self):
        self.assertEqual(
            parse_day_date("Segunda-feira, 14/07/2026"), date(2026, 7, 14)
        )

    def test_no_date_returns_none(self):
        self.assertIsNone(parse_day_date("Segunda-feira"))
        self.assertIsNone(parse_day_date("31/02/2026"))


class NormalizeRegistrationTest(unittest.TestCase):
    def test_equivalence(self):
        self.assertEqual(normalize_registration("pt-abc"), "PTABC")
        self.assertEqual(normalize_registration("PT ABC"), "PTABC")
        self.assertEqual(normalize_registration("PTABC"), "PTABC")


if __name__ == "__main__":
    unittest.main()
