# Aeroclube Schedule Monitor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o monitor read-only da escala de voo do SAGA que calcula disponibilidade e notifica via Discord, conforme `docs/superpowers/specs/2026-07-09-aeroes-monitor-design.md`.

**Architecture:** Camada Selenium (browser/login/scheduler/aircraft) produz dataclasses de domínio; camada pura (models/availability/report/utils) calcula e formata sem browser (ADR-0004). `main.py` orquestra: login → varredura multi-dia → regras → relatório → Discord, em `--once` ou loop.

**Tech Stack:** Python 3.13+ (máquina tem 3.14.5), Selenium 4 (Chrome + Selenium Manager), requests, unittest (stdlib), configparser.

## Global Constraints

- **Cwd:** todos os comandos rodam de `C:\Users\pedro\OneDrive\Documentos\python_portfolio\aeroes_monitor` (raiz do projeto; o repo git é a pasta pai `python_portfolio`, branch `feature/aeroes-monitor`).
- **Interpretador:** venv do projeto — Git Bash: `./.venv/Scripts/python`; PowerShell: `.\.venv\Scripts\python`. Nunca instalar nada fora do venv.
- **Testes:** `unittest` puro (NUNCA pytest). Um módulo: `./.venv/Scripts/python -m unittest tests.test_X -v`. Suíte inteira: `./.venv/Scripts/python -m unittest -v` (descoberta a partir do cwd; `tests/` tem `__init__.py`).
- **Pureza (ADR-0004):** `models.py`, `utils.py`, `availability.py`, `report.py` não importam selenium, requests nem `config.py`. Só `browser.py`, `login.py`, `scheduler.py`, `aircraft.py` conhecem WebDriver.
- **Domínio imutável:** dataclasses `frozen=True`; coleções internas são tuplas.
- **Idioma:** strings de relatório/notificação/erros de config em pt-BR.
- **Read-only (ADR-0001):** nenhum código submete formulário do SAGA além do login; nenhuma escrita no sistema de origem.
- **Segredos:** JAMAIS criar/commitar `config.ini` real; só `config.ini.example` com placeholders. `password`/`webhook_url` nunca aparecem em log (usar `config_to_safe_dict`).
- **Commits:** rodar `git add` com caminhos explícitos (nunca `git add -A` — o repo pai tem arquivos soltos alheios ao projeto). Toda mensagem de commit termina com os trailers exatos:

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9
```

Forma exata (Git Bash), substituindo só a primeira mensagem:

```bash
git commit -m "feat: <resumo>" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

- Avisos `LF will be replaced by CRLF` do git são esperados no Windows e inofensivos — ignorar.
- Emojis nos testes/strings são intencionais; salvar todos os arquivos em UTF-8.

---

### Task 1: Scaffolding do projeto (venv, deps, gitignore, pacote de testes)

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`

**Interfaces:**
- Consumes: nada.
- Produces: venv `./.venv` com `selenium` e `requests` instalados; pacote `tests` importável; `.gitignore` protegendo `config.ini`.

- [ ] **Step 1: Criar `requirements.txt`**

```
selenium>=4.21
requests>=2.32
```

- [ ] **Step 2: Criar `.gitignore`**

```
# Segredos — NUNCA versionar (PRD §7)
config.ini

# Artefatos de execução
debug/
*.log

# Python
__pycache__/
*.pyc
.venv/
```

- [ ] **Step 3: Criar `tests/__init__.py`** (arquivo vazio — só marca o pacote)

- [ ] **Step 4: Criar venv e instalar dependências**

Run (Git Bash):
```bash
python -m venv .venv && ./.venv/Scripts/python -m pip install -r requirements.txt
```
Expected: termina com `Successfully installed ...` listando `selenium` e `requests` (mais transitivas). Pode demorar ~1–2 min.

- [ ] **Step 5: Sanity check das dependências**

Run: `./.venv/Scripts/python -c "import selenium, requests; print('deps ok', selenium.__version__)"`
Expected: `deps ok 4.x.y`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore tests/__init__.py
git commit -m "chore(aeroes_monitor): scaffold project (deps, gitignore, tests pkg)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---

### Task 2: `models.py` — dataclasses de domínio

**Files:**
- Create: `models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nada (stdlib apenas — ADR-0004).
- Produces (usado por TODAS as tasks seguintes):
  - `TimePeriod(start: time, end: time, label: str = "")` — `ValueError` se `start >= end`; método `duration_minutes() -> int`.
  - `ResourceSchedule(name: str, model: str = "", busy_periods: tuple[TimePeriod, ...] = ())`
  - `DaySchedule(day: date, sunrise: time, sunset: time, resources: tuple[ResourceSchedule, ...] = ())`
  - `PeriodStatus` (Enum): `AVAILABLE`, `BUSY`
  - `ClassifiedPeriod(period: TimePeriod, status: PeriodStatus, reason: str)`
  - `ResourceAvailability(resource_name: str, resource_model: str, periods: tuple[ClassifiedPeriod, ...] = ())`
  - `DayAvailability(day: date, sunrise: time, sunset: time, window: TimePeriod | None, resources: tuple[ResourceAvailability, ...] = ())`
  - `ScanError(day_index: int, day_label: str, message: str)`
  - `ScanResult(days: tuple[DaySchedule, ...] = (), errors: tuple[ScanError, ...] = ())`

- [ ] **Step 1: Escrever o teste que falha — `tests/test_models.py`**

```python
"""Testes das dataclasses de domínio."""
import dataclasses
import unittest
from datetime import date, time

from models import (
    ClassifiedPeriod,
    DayAvailability,
    DaySchedule,
    PeriodStatus,
    ResourceAvailability,
    ResourceSchedule,
    ScanError,
    ScanResult,
    TimePeriod,
)


class TimePeriodTest(unittest.TestCase):
    def test_duration_minutes(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 30))
        self.assertEqual(period.duration_minutes(), 90)

    def test_start_must_precede_end(self):
        with self.assertRaises(ValueError):
            TimePeriod(start=time(8, 0), end=time(8, 0))
        with self.assertRaises(ValueError):
            TimePeriod(start=time(9, 0), end=time(8, 0))

    def test_is_frozen(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 0))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            period.start = time(5, 0)

    def test_default_label_empty(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 0))
        self.assertEqual(period.label, "")


class ContainerModelsTest(unittest.TestCase):
    def test_resource_schedule_defaults(self):
        resource = ResourceSchedule(name="PT-ABC")
        self.assertEqual(resource.model, "")
        self.assertEqual(resource.busy_periods, ())

    def test_day_schedule_holds_resources(self):
        resource = ResourceSchedule(name="Stand By")
        day = DaySchedule(
            day=date(2026, 7, 13),
            sunrise=time(5, 45),
            sunset=time(17, 30),
            resources=(resource,),
        )
        self.assertEqual(day.resources[0].name, "Stand By")

    def test_period_status_members(self):
        self.assertIn(PeriodStatus.AVAILABLE, PeriodStatus)
        self.assertIn(PeriodStatus.BUSY, PeriodStatus)

    def test_availability_models(self):
        entry = ClassifiedPeriod(
            period=TimePeriod(start=time(6, 0), end=time(7, 0)),
            status=PeriodStatus.AVAILABLE,
            reason="livre",
        )
        resource = ResourceAvailability(
            resource_name="PT-ABC", resource_model="C-152", periods=(entry,)
        )
        day = DayAvailability(
            day=date(2026, 7, 13),
            sunrise=time(5, 45),
            sunset=time(17, 30),
            window=TimePeriod(start=time(5, 45), end=time(12, 0)),
            resources=(resource,),
        )
        self.assertIs(day.resources[0].periods[0].status, PeriodStatus.AVAILABLE)

    def test_scan_result_defaults(self):
        result = ScanResult()
        self.assertEqual(result.days, ())
        self.assertEqual(result.errors, ())
        error = ScanError(day_index=2, day_label="16/07/2026", message="sem sol")
        self.assertEqual(error.day_index, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_models -v`
Expected: `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: Implementar `models.py`**

```python
"""Dataclasses de domínio do monitor.

Camada 100% pura: sem dependências de projeto ou de terceiros (ADR-0004).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from enum import Enum


@dataclass(frozen=True)
class TimePeriod:
    """Intervalo de horário dentro de um único dia (não cruza meia-noite)."""

    start: time
    end: time
    label: str = ""

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(
                f"Período inválido: início {self.start} deve ser antes do fim {self.end}"
            )

    def duration_minutes(self) -> int:
        return (self.end.hour * 60 + self.end.minute) - (
            self.start.hour * 60 + self.start.minute
        )


@dataclass(frozen=True)
class ResourceSchedule:
    """Agenda ocupada de um recurso (aeronave ou Stand By) em um dia."""

    name: str
    model: str = ""
    busy_periods: tuple[TimePeriod, ...] = ()


@dataclass(frozen=True)
class DaySchedule:
    """Escala de um dia como lida da página do SAGA."""

    day: date
    sunrise: time
    sunset: time
    resources: tuple[ResourceSchedule, ...] = ()


class PeriodStatus(Enum):
    AVAILABLE = "available"
    BUSY = "busy"


@dataclass(frozen=True)
class ClassifiedPeriod:
    """Período do relatório: 🟢 (AVAILABLE) ou 🔴 (BUSY) com motivo legível."""

    period: TimePeriod
    status: PeriodStatus
    reason: str


@dataclass(frozen=True)
class ResourceAvailability:
    resource_name: str
    resource_model: str
    periods: tuple[ClassifiedPeriod, ...] = ()


@dataclass(frozen=True)
class DayAvailability:
    """Resultado das regras de disponibilidade para um dia.

    window=None significa dia sem janela operacional (ex.: nascer do sol
    após o horário-limite do dia da semana).
    """

    day: date
    sunrise: time
    sunset: time
    window: TimePeriod | None
    resources: tuple[ResourceAvailability, ...] = ()


@dataclass(frozen=True)
class ScanError:
    """Erro recuperável na leitura de um dia (PRD F10)."""

    day_index: int
    day_label: str
    message: str


@dataclass(frozen=True)
class ScanResult:
    days: tuple[DaySchedule, ...] = ()
    errors: tuple[ScanError, ...] = ()
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_models -v`
Expected: todos os testes `ok`, sumário `OK`.

- [ ] **Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat(aeroes_monitor): add domain dataclasses (models.py)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 3: `utils.py` — parsing puro de texto

**Files:**
- Create: `utils.py`
- Test: `tests/test_utils.py`

**Interfaces:**
- Consumes: `models.TimePeriod`.
- Produces (usado por aircraft/scheduler):
  - `parse_time(text: str) -> time | None`
  - `find_times(text: str) -> list[time]`
  - `extract_period(text: str) -> TimePeriod | None` (label = texto restante)
  - `extract_sunrise(text: str) -> time | None` / `extract_sunset(text: str) -> time | None` (busca por palavra-chave pt-BR, insensível a acentos/caixa)
  - `parse_day_date(text: str) -> date | None` (formato dd/mm/aaaa)
  - `normalize_registration(text: str) -> str` (só alfanuméricos, uppercase)

- [ ] **Step 1: Escrever o teste que falha — `tests/test_utils.py`**

```python
"""Testes do parsing puro de texto (utils.py)."""
import unittest
from datetime import date, time

from utils import (
    extract_period,
    extract_sunrise,
    extract_sunset,
    find_times,
    normalize_registration,
    parse_day_date,
    parse_time,
)


class ParseTimeTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_time("06:15"), time(6, 15))
        self.assertEqual(parse_time("6:15"), time(6, 15))
        self.assertEqual(parse_time("06h15"), time(6, 15))
        self.assertEqual(parse_time("Saída às 14:05 confirmada"), time(14, 5))

    def test_invalid(self):
        self.assertIsNone(parse_time("sem horário"))
        self.assertIsNone(parse_time("99:99"))
        self.assertIsNone(parse_time(""))


class FindTimesTest(unittest.TestCase):
    def test_finds_all_valid_times_in_order(self):
        text = "Nascer do sol: 05:45 · Pôr do sol: 17:30"
        self.assertEqual(find_times(text), [time(5, 45), time(17, 30)])

    def test_empty_when_no_times(self):
        self.assertEqual(find_times("nada aqui"), [])


class ExtractPeriodTest(unittest.TestCase):
    def test_hyphen_separator(self):
        period = extract_period("06:00 - 07:00 João Silva")
        self.assertEqual(period.start, time(6, 0))
        self.assertEqual(period.end, time(7, 0))
        self.assertEqual(period.label, "João Silva")

    def test_en_dash_separator(self):
        period = extract_period("06:00–07:00")
        self.assertEqual((period.start, period.end), (time(6, 0), time(7, 0)))
        self.assertEqual(period.label, "")

    def test_as_separator(self):
        period = extract_period("Reserva 06:00 às 07:30")
        self.assertEqual((period.start, period.end), (time(6, 0), time(7, 30)))
        self.assertEqual(period.label, "Reserva")

    def test_invalid_or_inverted(self):
        self.assertIsNone(extract_period("apenas texto"))
        self.assertIsNone(extract_period("08:00 - 07:00 invertido"))


class SunTimesTest(unittest.TestCase):
    def test_extract_sunrise_pt_br(self):
        self.assertEqual(extract_sunrise("Nascer do sol: 05:45"), time(5, 45))
        self.assertEqual(extract_sunrise("NASCER DO SOL 05h45"), time(5, 45))

    def test_extract_sunset_pt_br_with_accents(self):
        self.assertEqual(extract_sunset("Pôr do sol: 17:30"), time(17, 30))
        self.assertEqual(extract_sunset("por do sol 17:30"), time(17, 30))
        self.assertEqual(extract_sunset("Pôr-do-sol: 17:30"), time(17, 30))

    def test_combined_line_distinguishes_both(self):
        text = "Nascer do sol: 05:45 | Pôr do sol: 17:30"
        self.assertEqual(extract_sunrise(text), time(5, 45))
        self.assertEqual(extract_sunset(text), time(17, 30))

    def test_missing_returns_none(self):
        self.assertIsNone(extract_sunrise("Pôr do sol: 17:30"))
        self.assertIsNone(extract_sunset("Nascer do sol: 05:45"))


class ParseDayDateTest(unittest.TestCase):
    def test_plain_date(self):
        self.assertEqual(parse_day_date("14/07/2026"), date(2026, 7, 14))

    def test_date_with_weekday_prefix(self):
        self.assertEqual(
            parse_day_date("Segunda-feira, 14/07/2026"), date(2026, 7, 14)
        )

    def test_no_date_returns_none(self):
        self.assertIsNone(parse_day_date("Segunda-feira"))
        self.assertIsNone(parse_day_date("31/02/2026"))


class NormalizeRegistrationTest(unittest.TestCase):
    def test_equivalence(self):
        self.assertEqual(normalize_registration("pt-abc"), "PTABC")
        self.assertEqual(normalize_registration("PT ABC"), "PTABC")
        self.assertEqual(normalize_registration("PTABC"), "PTABC")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_utils -v`
Expected: `ModuleNotFoundError: No module named 'utils'`

- [ ] **Step 3: Implementar `utils.py`**

```python
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
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_utils -v`
Expected: todos `ok`, sumário `OK`.

Nota: se `test_extract_sunrise_pt_br` falhar porque "nascer do sol" não casou, verifique a ordem dos keywords — "nascer do sol" deve vir antes de "nascer" para o snippet começar após a frase completa (ambos funcionam, mas a frase longa é mais precisa).

- [ ] **Step 5: Rodar a suíte inteira**

Run: `./.venv/Scripts/python -m unittest -v`
Expected: testes de models + utils, sumário `OK`.

- [ ] **Step 6: Commit**

```bash
git add utils.py tests/test_utils.py
git commit -m "feat(aeroes_monitor): add pure text parsing helpers (utils.py)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 4: `availability.py` (parte 1) — primitivas das regras

**Files:**
- Create: `availability.py`
- Test: `tests/test_availability.py`

**Interfaces:**
- Consumes: `models.TimePeriod`.
- Produces (usado na Task 5 e pelo `main.py`):
  - `AvailabilityRules(turnaround_minutes: int = 30, min_flight_minutes: int = 60, max_flight_minutes: int = 120)` — dataclass frozen própria (o módulo NÃO importa `config.py`).
  - `operating_window(day: date, sunrise: time, sunset: time) -> TimePeriod | None` — seg–sex sol→min(09:30, pôr); sáb sol→pôr; dom sol→min(12:00, pôr); `None` se fim ≤ início (PRD §6).
  - `apply_turnaround_buffer(periods: Iterable[TimePeriod], buffer_minutes: int) -> tuple[TimePeriod, ...]` — expande ±buffer (clamp 00:00/23:59), ordena e mescla.
  - `subtract_periods(window: TimePeriod, busy: Iterable[TimePeriod]) -> tuple[TimePeriod, ...]` — vãos livres dentro da janela.
  - `filter_bookable_periods(free: Iterable[TimePeriod], min_minutes: int) -> tuple[tuple[TimePeriod, ...], tuple[TimePeriod, ...]]` — (reserváveis ≥ mín, curtos).

- [ ] **Step 1: Escrever o teste que falha — `tests/test_availability.py`**

```python
"""Testes das regras de disponibilidade (PRD §6, ADR-0004)."""
import unittest
from datetime import date, time

from availability import (
    AvailabilityRules,
    apply_turnaround_buffer,
    filter_bookable_periods,
    operating_window,
    subtract_periods,
)
from models import TimePeriod

# Datas fixas de referência (julho/2026): 13=segunda, 18=sábado, 19=domingo.
MONDAY = date(2026, 7, 13)
SATURDAY = date(2026, 7, 18)
SUNDAY = date(2026, 7, 19)
SUNRISE = time(5, 45)
SUNSET = time(17, 30)


class OperatingWindowTest(unittest.TestCase):
    def test_weekday_closes_at_0930(self):
        window = operating_window(MONDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (SUNRISE, time(9, 30)))

    def test_saturday_closes_at_sunset(self):
        window = operating_window(SATURDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (SUNRISE, SUNSET))

    def test_sunday_closes_at_noon(self):
        window = operating_window(SUNDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (SUNRISE, time(12, 0)))

    def test_weekday_sunset_before_0930_wins(self):
        window = operating_window(MONDAY, time(5, 0), time(9, 0))
        self.assertEqual(window.end, time(9, 0))

    def test_no_window_when_sunrise_after_close(self):
        self.assertIsNone(operating_window(MONDAY, time(10, 0), SUNSET))


class TurnaroundBufferTest(unittest.TestCase):
    def test_expands_both_sides(self):
        buffered = apply_turnaround_buffer(
            [TimePeriod(start=time(8, 0), end=time(9, 0))], 30
        )
        self.assertEqual(buffered, (TimePeriod(start=time(7, 30), end=time(9, 30)),))

    def test_merges_neighbors_joined_by_buffer(self):
        buffered = apply_turnaround_buffer(
            [
                TimePeriod(start=time(6, 0), end=time(7, 0)),
                TimePeriod(start=time(7, 30), end=time(8, 30)),
            ],
            30,
        )
        self.assertEqual(buffered, (TimePeriod(start=time(5, 30), end=time(9, 0)),))

    def test_merges_overlapping_input(self):
        buffered = apply_turnaround_buffer(
            [
                TimePeriod(start=time(6, 0), end=time(8, 0)),
                TimePeriod(start=time(7, 0), end=time(7, 30)),
            ],
            0,
        )
        self.assertEqual(buffered, (TimePeriod(start=time(6, 0), end=time(8, 0)),))

    def test_clamps_at_day_bounds(self):
        buffered = apply_turnaround_buffer(
            [TimePeriod(start=time(0, 10), end=time(23, 40))], 30
        )
        self.assertEqual(buffered, (TimePeriod(start=time(0, 0), end=time(23, 59)),))

    def test_empty_input(self):
        self.assertEqual(apply_turnaround_buffer([], 30), ())


class SubtractPeriodsTest(unittest.TestCase):
    WINDOW = TimePeriod(start=time(6, 0), end=time(12, 0))

    def test_no_busy_returns_whole_window(self):
        self.assertEqual(
            subtract_periods(self.WINDOW, []),
            (TimePeriod(start=time(6, 0), end=time(12, 0)),),
        )

    def test_busy_in_middle_splits_window(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(8, 0), end=time(9, 0))]
        )
        self.assertEqual(
            free,
            (
                TimePeriod(start=time(6, 0), end=time(8, 0)),
                TimePeriod(start=time(9, 0), end=time(12, 0)),
            ),
        )

    def test_busy_covering_window_leaves_nothing(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(5, 0), end=time(13, 0))]
        )
        self.assertEqual(free, ())

    def test_busy_outside_window_ignored(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(13, 0), end=time(14, 0))]
        )
        self.assertEqual(free, (TimePeriod(start=time(6, 0), end=time(12, 0)),))

    def test_busy_crossing_window_edge_clipped(self):
        free = subtract_periods(
            self.WINDOW, [TimePeriod(start=time(5, 0), end=time(7, 0))]
        )
        self.assertEqual(free, (TimePeriod(start=time(7, 0), end=time(12, 0)),))


class FilterBookableTest(unittest.TestCase):
    def test_partition_by_min_duration(self):
        long_period = TimePeriod(start=time(6, 0), end=time(8, 0))
        short_period = TimePeriod(start=time(9, 0), end=time(9, 20))
        bookable, too_short = filter_bookable_periods([long_period, short_period], 60)
        self.assertEqual(bookable, (long_period,))
        self.assertEqual(too_short, (short_period,))

    def test_exactly_min_is_bookable(self):
        period = TimePeriod(start=time(6, 0), end=time(7, 0))
        bookable, too_short = filter_bookable_periods([period], 60)
        self.assertEqual(bookable, (period,))
        self.assertEqual(too_short, ())


class RulesDefaultsTest(unittest.TestCase):
    def test_defaults(self):
        rules = AvailabilityRules()
        self.assertEqual(rules.turnaround_minutes, 30)
        self.assertEqual(rules.min_flight_minutes, 60)
        self.assertEqual(rules.max_flight_minutes, 120)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_availability -v`
Expected: `ModuleNotFoundError: No module named 'availability'`

- [ ] **Step 3: Implementar `availability.py`**

```python
"""Regras de disponibilidade. Puro: importa apenas models (ADR-0004).

Janelas por dia da semana (PRD §6): seg–sex nascer→09:30; sáb nascer→pôr;
dom nascer→12:00. Buffer de turnaround expande voos ocupados antes do
cálculo dos vãos livres; vão livre < duração mínima não é reservável.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Iterable

from models import (
    ClassifiedPeriod,
    DayAvailability,
    DaySchedule,
    PeriodStatus,
    ResourceAvailability,
    TimePeriod,
)

# weekday() → horário-limite fixo; None = usa o pôr do sol (sábado).
WEEKDAY_CLOSE_LIMITS: dict[int, time | None] = {
    0: time(9, 30),
    1: time(9, 30),
    2: time(9, 30),
    3: time(9, 30),
    4: time(9, 30),
    5: None,
    6: time(12, 0),
}

_DAY_START_MIN = 0
_DAY_END_MIN = 23 * 60 + 59


@dataclass(frozen=True)
class AvailabilityRules:
    turnaround_minutes: int = 30
    min_flight_minutes: int = 60
    max_flight_minutes: int = 120


def _to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _to_time(minutes: int) -> time:
    minutes = max(_DAY_START_MIN, min(minutes, _DAY_END_MIN))
    return time(minutes // 60, minutes % 60)


def operating_window(day: date, sunrise: time, sunset: time) -> TimePeriod | None:
    limit = WEEKDAY_CLOSE_LIMITS[day.weekday()]
    end = sunset if limit is None else min(limit, sunset)
    if sunrise >= end:
        return None
    return TimePeriod(start=sunrise, end=end)


def apply_turnaround_buffer(
    periods: Iterable[TimePeriod], buffer_minutes: int
) -> tuple[TimePeriod, ...]:
    expanded = sorted(
        (
            max(_DAY_START_MIN, _to_minutes(p.start) - buffer_minutes),
            min(_DAY_END_MIN, _to_minutes(p.end) + buffer_minutes),
        )
        for p in periods
    )
    if not expanded:
        return ()
    merged: list[list[int]] = [list(expanded[0])]
    for start, end in expanded[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple(TimePeriod(start=_to_time(s), end=_to_time(e)) for s, e in merged)


def subtract_periods(
    window: TimePeriod, busy: Iterable[TimePeriod]
) -> tuple[TimePeriod, ...]:
    free: list[TimePeriod] = []
    cursor = _to_minutes(window.start)
    window_end = _to_minutes(window.end)
    for period in sorted(busy, key=lambda p: (p.start, p.end)):
        start = max(_to_minutes(period.start), _to_minutes(window.start))
        end = min(_to_minutes(period.end), window_end)
        if end <= cursor:
            continue
        if start >= window_end:
            break
        if start > cursor:
            free.append(TimePeriod(start=_to_time(cursor), end=_to_time(start)))
        cursor = max(cursor, end)
    if cursor < window_end:
        free.append(TimePeriod(start=_to_time(cursor), end=_to_time(window_end)))
    return tuple(free)


def filter_bookable_periods(
    free: Iterable[TimePeriod], min_minutes: int
) -> tuple[tuple[TimePeriod, ...], tuple[TimePeriod, ...]]:
    free = tuple(free)
    bookable = tuple(p for p in free if p.duration_minutes() >= min_minutes)
    too_short = tuple(p for p in free if p.duration_minutes() < min_minutes)
    return bookable, too_short
```

(As funções `classify_day_periods` e `enrich_day_schedule` entram na Task 5 — os imports de `ClassifiedPeriod`/`DayAvailability`/`DaySchedule`/`PeriodStatus`/`ResourceAvailability` já ficam prontos.)

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_availability -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Commit**

```bash
git add availability.py tests/test_availability.py
git commit -m "feat(aeroes_monitor): add availability rule primitives" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---

### Task 5: `availability.py` (parte 2) — classificação e enriquecimento

**Files:**
- Modify: `availability.py` (acrescentar ao final)
- Test: `tests/test_availability.py` (acrescentar classes ao final, antes do `if __name__`)

**Interfaces:**
- Consumes: primitivas da Task 4; `models.DaySchedule/DayAvailability/ClassifiedPeriod/ResourceAvailability/PeriodStatus`.
- Produces (usado por report/main):
  - `classify_day_periods(window: TimePeriod, raw_busy: Iterable[TimePeriod], rules: AvailabilityRules) -> tuple[ClassifiedPeriod, ...]` — timeline ordenado: ocupados originais recortados à janela (🔴 "reservado"/"reservado (label)"), livres ≥ mín (🟢 "livre"), livres curtos (🔴 "vão curto (Xmin < Ymin)").
  - `enrich_day_schedule(day_schedule: DaySchedule, rules: AvailabilityRules) -> DayAvailability`.

- [ ] **Step 1: Acrescentar os testes (em `tests/test_availability.py`, antes do bloco `if __name__`)**

```python
from availability import classify_day_periods, enrich_day_schedule
from models import DaySchedule, PeriodStatus, ResourceSchedule


class ClassifyDayPeriodsTest(unittest.TestCase):
    WINDOW = TimePeriod(start=time(6, 0), end=time(9, 30))
    RULES = AvailabilityRules(
        turnaround_minutes=30, min_flight_minutes=60, max_flight_minutes=120
    )

    def test_empty_schedule_is_one_available_block(self):
        entries = classify_day_periods(self.WINDOW, [], self.RULES)
        self.assertEqual(len(entries), 1)
        self.assertIs(entries[0].status, PeriodStatus.AVAILABLE)
        self.assertEqual(entries[0].reason, "livre")
        self.assertEqual(
            (entries[0].period.start, entries[0].period.end), (time(6, 0), time(9, 30))
        )

    def test_busy_with_label_and_free_gap(self):
        # Voo 06:00–07:00: com buffer de 30min o vão livre começa 07:30.
        # 07:30–09:30 = 2h ≥ 1h → 🟢.
        entries = classify_day_periods(
            self.WINDOW,
            [TimePeriod(start=time(6, 0), end=time(7, 0), label="João")],
            self.RULES,
        )
        self.assertEqual(len(entries), 2)
        self.assertIs(entries[0].status, PeriodStatus.BUSY)
        self.assertEqual(entries[0].reason, "reservado (João)")
        self.assertEqual(
            (entries[0].period.start, entries[0].period.end), (time(6, 0), time(7, 0))
        )
        self.assertIs(entries[1].status, PeriodStatus.AVAILABLE)
        self.assertEqual(
            (entries[1].period.start, entries[1].period.end),
            (time(7, 30), time(9, 30)),
        )

    def test_short_gap_reported_busy(self):
        # Voos 06:00–07:00 e 08:30–09:30 bufferizados deixam 07:30–08:00
        # (30min < 60min) → 🔴 "vão curto".
        entries = classify_day_periods(
            self.WINDOW,
            [
                TimePeriod(start=time(6, 0), end=time(7, 0)),
                TimePeriod(start=time(8, 30), end=time(9, 30)),
            ],
            self.RULES,
        )
        reasons = [e.reason for e in entries]
        self.assertIn("vão curto (30min < 60min)", reasons)
        short = next(e for e in entries if "vão curto" in e.reason)
        self.assertIs(short.status, PeriodStatus.BUSY)
        self.assertEqual(
            (short.period.start, short.period.end), (time(7, 30), time(8, 0))
        )

    def test_busy_outside_window_dropped_from_timeline(self):
        entries = classify_day_periods(
            self.WINDOW,
            [TimePeriod(start=time(14, 0), end=time(15, 0))],
            self.RULES,
        )
        self.assertTrue(all(e.status is PeriodStatus.AVAILABLE for e in entries))

    def test_busy_crossing_window_edge_clipped(self):
        entries = classify_day_periods(
            self.WINDOW,
            [TimePeriod(start=time(5, 0), end=time(6, 30))],
            self.RULES,
        )
        busy = [e for e in entries if e.status is PeriodStatus.BUSY and e.reason.startswith("reservado")]
        self.assertEqual(
            (busy[0].period.start, busy[0].period.end), (time(6, 0), time(6, 30))
        )

    def test_timeline_sorted_by_start(self):
        entries = classify_day_periods(
            self.WINDOW,
            [
                TimePeriod(start=time(8, 0), end=time(9, 0)),
                TimePeriod(start=time(6, 0), end=time(6, 30)),
            ],
            self.RULES,
        )
        starts = [e.period.start for e in entries]
        self.assertEqual(starts, sorted(starts))


class EnrichDayScheduleTest(unittest.TestCase):
    RULES = AvailabilityRules()

    def test_enriches_all_resources_on_monday(self):
        day = DaySchedule(
            day=MONDAY,
            sunrise=SUNRISE,
            sunset=SUNSET,
            resources=(
                ResourceSchedule(name="PT-ABC", model="C-152"),
                ResourceSchedule(name="Stand By"),
            ),
        )
        enriched = enrich_day_schedule(day, self.RULES)
        self.assertEqual(enriched.day, MONDAY)
        self.assertEqual(
            (enriched.window.start, enriched.window.end), (SUNRISE, time(9, 30))
        )
        self.assertEqual(len(enriched.resources), 2)
        self.assertEqual(enriched.resources[0].resource_name, "PT-ABC")
        self.assertEqual(enriched.resources[0].resource_model, "C-152")
        self.assertIs(
            enriched.resources[0].periods[0].status, PeriodStatus.AVAILABLE
        )

    def test_day_without_window(self):
        day = DaySchedule(
            day=MONDAY,
            sunrise=time(10, 0),
            sunset=SUNSET,
            resources=(ResourceSchedule(name="PT-ABC", model="C-152"),),
        )
        enriched = enrich_day_schedule(day, self.RULES)
        self.assertIsNone(enriched.window)
        self.assertEqual(enriched.resources[0].periods, ())
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_availability -v`
Expected: `ImportError: cannot import name 'classify_day_periods'`

- [ ] **Step 3: Acrescentar ao final de `availability.py`**

```python
def _clip_to_window(period: TimePeriod, window: TimePeriod) -> TimePeriod | None:
    start = max(period.start, window.start)
    end = min(period.end, window.end)
    if start >= end:
        return None
    return TimePeriod(start=start, end=end, label=period.label)


def classify_day_periods(
    window: TimePeriod, raw_busy: Iterable[TimePeriod], rules: AvailabilityRules
) -> tuple[ClassifiedPeriod, ...]:
    """Timeline do relatório: ocupados com horários originais (recortados à
    janela); vãos livres calculados sobre os ocupados bufferizados (spec §1).
    """
    raw_busy = tuple(raw_busy)
    entries: list[ClassifiedPeriod] = []
    for period in raw_busy:
        clipped = _clip_to_window(period, window)
        if clipped is None:
            continue
        reason = f"reservado ({clipped.label})" if clipped.label else "reservado"
        entries.append(
            ClassifiedPeriod(period=clipped, status=PeriodStatus.BUSY, reason=reason)
        )
    buffered = apply_turnaround_buffer(raw_busy, rules.turnaround_minutes)
    free = subtract_periods(window, buffered)
    bookable, too_short = filter_bookable_periods(free, rules.min_flight_minutes)
    for period in bookable:
        entries.append(
            ClassifiedPeriod(period=period, status=PeriodStatus.AVAILABLE, reason="livre")
        )
    for period in too_short:
        entries.append(
            ClassifiedPeriod(
                period=period,
                status=PeriodStatus.BUSY,
                reason=(
                    f"vão curto ({period.duration_minutes()}min "
                    f"< {rules.min_flight_minutes}min)"
                ),
            )
        )
    entries.sort(key=lambda e: (e.period.start, e.period.end))
    return tuple(entries)


def enrich_day_schedule(
    day_schedule: DaySchedule, rules: AvailabilityRules
) -> DayAvailability:
    window = operating_window(
        day_schedule.day, day_schedule.sunrise, day_schedule.sunset
    )
    resources: list[ResourceAvailability] = []
    for resource in day_schedule.resources:
        if window is None:
            periods: tuple[ClassifiedPeriod, ...] = ()
        else:
            periods = classify_day_periods(window, resource.busy_periods, rules)
        resources.append(
            ResourceAvailability(
                resource_name=resource.name,
                resource_model=resource.model,
                periods=periods,
            )
        )
    return DayAvailability(
        day=day_schedule.day,
        sunrise=day_schedule.sunrise,
        sunset=day_schedule.sunset,
        window=window,
        resources=tuple(resources),
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_availability -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Suíte inteira**

Run: `./.venv/Scripts/python -m unittest -v`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add availability.py tests/test_availability.py
git commit -m "feat(aeroes_monitor): classify periods and enrich day schedules" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 6: `report.py` — formatação do relatório

**Files:**
- Create: `report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `models.DayAvailability/PeriodStatus/ScanError`.
- Produces (usado pelo `main.py`):
  - `build_summary(days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()) -> str`
  - `build_report(days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()) -> str`
- Formato dos itens do timeline: `🟢|🔴 HH:MM–HH:MM — <reason> (<duração>)`; cabeçalho do dia: `📅 **Seg 13/07/2026** — 🌅 05:45 · 🌇 17:30 · janela 05:45–09:30`.

- [ ] **Step 1: Escrever o teste que falha — `tests/test_report.py`**

```python
"""Testes da formatação do relatório (PRD F8)."""
import unittest
from datetime import date, time

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    ScanError,
    TimePeriod,
)
from report import build_report, build_summary

MONDAY = date(2026, 7, 13)


def _sample_day() -> DayAvailability:
    return DayAvailability(
        day=MONDAY,
        sunrise=time(5, 45),
        sunset=time(17, 30),
        window=TimePeriod(start=time(5, 45), end=time(9, 30)),
        resources=(
            ResourceAvailability(
                resource_name="PT-ABC",
                resource_model="C-152",
                periods=(
                    ClassifiedPeriod(
                        period=TimePeriod(start=time(5, 45), end=time(7, 0)),
                        status=PeriodStatus.AVAILABLE,
                        reason="livre",
                    ),
                    ClassifiedPeriod(
                        period=TimePeriod(start=time(7, 0), end=time(8, 0)),
                        status=PeriodStatus.BUSY,
                        reason="reservado (João)",
                    ),
                ),
            ),
            ResourceAvailability(
                resource_name="Stand By",
                resource_model="",
                periods=(
                    ClassifiedPeriod(
                        period=TimePeriod(start=time(5, 45), end=time(9, 30)),
                        status=PeriodStatus.AVAILABLE,
                        reason="livre",
                    ),
                ),
            ),
        ),
    )


class BuildReportTest(unittest.TestCase):
    def test_day_header_and_lines(self):
        text = build_report([_sample_day()])
        self.assertIn("📅 **Seg 13/07/2026**", text)
        self.assertIn("🌅 05:45", text)
        self.assertIn("🌇 17:30", text)
        self.assertIn("janela 05:45–09:30", text)
        self.assertIn("✈️ **PT-ABC** (C-152)", text)
        self.assertIn("🟢 05:45–07:00 — livre (1h15)", text)
        self.assertIn("🔴 07:00–08:00 — reservado (João) (1h)", text)
        self.assertIn("✈️ **Stand By**", text)
        self.assertNotIn("Stand By** (", text)  # sem modelo → sem parênteses

    def test_day_without_window(self):
        day = DayAvailability(
            day=MONDAY,
            sunrise=time(10, 0),
            sunset=time(17, 30),
            window=None,
            resources=(),
        )
        text = build_report([day])
        self.assertIn("sem janela operacional", text)

    def test_errors_section(self):
        error = ScanError(day_index=4, day_label="17/07/2026", message="sol ausente")
        text = build_report([_sample_day()], [error])
        self.assertIn("⚠️", text)
        self.assertIn("17/07/2026", text)
        self.assertIn("sol ausente", text)

    def test_no_errors_no_error_section(self):
        self.assertNotIn("Dias com erro", build_report([_sample_day()]))


class BuildSummaryTest(unittest.TestCase):
    def test_summary_lists_available_slots(self):
        text = build_summary([_sample_day()])
        self.assertIn("1 dia(s) lidos", text)
        self.assertIn("2 janela(s) disponíveis", text)
        self.assertIn("Seg 13/07/2026: PT-ABC 05:45–07:00", text)
        self.assertIn("Seg 13/07/2026: Stand By 05:45–09:30", text)

    def test_summary_without_availability(self):
        day = DayAvailability(
            day=MONDAY,
            sunrise=time(10, 0),
            sunset=time(17, 30),
            window=None,
            resources=(),
        )
        text = build_summary([day])
        self.assertIn("Nenhum horário disponível", text)

    def test_summary_mentions_errors(self):
        error = ScanError(day_index=0, day_label="13/07/2026", message="x")
        text = build_summary([_sample_day()], [error])
        self.assertIn("1 com erro", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_report -v`
Expected: `ModuleNotFoundError: No module named 'report'`

- [ ] **Step 3: Implementar `report.py`**

```python
"""Formatação do relatório 🟢/🔴 para o Discord (PRD F8). Importa só models."""
from __future__ import annotations

from datetime import date, time
from typing import Sequence

from models import DayAvailability, PeriodStatus, ScanError

WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _fmt_time(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m/%Y')}"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def _day_header(day: DayAvailability) -> str:
    return (
        f"📅 **{_fmt_date(day.day)}** — 🌅 {_fmt_time(day.sunrise)} · "
        f"🌇 {_fmt_time(day.sunset)} · janela "
        f"{_fmt_time(day.window.start)}–{_fmt_time(day.window.end)}"
    )


def build_report(
    days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()
) -> str:
    lines: list[str] = ["📋 **Relatório de disponibilidade**", ""]
    for day in days:
        if day.window is None:
            lines.append(
                f"📅 **{_fmt_date(day.day)}** — sem janela operacional "
                f"(🌅 {_fmt_time(day.sunrise)} · 🌇 {_fmt_time(day.sunset)})"
            )
            lines.append("")
            continue
        lines.append(_day_header(day))
        for resource in day.resources:
            title = f"✈️ **{resource.resource_name}**"
            if resource.resource_model:
                title += f" ({resource.resource_model})"
            lines.append(title)
            for entry in resource.periods:
                icon = "🟢" if entry.status is PeriodStatus.AVAILABLE else "🔴"
                duration = _fmt_duration(entry.period.duration_minutes())
                lines.append(
                    f"    {icon} {_fmt_time(entry.period.start)}–"
                    f"{_fmt_time(entry.period.end)} — {entry.reason} ({duration})"
                )
        lines.append("")
    if errors:
        lines.append("⚠️ **Dias com erro de leitura:**")
        for error in errors:
            lines.append(
                f"    ⚠️ dia {error.day_index + 1} ({error.day_label}): {error.message}"
            )
    return "\n".join(lines).strip()


def build_summary(
    days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()
) -> str:
    slots: list[str] = []
    for day in days:
        for resource in day.resources:
            for entry in resource.periods:
                if entry.status is PeriodStatus.AVAILABLE:
                    slots.append(
                        f"- {_fmt_date(day.day)}: {resource.resource_name} "
                        f"{_fmt_time(entry.period.start)}–{_fmt_time(entry.period.end)}"
                    )
    lines = [
        f"✅ **Varredura concluída** — {len(days)} dia(s) lidos, "
        f"{len(errors)} com erro."
    ]
    if slots:
        lines.append(f"🟢 {len(slots)} janela(s) disponíveis:")
        lines.extend(slots)
    else:
        lines.append("Nenhum horário disponível encontrado. 😕")
    return "\n".join(lines)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_report -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Commit**

```bash
git add report.py tests/test_report.py
git commit -m "feat(aeroes_monitor): add Discord report formatting" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 7: `config.py` — carga e validação do config.ini

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: stdlib (`configparser`, `dataclasses`, `pathlib`).
- Produces (usado por login/scheduler/aircraft/main):
  - `ConfigError(Exception)`
  - `DEFAULT_SELECTORS: dict[str, tuple[str, ...]]` — chaves: `login_username`, `login_password`, `login_submit`, `login_form`, `logged_in_marker`, `schedule_container`, `schedule_date`, `next_day_button`, `sunrise_text`, `sunset_text`, `resource_row`, `resource_name`, `event_item`.
  - `CredentialsConfig(username, password)`; `DiscordConfig(webhook_url)`; `MonitorConfig(max_days=30, check_interval_seconds=3600, turnaround_minutes=30, min_flight_minutes=60, max_flight_minutes=120)`; `SeleniumConfig(base_url, schedule_url="", headless=True, page_load_timeout_seconds=30, element_timeout_seconds=15, debug_dir="debug")`; `LoggingConfig(level="INFO", file="")` — todas frozen.
  - `AppConfig(credentials, discord, monitor, selenium, selectors: dict[str, tuple[str, ...]], aircraft: dict[str, str], logging)` — frozen.
  - `load_config(path: str | Path) -> AppConfig` — acumula TODOS os erros num único `ConfigError`.
  - `config_to_safe_dict(config: AppConfig) -> dict` — redige `password` e `webhook_url` como `"***"`.
- Multivalor de seletor: um seletor CSS por LINHA (continuação indentada do INI); vírgula é sintaxe CSS, não separador.

- [ ] **Step 1: Escrever o teste que falha — `tests/test_config.py`**

```python
"""Testes da carga/validação de configuração (ADR-0005)."""
import tempfile
import unittest
from pathlib import Path

from config import (
    DEFAULT_SELECTORS,
    AppConfig,
    ConfigError,
    config_to_safe_dict,
    load_config,
)

VALID_INI = """
[credentials]
username = piloto@example.com
password = s3cr3t

[discord]
webhook_url = https://discord.com/api/webhooks/123/abc

[selenium]
base_url = https://saga.example.com/login

[aircraft]
PT-ABC = Cessna 152
PT-XYZ = Cessna 172
"""


def _write_ini(directory: str, content: str) -> Path:
    path = Path(directory) / "config.ini"
    path.write_text(content, encoding="utf-8")
    return path


class LoadConfigTest(unittest.TestCase):
    def test_minimal_valid_config_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.credentials.username, "piloto@example.com")
        self.assertEqual(config.monitor.max_days, 30)
        self.assertEqual(config.monitor.check_interval_seconds, 3600)
        self.assertEqual(config.monitor.turnaround_minutes, 30)
        self.assertEqual(config.monitor.min_flight_minutes, 60)
        self.assertEqual(config.monitor.max_flight_minutes, 120)
        self.assertTrue(config.selenium.headless)
        self.assertEqual(config.selenium.debug_dir, "debug")
        self.assertEqual(config.logging.level, "INFO")
        self.assertEqual(config.selectors, DEFAULT_SELECTORS)

    def test_aircraft_preserves_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertEqual(
            config.aircraft, {"PT-ABC": "Cessna 152", "PT-XYZ": "Cessna 172"}
        )

    def test_selector_override_multiline(self):
        ini = VALID_INI + """
[selectors]
login_username =
    input[name="email"]
    #campo-email
"""
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, ini))
        self.assertEqual(
            config.selectors["login_username"],
            ('input[name="email"]', "#campo-email"),
        )
        # Chaves não sobrescritas mantêm o default.
        self.assertEqual(
            config.selectors["login_password"], DEFAULT_SELECTORS["login_password"]
        )

    def test_missing_required_lists_all_errors(self):
        ini = """
[credentials]
username = x
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        message = str(ctx.exception)
        self.assertIn("credentials.password", message)
        self.assertIn("discord.webhook_url", message)
        self.assertIn("selenium.base_url", message)
        self.assertIn("aircraft", message)

    def test_numeric_validations(self):
        ini = VALID_INI + """
[monitor]
max_days = 0
min_flight_minutes = 120
max_flight_minutes = 60
check_interval_seconds = 5
turnaround_minutes = -1
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        message = str(ctx.exception)
        self.assertIn("max_days", message)
        self.assertIn("min_flight_minutes", message)
        self.assertIn("check_interval_seconds", message)
        self.assertIn("turnaround_minutes", message)

    def test_invalid_int_reported(self):
        ini = VALID_INI + """
[monitor]
max_days = trinta
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        self.assertIn("max_days", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(r"C:\caminho\que\nao\existe\config.ini")
        self.assertIn("config.ini.example", str(ctx.exception))


class SafeDictTest(unittest.TestCase):
    def test_secrets_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        safe = config_to_safe_dict(config)
        self.assertEqual(safe["credentials"]["password"], "***")
        self.assertEqual(safe["discord"]["webhook_url"], "***")
        self.assertEqual(safe["credentials"]["username"], "piloto@example.com")
        self.assertNotIn("s3cr3t", str(safe))
        self.assertNotIn("webhooks/123", str(safe))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_config -v`
Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Implementar `config.py`**

```python
"""Carrega e valida config.ini → dataclasses frozen (ADR-0005).

Seletores CSS ficam em [selectors] com defaults embutidos (ADR-0003):
um seletor por linha (vírgula é sintaxe CSS válida, não separador).
"""
from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Configuração ausente ou inválida."""


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
    "logged_in_marker": (".user-menu", ".logout", 'a[href*="logout"]', ".user-name"),
    "schedule_container": (".schedule", ".agenda", "#schedule", "table.schedule"),
    "schedule_date": (".schedule-date", ".agenda-data", ".current-date", "h2.date"),
    "next_day_button": (".next-day", 'button[title*="róximo"]', 'a[rel="next"]'),
    "sunrise_text": (".sunrise", ".nascer-do-sol", ".sun-info"),
    "sunset_text": (".sunset", ".por-do-sol", ".sun-info"),
    "resource_row": (".schedule-row", "tr.aircraft-row", ".resource-row"),
    "resource_name": (".resource-name", ".aircraft-name", "td:first-child"),
    "event_item": (".event", ".booking", ".reserved-slot"),
}


@dataclass(frozen=True)
class CredentialsConfig:
    username: str
    password: str


@dataclass(frozen=True)
class DiscordConfig:
    webhook_url: str


@dataclass(frozen=True)
class MonitorConfig:
    max_days: int = 30
    check_interval_seconds: int = 3600
    turnaround_minutes: int = 30
    min_flight_minutes: int = 60
    max_flight_minutes: int = 120


@dataclass(frozen=True)
class SeleniumConfig:
    base_url: str
    schedule_url: str = ""
    headless: bool = True
    page_load_timeout_seconds: int = 30
    element_timeout_seconds: int = 15
    debug_dir: str = "debug"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    file: str = ""


@dataclass(frozen=True)
class AppConfig:
    credentials: CredentialsConfig
    discord: DiscordConfig
    monitor: MonitorConfig
    selenium: SeleniumConfig
    selectors: dict[str, tuple[str, ...]]
    aircraft: dict[str, str]
    logging: LoggingConfig


def _require(
    parser: configparser.ConfigParser, section: str, key: str, errors: list[str]
) -> str:
    value = parser.get(section, key, fallback="").strip()
    if not value:
        errors.append(f"{section}.{key} é obrigatório")
    return value


def _get_int(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: int,
    errors: list[str],
) -> int:
    raw = parser.get(section, key, fallback=str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        errors.append(f"{section}.{key} deve ser um inteiro (recebido: {raw!r})")
        return default


def _get_bool(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: bool,
    errors: list[str],
) -> bool:
    try:
        return parser.getboolean(section, key, fallback=default)
    except ValueError:
        errors.append(f"{section}.{key} deve ser booleano (true/false)")
        return default


def _load_selectors(parser: configparser.ConfigParser) -> dict[str, tuple[str, ...]]:
    selectors = dict(DEFAULT_SELECTORS)
    if parser.has_section("selectors"):
        for key, raw in parser.items("selectors"):
            candidates = tuple(
                line.strip() for line in raw.splitlines() if line.strip()
            )
            if candidates:
                selectors[key] = candidates
    return selectors


def _load_aircraft(
    parser: configparser.ConfigParser, errors: list[str]
) -> dict[str, str]:
    if not parser.has_section("aircraft"):
        errors.append("seção [aircraft] é obrigatória, com ao menos uma aeronave")
        return {}
    aircraft = {
        registration.strip(): model.strip()
        for registration, model in parser.items("aircraft")
        if registration.strip()
    }
    if not aircraft:
        errors.append("seção [aircraft] precisa de ao menos uma aeronave (MATRÍCULA = modelo)")
    return aircraft


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"Arquivo de configuração não encontrado: {path}. "
            "Copie config.ini.example para config.ini e preencha."
        )
    # comment_prefixes só com ';': o default inclui '#', que engoliria
    # linhas de continuação com seletores CSS de id (ex.: "#email").
    parser = configparser.ConfigParser(interpolation=None, comment_prefixes=(";",))
    parser.optionxform = str  # preserva maiúsculas nas matrículas de [aircraft]
    parser.read(path, encoding="utf-8")

    errors: list[str] = []
    credentials = CredentialsConfig(
        username=_require(parser, "credentials", "username", errors),
        password=_require(parser, "credentials", "password", errors),
    )
    discord = DiscordConfig(
        webhook_url=_require(parser, "discord", "webhook_url", errors)
    )
    monitor = MonitorConfig(
        max_days=_get_int(parser, "monitor", "max_days", 30, errors),
        check_interval_seconds=_get_int(
            parser, "monitor", "check_interval_seconds", 3600, errors
        ),
        turnaround_minutes=_get_int(
            parser, "monitor", "turnaround_minutes", 30, errors
        ),
        min_flight_minutes=_get_int(
            parser, "monitor", "min_flight_minutes", 60, errors
        ),
        max_flight_minutes=_get_int(
            parser, "monitor", "max_flight_minutes", 120, errors
        ),
    )
    selenium = SeleniumConfig(
        base_url=_require(parser, "selenium", "base_url", errors),
        schedule_url=parser.get("selenium", "schedule_url", fallback="").strip(),
        headless=_get_bool(parser, "selenium", "headless", True, errors),
        page_load_timeout_seconds=_get_int(
            parser, "selenium", "page_load_timeout_seconds", 30, errors
        ),
        element_timeout_seconds=_get_int(
            parser, "selenium", "element_timeout_seconds", 15, errors
        ),
        debug_dir=parser.get("selenium", "debug_dir", fallback="debug").strip()
        or "debug",
    )
    logging_config = LoggingConfig(
        level=parser.get("logging", "level", fallback="INFO").strip() or "INFO",
        file=parser.get("logging", "file", fallback="").strip(),
    )
    selectors = _load_selectors(parser)
    aircraft = _load_aircraft(parser, errors)

    if monitor.max_days < 1:
        errors.append("monitor.max_days deve ser >= 1")
    if monitor.check_interval_seconds < 60:
        errors.append("monitor.check_interval_seconds deve ser >= 60")
    if monitor.turnaround_minutes < 0:
        errors.append("monitor.turnaround_minutes deve ser >= 0")
    if monitor.min_flight_minutes > monitor.max_flight_minutes:
        errors.append(
            "monitor.min_flight_minutes deve ser <= monitor.max_flight_minutes"
        )

    if errors:
        raise ConfigError("Configuração inválida:\n- " + "\n- ".join(errors))

    return AppConfig(
        credentials=credentials,
        discord=discord,
        monitor=monitor,
        selenium=selenium,
        selectors=selectors,
        aircraft=aircraft,
        logging=logging_config,
    )


def config_to_safe_dict(config: AppConfig) -> dict[str, Any]:
    """Versão logável da config: segredos redigidos (PRD §7)."""
    data = asdict(config)
    data["credentials"]["password"] = "***"
    data["discord"]["webhook_url"] = "***"
    return data
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_config -v`
Expected: todos `ok`, sumário `OK`.

Nota: `parser.optionxform = str` também preserva a caixa das chaves de `[selectors]` — as chaves documentadas são minúsculas, então segue equivalente aos defaults.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat(aeroes_monitor): load and validate config.ini into frozen dataclasses" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 8: `discord.py` — notificações via webhook

**Files:**
- Create: `discord.py`
- Test: `tests/test_discord.py`

**Interfaces:**
- Consumes: `requests` (único módulo do projeto que importa requests).
- Produces (usado pelo `main.py`):
  - `DISCORD_MESSAGE_LIMIT = 2000`
  - `split_message(text: str, limit: int = 2000) -> list[str]` — preserva quebras de linha; corte duro se uma linha exceder o limite; nunca retorna chunk vazio.
  - `DiscordNotifier(webhook_url: str, timeout_seconds: int = 10)` com métodos `send_message(content: str)`, `send_scan_started()`, `send_summary(text: str)`, `send_report(text: str)` (propagam `requests.RequestException`) e `send_error(message: str)` (engole e loga a própria falha).
- Obs.: módulo local chamado `discord.py` sombreia a lib `discord` de terceiros no sys.path do projeto — intencional e inofensivo (a lib não é usada; nomes vêm das ADRs).

- [ ] **Step 1: Escrever o teste que falha — `tests/test_discord.py`**

```python
"""Testes do notificador Discord (ADR-0006)."""
import unittest
from unittest import mock

import requests

from discord import DISCORD_MESSAGE_LIMIT, DiscordNotifier, split_message

WEBHOOK = "https://discord.com/api/webhooks/123/abc"


class SplitMessageTest(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(split_message("olá"), ["olá"])

    def test_exactly_limit_single_chunk(self):
        text = "a" * DISCORD_MESSAGE_LIMIT
        self.assertEqual(split_message(text), [text])

    def test_splits_on_line_boundaries(self):
        text = "\n".join(["linha-" + str(i) for i in range(10)])
        chunks = split_message(text, limit=30)
        self.assertTrue(all(len(c) <= 30 for c in chunks))
        self.assertEqual("\n".join(chunks), text)  # nada perdido

    def test_hard_split_for_giant_line(self):
        text = "x" * 45
        chunks = split_message(text, limit=20)
        self.assertEqual(chunks, ["x" * 20, "x" * 20, "x" * 5])

    def test_no_empty_chunks(self):
        text = "x" * 40  # múltiplo exato do limite
        chunks = split_message(text, limit=20)
        self.assertEqual(chunks, ["x" * 20, "x" * 20])
        self.assertTrue(all(chunks))

    def test_empty_text(self):
        self.assertEqual(split_message(""), [])


class DiscordNotifierTest(unittest.TestCase):
    def _response(self, status=204):
        response = mock.Mock()
        response.raise_for_status = mock.Mock()
        return response

    @mock.patch("discord.time.sleep")
    @mock.patch("discord.requests.post")
    def test_send_message_posts_chunks_in_order(self, post, _sleep):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        text = ("A" * 1500) + "\n" + ("B" * 1500)
        notifier.send_message(text)
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]["content"]
        second_payload = post.call_args_list[1].kwargs["json"]["content"]
        self.assertTrue(first_payload.startswith("A"))
        self.assertTrue(second_payload.startswith("B"))
        for call in post.call_args_list:
            self.assertEqual(call.args[0], WEBHOOK)
            self.assertEqual(call.kwargs["timeout"], 10)

    @mock.patch("discord.requests.post")
    def test_http_error_propagates(self, post):
        response = mock.Mock()
        response.raise_for_status.side_effect = requests.HTTPError("400")
        post.return_value = response
        notifier = DiscordNotifier(WEBHOOK)
        with self.assertRaises(requests.RequestException):
            notifier.send_message("oi")

    @mock.patch("discord.requests.post")
    def test_send_error_swallows_failure(self, post):
        post.side_effect = requests.ConnectionError("sem rede")
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_error("boom")  # não deve levantar

    @mock.patch("discord.requests.post")
    def test_send_error_prefixes_message(self, post):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_error("falha X")
        content = post.call_args.kwargs["json"]["content"]
        self.assertIn("🚨", content)
        self.assertIn("falha X", content)

    @mock.patch("discord.requests.post")
    def test_convenience_methods(self, post):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_scan_started()
        notifier.send_summary("resumo")
        notifier.send_report("relatório")
        contents = [c.kwargs["json"]["content"] for c in post.call_args_list]
        self.assertIn("🔎", contents[0])
        self.assertEqual(contents[1], "resumo")
        self.assertEqual(contents[2], "relatório")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_discord -v`
Expected: `ModuleNotFoundError: No module named 'discord'` (não há lib discord instalada no venv; se houvesse, falharia com `ImportError: cannot import name 'split_message'` — ambos indicam o módulo local ausente).

- [ ] **Step 3: Implementar `discord.py`**

```python
"""Notificações via Discord Webhook (ADR-0006).

Mensagens acima de 2000 caracteres são fragmentadas por split_message.
Falhas de envio propagam RequestException — exceto em send_error, que é
o último recurso e não pode mascarar o erro original.
"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000
_CHUNK_PAUSE_SECONDS = 0.5


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Fragmenta preservando quebras de linha; corte duro só quando uma
    única linha excede o limite. Nunca produz chunk vazio."""
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks


class DiscordNotifier:
    def __init__(self, webhook_url: str, timeout_seconds: int = 10) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    def _post(self, content: str) -> None:
        response = requests.post(
            self.webhook_url, json={"content": content}, timeout=self.timeout_seconds
        )
        response.raise_for_status()

    def send_message(self, content: str) -> None:
        chunks = split_message(content)
        for index, chunk in enumerate(chunks):
            self._post(chunk)
            if index < len(chunks) - 1:
                time.sleep(_CHUNK_PAUSE_SECONDS)  # rate limit do webhook
        logger.info("Mensagem enviada ao Discord (%d fragmento(s))", len(chunks))

    def send_scan_started(self) -> None:
        self.send_message("🔎 Iniciando varredura da escala do SAGA...")

    def send_summary(self, text: str) -> None:
        self.send_message(text)

    def send_report(self, text: str) -> None:
        self.send_message(text)

    def send_error(self, message: str) -> None:
        try:
            self.send_message(f"🚨 **Erro na varredura:** {message}")
        except requests.RequestException:
            logger.exception("Falha ao enviar notificação de erro ao Discord")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_discord -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Suíte inteira**

Run: `./.venv/Scripts/python -m unittest -v`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add discord.py tests/test_discord.py
git commit -m "feat(aeroes_monitor): add Discord webhook notifier with message splitting" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 9: `browser.py` — driver, esperas e artefatos de debug

**Files:**
- Create: `browser.py`
- Test: `tests/test_browser.py` (usa fakes; nenhum browser real)

**Interfaces:**
- Consumes: `selenium` (webdriver, By, WebDriverWait, exceções); `config.SeleniumConfig` (só em `create_driver`, via duck typing).
- Produces (usado por login/scheduler/aircraft/main):
  - `create_driver(cfg) -> webdriver.Chrome` — headless opcional, page load timeout. (Sem teste unitário: exige Chrome real.)
  - `find_all_first_match(context, selectors: Iterable[str]) -> list` — elementos do PRIMEIRO seletor que retornar algo; `context` é driver OU elemento (ambos têm `find_elements`).
  - `read_text_from_selectors(context, selectors) -> str | None` — primeiro texto não vazio percorrendo TODOS os candidatos.
  - `wait_for_any_visible(driver, selectors, timeout_seconds) -> WebElement` — `TimeoutException` listando os candidatos.
  - `element_exists(context, selectors) -> bool`
  - `save_debug_artifacts(driver, debug_dir, tag="failure") -> None` — `<debug_dir>/<YYYYmmdd-HHMMSS>-<tag>.png` + `.html`; nunca propaga exceção.

- [ ] **Step 1: Escrever o teste que falha — `tests/test_browser.py`**

```python
"""Testes dos helpers Selenium com driver falso (sem browser real)."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from selenium.common.exceptions import TimeoutException

from browser import (
    element_exists,
    find_all_first_match,
    read_text_from_selectors,
    save_debug_artifacts,
    wait_for_any_visible,
)


class FakeElement:
    def __init__(self, text="", displayed=True):
        self.text = text
        self._displayed = displayed

    def is_displayed(self):
        return self._displayed


class FakeDriver:
    """Duck type mínimo de WebDriver/WebElement para os helpers."""

    def __init__(self, elements_by_selector=None, page_source="<html></html>"):
        self.elements_by_selector = elements_by_selector or {}
        self.page_source = page_source
        self.screenshots = []

    def find_elements(self, by, selector):
        return self.elements_by_selector.get(selector, [])

    def save_screenshot(self, path):
        self.screenshots.append(path)
        Path(path).write_bytes(b"PNG")
        return True


class FindHelpersTest(unittest.TestCase):
    def test_first_matching_selector_wins(self):
        first, second = FakeElement("a"), FakeElement("b")
        driver = FakeDriver({".x": [], ".y": [first, second]})
        self.assertEqual(find_all_first_match(driver, [".x", ".y"]), [first, second])

    def test_no_match_returns_empty(self):
        self.assertEqual(find_all_first_match(FakeDriver(), [".x"]), [])

    def test_read_text_skips_empty_and_falls_through(self):
        driver = FakeDriver({".a": [FakeElement("  ")], ".b": [FakeElement("texto")]})
        self.assertEqual(read_text_from_selectors(driver, [".a", ".b"]), "texto")

    def test_read_text_none_when_nothing(self):
        self.assertIsNone(read_text_from_selectors(FakeDriver(), [".a"]))

    def test_element_exists(self):
        driver = FakeDriver({".a": [FakeElement()]})
        self.assertTrue(element_exists(driver, [".a"]))
        self.assertFalse(element_exists(driver, [".zzz"]))


class WaitForAnyVisibleTest(unittest.TestCase):
    def test_returns_first_visible(self):
        visible = FakeElement(displayed=True)
        driver = FakeDriver({".a": [FakeElement(displayed=False)], ".b": [visible]})
        self.assertIs(wait_for_any_visible(driver, [".a", ".b"], 1), visible)

    def test_timeout_lists_selectors(self):
        with self.assertRaises(TimeoutException) as ctx:
            wait_for_any_visible(FakeDriver(), [".a", ".b"], 0.3)
        self.assertIn(".a", str(ctx.exception))
        self.assertIn(".b", str(ctx.exception))


class DebugArtifactsTest(unittest.TestCase):
    def test_saves_screenshot_and_html(self):
        driver = FakeDriver(page_source="<html>debug</html>")
        with TemporaryDirectory() as tmp:
            save_debug_artifacts(driver, tmp, tag="teste")
            files = sorted(p.name for p in Path(tmp).iterdir())
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].endswith("-teste.html"))
        self.assertTrue(files[1].endswith("-teste.png"))

    def test_never_raises(self):
        class BrokenDriver:
            def save_screenshot(self, path):
                raise RuntimeError("browser morto")

            page_source = ""

        with TemporaryDirectory() as tmp:
            save_debug_artifacts(BrokenDriver(), tmp)  # não deve levantar


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_browser -v`
Expected: `ModuleNotFoundError: No module named 'browser'`

- [ ] **Step 3: Implementar `browser.py`**

```python
"""Camada Selenium: driver Chrome, esperas tolerantes a múltiplos seletores
candidatos (ADR-0003) e artefatos de debug (PRD F10)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


def create_driver(cfg) -> webdriver.Chrome:
    """Chrome via Selenium Manager (sem gerenciar chromedriver — ADR-0002)."""
    options = Options()
    if cfg.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(cfg.page_load_timeout_seconds)
    return driver


def find_all_first_match(context, selectors: Iterable[str]) -> list:
    """Elementos do primeiro seletor candidato que retornar algo.

    `context` pode ser o driver ou um elemento (busca escopada em linha).
    """
    for selector in selectors:
        try:
            elements = context.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue
        if elements:
            return list(elements)
    return []


def read_text_from_selectors(context, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        try:
            elements = context.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue
        for element in elements:
            text = (element.text or "").strip()
            if text:
                return text
    return None


def element_exists(context, selectors: Iterable[str]) -> bool:
    return bool(find_all_first_match(context, selectors))


def wait_for_any_visible(driver, selectors: Iterable[str], timeout_seconds):
    selectors = list(selectors)

    def _first_visible(drv):
        for selector in selectors:
            try:
                for element in drv.find_elements(By.CSS_SELECTOR, selector):
                    if element.is_displayed():
                        return element
            except WebDriverException:
                continue
        return False

    try:
        return WebDriverWait(driver, timeout_seconds).until(_first_visible)
    except TimeoutException as exc:
        raise TimeoutException(
            f"Nenhum seletor visível em {timeout_seconds}s: {selectors}"
        ) from exc


def save_debug_artifacts(driver, debug_dir, tag: str = "failure") -> None:
    """Screenshot + HTML para recalibração manual de seletores (PRD §11).

    Melhor esforço: nunca propaga exceção (roda dentro de handlers de erro).
    """
    try:
        directory = Path(debug_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        driver.save_screenshot(str(directory / f"{stamp}-{tag}.png"))
        (directory / f"{stamp}-{tag}.html").write_text(
            driver.page_source, encoding="utf-8"
        )
        logger.info("Artefatos de debug salvos em %s (%s-%s.*)", directory, stamp, tag)
    except Exception:
        logger.exception("Falha ao salvar artefatos de debug")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_browser -v`
Expected: todos `ok`, sumário `OK` (o teste de timeout leva ~0,3 s).

- [ ] **Step 5: Commit**

```bash
git add browser.py tests/test_browser.py
git commit -m "feat(aeroes_monitor): add Selenium helpers and debug artifacts" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---

### Task 10: `login.py` — autenticação e sessão

**Files:**
- Create: `login.py`
- Test: `tests/test_login.py`

**Interfaces:**
- Consumes: `browser.element_exists`, `browser.wait_for_any_visible`; `selenium.common.exceptions.TimeoutException`; `AppConfig` (duck typing: `.selenium.base_url`, `.selenium.element_timeout_seconds`, `.credentials.username/.password`, `.selectors`).
- Produces (usado por scheduler/main):
  - `LoginError(Exception)`
  - `is_login_page(driver, selectors: dict[str, tuple[str, ...]]) -> bool` (chave `login_form`)
  - `is_logged_in(driver, selectors) -> bool` (chave `logged_in_marker`)
  - `login(driver, config) -> None` — navega, reaproveita sessão válida (F1), senão preenche e submete; `LoginError` se o marcador de sessão não aparecer.

- [ ] **Step 1: Escrever o teste que falha — `tests/test_login.py`**

```python
"""Testes do fluxo de login com driver falso."""
import unittest
from types import SimpleNamespace
from unittest import mock

from selenium.common.exceptions import TimeoutException

from login import LoginError, is_logged_in, is_login_page, login

SELECTORS = {
    "login_username": ("#user",),
    "login_password": ("#pass",),
    "login_submit": ("#submit",),
    "login_form": ("form.login",),
    "logged_in_marker": (".user-menu",),
}


def _config():
    return SimpleNamespace(
        credentials=SimpleNamespace(username="piloto", password="senha"),
        selenium=SimpleNamespace(
            base_url="https://saga.example.com/login", element_timeout_seconds=1
        ),
        selectors=SELECTORS,
    )


class FakeField:
    def __init__(self):
        self.sent = []
        self.cleared = False
        self.clicked = False

    def clear(self):
        self.cleared = True

    def send_keys(self, value):
        self.sent.append(value)

    def click(self):
        self.clicked = True

    def is_displayed(self):
        return True


class FakeDriver:
    def __init__(self, elements_by_selector=None):
        self.elements_by_selector = elements_by_selector or {}
        self.visited = []

    def get(self, url):
        self.visited.append(url)

    def find_elements(self, by, selector):
        return self.elements_by_selector.get(selector, [])


class DetectionTest(unittest.TestCase):
    def test_is_login_page(self):
        driver = FakeDriver({"form.login": [FakeField()]})
        self.assertTrue(is_login_page(driver, SELECTORS))
        self.assertFalse(is_login_page(FakeDriver(), SELECTORS))

    def test_is_logged_in(self):
        driver = FakeDriver({".user-menu": [FakeField()]})
        self.assertTrue(is_logged_in(driver, SELECTORS))
        self.assertFalse(is_logged_in(FakeDriver(), SELECTORS))


class LoginFlowTest(unittest.TestCase):
    def test_session_reuse_skips_form(self):
        driver = FakeDriver({".user-menu": [FakeField()]})
        with mock.patch("login.wait_for_any_visible") as wait:
            login(driver, _config())
        wait.assert_not_called()
        self.assertEqual(driver.visited, ["https://saga.example.com/login"])

    def test_full_login_fills_and_submits(self):
        driver = FakeDriver({"form.login": [FakeField()]})
        user_field, pass_field, submit = FakeField(), FakeField(), FakeField()
        marker = FakeField()

        def fake_wait(drv, selectors, timeout):
            return {
                ("#user",): user_field,
                ("#pass",): pass_field,
                ("#submit",): submit,
                (".user-menu",): marker,
            }[tuple(selectors)]

        with mock.patch("login.wait_for_any_visible", side_effect=fake_wait):
            login(driver, _config())
        self.assertEqual(user_field.sent, ["piloto"])
        self.assertEqual(pass_field.sent, ["senha"])
        self.assertTrue(user_field.cleared)
        self.assertTrue(submit.clicked)

    def test_login_error_when_marker_never_appears(self):
        driver = FakeDriver({"form.login": [FakeField()]})
        field = FakeField()

        def fake_wait(drv, selectors, timeout):
            if tuple(selectors) == (".user-menu",):
                raise TimeoutException("timeout")
            return field

        with mock.patch("login.wait_for_any_visible", side_effect=fake_wait):
            with self.assertRaises(LoginError):
                login(driver, _config())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_login -v`
Expected: `ModuleNotFoundError: No module named 'login'`

- [ ] **Step 3: Implementar `login.py`**

```python
"""Login no SAGA e detecção de sessão expirada (PRD F1, F2).

Read-only exceto pelo formulário de LOGIN, único formulário que este
projeto submete (ADR-0001).
"""
from __future__ import annotations

import logging

from selenium.common.exceptions import TimeoutException

from browser import element_exists, wait_for_any_visible

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """Falha de autenticação no SAGA."""


def is_login_page(driver, selectors) -> bool:
    return element_exists(driver, selectors["login_form"])


def is_logged_in(driver, selectors) -> bool:
    return element_exists(driver, selectors["logged_in_marker"])


def login(driver, config) -> None:
    selectors = config.selectors
    timeout = config.selenium.element_timeout_seconds
    driver.get(config.selenium.base_url)
    if is_logged_in(driver, selectors) and not is_login_page(driver, selectors):
        logger.info("Sessão existente reaproveitada")
        return
    username_field = wait_for_any_visible(driver, selectors["login_username"], timeout)
    username_field.clear()
    username_field.send_keys(config.credentials.username)
    password_field = wait_for_any_visible(driver, selectors["login_password"], timeout)
    password_field.clear()
    password_field.send_keys(config.credentials.password)
    wait_for_any_visible(driver, selectors["login_submit"], timeout).click()
    try:
        wait_for_any_visible(driver, selectors["logged_in_marker"], timeout)
    except TimeoutException as exc:
        raise LoginError(
            "Login não confirmado: marcador de sessão não apareceu "
            "(verifique credenciais e o seletor logged_in_marker)"
        ) from exc
    logger.info("Login efetuado com sucesso")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_login -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Commit**

```bash
git add login.py tests/test_login.py
git commit -m "feat(aeroes_monitor): add SAGA login with session reuse" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 11: `aircraft.py` — agendas por aeronave + Stand By

**Files:**
- Create: `aircraft.py`
- Test: `tests/test_aircraft.py`

**Interfaces:**
- Consumes: `browser.find_all_first_match`, `browser.read_text_from_selectors`; `utils.extract_period`, `utils.normalize_registration`; `models.ResourceSchedule/TimePeriod`.
- Produces (usado pelo scheduler):
  - `STANDBY_NAME = "Stand By"`
  - `AircraftService(driver, selectors: dict[str, tuple[str, ...]], allowlist: dict[str, str])`
  - `AircraftService.build_aircraft_schedules() -> tuple[ResourceSchedule, ...]` — SEMPRE um `ResourceSchedule` por aeronave da allowlist, na ordem da allowlist (vazio se a linha não existir — ADR-0007), MAIS um para Stand By por último (F5). Casamento por matrícula normalizada contida no nome da linha; linha de Stand By casa com `/stand\s*-?\s*by/i`.

- [ ] **Step 1: Escrever o teste que falha — `tests/test_aircraft.py`**

```python
"""Testes do parsing de agendas com elementos falsos (ADR-0007, F5)."""
import unittest
from datetime import time

from aircraft import STANDBY_NAME, AircraftService

SELECTORS = {
    "resource_row": (".row",),
    "resource_name": (".name",),
    "event_item": (".event",),
}
ALLOWLIST = {"PT-ABC": "Cessna 152", "PT-XYZ": "Cessna 172"}


class FakeElement:
    def __init__(self, text="", children=None):
        self.text = text
        self._children = children or {}

    def find_elements(self, by, selector):
        return self._children.get(selector, [])

    def is_displayed(self):
        return True


def _row(name, events=()):
    return FakeElement(
        text=name,
        children={
            ".name": [FakeElement(text=name)],
            ".event": [FakeElement(text=e) for e in events],
        },
    )


class FakeDriver:
    def __init__(self, rows):
        self._rows = rows

    def find_elements(self, by, selector):
        return self._rows if selector == ".row" else []


class BuildAircraftSchedulesTest(unittest.TestCase):
    def test_allowlisted_aircraft_with_events(self):
        driver = FakeDriver(
            [
                _row("PT-ABC — Cessna 152", ["06:00 - 07:00 João", "08:00 - 09:00"]),
                _row("PT-QQQ — fora da lista", ["06:00 - 07:00"]),
                _row("STAND BY", ["07:00 - 08:00"]),
            ]
        )
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        names = [s.name for s in schedules]
        self.assertEqual(names, ["PT-ABC", "PT-XYZ", STANDBY_NAME])

        pt_abc = schedules[0]
        self.assertEqual(pt_abc.model, "Cessna 152")
        self.assertEqual(len(pt_abc.busy_periods), 2)
        self.assertEqual(pt_abc.busy_periods[0].start, time(6, 0))
        self.assertEqual(pt_abc.busy_periods[0].label, "João")

        # PT-XYZ não tem linha → agenda vazia, mas presente (ADR-0007).
        self.assertEqual(schedules[1].busy_periods, ())

        standby = schedules[2]
        self.assertEqual(standby.model, "")
        self.assertEqual(len(standby.busy_periods), 1)

    def test_standby_always_emitted_even_if_absent(self):
        driver = FakeDriver([_row("PT-ABC", [])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(schedules[-1].name, STANDBY_NAME)
        self.assertEqual(schedules[-1].busy_periods, ())

    def test_case_insensitive_registration_match(self):
        driver = FakeDriver([_row("pt-abc (Cessna)", ["06:00 - 07:00"])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(len(schedules[0].busy_periods), 1)

    def test_unparseable_event_ignored(self):
        driver = FakeDriver([_row("PT-ABC", ["manutenção sem horário", "06:00 - 07:00"])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(len(schedules[0].busy_periods), 1)

    def test_events_sorted_by_start(self):
        driver = FakeDriver([_row("PT-ABC", ["08:00 - 09:00", "06:00 - 07:00"])])
        schedules = AircraftService(driver, SELECTORS, ALLOWLIST).build_aircraft_schedules()
        starts = [p.start for p in schedules[0].busy_periods]
        self.assertEqual(starts, sorted(starts))

    def test_row_name_fallback_to_row_text_first_line(self):
        row = FakeElement(
            text="Stand-by\n07:00 - 08:00",
            children={".name": [], ".event": [FakeElement(text="07:00 - 08:00")]},
        )
        schedules = AircraftService(FakeDriver([row]), SELECTORS, ALLOWLIST).build_aircraft_schedules()
        self.assertEqual(len(schedules[-1].busy_periods), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_aircraft -v`
Expected: `ModuleNotFoundError: No module named 'aircraft'`

- [ ] **Step 3: Implementar `aircraft.py`**

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_aircraft -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Commit**

```bash
git add aircraft.py tests/test_aircraft.py
git commit -m "feat(aeroes_monitor): parse aircraft and Stand By schedules from page" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---

### Task 12: `scheduler.py` — varredura multi-dia

**Files:**
- Create: `scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `aircraft.AircraftService`; `browser.read_text_from_selectors/wait_for_any_visible`; `login.is_login_page/login`; `utils.extract_sunrise/extract_sunset/find_times/parse_day_date`; `models.DaySchedule/ScanError/ScanResult`; selenium `By`, `WebDriverWait`.
- Produces (usado pelo `main.py`):
  - `MAX_CONSECUTIVE_FAILURES = 3`
  - `ScheduleScanner(driver, config)` — config via duck typing: `.monitor.max_days`, `.selenium.schedule_url/.element_timeout_seconds`, `.selectors`, `.aircraft`, e o que `login()` consome.
  - `ScheduleScanner.scan() -> ScanResult` — erro em um dia vira `ScanError` e a varredura segue (F10); 3 falhas consecutivas OU falha ao avançar truncam com `ScanError` extra.

- [ ] **Step 1: Escrever o teste que falha — `tests/test_scheduler.py`**

```python
"""Testes da varredura multi-dia com métodos internos mockados."""
import unittest
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest import mock

from models import DaySchedule, ScanResult
from scheduler import MAX_CONSECUTIVE_FAILURES, ScheduleScanner

SELECTORS = {
    "schedule_container": (".schedule",),
    "schedule_date": (".date",),
    "next_day_button": (".next",),
    "sunrise_text": (".sunrise",),
    "sunset_text": (".sunset",),
    "resource_row": (".row",),
    "resource_name": (".name",),
    "event_item": (".event",),
    "login_form": ("form.login",),
    "logged_in_marker": (".user-menu",),
    "login_username": ("#user",),
    "login_password": ("#pass",),
    "login_submit": ("#submit",),
}


def _config(max_days=3):
    return SimpleNamespace(
        monitor=SimpleNamespace(max_days=max_days),
        selenium=SimpleNamespace(schedule_url="", element_timeout_seconds=1),
        selectors=SELECTORS,
        aircraft={"PT-ABC": "C-152"},
        credentials=SimpleNamespace(username="u", password="p"),
    )


def _day(index):
    return DaySchedule(
        day=date(2026, 7, 14) + timedelta(days=index),
        sunrise=time(5, 45),
        sunset=time(17, 30),
        resources=(),
    )


def _scanner(max_days=3):
    return ScheduleScanner(driver=mock.Mock(), config=_config(max_days))


class ScanLoopTest(unittest.TestCase):
    def test_happy_path_scans_all_days(self):
        scanner = _scanner(max_days=3)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(scanner, "_scan_single_day", side_effect=[_day(0), _day(1), _day(2)]), \
             mock.patch.object(scanner, "_advance_day", return_value=True) as advance, \
             mock.patch("scheduler.read_text_from_selectors", return_value="14/07/2026"):
            result = scanner.scan()
        self.assertIsInstance(result, ScanResult)
        self.assertEqual(len(result.days), 3)
        self.assertEqual(result.errors, ())
        self.assertEqual(advance.call_count, 2)  # não avança após o último dia

    def test_single_day_failure_is_recoverable(self):
        scanner = _scanner(max_days=3)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(
                 scanner,
                 "_scan_single_day",
                 side_effect=[_day(0), ValueError("sol ausente"), _day(2)],
             ), \
             mock.patch.object(scanner, "_advance_day", return_value=True), \
             mock.patch("scheduler.read_text_from_selectors", return_value="15/07/2026"):
            result = scanner.scan()
        self.assertEqual(len(result.days), 2)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].day_index, 1)
        self.assertIn("sol ausente", result.errors[0].message)

    def test_consecutive_failures_truncate_scan(self):
        scanner = _scanner(max_days=10)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(scanner, "_scan_single_day", side_effect=ValueError("boom")), \
             mock.patch.object(scanner, "_advance_day", return_value=True) as advance, \
             mock.patch("scheduler.read_text_from_selectors", return_value=""):
            result = scanner.scan()
        self.assertEqual(result.days, ())
        # 3 erros de dia + 1 erro de truncamento.
        self.assertEqual(len(result.errors), MAX_CONSECUTIVE_FAILURES + 1)
        self.assertIn("falhas consecutivas", result.errors[-1].message)
        self.assertEqual(advance.call_count, MAX_CONSECUTIVE_FAILURES - 1)

    def test_advance_failure_truncates_with_partial_result(self):
        scanner = _scanner(max_days=5)
        with mock.patch.object(scanner, "_open_schedule"), \
             mock.patch.object(scanner, "_ensure_session"), \
             mock.patch.object(scanner, "_scan_single_day", return_value=_day(0)), \
             mock.patch.object(scanner, "_advance_day", return_value=False), \
             mock.patch("scheduler.read_text_from_selectors", return_value="14/07/2026"):
            result = scanner.scan()
        self.assertEqual(len(result.days), 1)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("avançar", result.errors[0].message)


class EnsureSessionTest(unittest.TestCase):
    def test_relogin_when_back_at_login_page(self):
        scanner = _scanner()
        with mock.patch("scheduler.is_login_page", return_value=True), \
             mock.patch("scheduler.login") as do_login, \
             mock.patch.object(scanner, "_open_schedule") as reopen:
            scanner._ensure_session()
        do_login.assert_called_once()
        reopen.assert_called_once()

    def test_noop_when_session_alive(self):
        scanner = _scanner()
        with mock.patch("scheduler.is_login_page", return_value=False), \
             mock.patch("scheduler.login") as do_login:
            scanner._ensure_session()
        do_login.assert_not_called()


class ResolveDateTest(unittest.TestCase):
    def test_parses_label(self):
        scanner = _scanner()
        self.assertEqual(scanner._resolve_date(0, "Segunda, 14/07/2026"), date(2026, 7, 14))

    def test_fallback_from_last_parsed(self):
        scanner = _scanner()
        scanner._resolve_date(0, "14/07/2026")
        self.assertEqual(scanner._resolve_date(2, "sem data"), date(2026, 7, 16))

    def test_fallback_from_today_when_never_parsed(self):
        scanner = _scanner()
        expected = date.today() + timedelta(days=1)
        self.assertEqual(scanner._resolve_date(1, "???"), expected)


class ReadSunTimesTest(unittest.TestCase):
    def test_reads_from_selector_text(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value="Nascer do sol: 05:45"):
            self.assertEqual(scanner._read_sunrise(""), time(5, 45))

    def test_single_time_in_dedicated_element(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value="05:45"):
            self.assertEqual(scanner._read_sunrise(""), time(5, 45))

    def test_falls_back_to_page_text(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value=None):
            self.assertEqual(
                scanner._read_sunset("Pôr do sol: 17:30"), time(17, 30)
            )

    def test_raises_when_absent(self):
        scanner = _scanner()
        with mock.patch("scheduler.read_text_from_selectors", return_value=None):
            with self.assertRaises(ValueError):
                scanner._read_sunrise("página sem informação de sol")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_scheduler -v`
Expected: `ModuleNotFoundError: No module named 'scheduler'`

- [ ] **Step 3: Implementar `scheduler.py`**

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_scheduler -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Suíte inteira**

Run: `./.venv/Scripts/python -m unittest -v`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat(aeroes_monitor): add multi-day schedule scanner with recoverable errors" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---
### Task 13: `main.py` — CLI, logging e orquestração

**Files:**
- Create: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: tudo das tasks anteriores — `load_config/ConfigError/config_to_safe_dict`, `create_driver/save_debug_artifacts`, `login`, `ScheduleScanner`, `AvailabilityRules/enrich_day_schedule`, `build_summary/build_report`, `DiscordNotifier`.
- Produces:
  - `parse_args(argv=None) -> argparse.Namespace` — `--once` (bool) e `--config` (default `config.ini`).
  - `setup_logging(cfg: LoggingConfig) -> None`
  - `run_scan(config: AppConfig) -> bool` — nunca deixa exceção escapar; `finally` encerra o browser.
  - `main(argv=None) -> int` — 0 sucesso, 1 varredura falhou (`--once`), 2 erro de config; loop contínuo com `time.sleep` (ADR-0009).

- [ ] **Step 1: Escrever o teste que falha — `tests/test_main.py`**

```python
"""Testes da orquestração (run_scan) e CLI com dependências mockadas."""
import unittest
from types import SimpleNamespace
from unittest import mock

from main import main, parse_args, run_scan
from models import ScanResult


def _config():
    return SimpleNamespace(
        credentials=SimpleNamespace(username="u", password="p"),
        discord=SimpleNamespace(webhook_url="https://discord.example/webhook"),
        monitor=SimpleNamespace(
            max_days=1,
            check_interval_seconds=3600,
            turnaround_minutes=30,
            min_flight_minutes=60,
            max_flight_minutes=120,
        ),
        selenium=SimpleNamespace(
            base_url="https://saga.example.com",
            schedule_url="",
            headless=True,
            page_load_timeout_seconds=5,
            element_timeout_seconds=5,
            debug_dir="debug",
        ),
        selectors={},
        aircraft={"PT-ABC": "C-152"},
        logging=SimpleNamespace(level="INFO", file=""),
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


class RunScanTest(unittest.TestCase):
    @mock.patch("main.ScheduleScanner")
    @mock.patch("main.login")
    @mock.patch("main.create_driver")
    @mock.patch("main.DiscordNotifier")
    def test_happy_path(self, notifier_cls, create_driver, do_login, scanner_cls):
        notifier = notifier_cls.return_value
        driver = create_driver.return_value
        scanner_cls.return_value.scan.return_value = ScanResult()
        self.assertTrue(run_scan(_config()))
        notifier.send_scan_started.assert_called_once()
        notifier.send_summary.assert_called_once()
        notifier.send_report.assert_called_once()
        notifier.send_error.assert_not_called()
        do_login.assert_called_once()
        driver.quit.assert_called_once()

    @mock.patch("main.save_debug_artifacts")
    @mock.patch("main.ScheduleScanner")
    @mock.patch("main.login", side_effect=RuntimeError("login quebrou"))
    @mock.patch("main.create_driver")
    @mock.patch("main.DiscordNotifier")
    def test_fatal_error_notifies_saves_artifacts_and_quits(
        self, notifier_cls, create_driver, do_login, scanner_cls, save_artifacts
    ):
        notifier = notifier_cls.return_value
        driver = create_driver.return_value
        self.assertFalse(run_scan(_config()))
        notifier.send_error.assert_called_once()
        self.assertIn("login quebrou", notifier.send_error.call_args.args[0])
        save_artifacts.assert_called_once()
        driver.quit.assert_called_once()
        scanner_cls.return_value.scan.assert_not_called()

    @mock.patch("main.create_driver", side_effect=RuntimeError("sem chrome"))
    @mock.patch("main.DiscordNotifier")
    def test_driver_creation_failure_still_notifies(self, notifier_cls, create_driver):
        notifier = notifier_cls.return_value
        self.assertFalse(run_scan(_config()))
        notifier.send_error.assert_called_once()

    @mock.patch("main.ScheduleScanner")
    @mock.patch("main.login")
    @mock.patch("main.create_driver")
    @mock.patch("main.DiscordNotifier")
    def test_quit_failure_does_not_break_result(
        self, notifier_cls, create_driver, do_login, scanner_cls
    ):
        create_driver.return_value.quit.side_effect = RuntimeError("já fechado")
        scanner_cls.return_value.scan.return_value = ScanResult()
        self.assertTrue(run_scan(_config()))


class MainExitCodesTest(unittest.TestCase):
    def test_missing_config_returns_2(self):
        self.assertEqual(main(["--once", "--config", "nao_existe_123.ini"]), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `./.venv/Scripts/python -m unittest tests.test_main -v`
Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Implementar `main.py`**

```python
"""Ponto de entrada do Aeroclube Schedule Monitor (PRD F11, F12).

Uso:
    python main.py --once     # uma varredura e sai (0 ok, 1 falha, 2 config)
    python main.py            # loop contínuo (ADR-0009), Ctrl+C encerra
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from availability import AvailabilityRules, enrich_day_schedule
from browser import create_driver, save_debug_artifacts
from config import AppConfig, ConfigError, config_to_safe_dict, load_config
from discord import DiscordNotifier
from login import login
from report import build_report, build_summary
from scheduler import ScheduleScanner

logger = logging.getLogger("aeroes_monitor")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor read-only da escala de voo do SAGA (Aeroclube-ES)"
    )
    parser.add_argument(
        "--once", action="store_true", help="executa uma única varredura e sai"
    )
    parser.add_argument(
        "--config", default="config.ini", help="caminho do config.ini (default: ./config.ini)"
    )
    return parser.parse_args(argv)


def setup_logging(cfg) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if cfg.file:
        handlers.append(logging.FileHandler(cfg.file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, cfg.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _quit_quietly(driver) -> None:
    try:
        driver.quit()
    except Exception:
        logger.warning("Falha ao encerrar o browser", exc_info=True)


def run_scan(config: AppConfig) -> bool:
    """Uma varredura completa. Nunca propaga exceção (o loop sobrevive)."""
    notifier = DiscordNotifier(config.discord.webhook_url)
    driver = None
    try:
        notifier.send_scan_started()
        driver = create_driver(config.selenium)
        login(driver, config)
        result = ScheduleScanner(driver, config).scan()
        rules = AvailabilityRules(
            turnaround_minutes=config.monitor.turnaround_minutes,
            min_flight_minutes=config.monitor.min_flight_minutes,
            max_flight_minutes=config.monitor.max_flight_minutes,
        )
        availabilities = [enrich_day_schedule(day, rules) for day in result.days]
        notifier.send_summary(build_summary(availabilities, result.errors))
        notifier.send_report(build_report(availabilities, result.errors))
        logger.info(
            "Varredura concluída: %d dia(s), %d erro(s)",
            len(result.days),
            len(result.errors),
        )
        return True
    except Exception as exc:
        logger.exception("Falha fatal na varredura")
        if driver is not None:
            save_debug_artifacts(driver, config.selenium.debug_dir, tag="fatal")
        notifier.send_error(str(exc))
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
    if args.once:
        return 0 if run_scan(config) else 1
    logger.info(
        "Modo contínuo: varredura a cada %d s (Ctrl+C para encerrar)",
        config.monitor.check_interval_seconds,
    )
    try:
        while True:
            run_scan(config)
            logger.info(
                "Próxima varredura em %d s", config.monitor.check_interval_seconds
            )
            time.sleep(config.monitor.check_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuário")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Rodar e ver passar**

Run: `./.venv/Scripts/python -m unittest tests.test_main -v`
Expected: todos `ok`, sumário `OK`.

- [ ] **Step 5: Smoke do CLI**

Run: `./.venv/Scripts/python main.py --help`
Expected: texto de ajuda com `--once` e `--config`, exit 0.

Run: `./.venv/Scripts/python main.py --once` (sem config.ini presente)
Expected: `Erro de configuração: Arquivo de configuração não encontrado...` em stderr, exit code 2 (verifique com `echo $?`).

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat(aeroes_monitor): add CLI entrypoint with scan loop" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---

### Task 14: `config.ini.example` + `README.md`

**Files:**
- Create: `config.ini.example`
- Create: `README.md`

**Interfaces:**
- Consumes: `config.load_config` (para validar que o example carrega).
- Produces: documentação de setup/calibração; template de configuração coerente com `config.py` (Task 7).

- [ ] **Step 1: Criar `config.ini.example`**

```ini
; Aeroclube Schedule Monitor — copie para config.ini e preencha.
; ATENÇÃO: config.ini contém segredos e está no .gitignore — NUNCA versionar.
; Comentários usam ';' (o caractere '#' é reservado para seletores CSS de id).

[credentials]
; Credenciais de acesso ao SAGA (Aeroclube do Espírito Santo)
username = seu-email@example.com
password = sua-senha

[discord]
; Webhook do canal que recebe os relatórios
; (Configurações do canal → Integrações → Webhooks → Novo webhook)
webhook_url = https://discord.com/api/webhooks/SEU/WEBHOOK

[monitor]
; Quantos dias varrer a partir do dia exibido
max_days = 30
; Intervalo entre varreduras no modo contínuo (segundos, mínimo 60)
check_interval_seconds = 3600
; Intervalo mínimo entre voos consecutivos da mesma aeronave (minutos)
turnaround_minutes = 30
; Um vão livre só é 🟢 se durar pelo menos isto (minutos)
min_flight_minutes = 60
; Duração máxima de voo (informativo/validação; não fatia janelas)
max_flight_minutes = 120

[selenium]
; URL de login do SAGA
base_url = https://saga.example.com/login
; URL direta da escala (deixe vazio se a página pós-login já for a escala)
schedule_url =
; true = Chrome invisível; use false para calibrar seletores olhando a página
headless = true
page_load_timeout_seconds = 30
element_timeout_seconds = 15
; Pasta onde screenshots/HTML são salvos em falhas
debug_dir = debug

[aircraft]
; Aeronaves monitoradas: MATRICULA = modelo (uma por linha) — ADR-0007.
; Somente estas aparecem no relatório, independente do status no SAGA.
PT-ABC = Cessna 152
PT-XYZ = Cessna 172

[logging]
; DEBUG | INFO | WARNING | ERROR
level = INFO
; Arquivo de log (vazio = somente console)
file =

; [selectors] — OPCIONAL: descomente e ajuste após calibrar com a página real
; (ADR-0003; veja "Calibração de seletores" no README).
; Cada chave aceita VÁRIOS seletores CSS, um por linha (linhas continuadas
; indentadas). Vírgula NÃO separa: vírgula é sintaxe válida de CSS.
;[selectors]
;login_username =
;    input[name="email"]
;    #email
;login_password =
;    input[type="password"]
;login_submit =
;    button[type="submit"]
;login_form =
;    form.login
;logged_in_marker =
;    a[href*="logout"]
;schedule_container =
;    .schedule
;schedule_date =
;    .schedule-date
;next_day_button =
;    .next-day
;sunrise_text =
;    .sunrise
;sunset_text =
;    .sunset
;resource_row =
;    .schedule-row
;resource_name =
;    .resource-name
;event_item =
;    .event
```

- [ ] **Step 2: Validar que o example carrega**

Run: `./.venv/Scripts/python -c "from config import load_config; c = load_config('config.ini.example'); print('example ok:', sorted(c.aircraft))"`
Expected: `example ok: ['PT-ABC', 'PT-XYZ']`

- [ ] **Step 3: Criar `README.md`**

```markdown
# Aeroclube Schedule Monitor

Monitor **read-only** da escala de horários de voo do sistema SAGA do
Aeroclube do Espírito Santo. Varre a agenda dos próximos dias, aplica as
regras operacionais do clube e envia ao Discord um relatório do que está
🟢 livre e 🔴 ocupado, por aeronave e por dia.

## Garantia read-only

Este programa **não faz reservas e não altera nada no SAGA** (ADR-0001).
Ele apenas: autentica → navega → lê o HTML exibido → calcula localmente →
reporta no Discord. O único formulário que ele submete é o de **login**.
A ação de reservar continua 100% manual, no próprio SAGA.

## Requisitos

- Python 3.13+
- Google Chrome instalado (o chromedriver é resolvido automaticamente pelo
  Selenium Manager — nada para baixar)
- Um webhook de Discord

## Instalação

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Configuração

1. Copie `config.ini.example` para `config.ini`.
2. Preencha `[credentials]`, `[discord] webhook_url` e `[selenium] base_url`.
3. Liste em `[aircraft]` as aeronaves a monitorar (`MATRICULA = modelo`).
   Só elas aparecem no relatório (ADR-0007).

`config.ini` está no `.gitignore` — **nunca** o versione. Os logs redigem
senha e webhook automaticamente.

## Uso

```
.venv\Scripts\python main.py --once   # uma varredura e sai
.venv\Scripts\python main.py          # loop contínuo (intervalo do config.ini)
```

Códigos de saída de `--once`: `0` sucesso, `1` varredura falhou, `2` erro
de configuração.

## Regras de disponibilidade (PRD §6)

| Dia | Janela permitida |
|-----|------------------|
| Segunda a sexta | nascer do sol → 09:30 |
| Sábado | nascer do sol → pôr do sol |
| Domingo | nascer do sol → 12:00 |

- Nascer/pôr do sol vêm **da própria página do SAGA** (ADR-0008), nunca de
  API externa.
- Buffer de turnaround entre voos da mesma aeronave: `turnaround_minutes`
  (padrão 30 min).
- Vão livre menor que `min_flight_minutes` aparece como 🔴 "vão curto":
  não é reservável.

## Calibração de seletores (primeiro uso)

Os seletores CSS padrão são um palpite razoável — o SAGA real quase
certamente usa outros. Para calibrar (ADR-0003):

1. Rode com `headless = false` para ver o browser.
2. Abra o SAGA manualmente no Chrome, faça login e vá até a escala.
3. F12 (DevTools) → botão de inspecionar → clique no elemento desejado
   (campo de e-mail, linha de aeronave, texto do nascer do sol, botão de
   próximo dia, etc.).
4. Anote um seletor CSS estável (prefira `name`, `id` ou classes
   descritivas; evite classes geradas/aleatórias).
5. Descomente `[selectors]` no `config.ini` e preencha as chaves — um
   seletor por linha; a ordem é a ordem de tentativa.
6. Rode `python main.py --once` e ajuste até a varredura completar.

Em caso de falha, o monitor salva screenshot + HTML em `debug/` — use-os
para descobrir o que mudou.

## Arquitetura

| Módulo | Papel |
|--------|-------|
| `main.py` | CLI, logging, orquestração e loop (ADR-0009) |
| `config.py` | `config.ini` → dataclasses validadas (ADR-0005) |
| `models.py` | dataclasses de domínio, sem dependências |
| `availability.py` | regras de disponibilidade puras (ADR-0004) |
| `report.py` | formatação 🟢/🔴 do relatório |
| `discord.py` | webhook + fragmentação em 2000 chars (ADR-0006) |
| `browser.py` | Chrome/Selenium, esperas, artefatos de debug |
| `login.py` | autenticação e detecção de sessão expirada |
| `scheduler.py` | varredura dia a dia, erros recuperáveis |
| `aircraft.py` | parsing das agendas (aeronaves + Stand By) |
| `utils.py` | parsing puro de texto (horários, datas, sol) |

Decisões registradas em [`docs/adr/`](docs/adr/README.md); requisitos em
[`docs/PRD.md`](docs/PRD.md).

## Testes

```
.venv\Scripts\python -m unittest -v
```

Toda a lógica de negócio roda sem browser (ADR-0004). A camada Selenium é
testada com fakes; nenhum teste abre Chrome nem toca o SAGA real.

## Solução de problemas

- **`TimeoutException: Nenhum seletor visível`** — seletor desatualizado;
  recalibre (seção acima) usando os artefatos de `debug/`.
- **`Nascer do sol não encontrado`** — a página do dia não exibiu o
  horário; o dia é pulado e reportado com ⚠️ (ADR-0008).
- **Nada chega no Discord** — teste o webhook com
  `curl -X POST -H "Content-Type: application/json" -d "{\"content\": \"teste\"}" URL_DO_WEBHOOK`.
- **Sessão expira no meio** — reautenticação é automática (F2); veja o log.

## Limitações conhecidas

- Polling por intervalo, sem notificação em tempo real (fora de escopo).
- Sem histórico entre execuções (sem banco de dados).
- Uma mudança de layout do SAGA exige recalibração manual de seletores.
```

- [ ] **Step 4: Rodar a suíte (garantir que nada quebrou)**

Run: `./.venv/Scripts/python -m unittest`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add config.ini.example README.md
git commit -m "docs(aeroes_monitor): add config template and README with calibration guide" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VPCP9v5BQ8UHvB2F83a6A9"
```

---

### Task 15: Verificação final integrada

**Files:** nenhum novo — só execução e conferência.

**Interfaces:**
- Consumes: tudo.
- Produces: evidência de que o produto atende a spec (gate antes do merge).

- [ ] **Step 1: Suíte completa com contagem**

Run: `./.venv/Scripts/python -m unittest -v`
Expected: TODAS as classes de teste das tasks 2–13 listadas, sumário `OK` (nenhum `FAILED`, nenhum `ERROR`).

- [ ] **Step 2: Compilação de todos os módulos**

Run: `./.venv/Scripts/python -m py_compile models.py utils.py availability.py report.py config.py discord.py browser.py login.py scheduler.py aircraft.py main.py && echo COMPILA-OK`
Expected: `COMPILA-OK`

- [ ] **Step 3: Smokes do CLI (sem browser, sem rede)**

Run: `./.venv/Scripts/python main.py --help`
Expected: ajuda com `--once`/`--config`, exit 0.

Run: `./.venv/Scripts/python main.py --once --config inexistente.ini; echo "exit=$?"`
Expected: mensagem `Erro de configuração:` + `exit=2`.

Run: `./.venv/Scripts/python -c "from config import load_config; load_config('config.ini.example'); print('example ok')"`
Expected: `example ok`

- [ ] **Step 4: Checagem de invariantes da spec**

Run: `grep -n "import selenium\|from selenium\|import requests\|from requests\|import config\|from config" models.py utils.py availability.py report.py; echo "grep-exit=$?"`
Expected: nenhuma linha listada e `grep-exit=1` (camada pura sem dependências — ADR-0004).

Run: `git status --porcelain -- .`
Expected: árvore limpa dentro de `aeroes_monitor/` (nenhum arquivo esquecido sem commit; `config.ini` real NÃO deve existir/aparecer).

- [ ] **Step 5: Conferir o log de commits da branch**

Run: `git log --oneline main..HEAD -- . | head -30`
Expected: ~15 commits pequenos (scaffold → models → utils → availability ×2 → report → config → discord → browser → login → aircraft → scheduler → main → docs), todos com prefixo convencional.

Ao final desta task, **não fazer merge**: informar o resultado e seguir para a skill `superpowers:finishing-a-development-branch` (decisão de merge/PR é do usuário).

---

## Cobertura da spec (rastreabilidade)

| Spec/PRD | Task |
|---|---|
| Modelos §3 | 2 |
| Parsing texto §6/utils | 3 |
| Regras §5 (janela/buffer/vãos/classificação) | 4–5 |
| Relatório §9 (F8) | 6 |
| Config §4 (F4, ADR-0003/0005/0007) | 7 |
| Discord §7 (F9, ADR-0006) | 8 |
| Browser/debug (F10, ADR-0002) | 9 |
| Login/sessão (F1, F2) | 10 |
| Aeronaves + Stand By (F4, F5, ADR-0007) | 11 |
| Varredura multi-dia (F3, F6, F10, ADR-0008) | 12 |
| CLI/loop/log (F11, F12, ADR-0009) | 13 |
| config.ini.example + README (PRD §9, ADR-0001) | 14 |
| Métricas/invariantes (PRD §10) | 15 |

