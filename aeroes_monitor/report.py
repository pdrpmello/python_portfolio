"""Formatação do relatório 🟢/🔴 para o Discord (PRD F8). Importa só models."""
from __future__ import annotations

from datetime import date, time
from typing import Sequence

from models import DayAvailability, PeriodStatus, ScanError

WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _fmt_time(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m/%Y')}"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def _day_header(day: DayAvailability) -> str:
    return (
        f"📅 **{_fmt_date(day.day)}** — 🌅 {_fmt_time(day.sunrise)} · "
        f"🌇 {_fmt_time(day.sunset)} · janela "
        f"{_fmt_time(day.window.start)}–{_fmt_time(day.window.end)}"
    )


def build_report(
    days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()
) -> str:
    lines: list[str] = ["📋 **Relatório de disponibilidade**", ""]
    for day in days:
        if day.window is None:
            lines.append(
                f"📅 **{_fmt_date(day.day)}** — sem janela operacional "
                f"(🌅 {_fmt_time(day.sunrise)} · 🌇 {_fmt_time(day.sunset)})"
            )
            lines.append("")
            continue
        lines.append(_day_header(day))
        for resource in day.resources:
            title = f"✈️ **{resource.resource_name}**"
            if resource.resource_model:
                title += f" ({resource.resource_model})"
            lines.append(title)
            for entry in resource.periods:
                icon = "🟢" if entry.status is PeriodStatus.AVAILABLE else "🔴"
                duration = _fmt_duration(entry.period.duration_minutes())
                lines.append(
                    f"    {icon} {_fmt_time(entry.period.start)}–"
                    f"{_fmt_time(entry.period.end)} — {entry.reason} ({duration})"
                )
        lines.append("")
    if errors:
        lines.append("⚠️ **Dias com erro de leitura:**")
        for error in errors:
            lines.append(
                f"    ⚠️ dia {error.day_index + 1} ({error.day_label}): {error.message}"
            )
    return "\n".join(lines).strip()


def build_summary(
    days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()
) -> str:
    slots: list[str] = []
    for day in days:
        for resource in day.resources:
            for entry in resource.periods:
                if entry.status is PeriodStatus.AVAILABLE:
                    slots.append(
                        f"- {_fmt_date(day.day)}: {resource.resource_name} "
                        f"{_fmt_time(entry.period.start)}–{_fmt_time(entry.period.end)}"
                    )
    lines = [
        f"✅ **Varredura concluída** — {len(days)} dia(s) lidos, "
        f"{len(errors)} com erro."
    ]
    if slots:
        lines.append(f"🟢 {len(slots)} janela(s) disponíveis:")
        lines.extend(slots)
    else:
        lines.append("Nenhum horário disponível encontrado. 😕")
    return "\n".join(lines)
