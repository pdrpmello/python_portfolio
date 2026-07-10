"""Política de notificação por diff (specs 2026-07-09 e 2026-07-10).

Só aberturas NOVAS notificam; janela que some é silêncio. Guardas
anti-ruído (spec 2026-07-10): dia fora do snapshot anterior não notifica
(acabou de entrar no horizonte de varredura) e janela contida numa janela
livre anterior do mesmo dia+aeronave não é novidade (só encolheu). O
snapshot do último aviso vive em state.json — ausente/corrompido/versão
antiga significa baseline (relatório completo uma vez).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from models import DayAvailability, PeriodStatus

logger = logging.getLogger(__name__)

STATE_VERSION = 2

# (dia ISO, recurso, início "HH:MM", fim "HH:MM")
WindowKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class NotifyState:
    windows: frozenset[WindowKey]
    days: frozenset[str]
    last_scan_ok: bool = True


def extract_open_windows(days: Sequence[DayAvailability]) -> frozenset[WindowKey]:
    keys: set[WindowKey] = set()
    for day in days:
        for resource in day.resources:
            for entry in resource.periods:
                if entry.status is PeriodStatus.AVAILABLE:
                    keys.add(
                        (
                            day.day.isoformat(),
                            resource.resource_name,
                            entry.period.start.strftime("%H:%M"),
                            entry.period.end.strftime("%H:%M"),
                        )
                    )
    return frozenset(keys)


def extract_scanned_days(days: Sequence[DayAvailability]) -> frozenset[str]:
    return frozenset(day.day.isoformat() for day in days)


def _is_covered(candidate: WindowKey, windows: frozenset[WindowKey]) -> bool:
    """Contida numa janela anterior do mesmo dia+aeronave? Horários
    "HH:MM" zero-padded: comparação lexicográfica = numérica.
    """
    day, resource, start, end = candidate
    return any(
        prev_start <= start and end <= prev_end
        for prev_day, prev_resource, prev_start, prev_end in windows
        if prev_day == day and prev_resource == resource
    )


def diff_new_windows(
    previous: NotifyState, current: frozenset[WindowKey]
) -> tuple[WindowKey, ...]:
    """Chave nova notifica SE o dia já era varrido e nenhuma janela
    anterior a contém (dia novo no horizonte e janela que encolheu são
    silêncio — spec 2026-07-10).
    """
    return tuple(
        key
        for key in sorted(current - previous.windows)
        if key[0] in previous.days and not _is_covered(key, previous.windows)
    )


def load_state(path: Path) -> NotifyState | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("state.json não é um objeto JSON; tratando como baseline")
            return None
        if data.get("version") != STATE_VERSION:
            logger.warning("state.json com versão desconhecida; tratando como baseline")
            return None
        windows = frozenset(tuple(w) for w in data["windows"])
        if not all(
            len(w) == 4 and all(isinstance(part, str) for part in w) for w in windows
        ):
            raise ValueError("janela malformada")
        raw_days = data["days"]
        if not isinstance(raw_days, list) or not all(
            isinstance(d, str) for d in raw_days
        ):
            raise ValueError("dias malformados")
        return NotifyState(
            windows=windows,
            days=frozenset(raw_days),
            last_scan_ok=bool(data["last_scan_ok"]),
        )
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("state.json ilegível; tratando como baseline", exc_info=True)
        return None


def save_state(path: Path, state: NotifyState) -> None:
    payload = {
        "version": STATE_VERSION,
        "windows": sorted(state.windows),
        "days": sorted(state.days),
        "last_scan_ok": state.last_scan_ok,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
