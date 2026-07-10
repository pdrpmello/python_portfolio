# Relatório só-livres + grade de 30 min — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relatório do Discord lista apenas janelas livres em UMA mensagem, e a janela operacional arredonda nas pontas para a grade :00/:30 (spec `docs/superpowers/specs/2026-07-10-report-layout-design.md`).

**Architecture:** Duas mudanças independentes que se encontram na mensagem final: (1) `availability.operating_window` arredonda início ↑ / fim ↓ na grade de 30 min — muda a disponibilidade real, não só exibição; (2) `report.build_report` vira lista agrupada só de períodos `AVAILABLE` com cabeçalho de contagem, absorvendo `build_summary` (deletada junto com `DiscordNotifier.send_summary`). `main.run_scan` passa a mandar uma única mensagem na baseline.

**Tech Stack:** Python 3.13, unittest (stdlib), sem dependências novas.

## Global Constraints

- Rodar TUDO de dentro de `aeroes_monitor/` (o repo git é o diretório pai `python_portfolio/`).
- Suíte: `.venv\Scripts\python -m unittest -v` (Windows; venv local do projeto).
- Strings de UI em pt-BR EXATAMENTE como escritas aqui (emojis inclusive).
- NUNCA commitar `config.ini` nem `state.json` (já ignorados). O repo raiz tem arquivos alheios não rastreados — stage sempre por caminho explícito, nunca `git add -A` a partir da raiz.
- Mensagens de commit abaixo são o assunto; a sessão acrescenta os trailers dela (Co-Authored-By etc.).
- A grade de arredondamento é 30 min (`:00`/`:30`) — decisão do usuário, não parametrizar (YAGNI).

---

### Task 1: `availability.py` — pontas da janela na grade de 30 min

**Files:**
- Modify: `availability.py` (função `operating_window`, linhas ~53-58, + docstring do módulo linha 3)
- Test: `tests/test_availability.py` (classe `OperatingWindowTest` linhas 22-40; `EnrichDayScheduleTest.test_enriches_all_resources_on_monday` linha ~249)

**Interfaces:**
- Consumes: `_to_minutes(time) -> int`, `_to_time(int) -> time` (já existem em `availability.py`).
- Produces: `operating_window(day: date, sunrise: time, sunset: time) -> TimePeriod | None` (assinatura INALTERADA; comportamento novo: `start = ceil30(sunrise)`, `end = floor30(min(limite, sunset))`, `None` se `start >= end`). Task 4 depende disso indiretamente (janelas reais redondas).

- [ ] **Step 1: Reescrever `OperatingWindowTest` com os casos de arredondamento**

Em `tests/test_availability.py`, substituir a classe `OperatingWindowTest` inteira (linhas 22-40) por:

```python
class OperatingWindowTest(unittest.TestCase):
    def test_weekday_closes_at_0930_and_start_rounds_up(self):
        window = operating_window(MONDAY, SUNRISE, SUNSET)  # 05:45 → 06:00
        self.assertEqual((window.start, window.end), (time(6, 0), time(9, 30)))

    def test_start_already_on_grid_unchanged(self):
        self.assertEqual(operating_window(MONDAY, time(6, 0), SUNSET).start, time(6, 0))

    def test_start_rounding_examples_from_spec(self):
        self.assertEqual(operating_window(MONDAY, time(6, 17), SUNSET).start, time(6, 30))
        self.assertEqual(operating_window(MONDAY, time(5, 47), SUNSET).start, time(6, 0))
        self.assertEqual(operating_window(MONDAY, time(5, 5), SUNSET).start, time(5, 30))

    def test_saturday_closes_at_sunset_rounded_down(self):
        window = operating_window(SATURDAY, SUNRISE, time(17, 23))
        self.assertEqual((window.start, window.end), (time(6, 0), time(17, 0)))
        self.assertEqual(operating_window(SATURDAY, SUNRISE, time(17, 45)).end, time(17, 30))
        self.assertEqual(operating_window(SATURDAY, SUNRISE, time(17, 30)).end, time(17, 30))

    def test_sunday_closes_at_noon(self):
        window = operating_window(SUNDAY, SUNRISE, SUNSET)
        self.assertEqual((window.start, window.end), (time(6, 0), time(12, 0)))

    def test_weekday_sunset_before_0930_wins(self):
        window = operating_window(MONDAY, time(5, 0), time(9, 0))
        self.assertEqual(window.end, time(9, 0))

    def test_no_window_when_sunrise_after_close(self):
        self.assertIsNone(operating_window(MONDAY, time(10, 0), SUNSET))

    def test_no_window_when_rounding_collapses(self):
        # nascer 09:05 arredonda para 09:30 == fechamento de segunda ⇒ sem janela
        self.assertIsNone(operating_window(MONDAY, time(9, 5), SUNSET))
```

Na classe `EnrichDayScheduleTest`, em `test_enriches_all_resources_on_monday`, trocar a linha do assert da janela:

```python
        self.assertEqual(
            (enriched.window.start, enriched.window.end), (time(6, 0), time(9, 30))
        )
```

(era `(SUNRISE, time(9, 30))` — SUNRISE=05:45 agora arredonda para 06:00.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_availability -v`
Expected: FAIL — os testes novos de arredondamento quebram (`05:45 != 06:00` etc.); os demais passam.

- [ ] **Step 3: Implementar o arredondamento**

Em `availability.py`, logo após `_to_time` (linha ~50), acrescentar:

```python
_GRID_MINUTES = 30


def _ceil_to_grid(value: time) -> time:
    minutes = _to_minutes(value)
    remainder = minutes % _GRID_MINUTES
    if remainder:
        minutes += _GRID_MINUTES - remainder
    return _to_time(minutes)


def _floor_to_grid(value: time) -> time:
    minutes = _to_minutes(value)
    return _to_time(minutes - minutes % _GRID_MINUTES)
```

Substituir `operating_window` inteira por:

```python
def operating_window(day: date, sunrise: time, sunset: time) -> TimePeriod | None:
    """Pontas na grade :00/:30 (spec 2026-07-10): início = nascer ↑;
    fim = limite ↓ (só muda algo no sábado — 09:30/12:00 já estão na grade).
    """
    limit = WEEKDAY_CLOSE_LIMITS[day.weekday()]
    end = _floor_to_grid(sunset if limit is None else min(limit, sunset))
    start = _ceil_to_grid(sunrise)
    if start >= end:
        return None
    return TimePeriod(start=start, end=end)
```

No docstring do módulo (linha 3), trocar a frase das janelas por:

```python
"""Regras de disponibilidade. Puro: importa apenas models (ADR-0004).

Janelas por dia da semana (PRD §6): seg–sex nascer→09:30; sáb nascer→pôr;
dom nascer→12:00 — pontas arredondadas na grade de 30 min (início ↑,
fim ↓; spec 2026-07-10). Buffer de turnaround expande voos ocupados antes
do cálculo dos vãos livres; vão livre < duração mínima não é reservável.
"""
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS na suíte INTEIRA — `tests/test_main.py` usa horários já na grade (06:00/17:00, sábado), então não é afetado.

- [ ] **Step 5: Commit**

```bash
git add availability.py tests/test_availability.py
git commit -m "feat(aeroes_monitor): round operating window to 30-min grid"
```

---

### Task 2: relatório só-livres em uma mensagem (`report.py` + `main.py` + `discord.py`)

**Files:**
- Modify: `report.py` (reescrever `build_report`, deletar `build_summary`, helper `_fmt_period`, separador em `build_openings_message`, docstring)
- Modify: `main.py` (import linha 27; ramo baseline linhas 101-103)
- Modify: `discord.py` (deletar `send_summary`, linhas 63-64)
- Test: `tests/test_report.py` (reescrever), `tests/test_main.py` (asserts de `send_summary`), `tests/test_discord.py` (`test_convenience_methods`)

**Interfaces:**
- Consumes: `PeriodStatus.AVAILABLE`, `DayAvailability`, `ScanError` (models); `TimePeriod.duration_minutes() -> int`.
- Produces: `build_report(days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()) -> str` (assinatura INALTERADA, conteúdo novo); `_fmt_period(start: str, end: str) -> str` = `"HH:MM - HH:MM"`; `build_summary` e `DiscordNotifier.send_summary` DEIXAM DE EXISTIR (qualquer referência é erro).

- [ ] **Step 1: Reescrever `tests/test_report.py`**

Substituir o arquivo inteiro por:

```python
"""Testes da formatação das mensagens do Discord (PRD F8, spec 2026-07-10)."""
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
from report import build_openings_message, build_report

MONDAY = date(2026, 7, 13)
TUESDAY = date(2026, 7, 14)


def _entry(start, end, status, reason):
    return ClassifiedPeriod(
        period=TimePeriod(start=start, end=end), status=status, reason=reason
    )


def _day(day=MONDAY, resources=()):
    return DayAvailability(
        day=day,
        sunrise=time(5, 45),
        sunset=time(17, 30),
        window=TimePeriod(start=time(6, 0), end=time(9, 30)),
        resources=tuple(resources),
    )


def _sample_day():
    """Dia com 2 janelas 🟢 (PT-ABC e Stand By) e 1 voo 🔴 no meio."""
    return _day(
        resources=(
            ResourceAvailability(
                resource_name="PT-ABC",
                resource_model="C152",
                periods=(
                    _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                    _entry(time(7, 0), time(8, 0), PeriodStatus.BUSY, "reservado (João)"),
                ),
            ),
            ResourceAvailability(
                resource_name="Stand By",
                resource_model="",
                periods=(
                    _entry(time(6, 0), time(9, 30), PeriodStatus.AVAILABLE, "livre"),
                ),
            ),
        )
    )


class BuildReportTest(unittest.TestCase):
    def test_header_counts_days_and_free_windows(self):
        text = build_report([_sample_day()])
        self.assertTrue(
            text.startswith("✅ **1 dias varridos — 2 janelas livres**"), text
        )

    def test_free_lines_with_spaced_hyphen_and_duration(self):
        text = build_report([_sample_day()])
        self.assertIn("✈️ **PT-ABC** (C152)", text)
        self.assertIn("🟢 06:00 - 07:00 (1h)", text)
        self.assertIn("✈️ **Stand By**", text)
        self.assertNotIn("Stand By** (", text)  # sem modelo → sem parênteses
        self.assertIn("🟢 06:00 - 09:30 (3h30)", text)

    def test_busy_periods_do_not_appear(self):
        text = build_report([_sample_day()])
        self.assertNotIn("🔴", text)
        self.assertNotIn("reservado", text)
        self.assertNotIn("João", text)

    def test_day_header_is_bare_date(self):
        lines = build_report([_sample_day()]).split("\n")
        self.assertIn("📅 **Seg 13/07/2026**", lines)  # linha exata: sem 🌅/🌇/janela
        text = "\n".join(lines)
        self.assertNotIn("🌅", text)
        self.assertNotIn("🌇", text)

    def test_day_without_free_windows_is_omitted(self):
        busy_only = _day(
            day=TUESDAY,
            resources=(
                ResourceAvailability(
                    resource_name="PT-ABC",
                    resource_model="C152",
                    periods=(
                        _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
                    ),
                ),
            ),
        )
        text = build_report([_sample_day(), busy_only])
        self.assertIn("Seg 13/07/2026", text)
        self.assertNotIn("Ter 14/07/2026", text)
        self.assertIn("2 dias varridos", text)  # contagem inclui o dia omitido

    def test_aircraft_without_free_windows_is_omitted(self):
        day = _day(
            resources=(
                ResourceAvailability(
                    resource_name="PT-ABC",
                    resource_model="C152",
                    periods=(
                        _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                    ),
                ),
                ResourceAvailability(
                    resource_name="PT-XYZ",
                    resource_model="C172",
                    periods=(
                        _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
                    ),
                ),
            )
        )
        text = build_report([day])
        self.assertIn("PT-ABC", text)
        self.assertNotIn("PT-XYZ", text)

    def test_blank_line_between_aircraft_blocks(self):
        text = build_report([_sample_day()])
        self.assertIn("🟢 06:00 - 07:00 (1h)\n\n✈️ **Stand By**", text)

    def test_no_free_windows_at_all(self):
        text = build_report([_day(resources=()), _day(day=TUESDAY, resources=())])
        self.assertEqual(text, "✅ **2 dias varridos — nenhuma janela livre. 😕**")

    def test_errors_section(self):
        error = ScanError(day_index=4, day_label="17/07/2026", message="sol ausente")
        text = build_report([_sample_day()], [error])
        self.assertIn("⚠️ **Dias com erro de leitura:**", text)
        self.assertIn("dia 5 (17/07/2026): sol ausente", text)

    def test_errors_section_even_without_free_windows(self):
        error = ScanError(day_index=0, day_label="sol", message="sem sol")
        text = build_report([_day(resources=())], [error])
        self.assertIn("nenhuma janela livre", text)
        self.assertIn("sem sol", text)

    def test_no_errors_no_error_section(self):
        self.assertNotIn("Dias com erro", build_report([_sample_day()]))


class BuildOpeningsMessageTest(unittest.TestCase):
    def test_formats_each_window_with_weekday_and_spaced_hyphen(self):
        text = build_openings_message(
            [
                ("2026-07-11", "PP-AYB", "06:30", "09:30"),
                ("2026-07-12", "Stand By", "07:00", "12:00"),
            ]
        )
        self.assertIn("🔔 **Abriu horário!**", text)
        self.assertIn("🟢 Sáb 11/07/2026: PP-AYB 06:30 - 09:30", text)
        self.assertIn("🟢 Dom 12/07/2026: Stand By 07:00 - 12:00", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Ajustar `tests/test_main.py` e `tests/test_discord.py`**

Em `tests/test_main.py`:

- `test_first_run_sends_baseline_and_saves_state`: apagar a linha `notifier.send_summary.assert_called_once()` (o método deixa de existir; ficam os asserts de `send_report` chamado uma vez e `send_message` não chamado).
- `test_no_changes_is_silent`: apagar a linha `notifier.send_summary.assert_not_called()`.
- `test_new_window_notifies_openings_only`: apagar a linha `notifier.send_summary.assert_not_called()`.

Em `tests/test_discord.py`, substituir `test_convenience_methods` por:

```python
    @mock.patch("discord.requests.post")
    def test_convenience_methods(self, post):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_report("relatório")
        contents = [c.kwargs["json"]["content"] for c in post.call_args_list]
        self.assertEqual(contents, ["relatório"])
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_report -v`
Expected: FAIL — formato antigo não bate (header com contagem ausente, 🔴 presente, `–` em vez de ` - `).

- [ ] **Step 4: Implementar**

Substituir `report.py` inteiro por:

```python
"""Formatação das mensagens do Discord (PRD F8). Importa só models.

O relatório lista APENAS janelas livres (spec 2026-07-10): dia ou
aeronave sem 🟢 não aparece; ocupados e vãos curtos ficam de fora.
"""
from __future__ import annotations

from datetime import date, time
from typing import Iterator, Sequence

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    ScanError,
)

WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def _fmt_time(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m/%Y')}"


def _fmt_period(start: str, end: str) -> str:
    return f"{start} - {end}"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def _free_blocks(
    day: DayAvailability,
) -> Iterator[tuple[ResourceAvailability, list[ClassifiedPeriod]]]:
    for resource in day.resources:
        available = [
            e for e in resource.periods if e.status is PeriodStatus.AVAILABLE
        ]
        if available:
            yield resource, available


def build_report(
    days: Sequence[DayAvailability], errors: Sequence[ScanError] = ()
) -> str:
    day_blocks = [(day, list(_free_blocks(day))) for day in days]
    day_blocks = [(day, blocks) for day, blocks in day_blocks if blocks]
    total = sum(len(available) for _, blocks in day_blocks for _, available in blocks)

    if total == 0:
        lines = [f"✅ **{len(days)} dias varridos — nenhuma janela livre. 😕**"]
    else:
        lines = [f"✅ **{len(days)} dias varridos — {total} janelas livres**"]
        for day, blocks in day_blocks:
            lines.append("")
            lines.append(f"📅 **{_fmt_date(day.day)}**")
            for resource, available in blocks:
                lines.append("")
                title = f"✈️ **{resource.resource_name}**"
                if resource.resource_model:
                    title += f" ({resource.resource_model})"
                lines.append(title)
                for entry in available:
                    period = _fmt_period(
                        _fmt_time(entry.period.start), _fmt_time(entry.period.end)
                    )
                    duration = _fmt_duration(entry.period.duration_minutes())
                    lines.append(f"🟢 {period} ({duration})")
    if errors:
        lines.append("")
        lines.append("⚠️ **Dias com erro de leitura:**")
        for error in errors:
            lines.append(
                f"⚠️ dia {error.day_index + 1} ({error.day_label}): {error.message}"
            )
    return "\n".join(lines)


def build_openings_message(
    new_windows: Sequence[tuple[str, str, str, str]]
) -> str:
    """Aviso enxuto de janelas 🟢 que não existiam na varredura anterior."""
    lines = ["🔔 **Abriu horário!**"]
    for day_iso, resource, start, end in new_windows:
        lines.append(
            f"🟢 {_fmt_date(date.fromisoformat(day_iso))}: {resource} "
            f"{_fmt_period(start, end)}"
        )
    return "\n".join(lines)
```

Em `main.py`:

- Linha 27, trocar o import por: `from report import build_openings_message, build_report`
- Ramo baseline (linhas 101-103), trocar por:

```python
        if previous is None:
            notifier.send_report(build_report(availabilities, result.errors))
```

Em `discord.py`, deletar o método `send_summary` (linhas 63-64):

```python
    def send_summary(self, text: str) -> None:
        self.send_message(text)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS na suíte inteira; `grep`ar por segurança: nenhuma ocorrência de `build_summary`/`send_summary` fora de docs (`git grep -n "build_summary\|send_summary" -- "*.py"` vazio).

- [ ] **Step 6: Commit**

```bash
git add report.py main.py discord.py tests/test_report.py tests/test_main.py tests/test_discord.py
git commit -m "feat(aeroes_monitor): free-only report in a single baseline message"
```

---

### Task 3: config + README

**Files:**
- Modify: `config.ini.example` (seção `[aircraft]`, linhas 40-44)
- Modify: `config.ini` (LOCAL, não versionado — modelos abreviados)
- Modify: `README.md` (Uso; Regras de disponibilidade; Arquitetura)

**Interfaces:**
- Consumes: nada de código.
- Produces: modelos abreviados nos configs; documentação coerente com o comportamento novo. Task 4 assume o `config.ini` local já abreviado.

- [ ] **Step 1: `config.ini.example`** — trocar os exemplos de `[aircraft]`:

```ini
[aircraft]
; Aeronaves monitoradas: MATRICULA = modelo (uma por linha) — ADR-0007.
; Somente estas aparecem no relatório, independente do status no SAGA.
; O modelo é texto livre exibido no relatório — prefira abreviado (C152).
PT-ABC = C152
PT-XYZ = C172
```

- [ ] **Step 2: `config.ini` local (NÃO commitar)** — abreviar os modelos preservando o encoding:

Run:
```
.venv\Scripts\python -c "import pathlib; p = pathlib.Path('config.ini'); s = p.read_text(encoding='utf-8'); p.write_text(s.replace('Cessna 152', 'C152').replace('Cessna 172', 'C172'), encoding='utf-8')"
```

Verificar: `Select-String -Path config.ini -Pattern 'C152|C172'` mostra `PP-AYB = C152` e `PT-JTK = C172`.

- [ ] **Step 3: README** — três edições:

(a) Em "Uso", substituir o parágrafo da baseline por:

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

(b) Em "Regras de disponibilidade (PRD §6)", acrescentar ao final da lista de bullets:

```markdown
- A janela é arredondada na grade de 30 min: começa no nascer do sol
  arredondado para cima (06:17 → 06:30) e, no sábado, termina no pôr do
  sol arredondado para baixo (17:23 → 17:00).
```

(c) Na tabela "Arquitetura", trocar a linha do `report.py` por:

```markdown
| `report.py` | formatação das janelas livres (relatório e aberturas) |
```

- [ ] **Step 4: Commit**

```bash
git add config.ini.example README.md
git commit -m "docs(aeroes_monitor): abbreviated models and free-only report docs"
```

---

### Task 4: Validação ponta a ponta (ambiente real)

**Files:**
- Modify: `state.json` (LOCAL — deletado para re-baseline; ver spec §5: as chaves das janelas mudam com o arredondamento)

- [ ] **Step 1: Suíte completa**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS, 0 falhas.

- [ ] **Step 2: Re-baseline real**

```
Remove-Item state.json
.venv\Scripts\python main.py --once
```

Expected: exit 0; log mostra UMA linha `Mensagem enviada ao Discord` (mensagem única, ~1-2 fragmentos em vez de 1+9); no Discord, cabeçalho `✅ **30 dias varridos — N janelas livres**`, dias só com janelas 🟢, horários redondos (:00/:30), modelos `C152`/`C172`, hífen espaçado.

- [ ] **Step 3: Diff real (silêncio)**

Run: `.venv\Scripts\python main.py --once`
Expected: exit 0; NENHUM `Mensagem enviada` no log; `state.json` atualizado.

- [ ] **Step 4: Confirmar com o usuário** que a mensagem nova chegou legível e no formato aprovado; commit final só se algo do ambiente exigir ajuste documentável.

---

## Self-Review (executado na escrita)

- **Cobertura da spec:** §1 grade→Task 1; §2 relatório/uma mensagem/openings→Task 2; §3 modelos→Task 3; §4 orquestração→Task 2; §5 migração state.json→Task 4 Step 2 + README (Task 3). Sem lacunas.
- **Placeholders:** nenhum TBD/TODO; todo step de código tem o código.
- **Consistência de tipos:** `build_report` mantém assinatura consumida por `main.py`; `_fmt_period(start: str, end: str)` usado nos dois pontos; `test_main` não referencia mais `send_summary` (método deletado no mesmo task).
- **Riscos checados:** `test_main._scan_result` usa 06:00/17:00 (sábado, na grade) — Task 1 não quebra `test_main`; deleção de `build_summary` e ajuste do import de `main.py` acontecem no MESMO task/commit (sem estado intermediário quebrado).
