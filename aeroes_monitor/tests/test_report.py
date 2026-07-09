"""Testes da formatação do relatório (PRD F8)."""
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
from report import build_report, build_summary

MONDAY = date(2026, 7, 13)


def _sample_day() -> DayAvailability:
    return DayAvailability(
        day=MONDAY,
        sunrise=time(5, 45),
        sunset=time(17, 30),
        window=TimePeriod(start=time(5, 45), end=time(9, 30)),
        resources=(
            ResourceAvailability(
                resource_name="PT-ABC",
                resource_model="C-152",
                periods=(
                    ClassifiedPeriod(
                        period=TimePeriod(start=time(5, 45), end=time(7, 0)),
                        status=PeriodStatus.AVAILABLE,
                        reason="livre",
                    ),
                    ClassifiedPeriod(
                        period=TimePeriod(start=time(7, 0), end=time(8, 0)),
                        status=PeriodStatus.BUSY,
                        reason="reservado (João)",
                    ),
                ),
            ),
            ResourceAvailability(
                resource_name="Stand By",
                resource_model="",
                periods=(
                    ClassifiedPeriod(
                        period=TimePeriod(start=time(5, 45), end=time(9, 30)),
                        status=PeriodStatus.AVAILABLE,
                        reason="livre",
                    ),
                ),
            ),
        ),
    )


class BuildReportTest(unittest.TestCase):
    def test_day_header_and_lines(self):
        text = build_report([_sample_day()])
        self.assertIn("📅 **Seg 13/07/2026**", text)
        self.assertIn("🌅 05:45", text)
        self.assertIn("🌇 17:30", text)
        self.assertIn("janela 05:45–09:30", text)
        self.assertIn("✈️ **PT-ABC** (C-152)", text)
        self.assertIn("🟢 05:45–07:00 — livre (1h15)", text)
        self.assertIn("🔴 07:00–08:00 — reservado (João) (1h)", text)
        self.assertIn("✈️ **Stand By**", text)
        self.assertNotIn("Stand By** (", text)  # sem modelo → sem parênteses

    def test_day_without_window(self):
        day = DayAvailability(
            day=MONDAY,
            sunrise=time(10, 0),
            sunset=time(17, 30),
            window=None,
            resources=(),
        )
        text = build_report([day])
        self.assertIn("sem janela operacional", text)

    def test_errors_section(self):
        error = ScanError(day_index=4, day_label="17/07/2026", message="sol ausente")
        text = build_report([_sample_day()], [error])
        self.assertIn("⚠️", text)
        self.assertIn("17/07/2026", text)
        self.assertIn("sol ausente", text)

    def test_no_errors_no_error_section(self):
        self.assertNotIn("Dias com erro", build_report([_sample_day()]))


class BuildSummaryTest(unittest.TestCase):
    def test_summary_lists_available_slots(self):
        text = build_summary([_sample_day()])
        self.assertIn("1 dia(s) lidos", text)
        self.assertIn("2 janela(s) disponíveis", text)
        self.assertIn("Seg 13/07/2026: PT-ABC 05:45–07:00", text)
        self.assertIn("Seg 13/07/2026: Stand By 05:45–09:30", text)

    def test_summary_without_availability(self):
        day = DayAvailability(
            day=MONDAY,
            sunrise=time(10, 0),
            sunset=time(17, 30),
            window=None,
            resources=(),
        )
        text = build_summary([day])
        self.assertIn("Nenhum horário disponível", text)

    def test_summary_mentions_errors(self):
        error = ScanError(day_index=0, day_label="13/07/2026", message="x")
        text = build_summary([_sample_day()], [error])
        self.assertIn("1 com erro", text)


if __name__ == "__main__":
    unittest.main()
