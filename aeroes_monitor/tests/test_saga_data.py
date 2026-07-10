"""Testes das funções puras de dados do SAGA (sol e agendamentos)."""
import unittest
from datetime import date, time

from saga_data import parse_sun_xml, utc_time_to_local

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


if __name__ == "__main__":
    unittest.main()
