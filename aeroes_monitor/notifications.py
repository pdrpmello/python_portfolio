"""Política de notificação por diff (spec 2026-07-09).

Só aberturas NOVAS notificam; janela que some é silêncio. O snapshot do
último aviso vive em state.json — ausente/corrompido significa baseline
(relatório completo uma vez).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from models import DayAvailability, PeriodStatus

logger = logging.getLogger(__name__)

STATE_VERSION = 1

# (dia ISO, recurso, início "HH:MM", fim "HH:MM")
WindowKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class NotifyState:
    windows: frozenset[WindowKey]
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


def diff_new_windows(
    previous: frozenset[WindowKey], current: frozenset[WindowKey]
) -> tuple[WindowKey, ...]:
    return tuple(sorted(current - previous))


def load_state(path: Path) -> NotifyState | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != STATE_VERSION:
            logger.warning("state.json com versão desconhecida; tratando como baseline")
            return None
        windows = frozenset(tuple(w) for w in data["windows"])
        if not all(len(w) == 4 for w in windows):
            raise ValueError("janela malformada")
        return NotifyState(windows=windows, last_scan_ok=bool(data["last_scan_ok"]))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        logger.warning("state.json ilegível; tratando como baseline", exc_info=True)
        return None


def save_state(path: Path, state: NotifyState) -> None:
    payload = {
        "version": STATE_VERSION,
        "windows": sorted(state.windows),
        "last_scan_ok": state.last_scan_ok,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
