"""Testes do parsing puro de texto (utils.py)."""
import unittest
from datetime import time

from utils import normalize_registration, parse_time


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


class NormalizeRegistrationTest(unittest.TestCase):
    def test_equivalence(self):
        self.assertEqual(normalize_registration("pt-abc"), "PTABC")
        self.assertEqual(normalize_registration("PT ABC"), "PTABC")
        self.assertEqual(normalize_registration("PTABC"), "PTABC")


if __name__ == "__main__":
    unittest.main()
