"""Dados brutos do SAGA → domínio. Puro: sem Selenium (ADR-0004).

A página /schedules/personal embute a variável JS `allSchedules` e busca
nascer/pôr do sol em /aisweb/sun/SBVT (XML, horários UTC — ADR-0008/0010).
Este módulo converte esses dois insumos em dataclasses de domínio.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from models import DaySchedule, ResourceSchedule, ScanError, ScanResult, TimePeriod
from utils import normalize_registration, parse_time

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
UTC = ZoneInfo("UTC")


def parse_sun_xml(xml_text: str) -> tuple[time, time] | None:
    """(nascer, pôr) em UTC a partir do XML de /aisweb/sun/SBVT; None se inválido."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    sunrise = parse_time(root.findtext(".//sunrise") or "")
    sunset = parse_time(root.findtext(".//sunset") or "")
    if sunrise is None or sunset is None:
        return None
    return sunrise, sunset


def utc_time_to_local(value: time, day: date) -> time:
    moment = datetime.combine(day, value, tzinfo=UTC)
    return moment.astimezone(LOCAL_TZ).time().replace(second=0, microsecond=0)


# Janela que a página expõe (input date: min=hoje, max=hoje+30d) — ADR-0010.
PAGE_WINDOW_DAYS = 30
STANDBY_PATTERN = re.compile(r"stand\s*-?\s*by", re.IGNORECASE)
STANDBY_NAME = "Stand By"
_RAW_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_raw_timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, _RAW_TS_FORMAT)
    except ValueError:
        return None


def _resource_key(registration: str, allowlist: Mapping[str, str]) -> str | None:
    """Chave canônica do recurso: matrícula da allowlist, Stand By, ou None."""
    if STANDBY_PATTERN.search(registration):
        return STANDBY_NAME
    normalized = normalize_registration(registration)
    for candidate in allowlist:
        if normalize_registration(candidate) in normalized:
            return candidate
    return None


def _label(item: Mapping) -> str:
    student = item.get("student") or {}
    return (student.get("nickname") or "").strip()


def build_day_schedules(
    raw_schedules: Sequence[Mapping],
    allowlist: Mapping[str, str],
    sunrise: time,
    sunset: time,
    start_day: date,
    max_days: int,
) -> ScanResult:
    """`allSchedules` (JSON da página) → dias de escala (ADR-0010).

    Horários vêm de start_at_raw/end_at_raw (hora local). CANCELED é
    descartado como o próprio UI faz; matrículas fora da allowlist são
    ignoradas (ADR-0007); SLOT STAND-BY vira o recurso Stand By (PRD F5).
    """
    errors: list[ScanError] = []
    scan_days = min(max_days, PAGE_WINDOW_DAYS)
    if max_days > PAGE_WINDOW_DAYS:
        errors.append(
            ScanError(
                day_index=PAGE_WINDOW_DAYS,
                day_label="janela do SAGA",
                message=(
                    f"max_days={max_days} excede os {PAGE_WINDOW_DAYS} dias "
                    f"expostos pela página; varredura limitada a {PAGE_WINDOW_DAYS}"
                ),
            )
        )
    window_days = [start_day + timedelta(days=i) for i in range(scan_days)]
    by_day_resource: dict[tuple[date, str], list[TimePeriod]] = {}
    for item in raw_schedules:
        if item.get("status") == "CANCELED":
            continue
        registration = (item.get("aircraft") or {}).get("registration") or ""
        key = _resource_key(registration, allowlist)
        if key is None:
            continue
        start = _parse_raw_timestamp(item.get("start_at_raw"))
        end = _parse_raw_timestamp(item.get("end_at_raw"))
        if start is None or end is None:
            logger.warning("Agendamento sem *_raw parseável ignorado: %r", item.get("id"))
            continue
        if end.date() > start.date():
            logger.warning(
                "Agendamento cruza meia-noite; recortado em 23:59: %r", item.get("id")
            )
            end = datetime.combine(start.date(), time(23, 59))
        if start.time() >= end.time():
            logger.warning("Agendamento com período inválido ignorado: %r", item.get("id"))
            continue
        period = TimePeriod(start=start.time(), end=end.time(), label=_label(item))
        by_day_resource.setdefault((start.date(), key), []).append(period)

    resource_names = list(allowlist) + [STANDBY_NAME]
    days = tuple(
        DaySchedule(
            day=day,
            sunrise=sunrise,
            sunset=sunset,
            resources=tuple(
                ResourceSchedule(
                    name=name,
                    model=allowlist.get(name, ""),
                    busy_periods=tuple(
                        sorted(
                            by_day_resource.get((day, name), ()),
                            key=lambda p: (p.start, p.end),
                        )
                    ),
                )
                for name in resource_names
            ),
        )
        for day in window_days
    )
    return ScanResult(days=days, errors=tuple(errors))
