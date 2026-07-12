"""Formatação das mensagens do Discord (PRD F8). Importa só models.

O relatório lista APENAS janelas livres, em tabelas monoespaçadas por
dia (specs 2026-07-10): dia ou aeronave sem 🟢 não aparece; ocupados e
vãos curtos ficam de fora. Emojis ficam FORA dos blocos ``` (dentro
perdem a renderização colorida do Discord).
"""
from __future__ import annotations

from datetime import date, time
from typing import Iterator, Mapping, Sequence

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    ScanError,
)

WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
FENCE = "```"


def _fmt_time(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m/%Y')}"


def _fmt_short_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m')}"


def _fmt_period(start: str, end: str) -> str:
    return f"{start} - {end}"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def _name_cell(name: str, model: str) -> str:
    return f"{name} {model}" if model else name


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
        width = max(
            len(_name_cell(resource.resource_name, resource.resource_model))
            for _, blocks in day_blocks
            for resource, _ in blocks
        )
        lines = [f"✅ **{len(days)} dias varridos — {total} janelas livres**", ""]
        for day, blocks in day_blocks:
            lines.append(f"📅 **{_fmt_date(day.day)}**")
            lines.append(FENCE)
            for resource, available in blocks:
                cell = _name_cell(resource.resource_name, resource.resource_model)
                for entry in available:
                    period = _fmt_period(
                        _fmt_time(entry.period.start), _fmt_time(entry.period.end)
                    )
                    duration = _fmt_duration(entry.period.duration_minutes())
                    lines.append(f"{cell:<{width}}  {period}  {duration}")
            lines.append(FENCE)
    if errors:
        lines.append("")
        lines.append("⚠️ **Dias com erro de leitura:**")
        for error in errors:
            lines.append(
                f"⚠️ dia {error.day_index + 1} ({error.day_label}): {error.message}"
            )
    return "\n".join(lines)


def build_openings_message(
    new_windows: Sequence[tuple[str, str, str, str]],
    models: Mapping[str, str],
) -> str:
    """Aviso de janelas 🟢 novas: tabela única, dia curto sem ano; o
    modelo vem de `models` (a WindowKey não o carrega)."""
    cells = [
        _name_cell(resource, models.get(resource, ""))
        for _, resource, _, _ in new_windows
    ]
    width = max(len(cell) for cell in cells)
    lines = ["🔔 **Abriu horário!**", FENCE]
    for (day_iso, _, start, end), cell in zip(new_windows, cells):
        lines.append(
            f"{_fmt_short_date(date.fromisoformat(day_iso))}  "
            f"{cell:<{width}}  {_fmt_period(start, end)}"
        )
    lines.append(FENCE)
    return "\n".join(lines)
