"""Aquisição da escala SAGA por HTTP direto, sem browser (ADR-0011).

Uma varredura = uma sessão requests: login (único POST — ADR-0001), leitura
da variável `allSchedules` embutida no HTML server-rendered (ADR-0010) e do
XML de nascer/pôr do sol (/aisweb/sun/SBVT, UTC — ADR-0008). Substitui a
antiga camada Selenium (browser/login/scheduler).
"""
from __future__ import annotations

import json
import logging
import re

import requests

from models import ScanError, ScanResult
from saga_data import (
    build_day_schedules,
    local_today,
    parse_sun_xml,
    utc_time_to_local,
)

logger = logging.getLogger(__name__)

SUN_ENDPOINT = "/aisweb/sun/SBVT"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
_TOKEN_RE = re.compile(r'name="_token"\s+value="([^"]+)"')
# allSchedules fica numa única linha `const allSchedules = [...];`; greedy até
# o `];` no fim da linha pega o fechamento real do array (ADR-0010).
_ALL_SCHEDULES_RE = re.compile(r"^\s*const allSchedules\s*=\s*(\[.*\]);", re.MULTILINE)
_LOGIN_MARKERS = ('action="/login"', 'name="_token"')

_SUN_UNAVAILABLE = (
    "Nascer/pôr do sol indisponível no SAGA — janelas não calculadas nesta "
    "varredura (ADR-0008)"
)


class ScanHttpError(Exception):
    """Falha de aquisição HTTP; page_html carrega o HTML para debug quando há."""

    def __init__(self, message: str, page_html: str | None = None) -> None:
        super().__init__(message)
        self.page_html = page_html


class LoginError(ScanHttpError):
    """Login não confirmado (credencial inválida ou fluxo do SAGA mudou)."""


def _looks_like_login(html: str) -> bool:
    return all(marker in html for marker in _LOGIN_MARKERS)


def _origin(base_url: str) -> str:
    return base_url.rsplit("/", 1)[0]


def _extract_all_schedules(html: str) -> list:
    match = _ALL_SCHEDULES_RE.search(html)
    if match is None:
        raise ScanHttpError(
            "allSchedules não encontrado na página da escala — layout do SAGA "
            "mudou? Verifique saga.schedule_url e o HTML de debug",
            page_html=html,
        )
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ScanHttpError(
            f"allSchedules com JSON inválido: {exc}", page_html=html
        ) from exc
    if not isinstance(data, list):
        raise ScanHttpError(
            f"allSchedules com formato inesperado: {type(data).__name__}",
            page_html=html,
        )
    logger.info("allSchedules lido: %d agendamento(s)", len(data))
    return data


def _read_sun_times(session, origin: str, timeout: int):
    """(nascer, pôr) LOCAIS de hoje, ou None se indisponível (recuperável)."""
    try:
        response = session.get(f"{origin}{SUN_ENDPOINT}", timeout=timeout)
        if response.status_code != 200:
            logger.warning("Endpoint do sol respondeu %s", response.status_code)
            return None
        parsed = parse_sun_xml(response.text)
        if parsed is None:
            logger.warning("XML do sol não parseável")
            return None
        today = local_today()
        return utc_time_to_local(parsed[0], today), utc_time_to_local(parsed[1], today)
    except Exception:
        logger.exception("Falha ao consultar o sol")
        return None


def scan(config) -> ScanResult:
    cfg = config.saga
    timeout = cfg.request_timeout_seconds
    origin = _origin(cfg.base_url)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    response = session.get(cfg.base_url, timeout=timeout)
    match = _TOKEN_RE.search(response.text)
    if match is None:
        raise LoginError(
            "Formulário de login sem _token — layout do SAGA mudou?",
            page_html=response.text,
        )

    response = session.post(
        f"{origin}/login",
        data={
            "_token": match.group(1),
            "email": config.credentials.username,
            "password": config.credentials.password,
        },
        timeout=timeout,
        allow_redirects=True,
    )
    if _looks_like_login(response.text):
        raise LoginError(
            "Login não confirmado (verifique credenciais).", page_html=response.text
        )
    logger.info("Login efetuado com sucesso")

    response = session.get(cfg.schedule_url or cfg.base_url, timeout=timeout)
    if _looks_like_login(response.text):
        raise LoginError(
            "Sessão não autenticada na página da escala.", page_html=response.text
        )
    raw = _extract_all_schedules(response.text)

    sun = _read_sun_times(session, origin, timeout)
    if sun is None:
        return ScanResult(
            days=(),
            errors=(ScanError(day_index=0, day_label="sol", message=_SUN_UNAVAILABLE),),
        )
    sunrise, sunset = sun
    return build_day_schedules(
        raw, config.aircraft, sunrise, sunset, local_today(), config.monitor.max_days
    )
