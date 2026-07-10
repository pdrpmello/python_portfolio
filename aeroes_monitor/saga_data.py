"""Dados brutos do SAGA → domínio. Puro: sem Selenium (ADR-0004).

A página /schedules/personal embute a variável JS `allSchedules` e busca
nascer/pôr do sol em /aisweb/sun/SBVT (XML, horários UTC — ADR-0008/0010).
Este módulo converte esses dois insumos em dataclasses de domínio.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from utils import parse_time

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
