"""Aquisição da escala via variável JS `allSchedules` (ADR-0010).

A página /schedules/personal embute a janela inteira (~30 dias) em uma
variável JavaScript; uma leitura cobre a varredura toda. O sol vem do
endpoint /aisweb/sun/SBVT (UTC — ADR-0008) na MESMA sessão autenticada.
Read-only: apenas GET e leitura de variável (ADR-0001).
"""
from __future__ import annotations

import logging

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from login import is_login_page, login
from models import ScanError, ScanResult
from saga_data import build_day_schedules, local_today, parse_sun_xml, utc_time_to_local

logger = logging.getLogger(__name__)

SUN_ENDPOINT = "/aisweb/sun/SBVT"

_FETCH_TEXT_ASYNC = """
const done = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: 'same-origin'})
  .then(r => r.text().then(t => done({status: r.status, body: t})))
  .catch(e => done({status: -1, body: String(e)}));
"""


class ScheduleScanner:
    def __init__(self, driver, config) -> None:
        self.driver = driver
        self.config = config

    def scan(self) -> ScanResult:
        self._open_schedule()
        raw = self._read_all_schedules()
        sun = self._read_sun_times()
        if sun is None:
            return ScanResult(
                days=(),
                errors=(
                    ScanError(
                        day_index=0,
                        day_label="sol",
                        message=(
                            "Nascer/pôr do sol indisponível no SAGA — janelas "
                            "não calculadas nesta varredura (ADR-0008)"
                        ),
                    ),
                ),
            )
        sunrise, sunset = sun
        return build_day_schedules(
            raw,
            self.config.aircraft,
            sunrise,
            sunset,
            local_today(),
            self.config.monitor.max_days,
        )

    def _schedule_page_url(self) -> str:
        return self.config.selenium.schedule_url or self.config.selenium.base_url

    def _open_schedule(self) -> None:
        self.driver.get(self._schedule_page_url())
        if is_login_page(self.driver, self.config.selectors):
            logger.info("Sessão expirada — reautenticando (F2)")
            login(self.driver, self.config)
            self.driver.get(self._schedule_page_url())
        self._wait_for_schedule_data()

    def _wait_for_schedule_data(self) -> None:
        def _has_data(drv):
            return drv.execute_script("return typeof allSchedules !== 'undefined'")

        try:
            WebDriverWait(
                self.driver, self.config.selenium.element_timeout_seconds
            ).until(_has_data)
        except TimeoutException as exc:
            raise ValueError(
                "allSchedules não encontrado na página da escala — layout do "
                "SAGA mudou? Verifique selenium.schedule_url e os artefatos de debug"
            ) from exc

    def _read_all_schedules(self) -> list:
        raw = self.driver.execute_script("return allSchedules")
        if not isinstance(raw, list):
            raise ValueError(
                f"allSchedules com formato inesperado: {type(raw).__name__}"
            )
        logger.info("allSchedules lido: %d agendamento(s)", len(raw))
        return raw

    def _read_sun_times(self):
        """(nascer, pôr) LOCAIS de hoje, ou None se indisponível (recuperável)."""
        try:
            self.driver.set_script_timeout(
                self.config.selenium.element_timeout_seconds
            )
            response = self.driver.execute_async_script(
                _FETCH_TEXT_ASYNC, SUN_ENDPOINT
            )
            if response.get("status") != 200:
                logger.warning("Endpoint do sol respondeu %s", response.get("status"))
                return None
            parsed = parse_sun_xml(response.get("body") or "")
            if parsed is None:
                logger.warning("XML do sol não parseável")
                return None
            today = local_today()
            return (
                utc_time_to_local(parsed[0], today),
                utc_time_to_local(parsed[1], today),
            )
        except Exception:
            logger.exception("Falha ao consultar o sol")
            return None
