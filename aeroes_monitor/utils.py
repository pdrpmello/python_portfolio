"""Parsing puro de texto → domínio. Sem Selenium (ADR-0004)."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, time

from models import TimePeriod

_TIME_RE = re.compile(r"(\d{1,2})\s*[:hH]\s*(\d{2})(?!\d)")
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_PERIOD_RE = re.compile(
    r"(\d{1,2}\s*[:hH]\s*\d{2})\s*(?:[-–—]|às|as\b|até\b|ate\b|a\b)\s*"
    r"(\d{1,2}\s*[:hH]\s*\d{2})",
    re.IGNORECASE,
)
_SUNRISE_KEYWORDS = ("nascer do sol", "nascer-do-sol", "nascer", "aurora", "sunrise")
_SUNSET_KEYWORDS = ("por do sol", "por-do-sol", "ocaso", "sunset")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def _to_time(hour: int, minute: int) -> time | None:
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_time(text: str) -> time | None:
    """Primeiro horário HH:MM (ou HhMM) válido encontrado no texto."""
    match = _TIME_RE.search(text)
    if not match:
        return None
    return _to_time(int(match.group(1)), int(match.group(2)))


def find_times(text: str) -> list[time]:
    """Todos os horários válidos do texto, na ordem em que aparecem."""
    results: list[time] = []
    for match in _TIME_RE.finditer(text):
        value = _to_time(int(match.group(1)), int(match.group(2)))
        if value is not None:
            results.append(value)
    return results


def extract_period(text: str) -> TimePeriod | None:
    """Período "HH:MM - HH:MM" (separadores -, –, —, às, até, a).

    O texto restante vira o label (ex.: nome de quem reservou).
    """
    match = _PERIOD_RE.search(text)
    if not match:
        return None
    start = parse_time(match.group(1))
    end = parse_time(match.group(2))
    if start is None or end is None or start >= end:
        return None
    remainder = text[: match.start()] + " " + text[match.end() :]
    label = " ".join(remainder.replace("|", " ").replace("•", " ").split())
    label = label.strip("-–—:· ")
    return TimePeriod(start=start, end=end, label=label)


def _extract_time_near_keyword(text: str, keywords: tuple[str, ...]) -> time | None:
    # Busca e extração acontecem AMBAS no texto normalizado: strip de acentos
    # muda o comprimento da string, então índices não podem ser reusados no
    # texto original. Dígitos não são afetados pela normalização.
    normalized = _strip_accents(text).lower()
    for keyword in keywords:
        idx = normalized.find(keyword)
        while idx != -1:
            snippet = normalized[idx + len(keyword) : idx + len(keyword) + 40]
            value = parse_time(snippet)
            if value is not None:
                return value
            idx = normalized.find(keyword, idx + 1)
    return None


def extract_sunrise(text: str) -> time | None:
    return _extract_time_near_keyword(text, _SUNRISE_KEYWORDS)


def extract_sunset(text: str) -> time | None:
    return _extract_time_near_keyword(text, _SUNSET_KEYWORDS)


def parse_day_date(text: str) -> date | None:
    """Data dd/mm/aaaa em qualquer lugar do texto (formato exibido pelo SAGA)."""
    match = _DATE_RE.search(text)
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def normalize_registration(text: str) -> str:
    """Matrícula canônica para casamento com a allowlist: 'pt-abc' ≡ 'PTABC'."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())
