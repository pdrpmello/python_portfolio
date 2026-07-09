"""Regras de disponibilidade. Puro: importa apenas models (ADR-0004).

Janelas por dia da semana (PRD §6): seg–sex nascer→09:30; sáb nascer→pôr;
dom nascer→12:00. Buffer de turnaround expande voos ocupados antes do
cálculo dos vãos livres; vão livre < duração mínima não é reservável.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Iterable

from models import (
    ClassifiedPeriod,
    DayAvailability,
    DaySchedule,
    PeriodStatus,
    ResourceAvailability,
    TimePeriod,
)

# weekday() → horário-limite fixo; None = usa o pôr do sol (sábado).
WEEKDAY_CLOSE_LIMITS: dict[int, time | None] = {
    0: time(9, 30),
    1: time(9, 30),
    2: time(9, 30),
    3: time(9, 30),
    4: time(9, 30),
    5: None,
    6: time(12, 0),
}

_DAY_START_MIN = 0
_DAY_END_MIN = 23 * 60 + 59


@dataclass(frozen=True)
class AvailabilityRules:
    turnaround_minutes: int = 30
    min_flight_minutes: int = 60
    max_flight_minutes: int = 120


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _to_time(minutes: int) -> time:
    minutes = max(_DAY_START_MIN, min(minutes, _DAY_END_MIN))
    return time(minutes // 60, minutes % 60)


def operating_window(day: date, sunrise: time, sunset: time) -> TimePeriod | None:
    limit = WEEKDAY_CLOSE_LIMITS[day.weekday()]
    end = sunset if limit is None else min(limit, sunset)
    if sunrise >= end:
        return None
    return TimePeriod(start=sunrise, end=end)


def apply_turnaround_buffer(
    periods: Iterable[TimePeriod], buffer_minutes: int
) -> tuple[TimePeriod, ...]:
    expanded = sorted(
        (
            max(_DAY_START_MIN, _to_minutes(p.start) - buffer_minutes),
            min(_DAY_END_MIN, _to_minutes(p.end) + buffer_minutes),
        )
        for p in periods
    )
    if not expanded:
        return ()
    merged: list[list[int]] = [list(expanded[0])]
    for start, end in expanded[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple(TimePeriod(start=_to_time(s), end=_to_time(e)) for s, e in merged)


def subtract_periods(
    window: TimePeriod, busy: Iterable[TimePeriod]
) -> tuple[TimePeriod, ...]:
    free: list[TimePeriod] = []
    cursor = _to_minutes(window.start)
    window_end = _to_minutes(window.end)
    for period in sorted(busy, key=lambda p: (p.start, p.end)):
        start = max(_to_minutes(period.start), _to_minutes(window.start))
        end = min(_to_minutes(period.end), window_end)
        if end <= cursor:
            continue
        if start >= window_end:
            break
        if start > cursor:
            free.append(TimePeriod(start=_to_time(cursor), end=_to_time(start)))
        cursor = max(cursor, end)
    if cursor < window_end:
        free.append(TimePeriod(start=_to_time(cursor), end=_to_time(window_end)))
    return tuple(free)


def filter_bookable_periods(
    free: Iterable[TimePeriod], min_minutes: int
) -> tuple[tuple[TimePeriod, ...], tuple[TimePeriod, ...]]:
    free = tuple(free)
    bookable = tuple(p for p in free if p.duration_minutes() >= min_minutes)
    too_short = tuple(p for p in free if p.duration_minutes() < min_minutes)
    return bookable, too_short


def _clip_to_window(period: TimePeriod, window: TimePeriod) -> TimePeriod | None:
    start = max(period.start, window.start)
    end = min(period.end, window.end)
    if start >= end:
        return None
    return TimePeriod(start=start, end=end, label=period.label)


def classify_day_periods(
    window: TimePeriod, raw_busy: Iterable[TimePeriod], rules: AvailabilityRules
) -> tuple[ClassifiedPeriod, ...]:
    """Timeline do relatório: ocupados com horários originais (recortados à
    janela); vãos livres calculados sobre os ocupados bufferizados (spec §1).
    """
    raw_busy = tuple(raw_busy)
    entries: list[ClassifiedPeriod] = []
    for period in raw_busy:
        clipped = _clip_to_window(period, window)
        if clipped is None:
            continue
        reason = f"reservado ({clipped.label})" if clipped.label else "reservado"
        entries.append(
            ClassifiedPeriod(period=clipped, status=PeriodStatus.BUSY, reason=reason)
        )
    buffered = apply_turnaround_buffer(raw_busy, rules.turnaround_minutes)
    free = subtract_periods(window, buffered)
    bookable, too_short = filter_bookable_periods(free, rules.min_flight_minutes)
    for period in bookable:
        entries.append(
            ClassifiedPeriod(period=period, status=PeriodStatus.AVAILABLE, reason="livre")
        )
    for period in too_short:
        entries.append(
            ClassifiedPeriod(
                period=period,
                status=PeriodStatus.BUSY,
                reason=(
                    f"vão curto ({period.duration_minutes()}min "
                    f"< {rules.min_flight_minutes}min)"
                ),
            )
        )
    entries.sort(key=lambda e: (e.period.start, e.period.end))
    return tuple(entries)


def enrich_day_schedule(
    day_schedule: DaySchedule, rules: AvailabilityRules
) -> DayAvailability:
    window = operating_window(
        day_schedule.day, day_schedule.sunrise, day_schedule.sunset
    )
    resources: list[ResourceAvailability] = []
    for resource in day_schedule.resources:
        if window is None:
            periods: tuple[ClassifiedPeriod, ...] = ()
        else:
            periods = classify_day_periods(window, resource.busy_periods, rules)
        resources.append(
            ResourceAvailability(
                resource_name=resource.name,
                resource_model=resource.model,
                periods=periods,
            )
        )
    return DayAvailability(
        day=day_schedule.day,
        sunrise=day_schedule.sunrise,
        sunset=day_schedule.sunset,
        window=window,
        resources=tuple(resources),
    )
