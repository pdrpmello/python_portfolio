"""Extração das agendas de aeronaves e Stand By da página do SAGA.

A allowlist manual decide o que é reportado (ADR-0007); o status exibido
pelo sistema é ignorado. Stand By é um recurso independente (PRD F5).
"""
from __future__ import annotations

import logging
import re

from browser import find_all_first_match, read_text_from_selectors
from models import ResourceSchedule, TimePeriod
from utils import extract_period, normalize_registration

logger = logging.getLogger(__name__)

STANDBY_PATTERN = re.compile(r"stand\s*-?\s*by", re.IGNORECASE)
STANDBY_NAME = "Stand By"


class AircraftService:
    def __init__(self, driver, selectors, allowlist: dict[str, str]) -> None:
        self.driver = driver
        self.selectors = selectors
        self.allowlist = allowlist

    def _row_name(self, row) -> str:
        name = read_text_from_selectors(row, self.selectors["resource_name"])
        if name:
            return name
        return (row.text or "").strip().split("\n")[0]

    def _row_periods(self, row) -> tuple[TimePeriod, ...]:
        periods: list[TimePeriod] = []
        for event in find_all_first_match(row, self.selectors["event_item"]):
            text = (event.text or "").strip()
            if not text:
                continue
            period = extract_period(text)
            if period is None:
                logger.warning("Evento sem horário parseável ignorado: %r", text)
                continue
            periods.append(period)
        return tuple(sorted(periods, key=lambda p: (p.start, p.end)))

    def build_aircraft_schedules(self) -> tuple[ResourceSchedule, ...]:
        rows = find_all_first_match(self.driver, self.selectors["resource_row"])
        by_registration: dict[str, tuple[TimePeriod, ...]] = {}
        standby_periods: tuple[TimePeriod, ...] = ()
        standby_found = False
        for row in rows:
            name = self._row_name(row)
            if not name:
                continue
            if STANDBY_PATTERN.search(name):
                standby_periods += self._row_periods(row)
                standby_found = True
                continue
            normalized_name = normalize_registration(name)
            for registration in self.allowlist:
                if normalize_registration(registration) in normalized_name:
                    by_registration[registration] = (
                        by_registration.get(registration, ()) + self._row_periods(row)
                    )
                    break
        if not standby_found:
            logger.warning("Linha de Stand By não encontrada na página")
        schedules = [
            ResourceSchedule(
                name=registration,
                model=self.allowlist[registration],
                busy_periods=tuple(
                    sorted(by_registration.get(registration, ()), key=lambda p: (p.start, p.end))
                ),
            )
            for registration in self.allowlist
        ]
        schedules.append(
            ResourceSchedule(
                name=STANDBY_NAME,
                model="",
                busy_periods=tuple(sorted(standby_periods, key=lambda p: (p.start, p.end))),
            )
        )
        return tuple(schedules)
