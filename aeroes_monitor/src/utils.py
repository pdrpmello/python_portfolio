"""Parsing puro de texto → domínio. Sem Selenium (ADR-0004)."""
from __future__ import annotations

import re
from datetime import time

_TIME_RE = re.compile(r"(\d{1,2})\s*[:hH]\s*(\d{2})(?!\d)")


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


def normalize_registration(text: str) -> str:
    """Matrícula canônica para casamento com a allowlist: 'pt-abc' ≡ 'PTABC'."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())
