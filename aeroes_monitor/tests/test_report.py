"""Testes da formatação das mensagens do Discord (PRD F8, spec 2026-07-10)."""
import unittest
from datetime import date, time

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    ScanError,
    TimePeriod,
)
from report import build_openings_message, build_report

MONDAY = date(2026, 7, 13)
TUESDAY = date(2026, 7, 14)


def _entry(start, end, status, reason):
    return ClassifiedPeriod(
        period=TimePeriod(start=start, end=end), status=status, reason=reason
    )


def _day(day=MONDAY, resources=()):
    return DayAvailability(
        day=day,
        sunrise=time(5, 45),
        sunset=time(17, 30),
        window=TimePeriod(start=time(6, 0), end=time(9, 30)),
        resources=tuple(resources),
    )


def _sample_day():
    """Dia com 2 janelas 🟢 (PT-ABC e Stand By) e 1 voo 🔴 no meio."""
    return _day(
        resources=(
            ResourceAvailability(
                resource_name="PT-ABC",
                resource_model="C152",
                periods=(
                    _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                    _entry(time(7, 0), time(8, 0), PeriodStatus.BUSY, "reservado (João)"),
                ),
            ),
            ResourceAvailability(
                resource_name="Stand By",
                resource_model="",
                periods=(
                    _entry(time(6, 0), time(9, 30), PeriodStatus.AVAILABLE, "livre"),
                ),
            ),
        )
    )


class BuildReportTest(unittest.TestCase):
    def test_header_counts_days_and_free_windows(self):
        text = build_report([_sample_day()])
        self.assertTrue(
            text.startswith("✅ **1 dias varridos — 2 janelas livres**"), text
        )

    def test_free_lines_with_spaced_hyphen_and_duration(self):
        text = build_report([_sample_day()])
        self.assertIn("✈️ **PT-ABC** (C152)", text)
        self.assertIn("🟢 06:00 - 07:00 (1h)", text)
        self.assertIn("✈️ **Stand By**", text)
        self.assertNotIn("Stand By** (", text)  # sem modelo → sem parênteses
        self.assertIn("🟢 06:00 - 09:30 (3h30)", text)

    def test_busy_periods_do_not_appear(self):
        text = build_report([_sample_day()])
        self.assertNotIn("🔴", text)
        self.assertNotIn("reservado", text)
        self.assertNotIn("João", text)

    def test_day_header_is_bare_date(self):
        lines = build_report([_sample_day()]).split("\n")
        self.assertIn("📅 **Seg 13/07/2026**", lines)  # linha exata: sem 🌅/🌇/janela
        text = "\n".join(lines)
        self.assertNotIn("🌅", text)
        self.assertNotIn("🌇", text)

    def test_day_without_free_windows_is_omitted(self):
        busy_only = _day(
            day=TUESDAY,
            resources=(
                ResourceAvailability(
                    resource_name="PT-ABC",
                    resource_model="C152",
                    periods=(
                        _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
                    ),
                ),
            ),
        )
        text = build_report([_sample_day(), busy_only])
        self.assertIn("Seg 13/07/2026", text)
        self.assertNotIn("Ter 14/07/2026", text)
        self.assertIn("2 dias varridos", text)  # contagem inclui o dia omitido

    def test_aircraft_without_free_windows_is_omitted(self):
        day = _day(
            resources=(
                ResourceAvailability(
                    resource_name="PT-ABC",
                    resource_model="C152",
                    periods=(
                        _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                    ),
                ),
                ResourceAvailability(
                    resource_name="PT-XYZ",
                    resource_model="C172",
                    periods=(
                        _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
                    ),
                ),
            )
        )
        text = build_report([day])
        self.assertIn("PT-ABC", text)
        self.assertNotIn("PT-XYZ", text)

    def test_blank_line_between_aircraft_blocks(self):
        text = build_report([_sample_day()])
        self.assertIn("🟢 06:00 - 07:00 (1h)\n\n✈️ **Stand By**", text)

    def test_no_free_windows_at_all(self):
        text = build_report([_day(resources=()), _day(day=TUESDAY, resources=())])
        self.assertEqual(text, "✅ **2 dias varridos — nenhuma janela livre. 😕**")

    def test_errors_section(self):
        error = ScanError(day_index=4, day_label="17/07/2026", message="sol ausente")
        text = build_report([_sample_day()], [error])
        self.assertIn("⚠️ **Dias com erro de leitura:**", text)
        self.assertIn("dia 5 (17/07/2026): sol ausente", text)

    def test_errors_section_even_without_free_windows(self):
        error = ScanError(day_index=0, day_label="sol", message="sem sol")
        text = build_report([_day(resources=())], [error])
        self.assertIn("nenhuma janela livre", text)
        self.assertIn("sem sol", text)

    def test_no_errors_no_error_section(self):
        self.assertNotIn("Dias com erro", build_report([_sample_day()]))


class BuildOpeningsMessageTest(unittest.TestCase):
    def test_formats_each_window_with_weekday_and_spaced_hyphen(self):
        text = build_openings_message(
            [
                ("2026-07-11", "PP-AYB", "06:30", "09:30"),
                ("2026-07-12", "Stand By", "07:00", "12:00"),
            ]
        )
        self.assertIn("🔔 **Abriu horário!**", text)
        self.assertIn("🟢 Sáb 11/07/2026: PP-AYB 06:30 - 09:30", text)
        self.assertIn("🟢 Dom 12/07/2026: Stand By 07:00 - 12:00", text)


if __name__ == "__main__":
    unittest.main()
