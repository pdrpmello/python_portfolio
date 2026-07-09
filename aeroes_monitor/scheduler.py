"""Varredura multi-dia da escala do SAGA (PRD F2, F3, F6, F10).

Nascer/pôr do sol vêm EXCLUSIVAMENTE da página (ADR-0008): seletor
dedicado primeiro, senão regex no texto da página; ausência é erro
recuperável do dia, nunca um valor calculado.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from aircraft import AircraftService
from browser import read_text_from_selectors, wait_for_any_visible
from login import is_login_page, login
from models import DaySchedule, ScanError, ScanResult
from utils import extract_sunrise, extract_sunset, find_times, parse_day_date

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 3


class ScheduleScanner:
    def __init__(self, driver, config) -> None:
        self.driver = driver
        self.config = config
        self.selectors = config.selectors
        self._last_parsed_date: date | None = None
        self._last_parsed_index = 0

    def scan(self) -> ScanResult:
        self._open_schedule()
        days: list[DaySchedule] = []
        errors: list[ScanError] = []
        consecutive_failures = 0
        for index in range(self.config.monitor.max_days):
            day_label = ""
            try:
                self._ensure_session()
                day_label = (
                    read_text_from_selectors(
                        self.driver, self.selectors["schedule_date"]
                    )
                    or ""
                )
                days.append(self._scan_single_day(index, day_label))
                consecutive_failures = 0
            except Exception as exc:
                logger.exception("Falha ao ler o dia %d", index + 1)
                errors.append(
                    ScanError(
                        day_index=index,
                        day_label=day_label or f"dia {index + 1}",
                        message=str(exc),
                    )
                )
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    errors.append(
                        ScanError(
                            day_index=index,
                            day_label="varredura interrompida",
                            message=(
                                f"{MAX_CONSECUTIVE_FAILURES} falhas consecutivas — "
                                "dias restantes não lidos"
                            ),
                        )
                    )
                    break
            if index < self.config.monitor.max_days - 1:
                if not self._advance_day(day_label):
                    errors.append(
                        ScanError(
                            day_index=index,
                            day_label=day_label or f"dia {index + 1}",
                            message=(
                                "não foi possível avançar para o dia seguinte — "
                                "dias restantes não lidos"
                            ),
                        )
                    )
                    break
        logger.info(
            "Varredura terminou: %d dia(s) lidos, %d erro(s)", len(days), len(errors)
        )
        return ScanResult(days=tuple(days), errors=tuple(errors))

    def _open_schedule(self) -> None:
        if self.config.selenium.schedule_url:
            self.driver.get(self.config.selenium.schedule_url)
        wait_for_any_visible(
            self.driver,
            self.selectors["schedule_container"],
            self.config.selenium.element_timeout_seconds,
        )

    def _ensure_session(self) -> None:
        if is_login_page(self.driver, self.selectors):
            logger.info("Sessão expirada — reautenticando (F2)")
            login(self.driver, self.config)
            self._open_schedule()

    def _scan_single_day(self, index: int, day_label: str) -> DaySchedule:
        day = self._resolve_date(index, day_label)
        page_text = self._page_text()
        sunrise = self._read_sunrise(page_text)
        sunset = self._read_sunset(page_text)
        service = AircraftService(self.driver, self.selectors, self.config.aircraft)
        resources = service.build_aircraft_schedules()
        logger.info("Dia %s lido: %d recurso(s)", day.isoformat(), len(resources))
        return DaySchedule(day=day, sunrise=sunrise, sunset=sunset, resources=resources)

    def _resolve_date(self, index: int, day_label: str) -> date:
        parsed = parse_day_date(day_label) if day_label else None
        if parsed is not None:
            self._last_parsed_date = parsed
            self._last_parsed_index = index
            return parsed
        if self._last_parsed_date is not None:
            fallback = self._last_parsed_date + timedelta(
                days=index - self._last_parsed_index
            )
        else:
            fallback = date.today() + timedelta(days=index)
        logger.warning(
            "Data do dia %d não parseada (%r); usando %s", index + 1, day_label, fallback
        )
        return fallback

    def _page_text(self) -> str:
        try:
            return self.driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            return ""

    def _read_sun_value(self, selector_key, extractor, page_text, label):
        text = read_text_from_selectors(self.driver, self.selectors[selector_key])
        value = None
        if text:
            value = extractor(text)
            if value is None:
                times = find_times(text)
                if len(times) == 1:
                    # Elemento dedicado exibindo só o horário, sem rótulo.
                    value = times[0]
        if value is None:
            value = extractor(page_text)
        if value is None:
            raise ValueError(f"{label} não encontrado na página (ADR-0008)")
        return value

    def _read_sunrise(self, page_text: str):
        return self._read_sun_value(
            "sunrise_text", extract_sunrise, page_text, "Nascer do sol"
        )

    def _read_sunset(self, page_text: str):
        return self._read_sun_value(
            "sunset_text", extract_sunset, page_text, "Pôr do sol"
        )

    def _advance_day(self, previous_label: str) -> bool:
        try:
            button = wait_for_any_visible(
                self.driver,
                self.selectors["next_day_button"],
                self.config.selenium.element_timeout_seconds,
            )
            button.click()
            WebDriverWait(
                self.driver, self.config.selenium.element_timeout_seconds
            ).until(
                lambda drv: (
                    read_text_from_selectors(drv, self.selectors["schedule_date"]) or ""
                )
                not in ("", previous_label)
            )
            return True
        except Exception:
            logger.exception("Falha ao avançar para o próximo dia")
            return False
