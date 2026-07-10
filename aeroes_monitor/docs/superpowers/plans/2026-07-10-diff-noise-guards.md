# Guardas anti-ruído no diff de aberturas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "🔔 Abriu horário!" só para abertura genuína: dia recém-entrado no horizonte e janela que apenas encolheu deixam de notificar (spec `docs/superpowers/specs/2026-07-10-diff-noise-guards-design.md`).

**Architecture:** `diff_new_windows` ganha duas guardas puras: (1) só dias varridos com sucesso na varredura anterior — o que exige gravar os dias no snapshot (`NotifyState.days`, `state.json` v2; sem isso, dia 100% lotado que abre vaga seria silenciado); (2) janela contida numa janela livre anterior do mesmo dia+aeronave não é novidade. `main.run_scan` passa o `NotifyState` inteiro ao diff e grava os dias varridos; state v1 vira baseline automática (caminho de versão desconhecida já existente).

**Tech Stack:** Python 3.13, unittest (stdlib), sem dependências novas.

## Global Constraints

- Rodar TUDO de dentro de `aeroes_monitor/` (o repo git é o diretório pai `python_portfolio/`).
- Suíte: `.venv\Scripts\python -m unittest -v` (Windows; venv local do projeto).
- Strings de UI em pt-BR EXATAMENTE como escritas aqui (emojis inclusive).
- NUNCA commitar `config.ini` nem `state.json` (já ignorados). O repo raiz tem arquivos alheios não rastreados — stage sempre por caminho explícito, nunca `git add -A` a partir da raiz.
- Mensagens de commit abaixo são o assunto; a sessão acrescenta os trailers dela (Co-Authored-By etc.).
- `NotifyState.days` é obrigatório, SEM default — decisão da spec (default vazio silenciaria tudo em silêncio); não "melhorar".
- Horários `"HH:MM"` zero-padded comparam por string (ordem lexicográfica = numérica); não converter para minutos.

---

### Task 1: guardas + state v2 (`notifications.py` + `main.py`)

**Files:**
- Modify: `notifications.py` (reescrever: docstring, `STATE_VERSION`, `NotifyState`, novo `extract_scanned_days`, novo `_is_covered`, `diff_new_windows`, `load_state`, `save_state`)
- Modify: `main.py` (import linhas 20-26; `_save_failure_state` linhas 73-76; chamadas do diff e do save linhas 106 e 109)
- Test: `tests/test_notifications.py` (reescrever), `tests/test_main.py` (2 edições)

**Interfaces:**
- Consumes: `DayAvailability`, `PeriodStatus` (models) — inalterados.
- Produces: `NotifyState(windows: frozenset[WindowKey], days: frozenset[str], last_scan_ok: bool = True)`; `extract_scanned_days(days: Sequence[DayAvailability]) -> frozenset[str]`; `diff_new_windows(previous: NotifyState, current: frozenset[WindowKey]) -> tuple[WindowKey, ...]` (ANTES recebia `frozenset` como 1º arg — qualquer chamador antigo é erro); `STATE_VERSION = 2`. `report.py`, `discord.py`, `availability.py`: intocados.

- [ ] **Step 1: Reescrever `tests/test_notifications.py`**

Substituir o arquivo inteiro por:

```python
"""Testes da política de notificação por diff (specs 2026-07-09 e 2026-07-10)."""
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
    extract_scanned_days,
    load_state,
    save_state,
)

W_MORNING = ("2026-07-11", "PP-AYB", "06:00", "09:30")


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


def _state(windows=(), days=("2026-07-11", "2026-07-12"), last_scan_ok=True):
    return NotifyState(
        windows=frozenset(windows), days=frozenset(days), last_scan_ok=last_scan_ok
    )


class ExtractTest(unittest.TestCase):
    def test_only_available_periods_become_keys(self):
        windows = extract_open_windows([_day()])
        self.assertEqual(windows, frozenset({W_MORNING}))

    def test_scanned_days_are_iso_dates(self):
        self.assertEqual(extract_scanned_days([_day()]), frozenset({"2026-07-11"}))


class DiffTest(unittest.TestCase):
    def test_new_windows_detected_sorted(self):
        previous = _state(windows={W_MORNING})
        current = frozenset(
            {
                W_MORNING,
                ("2026-07-12", "PT-JTK", "07:00", "09:00"),
                ("2026-07-11", "PP-AYB", "14:00", "16:00"),
            }
        )
        self.assertEqual(
            diff_new_windows(previous, current),
            (
                ("2026-07-11", "PP-AYB", "14:00", "16:00"),
                ("2026-07-12", "PT-JTK", "07:00", "09:00"),
            ),
        )

    def test_removed_windows_are_silent(self):
        self.assertEqual(diff_new_windows(_state(windows={W_MORNING}), frozenset()), ())

    def test_day_new_to_horizon_is_silent(self):
        previous = _state(windows={W_MORNING}, days=("2026-07-11",))
        current = frozenset({W_MORNING, ("2026-08-10", "PP-AYB", "06:00", "09:30")})
        self.assertEqual(diff_new_windows(previous, current), ())

    def test_scanned_day_without_windows_notifies_when_it_opens(self):
        """Dia lotado ontem (varrido, zero 🟢) que abre vaga: NOTIFICA."""
        previous = _state(windows=(), days=("2026-07-11",))
        self.assertEqual(
            diff_new_windows(previous, frozenset({W_MORNING})), (W_MORNING,)
        )

    def test_shrunken_window_is_silent(self):
        previous = _state(windows={W_MORNING})
        current = frozenset({("2026-07-11", "PP-AYB", "08:30", "09:30")})
        self.assertEqual(diff_new_windows(previous, current), ())

    def test_grown_window_notifies(self):
        previous = _state(windows={("2026-07-11", "PP-AYB", "08:00", "09:30")})
        self.assertEqual(
            diff_new_windows(previous, frozenset({W_MORNING})), (W_MORNING,)
        )

    def test_partially_shifted_window_notifies(self):
        previous = _state(windows={("2026-07-11", "PP-AYB", "06:00", "08:00")})
        current = frozenset({("2026-07-11", "PP-AYB", "07:00", "09:00")})
        self.assertEqual(
            diff_new_windows(previous, current),
            (("2026-07-11", "PP-AYB", "07:00", "09:00"),),
        )

    def test_containment_requires_same_day_and_resource(self):
        previous = _state(
            windows={
                ("2026-07-11", "PP-AYB", "06:00", "09:30"),
                ("2026-07-12", "PT-JTK", "06:00", "12:00"),
            }
        )
        current = frozenset(
            {
                ("2026-07-11", "PT-JTK", "07:00", "08:30"),  # outra aeronave
                ("2026-07-12", "PP-AYB", "07:00", "08:30"),  # outro dia
            }
        )
        self.assertEqual(
            diff_new_windows(previous, current),
            (
                ("2026-07-11", "PT-JTK", "07:00", "08:30"),
                ("2026-07-12", "PP-AYB", "07:00", "08:30"),
            ),
        )


class StatePersistenceTest(unittest.TestCase):
    def test_roundtrip(self):
        state = NotifyState(
            windows=frozenset({W_MORNING}),
            days=frozenset({"2026-07-11", "2026-07-12"}),
            last_scan_ok=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            save_state(path, state)
            self.assertEqual(load_state(path), state)

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_state(Path("nao_existe_state_9x8.json")))

    def test_v1_state_is_baseline(self):
        """Migração: state antigo (v1, sem days) vira baseline automática."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                '{"version": 1, "windows": [["2026-07-11", "PP-AYB", "06:00", "09:30"]],'
                ' "last_scan_ok": true}',
                encoding="utf-8",
            )
            with self.assertLogs("notifications", level="WARNING"):
                self.assertIsNone(load_state(path))

    def test_corrupted_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{isso não é json", encoding="utf-8")
            with self.assertLogs("notifications", level="WARNING"):
                self.assertIsNone(load_state(path))
            path.write_text('{"version": 99, "windows": []}', encoding="utf-8")
            with self.assertLogs("notifications", level="WARNING"):
                self.assertIsNone(load_state(path))

    def test_wrong_shape_json_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            for payload in ("null", "[]", "42", "true", '"texto"'):
                path.write_text(payload, encoding="utf-8")
                with self.assertLogs("notifications", level="WARNING"):
                    self.assertIsNone(load_state(path))
            bad_payloads = (
                # janela com 3 partes
                '{"version": 2, "windows": [["2026-07-11", "PP-AYB", "06:00"]],'
                ' "days": ["2026-07-11"], "last_scan_ok": true}',
                # janela com partes não-string
                '{"version": 2, "windows": [[1, 2, 3, 4]],'
                ' "days": ["2026-07-11"], "last_scan_ok": true}',
                # days não é lista
                '{"version": 2, "windows": [], "days": "2026-07-11",'
                ' "last_scan_ok": true}',
                # days com item não-string
                '{"version": 2, "windows": [], "days": [20260711],'
                ' "last_scan_ok": true}',
                # sem days
                '{"version": 2, "windows": [], "last_scan_ok": true}',
            )
            for payload in bad_payloads:
                path.write_text(payload, encoding="utf-8")
                with self.assertLogs("notifications", level="WARNING"):
                    self.assertIsNone(load_state(path))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Ajustar `tests/test_main.py` (2 edições)**

(a) Em `test_first_run_sends_baseline_and_saves_state`, após a linha `self.assertEqual(len(state.windows), 1)`, acrescentar:

```python
        self.assertEqual(state.days, frozenset({"2026-07-11"}))
```

(b) Em `test_recovery_notifies_and_diffs_against_preserved_windows`, o `NotifyState` seedado ganha `days` (o dia da janela preservada):

```python
        save_state(
            self.state_path,
            NotifyState(
                windows=frozenset({("2026-07-11", "PT-ABC", "06:00", "17:00")}),
                days=frozenset({"2026-07-11"}),
                last_scan_ok=False,
            ),
        )
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_notifications tests.test_main -v`
Expected: FAIL/ERROR — `extract_scanned_days` não existe (ImportError) OU, se importar parcial, `NotifyState` não aceita `days` (TypeError) e `diff_new_windows` não aceita `NotifyState` como 1º arg.

- [ ] **Step 4: Reescrever `notifications.py`**

Substituir o arquivo inteiro por:

```python
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
```

- [ ] **Step 5: Ajustar `main.py` (4 edições)**

(a) Import de notifications (linhas 20-26) ganha `extract_scanned_days`:

```python
from notifications import (
    NotifyState,
    diff_new_windows,
    extract_open_windows,
    extract_scanned_days,
    load_state,
    save_state,
)
```

(b) `_save_failure_state` (linhas 73-76) preserva `days`:

```python
def _save_failure_state(state_path, previous) -> None:
    """Preserva janelas conhecidas; sem state prévio, baseline fica pendente."""
    if previous is not None:
        save_state(
            state_path,
            NotifyState(
                windows=previous.windows, days=previous.days, last_scan_ok=False
            ),
        )
```

(c) Chamada do diff (linha 106) passa o estado inteiro:

```python
            new_windows = diff_new_windows(previous, windows)
```

(d) Gravação do estado (linha 109) ganha os dias varridos:

```python
        save_state(
            state_path,
            NotifyState(
                windows=windows,
                days=extract_scanned_days(availabilities),
                last_scan_ok=True,
            ),
        )
```

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS na suíte INTEIRA. Em especial `test_new_window_notifies_openings_only` (dia lotado que abre — prova do campo `days`) e `test_recovery_notifies_and_diffs_against_preserved_windows` (recuperação diffa contra snapshot preservado) continuam verdes.

- [ ] **Step 7: Commit**

```bash
git add notifications.py main.py tests/test_notifications.py tests/test_main.py
git commit -m "feat(aeroes_monitor): noise guards in openings diff (state v2)"
```

---

### Task 2: README

**Files:**
- Modify: `README.md` (parágrafo da política, linhas 49-56)

**Interfaces:**
- Consumes: nada de código.
- Produces: documentação coerente com as guardas; nenhum task depende.

- [ ] **Step 1: Substituir o parágrafo da baseline/política**

Trocar o parágrafo (linhas 49-56):

```markdown
A primeira varredura estabelece a **baseline**: envia UMA mensagem com as
janelas livres dos próximos dias (dias e aeronaves sem janela 🟢 ficam de
fora) e grava o snapshot em `state.json` (não versionado). Das varreduras
seguintes em diante vale a política "**só aberturas novas**": o Discord só
recebe mensagem quando surge uma janela 🟢 que não existia no snapshot
anterior — janela que some é silêncio. Apague `state.json` para forçar uma
nova baseline (faça isso também após atualizar o monitor, se a regra ou o
formato das janelas mudou — evita um falso "🔔 Abriu horário!").
```

por:

```markdown
A primeira varredura estabelece a **baseline**: envia UMA mensagem com as
janelas livres dos próximos dias (dias e aeronaves sem janela 🟢 ficam de
fora) e grava o snapshot em `state.json` (não versionado). Das varreduras
seguintes em diante vale a política "**só aberturas novas**": o Discord só
recebe mensagem quando surge uma janela 🟢 que não existia no snapshot
anterior — janela que some é silêncio. Duas guardas anti-ruído: dia que
acabou de entrar no horizonte de varredura não conta como abertura, e
janela que apenas **encolheu** (alguém reservou um pedaço dela) também
não — só janela com tempo novo de verdade notifica. Apague `state.json`
para forçar uma nova baseline manualmente; quando o formato do snapshot
muda numa atualização do monitor, a versão do arquivo re-baselineia
sozinha (um relatório completo novo, sem alarme falso).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(aeroes_monitor): document diff noise guards in README"
```

---

### Task 3: Validação ponta a ponta (ambiente real)

**Files:**
- Modify: `state.json` (LOCAL — hoje está em v1; a execução migra sozinha para v2. NÃO apagar na mão: a migração automática é parte do que se valida.)

- [ ] **Step 1: Suíte completa**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS, 0 falhas.

- [ ] **Step 2: Confirmar que o state local está em v1**

Run: `Select-String -Path state.json -Pattern '"version"'`
Expected: `"version": 1`. (Se já estiver em 2, alguém rodou antes — pular para o Step 4.)

- [ ] **Step 3: Migração automática v1 → baseline**

Run: `.venv\Scripts\python main.py --once`
Expected: exit 0; log tem `state.json com versão desconhecida; tratando como baseline` e UMA linha `Mensagem enviada ao Discord` (relatório baseline, ~1-2 fragmentos); `state.json` novo com `"version": 2` e campo `"days"` com ~30 datas ISO (`Select-String -Path state.json -Pattern '"version"|"days"'`).

- [ ] **Step 4: Silêncio no diff imediato**

Run: `.venv\Scripts\python main.py --once`
Expected: exit 0; NENHUM `Mensagem enviada` no log; `state.json` continua v2.

- [ ] **Step 5: Confirmar com o usuário** que a baseline nova chegou no Discord e que dali em diante só aberturas genuínas notificam; commit adicional só se o ambiente exigir ajuste documentável.

---

## Self-Review (executado na escrita)

- **Cobertura da spec:** §1 guarda de dias→Task 1 (`diff_new_windows` + teste horizonte); §2 state v2/`days`/migração→Task 1 (`STATE_VERSION`, `load_state`, `save_state`, teste v1-baseline) + Task 3 Steps 2-3; §3 subconjunto→Task 1 (`_is_covered` + testes encolhida/crescida/deslocada/mesmo dia+aeronave); §4 interfaces→Task 1 Steps 4-5; §5 comportamentos aceitos→sem código (documentados na spec) + README (Task 2). Sem lacunas.
- **Placeholders:** nenhum TBD/TODO; todo step de código tem o código completo.
- **Consistência de tipos:** `diff_new_windows(previous: NotifyState, current)` usada igual em Task 1 Step 1 (testes), Step 4 (impl) e Step 5c (main); `extract_scanned_days` importada nos testes, definida na impl e usada no main; fixtures de shape usam `"version": 2` (senão falhariam pela versão, não pelo shape).
- **Riscos checados:** `NotifyState.days` sem default quebra QUALQUER construção esquecida em tempo de teste (TypeError) — é o comportamento desejado; `test_main` só constrói `NotifyState` direto no teste de recuperação (Step 2b cobre); os demais passam por `run_scan`/`save_state` (Step 5 cobre); ordem dos campos (`days` antes de `last_scan_ok`, que tem default) é exigência de dataclass.
