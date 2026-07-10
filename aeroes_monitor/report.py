"""Formatação das mensagens do Discord (PRD F8). Importa só models.

O relatório lista APENAS janelas livres (spec 2026-07-10): dia ou
aeronave sem 🟢 não aparece; ocupados e vãos curtos ficam de fora.
"""
from __future__ import annotations

from datetime import date, time
from typing import Iterator, Sequence

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    ScanError,
)

WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _fmt_time(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m/%Y')}"


def _fmt_period(start: str, end: str) -> str:
    return f"{start} - {end}"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def _free_blocks(
    day: DayAvailability,
) -> Iterator[tuple[ResourceAvailability, list[ClassifiedPeriod]]]:
    for resource in day.resources:
        available = [
            e for e in resource.periods if e.status is PeriodStatus.AVAILABLE
        ]
        if available:
            yield resource, available


def build_report(
    days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()
) -> str:
    day_blocks = [(day, list(_free_blocks(day))) for day in days]
    day_blocks = [(day, blocks) for day, blocks in day_blocks if blocks]
    total = sum(len(available) for _, blocks in day_blocks for _, available in blocks)

    if total == 0:
        lines = [f"✅ **{len(days)} dias varridos — nenhuma janela livre. 😕**"]
    else:
        lines = [f"✅ **{len(days)} dias varridos — {total} janelas livres**"]
        for day, blocks in day_blocks:
            lines.append("")
            lines.append(f"📅 **{_fmt_date(day.day)}**")
            for resource, available in blocks:
                lines.append("")
                title = f"✈️ **{resource.resource_name}**"
                if resource.resource_model:
                    title += f" ({resource.resource_model})"
                lines.append(title)
                for entry in available:
                    period = _fmt_period(
                        _fmt_time(entry.period.start), _fmt_time(entry.period.end)
                    )
                    duration = _fmt_duration(entry.period.duration_minutes())
                    lines.append(f"🟢 {period} ({duration})")
    if errors:
        lines.append("")
        lines.append("⚠️ **Dias com erro de leitura:**")
        for error in errors:
            lines.append(
                f"⚠️ dia {error.day_index + 1} ({error.day_label}): {error.message}"
            )
    return "\n".join(lines)


def build_openings_message(
    new_windows: Sequence[tuple[str, str, str, str]]
) -> str:
    """Aviso enxuto de janelas 🟢 que não existiam na varredura anterior."""
    lines = ["🔔 **Abriu horário!**"]
    for day_iso, resource, start, end in new_windows:
        lines.append(
            f"🟢 {_fmt_date(date.fromisoformat(day_iso))}: {resource} "
            f"{_fmt_period(start, end)}"
        )
    return "\n".join(lines)
