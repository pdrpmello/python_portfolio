"""Testes da formatação das mensagens do Discord (PRD F8, spec tabela 2026-07-10)."""
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


def _resource(name, model, *periods):
    return ResourceAvailability(
        resource_name=name, resource_model=model, periods=tuple(periods)
    )


def _sample_day():
    """Dia com 2 janelas 🟢 (PT-ABC e Stand By) e 1 voo 🔴 no meio."""
    return _day(
        resources=(
            _resource(
                "PT-ABC",
                "C152",
                _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                _entry(time(7, 0), time(8, 0), PeriodStatus.BUSY, "reservado (João)"),
            ),
            _resource(
                "Stand By",
                "",
                _entry(time(6, 0), time(9, 30), PeriodStatus.AVAILABLE, "livre"),
            ),
        )
    )


class BuildReportTest(unittest.TestCase):
    def test_full_layout_single_day(self):
        expected = (
            "✅ **1 dias varridos — 2 janelas livres**\n"
            "\n"
            "📅 **Seg 13/07/2026**\n"
            "```\n"
            "PT-ABC C152  06:00 - 07:00  1h\n"
            "Stand By     06:00 - 09:30  3h30\n"
            "```"
        )
        self.assertEqual(build_report([_sample_day()]), expected)

    def test_no_list_emojis_in_body(self):
        text = build_report([_sample_day()])
        self.assertNotIn("✈️", text)
        self.assertNotIn("🟢", text)

    def test_busy_periods_do_not_appear(self):
        text = build_report([_sample_day()])
        self.assertNotIn("🔴", text)
        self.assertNotIn("reservado", text)
        self.assertNotIn("João", text)

    def test_day_header_is_bare_date_outside_fence(self):
        lines = build_report([_sample_day()]).split("\n")
        index = lines.index("📅 **Seg 13/07/2026**")
        self.assertEqual(lines[index + 1], "```")
        text = "\n".join(lines)
        self.assertNotIn("🌅", text)
        self.assertNotIn("🌇", text)

    def test_no_blank_line_between_days_and_global_width(self):
        day1 = _day(
            resources=(
                _resource(
                    "Stand By",
                    "",
                    _entry(time(6, 0), time(9, 30), PeriodStatus.AVAILABLE, "livre"),
                ),
            )
        )
        day2 = _day(
            day=TUESDAY,
            resources=(
                _resource(
                    "PT-ABC",
                    "C152",
                    _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                ),
            ),
        )
        text = build_report([day1, day2])
        self.assertIn("```\n📅 **Ter 14/07/2026**", text)  # sem linha em branco
        # largura global: "Stand By" preenchido até len("PT-ABC C152") = 11
        self.assertIn("Stand By     06:00 - 09:30  3h30", text)

    def test_day_without_free_windows_is_omitted(self):
        busy_only = _day(
            day=TUESDAY,
            resources=(
                _resource(
                    "PT-ABC",
                    "C152",
                    _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
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
                _resource(
                    "PT-ABC",
                    "C152",
                    _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                ),
                _resource(
                    "PT-XYZ",
                    "C172",
                    _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
                ),
            )
        )
        text = build_report([day])
        self.assertIn("PT-ABC", text)
        self.assertNotIn("PT-XYZ", text)

    def test_no_free_windows_at_all(self):
        text = build_report([_day(resources=()), _day(day=TUESDAY, resources=())])
        self.assertEqual(text, "✅ **2 dias varridos — nenhuma janela livre. 😕**")

    def test_errors_section_outside_fence(self):
        error = ScanError(day_index=4, day_label="17/07/2026", message="sol ausente")
        text = build_report([_sample_day()], [error])
        self.assertIn("```\n\n⚠️ **Dias com erro de leitura:**", text)
        self.assertIn("dia 5 (17/07/2026): sol ausente", text)

    def test_errors_section_even_without_free_windows(self):
        error = ScanError(day_index=0, day_label="sol", message="sem sol")
        text = build_report([_day(resources=())], [error])
        self.assertIn("nenhuma janela livre", text)
        self.assertIn("sem sol", text)

    def test_no_errors_no_error_section(self):
        self.assertNotIn("Dias com erro", build_report([_sample_day()]))


class BuildOpeningsMessageTest(unittest.TestCase):
    def test_table_with_short_day_and_models(self):
        text = build_openings_message(
            [
                ("2026-07-11", "PP-AYB", "06:30", "09:30"),
                ("2026-07-12", "Stand By", "07:00", "12:00"),
            ],
            {"PP-AYB": "C152", "PT-JTK": "C172"},
        )
        expected = (
            "🔔 **Abriu horário!**\n"
            "```\n"
            "Sáb 11/07  PP-AYB C152  06:30 - 09:30\n"
            "Dom 12/07  Stand By     07:00 - 12:00\n"
            "```"
        )
        self.assertEqual(text, expected)


if __name__ == "__main__":
    unittest.main()
