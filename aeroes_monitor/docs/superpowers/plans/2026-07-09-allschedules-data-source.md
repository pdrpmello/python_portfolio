# allSchedules + Notificação por Diff — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar a aquisição da escala para a variável JS `allSchedules` da página `/schedules/personal`, aplicar o sol de hoje (SAGA/AISWEB, UTC→local) à janela toda e notificar no Discord só aberturas novas (diff com `state.json`).

**Architecture:** `scheduler.py` vira aquisição fina (Selenium: carregar página, `execute_script`, fetch do XML do sol); toda a construção de domínio vai para funções puras novas em `saga_data.py`; a política de notificação (baseline/diff/transições de erro) vive em `notifications.py` puro + persistência JSON; `main.py` orquestra. `aircraft.py` e o loop dia-a-dia morrem. Spec: `docs/superpowers/specs/2026-07-09-schedule-data-source-design.md`.

**Tech Stack:** Python 3.13+ (venv local: 3.14), Selenium 4, `unittest` (stdlib), `zoneinfo` + `tzdata` (novo, só dados de fuso — Windows não tem tz database do sistema).

## Global Constraints

- Read-only no SAGA (ADR-0001): nada de POST além do login; `execute_script` apenas LÊ variáveis/faz GET.
- Docstrings/comentários/mensagens em pt-BR, no estilo dos módulos atuais (citando ADR/PRD quando pertinente).
- Testes `unittest` sem browser/rede real (fakes, como `tests/test_scheduler.py` atual).
- Rodar testes: `.venv\Scripts\python -m unittest -v` (cwd = `aeroes_monitor/`). Seletivo: `.venv\Scripts\python -m unittest tests.test_saga_data -v`.
- Commits: `tipo(aeroes_monitor): descrição` + trailers:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` e
  `Claude-Session: https://claude.ai/code/session_01FMEHFhujxCWDH9oAecuCkN`.
- `config.ini` real NUNCA é commitado; `config.ini.example` sim.
- Horários de evento vêm de `start_at_raw`/`end_at_raw` (hora LOCAL). Nunca usar `start_at`/`end_at` (UTC) para montar períodos.

---

### Task 1: `saga_data.py` — sol (parse do XML + UTC→local)

**Files:**
- Create: `saga_data.py`
- Create: `tests/test_saga_data.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `utils.parse_time` (existente), `models.TimePeriod` (nada ainda).
- Produces: `parse_sun_xml(xml_text: str) -> tuple[time, time] | None` (horários UTC);
  `utc_time_to_local(value: time, day: date) -> time`; `LOCAL_TZ = ZoneInfo("America/Sao_Paulo")`.

- [ ] **Step 1: Adicionar tzdata ao requirements.txt**

```
selenium>=4.21
requests>=2.32
tzdata>=2024.1
```

Instalar: `.venv\Scripts\python -m pip install -r requirements.txt`

- [ ] **Step 2: Escrever testes que falham**

```python
"""Testes das funções puras de dados do SAGA (sol e agendamentos)."""
import unittest
from datetime import date, time

from saga_data import parse_sun_xml, utc_time_to_local

SUN_XML = (
    '<?xml version="1.0" encoding="UTF-8"?><aisweb><day>'
    "<date>2026-07-09</date><sunrise>09:17</sunrise><sunset>20:15</sunset>"
    "<weekDay>4</weekDay><aero>SBVT</aero></day></aisweb>"
)


class ParseSunXmlTest(unittest.TestCase):
    def test_parses_sunrise_and_sunset(self):
        self.assertEqual(parse_sun_xml(SUN_XML), (time(9, 17), time(20, 15)))

    def test_missing_field_returns_none(self):
        xml = "<aisweb><day><sunrise>09:17</sunrise></day></aisweb>"
        self.assertIsNone(parse_sun_xml(xml))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_sun_xml("<html>Erro 500</html>"))
        self.assertIsNone(parse_sun_xml(""))
        self.assertIsNone(parse_sun_xml("não é xml"))


class UtcTimeToLocalTest(unittest.TestCase):
    def test_converts_utc_to_america_sao_paulo(self):
        # SBVT em julho: UTC-3 (Brasil sem horário de verão desde 2019).
        self.assertEqual(utc_time_to_local(time(9, 17), date(2026, 7, 9)), time(6, 17))
        self.assertEqual(utc_time_to_local(time(20, 15), date(2026, 7, 9)), time(17, 15))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_data -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saga_data'`

- [ ] **Step 4: Implementação mínima**

```python
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
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_data -v`
Expected: PASS (5 testes)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt saga_data.py tests/test_saga_data.py
git commit -m "feat(aeroes_monitor): parse sun XML and UTC->local conversion"
```

---

### Task 2: `saga_data.py` — `build_day_schedules`

**Files:**
- Modify: `saga_data.py`
- Modify: `tests/test_saga_data.py`

**Interfaces:**
- Consumes: `models.DaySchedule/ResourceSchedule/TimePeriod/ScanError/ScanResult`, `utils.normalize_registration`.
- Produces: `build_day_schedules(raw_schedules: Sequence[Mapping], allowlist: Mapping[str, str], sunrise: time, sunset: time, start_day: date, max_days: int) -> ScanResult`; constantes `PAGE_WINDOW_DAYS = 30`, `STANDBY_NAME = "Stand By"`.

Regras (da spec):
- Descartar `status == "CANCELED"` (como o UI da página faz).
- Períodos vêm de `start_at_raw`/`end_at_raw` (`"YYYY-MM-DD HH:MM:SS"`, hora local). Item sem `*_raw` ou com timestamp inválido: pular com `logger.warning`.
- Matrícula casa com a allowlist via `normalize_registration` (substring, como o `aircraft.py` fazia). `SLOT STAND-BY` (regex `stand\s*-?\s*by`, case-insensitive) vira o recurso `Stand By`. Demais matrículas: ignoradas.
- Evento cruzando meia-noite: recortar no dia de início até `23:59` com warning.
- Evento com início ≥ fim após recorte: pular com warning.
- `label` do período = `student.nickname` se existir, senão `""`.
- Todo dia da janela produz TODAS as aeronaves da allowlist + `Stand By` (dia sem eventos = tudo livre — não é erro).
- Janela = `start_day` .. `start_day + min(max_days, PAGE_WINDOW_DAYS) - 1`; se `max_days > PAGE_WINDOW_DAYS`, anexar `ScanError(day_index=PAGE_WINDOW_DAYS, day_label="janela do SAGA", message="max_days=N excede os 30 dias expostos pela página; varredura limitada a 30")`.

- [ ] **Step 1: Acrescentar testes que falham** (em `tests/test_saga_data.py`)

```python
from saga_data import PAGE_WINDOW_DAYS, STANDBY_NAME, build_day_schedules
from models import ScanResult


def _raw(reg, start, end, status="CONFIRMED", student=None, icao="C152"):
    return {
        "start_at_raw": start,
        "end_at_raw": end,
        "status": status,
        "aircraft": {"registration": reg, "icao": icao},
        "student": {"nickname": student} if student else None,
    }


ALLOWLIST = {"PP-AYB": "Cessna 152", "PT-JTK": "Cessna 172"}
DAY = date(2026, 7, 9)
SUNRISE, SUNSET = time(6, 17), time(17, 15)


def _build(raw, max_days=2, allowlist=ALLOWLIST):
    return build_day_schedules(raw, allowlist, SUNRISE, SUNSET, DAY, max_days)


class BuildDaySchedulesTest(unittest.TestCase):
    def test_groups_by_day_and_registration(self):
        result = _build(
            [
                _raw("PP-AYB", "2026-07-09 07:00:00", "2026-07-09 08:00:00", student="Ana"),
                _raw("PT-JTK", "2026-07-10 09:00:00", "2026-07-10 10:30:00"),
            ]
        )
        self.assertIsInstance(result, ScanResult)
        self.assertEqual(len(result.days), 2)
        d0 = result.days[0]
        self.assertEqual(d0.day, DAY)
        self.assertEqual((d0.sunrise, d0.sunset), (SUNRISE, SUNSET))
        ayb = next(r for r in d0.resources if r.name == "PP-AYB")
        self.assertEqual(ayb.model, "Cessna 152")
        self.assertEqual(ayb.busy_periods[0].start, time(7, 0))
        self.assertEqual(ayb.busy_periods[0].label, "Ana")
        jtk_d1 = next(r for r in result.days[1].resources if r.name == "PT-JTK")
        self.assertEqual(jtk_d1.busy_periods[0].end, time(10, 30))

    def test_all_resources_present_even_on_empty_day(self):
        result = _build([])
        names = [r.name for r in result.days[0].resources]
        self.assertEqual(names, ["PP-AYB", "PT-JTK", STANDBY_NAME])
        self.assertTrue(all(r.busy_periods == () for r in result.days[0].resources))

    def test_canceled_and_unknown_registrations_ignored(self):
        result = _build(
            [
                _raw("PP-AYB", "2026-07-09 07:00:00", "2026-07-09 08:00:00", status="CANCELED"),
                _raw("XX-XXX", "2026-07-09 09:00:00", "2026-07-09 10:00:00"),
            ]
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(ayb.busy_periods, ())

    def test_standby_slot_maps_to_standby_resource(self):
        result = _build(
            [_raw("SLOT STAND-BY", "2026-07-09 06:00:00", "2026-07-09 07:00:00")]
        )
        standby = next(r for r in result.days[0].resources if r.name == STANDBY_NAME)
        self.assertEqual(standby.busy_periods[0].start, time(6, 0))

    def test_registration_matching_is_normalized(self):
        result = _build(
            [_raw("pp ayb", "2026-07-09 07:00:00", "2026-07-09 08:00:00")]
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(len(ayb.busy_periods), 1)

    def test_midnight_crossing_clipped_and_invalid_skipped(self):
        result = _build(
            [
                _raw("PP-AYB", "2026-07-09 22:00:00", "2026-07-10 01:00:00"),
                _raw("PT-JTK", "2026-07-09 10:00:00", "2026-07-09 10:00:00"),
                {"start_at_raw": None, "end_at_raw": None, "status": "CONFIRMED",
                 "aircraft": {"registration": "PP-AYB"}, "student": None},
            ]
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(ayb.busy_periods[0].end, time(23, 59))
        jtk = next(r for r in result.days[0].resources if r.name == "PT-JTK")
        self.assertEqual(jtk.busy_periods, ())

    def test_events_outside_window_ignored(self):
        result = _build(
            [_raw("PP-AYB", "2026-08-20 07:00:00", "2026-08-20 08:00:00")],
            max_days=2,
        )
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        self.assertEqual(ayb.busy_periods, ())
        self.assertEqual(result.errors, ())

    def test_max_days_beyond_page_window_truncates_with_error(self):
        result = _build([], max_days=45)
        self.assertEqual(len(result.days), PAGE_WINDOW_DAYS)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("30", result.errors[0].message)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_data -v`
Expected: FAIL — `ImportError: cannot import name 'build_day_schedules'`

- [ ] **Step 3: Implementar** (acrescentar a `saga_data.py`)

```python
import re
from datetime import timedelta
from typing import Mapping, Sequence

from models import DaySchedule, ResourceSchedule, ScanError, ScanResult, TimePeriod
from utils import normalize_registration

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
```

Ajustar o import de datetime no topo do arquivo (já existe `from datetime import date, datetime, time`; acrescentar `timedelta` lá em vez de import separado).

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_data -v`
Expected: PASS (13 testes)

- [ ] **Step 5: Commit**

```bash
git add saga_data.py tests/test_saga_data.py
git commit -m "feat(aeroes_monitor): build day schedules from allSchedules JSON"
```

---

### Task 3: `notifications.py` — política de diff + `state.json`

**Files:**
- Create: `notifications.py`
- Create: `tests/test_notifications.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `models.DayAvailability`, `models.PeriodStatus`.
- Produces:
  - `WindowKey = tuple[str, str, str, str]` — `(dia ISO, recurso, "HH:MM", "HH:MM")`
  - `NotifyState(windows: frozenset[WindowKey], last_scan_ok: bool = True)` (frozen dataclass)
  - `extract_open_windows(days: Sequence[DayAvailability]) -> frozenset[WindowKey]`
  - `diff_new_windows(previous: frozenset[WindowKey], current: frozenset[WindowKey]) -> tuple[WindowKey, ...]` (ordenado)
  - `load_state(path: Path) -> NotifyState | None` (None = ausente/corrompido ⇒ baseline)
  - `save_state(path: Path, state: NotifyState) -> None`

- [ ] **Step 1: `.gitignore`** — acrescentar ao bloco "Artefatos de execução":

```
state.json
```

- [ ] **Step 2: Testes que falham** (`tests/test_notifications.py`)

```python
"""Testes da política de notificação por diff (spec 2026-07-09)."""
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    TimePeriod,
)
from notifications import (
    NotifyState,
    diff_new_windows,
    extract_open_windows,
    load_state,
    save_state,
)


def _day(availables=((time(6, 0), time(9, 30)),)):
    periods = tuple(
        ClassifiedPeriod(
            period=TimePeriod(start=s, end=e),
            status=PeriodStatus.AVAILABLE,
            reason="livre",
        )
        for s, e in availables
    ) + (
        ClassifiedPeriod(
            period=TimePeriod(start=time(10, 0), end=time(11, 0)),
            status=PeriodStatus.BUSY,
            reason="reservado",
        ),
    )
    return DayAvailability(
        day=date(2026, 7, 11),
        sunrise=time(6, 0),
        sunset=time(17, 15),
        window=TimePeriod(start=time(6, 0), end=time(17, 15)),
        resources=(
            ResourceAvailability(
                resource_name="PP-AYB", resource_model="C152", periods=periods
            ),
        ),
    )


class ExtractOpenWindowsTest(unittest.TestCase):
    def test_only_available_periods_become_keys(self):
        windows = extract_open_windows([_day()])
        self.assertEqual(
            windows, frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")})
        )


class DiffTest(unittest.TestCase):
    def test_new_windows_detected_sorted(self):
        old = frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")})
        new = old | {
            ("2026-07-12", "PT-JTK", "07:00", "09:00"),
            ("2026-07-11", "PP-AYB", "14:00", "16:00"),
        }
        self.assertEqual(
            diff_new_windows(old, new),
            (
                ("2026-07-11", "PP-AYB", "14:00", "16:00"),
                ("2026-07-12", "PT-JTK", "07:00", "09:00"),
            ),
        )

    def test_removed_windows_are_silent(self):
        old = frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")})
        self.assertEqual(diff_new_windows(old, frozenset()), ())


class StatePersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        state = NotifyState(
            windows=frozenset({("2026-07-11", "PP-AYB", "06:00", "09:30")}),
            last_scan_ok=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_state(path, state)
            self.assertEqual(load_state(path), state)

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_state(Path("nao_existe_state_9x8.json")))

    def test_corrupted_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{isso não é json", encoding="utf-8")
            self.assertIsNone(load_state(path))
            path.write_text('{"version": 99, "windows": []}', encoding="utf-8")
            self.assertIsNone(load_state(path))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_notifications -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'notifications'`

- [ ] **Step 4: Implementar** (`notifications.py`)

```python
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
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_notifications -v`
Expected: PASS (6 testes)

- [ ] **Step 6: Commit**

```bash
git add notifications.py tests/test_notifications.py .gitignore
git commit -m "feat(aeroes_monitor): diff-based notification policy with state.json"
```

---

### Task 4: `report.py` — mensagem de aberturas novas

**Files:**
- Modify: `report.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: `WindowKey`-shaped tuples `(dia ISO, recurso, "HH:MM", "HH:MM")` (strings; não importa `notifications` para manter `report.py` importando só `models`).
- Produces: `build_openings_message(new_windows: Sequence[tuple[str, str, str, str]]) -> str`.

- [ ] **Step 1: Testes que falham** (acrescentar em `tests/test_report.py`)

```python
from report import build_openings_message


class BuildOpeningsMessageTest(unittest.TestCase):
    def test_formats_each_window_with_weekday(self):
        text = build_openings_message(
            [
                ("2026-07-11", "PP-AYB", "06:17", "09:30"),
                ("2026-07-12", "Stand By", "07:00", "12:00"),
            ]
        )
        self.assertIn("🔔 **Abriu horário!**", text)
        self.assertIn("🟢 Sáb 11/07/2026: PP-AYB 06:17–09:30", text)
        self.assertIn("🟢 Dom 12/07/2026: Stand By 07:00–12:00", text)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_report -v`
Expected: FAIL — `ImportError: cannot import name 'build_openings_message'`

- [ ] **Step 3: Implementar** (acrescentar em `report.py`; `date.fromisoformat` já coberto pelo import existente de `date`)

```python
def build_openings_message(
    new_windows: Sequence[tuple[str, str, str, str]]
) -> str:
    """Aviso enxuto de janelas 🟢 que não existiam na varredura anterior."""
    lines = ["🔔 **Abriu horário!**"]
    for day_iso, resource, start, end in new_windows:
        lines.append(
            f"🟢 {_fmt_date(date.fromisoformat(day_iso))}: {resource} {start}–{end}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_report -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add report.py tests/test_report.py
git commit -m "feat(aeroes_monitor): openings message for diff notifications"
```

---

### Task 5: `scheduler.py` — aquisição via `allSchedules` (reescrita)

**Files:**
- Rewrite: `scheduler.py`
- Rewrite: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `saga_data.build_day_schedules/parse_sun_xml/utc_time_to_local`, `login.is_login_page/login`, `models.ScanError/ScanResult`.
- Produces: `ScheduleScanner(driver, config).scan() -> ScanResult` (mesma assinatura usada por `main.py`); constante `SUN_ENDPOINT = "/aisweb/sun/SBVT"`. Erro fatal = `ValueError` propagada (main salva artefatos). Sol indisponível = `ScanResult(days=(), errors=(ScanError(...),))` — recuperável.

- [ ] **Step 1: Reescrever `tests/test_scheduler.py`**

```python
"""Testes da aquisição via allSchedules com driver fake (sem browser)."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

from models import ScanResult
from scheduler import ScheduleScanner

SELECTORS = {
    "login_form": ("form.login",),
    "logged_in_marker": (".user-menu",),
    "login_username": ("#user",),
    "login_password": ("#pass",),
    "login_submit": ("#submit",),
}

SUN_XML = (
    "<aisweb><day><sunrise>09:17</sunrise><sunset>20:15</sunset></day></aisweb>"
)

RAW = [
    {
        "start_at_raw": "2026-07-09 07:00:00",
        "end_at_raw": "2026-07-09 08:00:00",
        "status": "CONFIRMED",
        "aircraft": {"registration": "PP-AYB"},
        "student": {"nickname": "Ana"},
    }
]


def _config(max_days=2, schedule_url="https://saga.example/schedules/personal"):
    return SimpleNamespace(
        monitor=SimpleNamespace(max_days=max_days),
        selenium=SimpleNamespace(
            base_url="https://saga.example/login",
            schedule_url=schedule_url,
            element_timeout_seconds=1,
        ),
        selectors=SELECTORS,
        aircraft={"PP-AYB": "Cessna 152"},
        credentials=SimpleNamespace(username="u", password="p"),
    )


class FakeDriver:
    """Driver mínimo: get() registra URLs; scripts respondem por roteiro."""

    def __init__(self, all_schedules=RAW, sun_response=SUN_XML, has_data=True):
        self.urls: list[str] = []
        self.all_schedules = all_schedules
        self.sun_response = sun_response
        self.has_data = has_data

    def get(self, url):
        self.urls.append(url)

    def execute_script(self, script, *args):
        if "typeof allSchedules" in script:
            return self.has_data
        if "return allSchedules" in script:
            return self.all_schedules
        raise AssertionError(f"script inesperado: {script}")

    def execute_async_script(self, script, *args):
        if self.sun_response is None:
            return {"status": -1, "body": "falha de rede"}
        return {"status": 200, "body": self.sun_response}

    def set_script_timeout(self, seconds):
        pass


def _scan(driver, config=None):
    scanner = ScheduleScanner(driver, config or _config())
    with mock.patch("scheduler.is_login_page", return_value=False):
        return scanner.scan()


class ScanTest(unittest.TestCase):
    def test_happy_path_builds_days_from_all_schedules(self):
        driver = FakeDriver()
        result = _scan(driver)
        self.assertIsInstance(result, ScanResult)
        self.assertEqual(len(result.days), 2)
        self.assertEqual(result.days[0].day, date.today())
        ayb = next(r for r in result.days[0].resources if r.name == "PP-AYB")
        # 07:00 local vindo de start_at_raw; sol 09:17Z -> 06:17 local.
        self.assertEqual(result.days[0].sunrise.strftime("%H:%M"), "06:17")
        self.assertEqual(driver.urls, ["https://saga.example/schedules/personal"])

    def test_falls_back_to_base_url_without_schedule_url(self):
        driver = FakeDriver()
        _scan(driver, _config(schedule_url=""))
        self.assertEqual(driver.urls, ["https://saga.example/login"])

    def test_missing_all_schedules_is_fatal(self):
        driver = FakeDriver(has_data=False)
        with self.assertRaises(Exception) as ctx:
            _scan(driver)
        self.assertIn("allSchedules", str(ctx.exception))

    def test_non_list_all_schedules_is_fatal(self):
        driver = FakeDriver(all_schedules={"nada": 1})
        with self.assertRaises(ValueError):
            _scan(driver)

    def test_sun_failure_is_recoverable_error(self):
        driver = FakeDriver(sun_response=None)
        result = _scan(driver)
        self.assertEqual(result.days, ())
        self.assertEqual(len(result.errors), 1)
        self.assertIn("sol", result.errors[0].message.lower())

    def test_relogin_when_session_expired(self):
        driver = FakeDriver()
        scanner = ScheduleScanner(driver, _config())
        with mock.patch("scheduler.is_login_page", side_effect=[True, False]), \
             mock.patch("scheduler.login") as do_login:
            scanner.scan()
        do_login.assert_called_once()
        # get() da página da escala ocorre de novo após o relogin.
        self.assertEqual(len(driver.urls), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_scheduler -v`
Expected: FAIL (API antiga não tem esse comportamento)

- [ ] **Step 3: Reescrever `scheduler.py`**

```python
"""Aquisição da escala via variável JS `allSchedules` (ADR-0010).

A página /schedules/personal embute a janela inteira (~30 dias) em uma
variável JavaScript; uma leitura cobre a varredura toda. O sol vem do
endpoint /aisweb/sun/SBVT (UTC — ADR-0008) na MESMA sessão autenticada.
Read-only: apenas GET e leitura de variável (ADR-0001).
"""
from __future__ import annotations

import logging
from datetime import date

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from login import is_login_page, login
from models import ScanError, ScanResult
from saga_data import build_day_schedules, parse_sun_xml, utc_time_to_local

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
            date.today(),
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
            today = date.today()
            return (
                utc_time_to_local(parsed[0], today),
                utc_time_to_local(parsed[1], today),
            )
        except Exception:
            logger.exception("Falha ao consultar o sol")
            return None
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_scheduler -v`
Expected: PASS (6 testes). Rodar também a suíte inteira: `.venv\Scripts\python -m unittest -v` — `tests.test_aircraft` ainda passa (módulo ainda existe; remoção na Task 7).

- [ ] **Step 5: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(aeroes_monitor): acquire schedules from allSchedules JS variable"
```

---

### Task 6: `main.py` + `discord.py` — orquestrar política de notificação

**Files:**
- Modify: `main.py`
- Modify: `discord.py` (remover `send_scan_started`)
- Modify: `tests/test_main.py`
- Modify: `tests/test_discord.py:88-93` (teste `test_convenience_methods`)

**Interfaces:**
- Consumes: `notifications.*` (Task 3), `report.build_openings_message` (Task 4), `ScheduleScanner` (Task 5).
- Produces: `run_scan(config: AppConfig, state_path: Path) -> bool`; `main()` deriva `state_path = Path(args.config).resolve().parent / "state.json"`.

Política (spec, seção "Política de notificação"):
- `previous is None` (sem state) ⇒ baseline: `send_summary` + `send_report`; salvar estado ok.
- Com state: se `previous.last_scan_ok` é False ⇒ `send_message("✅ Varredura voltou a funcionar.")`. Depois, `diff_new_windows`; se houver novas ⇒ `send_message(build_openings_message(novas))`. Sem novas ⇒ silêncio. Salvar estado ok com janelas atuais.
- Varredura degradada (`not result.days and result.errors`) conta como falha para o estado: preserva janelas anteriores, `last_scan_ok=False`, notifica `send_error` só na transição ok→falha.
- Exceção fatal: idem degradada (+ artefatos de debug, como hoje). Se `previous is None`, notifica o erro mas NÃO cria state (próximo sucesso ainda é baseline).

- [ ] **Step 1: Reescrever a classe `RunScanTest` em `tests/test_main.py`**

Substituir o arquivo inteiro por:

```python
"""Testes da orquestração (run_scan) e CLI com dependências mockadas."""
import tempfile
import unittest
from datetime import date, time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from main import main, parse_args, run_scan
from models import DaySchedule, ResourceSchedule, ScanResult, TimePeriod
from notifications import NotifyState, load_state, save_state


def _config():
    return SimpleNamespace(
        credentials=SimpleNamespace(username="u", password="p"),
        discord=SimpleNamespace(webhook_url="https://discord.example/webhook"),
        monitor=SimpleNamespace(
            max_days=1,
            check_interval_seconds=900,
            turnaround_minutes=30,
            min_flight_minutes=60,
            max_flight_minutes=120,
        ),
        selenium=SimpleNamespace(
            base_url="https://saga.example.com",
            schedule_url="https://saga.example.com/schedules/personal",
            headless=True,
            page_load_timeout_seconds=5,
            element_timeout_seconds=5,
            debug_dir="debug",
        ),
        selectors={},
        aircraft={"PT-ABC": "C-152"},
        logging=SimpleNamespace(level="INFO", file=""),
    )


def _scan_result(busy=()):
    """Um sábado com janela ampla: sem ocupação ⇒ 1 janela 🟢 o dia todo."""
    return ScanResult(
        days=(
            DaySchedule(
                day=date(2026, 7, 11),  # sábado
                sunrise=time(6, 0),
                sunset=time(17, 0),
                resources=(
                    ResourceSchedule(
                        name="PT-ABC", model="C-152", busy_periods=tuple(busy)
                    ),
                ),
            ),
        ),
    )


class ParseArgsTest(unittest.TestCase):
    def test_defaults(self):
        args = parse_args([])
        self.assertFalse(args.once)
        self.assertEqual(args.config, "config.ini")

    def test_once_and_custom_config(self):
        args = parse_args(["--once", "--config", "outro.ini"])
        self.assertTrue(args.once)
        self.assertEqual(args.config, "outro.ini")


@mock.patch("main.ScheduleScanner")
@mock.patch("main.login")
@mock.patch("main.create_driver")
@mock.patch("main.DiscordNotifier")
class RunScanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_path = Path(self._tmp.name) / "state.json"

    def test_first_run_sends_baseline_and_saves_state(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_summary.assert_called_once()
        notifier.send_report.assert_called_once()
        notifier.send_message.assert_not_called()
        state = load_state(self.state_path)
        self.assertTrue(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)

    def test_no_changes_is_silent(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline
        notifier.reset_mock()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_summary.assert_not_called()
        notifier.send_report.assert_not_called()
        notifier.send_message.assert_not_called()
        notifier.send_error.assert_not_called()

    def test_new_window_notifies_openings_only(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        # Baseline com o dia inteiro ocupado ⇒ nenhuma janela.
        scanner_cls.return_value.scan.return_value = _scan_result(
            busy=(TimePeriod(start=time(6, 0), end=time(17, 0)),)
        )
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        # Cancelaram tudo ⇒ abre janela nova.
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_message.assert_called_once()
        self.assertIn("Abriu horário", notifier.send_message.call_args.args[0])
        notifier.send_summary.assert_not_called()
        notifier.send_report.assert_not_called()

    def test_error_notifies_only_on_transition(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline ok
        notifier.reset_mock()
        scanner_cls.return_value.scan.side_effect = RuntimeError("SAGA fora do ar")
        with mock.patch("main.save_debug_artifacts"):
            self.assertFalse(run_scan(_config(), self.state_path))
            notifier.send_error.assert_called_once()  # transição ok→falha
            notifier.reset_mock()
            self.assertFalse(run_scan(_config(), self.state_path))
            notifier.send_error.assert_not_called()  # falha repetida: silêncio
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # janelas preservadas

    def test_recovery_notifies_and_diffs_against_preserved_windows(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        save_state(
            self.state_path,
            NotifyState(
                windows=frozenset({("2026-07-11", "PT-ABC", "06:00", "17:00")}),
                last_scan_ok=False,
            ),
        )
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        sent = [c.args[0] for c in notifier.send_message.call_args_list]
        self.assertTrue(any("voltou a funcionar" in m for m in sent))
        # Janela é a mesma do estado preservado ⇒ nenhum "Abriu horário".
        self.assertFalse(any("Abriu horário" in m for m in sent))

    def test_degraded_scan_counts_as_failure(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        from models import ScanError

        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        scanner_cls.return_value.scan.return_value = ScanResult(
            days=(), errors=(ScanError(day_index=0, day_label="sol", message="sem sol"),)
        )
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # preservadas

    def test_failure_without_state_notifies_but_keeps_baseline_pending(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        notifier = notifier_cls.return_value
        scanner_cls.return_value.scan.side_effect = RuntimeError("boom")
        with mock.patch("main.save_debug_artifacts"):
            self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        self.assertIsNone(load_state(self.state_path))  # baseline continua pendente

    def test_driver_quit_failure_does_not_break_result(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        create_driver.return_value.quit.side_effect = RuntimeError("já fechado")
        scanner_cls.return_value.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))


class MainExitCodesTest(unittest.TestCase):
    def test_missing_config_returns_2(self):
        self.assertEqual(main(["--once", "--config", "nao_existe_123.ini"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_main -v`
Expected: FAIL — `run_scan()` não aceita `state_path`.

- [ ] **Step 3: Reescrever `run_scan`/`main` em `main.py`**

Substituir `run_scan` e `main` (imports novos: `from pathlib import Path`, `from notifications import NotifyState, diff_new_windows, extract_open_windows, load_state, save_state`, `from report import build_openings_message, build_report, build_summary`; remover nada mais):

```python
def _notify_failure(notifier, previous, message: str) -> None:
    """Erro só na transição ok→falha (spec: sem spam de falha repetida)."""
    if previous is None or previous.last_scan_ok:
        notifier.send_error(message)
    else:
        logger.info("Falha repetida; Discord não notificado")


def _save_failure_state(state_path, previous) -> None:
    """Preserva janelas conhecidas; sem state prévio, baseline fica pendente."""
    if previous is not None:
        save_state(state_path, NotifyState(windows=previous.windows, last_scan_ok=False))


def run_scan(config: AppConfig, state_path: Path) -> bool:
    """Uma varredura completa. Nunca propaga exceção (o loop sobrevive)."""
    notifier = DiscordNotifier(config.discord.webhook_url)
    previous = load_state(state_path)
    driver = None
    try:
        driver = create_driver(config.selenium)
        login(driver, config)
        result = ScheduleScanner(driver, config).scan()
        if not result.days and result.errors:
            message = "; ".join(e.message for e in result.errors)
            logger.error("Varredura degradada: %s", message)
            _notify_failure(notifier, previous, message)
            _save_failure_state(state_path, previous)
            return False
        rules = AvailabilityRules(
            turnaround_minutes=config.monitor.turnaround_minutes,
            min_flight_minutes=config.monitor.min_flight_minutes,
            max_flight_minutes=config.monitor.max_flight_minutes,
        )
        availabilities = [enrich_day_schedule(day, rules) for day in result.days]
        windows = extract_open_windows(availabilities)
        if previous is None:
            notifier.send_summary(build_summary(availabilities, result.errors))
            notifier.send_report(build_report(availabilities, result.errors))
        else:
            if not previous.last_scan_ok:
                notifier.send_message("✅ Varredura voltou a funcionar.")
            new_windows = diff_new_windows(previous.windows, windows)
            if new_windows:
                notifier.send_message(build_openings_message(new_windows))
        save_state(state_path, NotifyState(windows=windows, last_scan_ok=True))
        logger.info(
            "Varredura concluída: %d dia(s), %d erro(s), %d janela(s) 🟢",
            len(result.days),
            len(result.errors),
            len(windows),
        )
        return True
    except Exception as exc:
        logger.exception("Falha fatal na varredura")
        if driver is not None:
            save_debug_artifacts(driver, config.selenium.debug_dir, tag="fatal")
        _notify_failure(notifier, previous, str(exc))
        _save_failure_state(state_path, previous)
        return False
    finally:
        if driver is not None:
            _quit_quietly(driver)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2
    setup_logging(config.logging)
    logger.info("Configuração carregada: %s", config_to_safe_dict(config))
    state_path = Path(args.config).resolve().parent / "state.json"
    if args.once:
        return 0 if run_scan(config, state_path) else 1
    logger.info(
        "Modo contínuo: varredura a cada %d s (Ctrl+C para encerrar)",
        config.monitor.check_interval_seconds,
    )
    try:
        while True:
            run_scan(config, state_path)
            logger.info(
                "Próxima varredura em %d s", config.monitor.check_interval_seconds
            )
            time.sleep(config.monitor.check_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuário")
        return 0
```

- [ ] **Step 4: Remover `send_scan_started` de `discord.py`** (deletar o método inteiro, linhas 63-64) e em `tests/test_discord.py` remover a linha `notifier.send_scan_started()` e ajustar a contagem de posts esperada do teste `test_convenience_methods` (3 chamadas: summary, report, error → verificar o assert existente e reduzir em 1).

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_main tests.test_discord -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add main.py discord.py tests/test_main.py tests/test_discord.py
git commit -m "feat(aeroes_monitor): wire diff notification policy into scan loop"
```

---

### Task 7: Aposentar `aircraft.py`, podar `utils.py`/`config.py`, atualizar `config.ini.example`

**Files:**
- Delete: `aircraft.py`, `tests/test_aircraft.py`
- Modify: `utils.py`, `tests/test_utils.py`
- Modify: `config.py` (DEFAULT_SELECTORS), `tests/test_config.py` (só se referenciar chave removida — `login_password` continua existindo, o assert de igualdade com `DEFAULT_SELECTORS` se ajusta sozinho)
- Modify: `config.ini.example`

- [ ] **Step 1: Deletar módulo aposentado**

```bash
git rm aircraft.py tests/test_aircraft.py
```

- [ ] **Step 2: Podar `utils.py`** — remover `extract_period`, `extract_sunrise`, `extract_sunset`, `find_times`, `parse_day_date`, `_extract_time_near_keyword`, `_strip_accents`, `_PERIOD_RE`, `_DATE_RE`, `_SUNRISE_KEYWORDS`, `_SUNSET_KEYWORDS` e os imports órfãos (`unicodedata`, `date`, `TimePeriod`). Ficam: `_TIME_RE`, `_to_time`, `parse_time`, `normalize_registration`.

- [ ] **Step 3: Podar `tests/test_utils.py`** — remover classes `FindTimesTest`, `ExtractPeriodTest`, `SunTimesTest`, `ParseDayDateTest` e os imports correspondentes. Ficam `ParseTimeTest` e `NormalizeRegistrationTest`.

- [ ] **Step 4: Enxugar `DEFAULT_SELECTORS` em `config.py`** — manter apenas as 5 chaves de login/sessão, com `logged_in_marker` calibrado (visíveis primeiro):

```python
DEFAULT_SELECTORS: dict[str, tuple[str, ...]] = {
    "login_username": (
        'input[name="email"]',
        'input[type="email"]',
        'input[name="username"]',
        "#email",
    ),
    "login_password": ('input[name="password"]', 'input[type="password"]', "#password"),
    "login_submit": ('button[type="submit"]', 'input[type="submit"]', ".btn-login"),
    "login_form": ("form.login", "form#login", 'input[type="password"]'),
    # Precisa estar VISÍVEL pós-login (o a[href*="logout"] fica oculto no
    # dropdown do perfil do SAGA) — calibrado em 2026-07-09.
    "logged_in_marker": (
        "#navbarDropdownProfile",
        "#menuSearch",
        'a.nav-link[href="/dashboard"]',
        ".user-menu",
    ),
}
```

- [ ] **Step 5: Atualizar `config.ini.example`** — em `[selenium]`, trocar o comentário/valor de `schedule_url` para:

```ini
; URL da página da escala (menu Escala → Meus Voos). É dela que o monitor
; lê a variável allSchedules (ADR-0010).
schedule_url = https://aeroes.saga.aero/schedules/personal
```

Em `[monitor]`, exemplo `check_interval_seconds = 900`. No bloco comentado `[selectors]`, deixar somente as 5 chaves de login/sessão (com os novos defaults do Step 4 como exemplo) e remover as chaves de escala.

- [ ] **Step 6: Suíte inteira verde**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS, zero referências a módulos removidos (se `ImportError`, procurar import órfão).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(aeroes_monitor): retire DOM scraping path and slim selectors"
```

---

### Task 8: Documentação — ADR-0010, emendas 0003/0008, README

**Files:**
- Create: `docs/adr/0010-allschedules-js-variable.md`
- Modify: `docs/adr/README.md` (linha nova na tabela: `| [0010](0010-allschedules-js-variable.md) | Agendamentos lidos da variável JS allSchedules |`)
- Modify: `docs/adr/0003-configurable-css-selectors.md`, `docs/adr/0008-sunrise-sunset-from-saga-page.md` (seção `## Emenda (2026-07-09)` em cada)
- Modify: `README.md`

- [ ] **Step 1: Escrever ADR-0010** (seguir o formato dos ADRs existentes — ler `docs/adr/0008-*.md` antes para copiar o template). Conteúdo essencial: contexto (página embute `allSchedules` com a janela de 30 dias; eventos são divs sem classe; não há botão próximo-dia), decisão (ler a variável via `execute_script`; horários locais de `*_raw`; descartar CANCELED; read-only preservado), consequências (parsing DOM aposentado; dependência do contrato JS da página — se o SAGA remover a variável, falha fatal com artefatos de debug).

- [ ] **Step 2: Emendas.** ADR-0003: seletores agora cobrem apenas login/sessão; a escala não é raspada do DOM (ver ADR-0010). ADR-0008: o endpoint `/aisweb/sun/SBVT` só serve o dia atual e em UTC; o valor de hoje (convertido para hora local) aplica-se à janela inteira, rotulado aproximado (desvio ≤ ~7 min no dia 30); sol indisponível ⇒ varredura degradada sem janelas.

- [ ] **Step 3: README.** Atualizar: seção "Uso" (mencionar `state.json` e a política "só aberturas novas"; baseline na primeira execução), "Calibração de seletores" (agora só login/sessão; escala vem de `allSchedules` — apontar ADR-0010), "Solução de problemas" (novo item: `allSchedules não encontrado` ⇒ conferir `schedule_url`; item do sol atualizado), "Arquitetura" (tabela: remover `aircraft.py`; adicionar `saga_data.py` e `notifications.py`; descrição nova de `scheduler.py`), "Limitações conhecidas" (trocar "sem histórico entre execuções" por nota sobre `state.json`; acrescentar "sol dos dias futuros é aproximação do valor de hoje").

- [ ] **Step 4: Commit**

```bash
git add docs/adr README.md
git commit -m "docs(aeroes_monitor): ADR-0010 allSchedules source and policy amendments"
```

---

### Task 9: Validação ponta a ponta (ambiente real)

**Files:**
- Modify: `config.ini` (LOCAL, não versionado): `schedule_url = https://aeroes.saga.aero/schedules/personal`

- [ ] **Step 1: Suíte completa**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS, 0 falhas.

- [ ] **Step 2: Preencher `schedule_url` no `config.ini` local** (valor acima).

- [ ] **Step 3: Baseline real** — apagar `state.json` se existir e rodar:

Run: `.venv\Scripts\python main.py --once`
Expected: exit code 0; log `allSchedules lido: N agendamento(s)`; Discord recebe resumo + relatório completo dos 30 dias (PP-AYB, PT-JTK, Stand By) com sol ~06:17/17:15 local; `state.json` criado.

- [ ] **Step 4: Diff real (silêncio)** — rodar de novo imediatamente:

Run: `.venv\Scripts\python main.py --once`
Expected: exit code 0; NENHUMA mensagem nova no Discord (sem mudanças em 15 min); `state.json` atualizado.

- [ ] **Step 5: Confirmar com o usuário** que as mensagens chegaram como esperado no canal, e commit final se algo do ambiente precisou de ajuste documentável.

---

## Self-Review (executado na escrita)

- **Cobertura da spec:** aquisição (T5), construção pura (T1-T2), sol UTC→local (T1), política de notificação + state (T3, T6), mensagem de aberturas (T4), truncamento de janela (T2), degradação sem sol (T5, T6), aposentadoria do DOM (T7), config example + marcador visível (T7), ADRs/README (T8), critérios de sucesso (T9). Sem lacunas.
- **Placeholders:** nenhum TBD; todos os passos de código têm código.
- **Consistência de tipos:** `ScanResult/ScanError/DaySchedule` reusados como definidos em `models.py`; `run_scan(config, state_path)` casa entre T6 (main) e testes; `WindowKey` (T3) é o formato consumido por `build_openings_message` (T4) e por `extract_open_windows`→`save_state` (T6); `ScheduleScanner.scan() -> ScanResult` preserva o contrato usado em `main.py`.
