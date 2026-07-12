# Relatório em tabela monoespaçada — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relatório e aviso de aberturas do Discord em tabelas monoespaçadas (blocos ```), com fragmentação que nunca quebra um bloco no meio (spec `docs/superpowers/specs/2026-07-10-table-report-design.md`).

**Architecture:** Duas mudanças em sequência: (1) `discord.split_message` vira fence-aware — corte dentro de um bloco fecha a cerca e reabre no fragmento seguinte (fundação independente; sem ela, o relatório de ~43 janelas fragmentaria com markdown quebrado); (2) `report.build_report` troca as linhas ✈️/🟢 por um bloco-tabela por dia e `build_openings_message` vira tabela única ganhando `models` na assinatura (a `WindowKey` não carrega modelo) — `main.py` passa `config.aircraft` na mesma leva/commit.

**Tech Stack:** Python 3.13, unittest (stdlib), sem dependências novas.

## Global Constraints

- Rodar TUDO de dentro de `aeroes_monitor/` (o repo git é o diretório pai `python_portfolio/`).
- Suíte: `.venv\Scripts\python -m unittest -v` (Windows; venv local do projeto).
- Strings de UI em pt-BR EXATAMENTE como escritas aqui (emojis inclusive); emojis SEMPRE fora dos blocos ``` (dentro perdem a cor no Discord).
- Padding e gaps das tabelas exatamente como nos testes: célula de nome preenchida à esquerda até a maior célula da mensagem, gap de 2 espaços entre colunas.
- NUNCA commitar `config.ini` nem `state.json` (já ignorados). Stage sempre por caminho explícito, nunca `git add -A` a partir da raiz.
- Mensagens de commit abaixo são o assunto; a sessão acrescenta os trailers dela (Co-Authored-By etc.).

---

### Task 1: `split_message` fence-aware (`discord.py`)

**Files:**
- Modify: `discord.py` (constantes + reescrever `split_message`, linhas 16-41)
- Test: `tests/test_discord.py` (2 métodos novos em `SplitMessageTest`)

**Interfaces:**
- Consumes: nada novo.
- Produces: `split_message(text: str, limit: int = 2000) -> list[str]` (assinatura INALTERADA; invariante nova: todo fragmento tem número PAR de linhas-cerca ` ``` `; fragmento que continua um bloco começa com ` ``` `). Task 2 depende disso para o relatório fragmentado renderizar.

- [ ] **Step 1: Testes novos em `tests/test_discord.py`**

Acrescentar ao FINAL da classe `SplitMessageTest` (após `test_empty_text`, linha 38):

```python
    def test_fenced_block_reopens_across_chunks(self):
        rows = "\n".join(f"linha-{i:02d}" for i in range(6))
        text = f"cabeçalho\n```\n{rows}\n```"
        chunks = split_message(text, limit=30)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertEqual(chunk.count("```") % 2, 0, chunk)
            self.assertLessEqual(len(chunk), 30)
        self.assertTrue(chunks[1].startswith("```\n"))
        joined = "\n".join(chunks)
        for i in range(6):
            self.assertIn(f"linha-{i:02d}", joined)  # nenhuma linha perdida

    def test_fenced_block_that_fits_is_untouched(self):
        text = "📅 dia\n```\nlinha\n```"
        self.assertEqual(split_message(text, limit=100), [text])
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_discord -v`
Expected: FAIL — `test_fenced_block_reopens_across_chunks` quebra (fragmento com número ímpar de cercas e/ou segundo fragmento não começa com ` ``` `); `test_fenced_block_that_fits_is_untouched` já passa.

- [ ] **Step 3: Implementar**

Em `discord.py`, substituir o trecho das constantes + `split_message` (linhas 16-41) por:

```python
DISCORD_MESSAGE_LIMIT = 2000
_CHUNK_PAUSE_SECONDS = 0.5
_FENCE = "```"
# Reserva para o fechamento "\n```" caber quando o corte cai dentro de um bloco.
_FENCE_RESERVE = len("\n" + _FENCE)


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Fragmenta preservando quebras de linha e cercas ``` balanceadas:
    corte dentro de um bloco fecha a cerca no fragmento e a reabre no
    seguinte (linha exatamente ``` alterna o estado; o gerador só emite
    cercas nuas). Corte duro só quando uma única linha excede o limite
    (não ocorre com o gerador; aí as cercas ficam por conta do chamador).
    Nunca produz chunk vazio."""
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    in_fence = False
    for line in text.split("\n"):
        line_in_fence = in_fence != (line == _FENCE)  # estado APÓS esta linha
        reserve = _FENCE_RESERVE if line_in_fence else 0
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit - reserve:
            if current:
                chunks.append(f"{current}\n{_FENCE}" if in_fence else current)
                current = _FENCE if in_fence else ""
                candidate = f"{current}\n{line}" if current else line
            while len(candidate) > limit - reserve:
                chunks.append(candidate[:limit])
                candidate = candidate[limit:]
        current = candidate
        in_fence = line_in_fence
    if current:
        chunks.append(current)
    return chunks
```

(A acumulação com `reserve` garante que `current` cabe no limite mesmo
recebendo o `\n``` ` de fechamento; quando a linha fecha o bloco, a
reserva zera e o fragmento pode usar o limite cheio.)

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS na suíte INTEIRA — os 6 testes antigos de `split_message` não usam cercas e mantêm o comportamento (agrupamento por linhas, corte duro, sem chunk vazio).

- [ ] **Step 5: Commit**

```bash
git add discord.py tests/test_discord.py
git commit -m "feat(aeroes_monitor): fence-aware Discord message splitting"
```

---

### Task 2: tabelas no relatório e nas aberturas (`report.py` + `main.py`)

**Files:**
- Modify: `report.py` (reescrever: docstring, `FENCE`, `_fmt_short_date`, `_name_cell`, `build_report`, `build_openings_message`)
- Modify: `main.py` (linha da chamada `build_openings_message`, ~108)
- Test: `tests/test_report.py` (reescrever), `tests/test_main.py` (1 assert novo)

**Interfaces:**
- Consumes: `split_message` fence-aware (Task 1) — indiretamente, via envio.
- Produces: `build_report(days, errors=()) -> str` (assinatura INALTERADA, corpo em tabelas); `build_openings_message(new_windows: Sequence[tuple[str, str, str, str]], models: Mapping[str, str]) -> str` (PARÂMETRO NOVO obrigatório `models`; chamador antigo com 1 argumento é erro). `main.py` passa `config.aircraft` (dict matrícula→modelo).

- [ ] **Step 1: Reescrever `tests/test_report.py`**

Substituir o arquivo inteiro por:

```python
"""Testes da formatação das mensagens do Discord (PRD F8, spec tabela 2026-07-10)."""
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


def _resource(name, model, *periods):
    return ResourceAvailability(
        resource_name=name, resource_model=model, periods=tuple(periods)
    )


def _sample_day():
    """Dia com 2 janelas 🟢 (PT-ABC e Stand By) e 1 voo 🔴 no meio."""
    return _day(
        resources=(
            _resource(
                "PT-ABC",
                "C152",
                _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                _entry(time(7, 0), time(8, 0), PeriodStatus.BUSY, "reservado (João)"),
            ),
            _resource(
                "Stand By",
                "",
                _entry(time(6, 0), time(9, 30), PeriodStatus.AVAILABLE, "livre"),
            ),
        )
    )


class BuildReportTest(unittest.TestCase):
    def test_full_layout_single_day(self):
        expected = (
            "✅ **1 dias varridos — 2 janelas livres**\n"
            "\n"
            "📅 **Seg 13/07/2026**\n"
            "```\n"
            "PT-ABC C152  06:00 - 07:00  1h\n"
            "Stand By     06:00 - 09:30  3h30\n"
            "```"
        )
        self.assertEqual(build_report([_sample_day()]), expected)

    def test_no_list_emojis_in_body(self):
        text = build_report([_sample_day()])
        self.assertNotIn("✈️", text)
        self.assertNotIn("🟢", text)

    def test_busy_periods_do_not_appear(self):
        text = build_report([_sample_day()])
        self.assertNotIn("🔴", text)
        self.assertNotIn("reservado", text)
        self.assertNotIn("João", text)

    def test_day_header_is_bare_date_outside_fence(self):
        lines = build_report([_sample_day()]).split("\n")
        index = lines.index("📅 **Seg 13/07/2026**")
        self.assertEqual(lines[index + 1], "```")
        text = "\n".join(lines)
        self.assertNotIn("🌅", text)
        self.assertNotIn("🌇", text)

    def test_no_blank_line_between_days_and_global_width(self):
        day1 = _day(
            resources=(
                _resource(
                    "Stand By",
                    "",
                    _entry(time(6, 0), time(9, 30), PeriodStatus.AVAILABLE, "livre"),
                ),
            )
        )
        day2 = _day(
            day=TUESDAY,
            resources=(
                _resource(
                    "PT-ABC",
                    "C152",
                    _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                ),
            ),
        )
        text = build_report([day1, day2])
        self.assertIn("```\n📅 **Ter 14/07/2026**", text)  # sem linha em branco
        # largura global: "Stand By" preenchido até len("PT-ABC C152") = 11
        self.assertIn("Stand By     06:00 - 09:30  3h30", text)

    def test_day_without_free_windows_is_omitted(self):
        busy_only = _day(
            day=TUESDAY,
            resources=(
                _resource(
                    "PT-ABC",
                    "C152",
                    _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
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
                _resource(
                    "PT-ABC",
                    "C152",
                    _entry(time(6, 0), time(7, 0), PeriodStatus.AVAILABLE, "livre"),
                ),
                _resource(
                    "PT-XYZ",
                    "C172",
                    _entry(time(6, 0), time(9, 30), PeriodStatus.BUSY, "reservado"),
                ),
            )
        )
        text = build_report([day])
        self.assertIn("PT-ABC", text)
        self.assertNotIn("PT-XYZ", text)

    def test_no_free_windows_at_all(self):
        text = build_report([_day(resources=()), _day(day=TUESDAY, resources=())])
        self.assertEqual(text, "✅ **2 dias varridos — nenhuma janela livre. 😕**")

    def test_errors_section_outside_fence(self):
        error = ScanError(day_index=4, day_label="17/07/2026", message="sol ausente")
        text = build_report([_sample_day()], [error])
        self.assertIn("```\n\n⚠️ **Dias com erro de leitura:**", text)
        self.assertIn("dia 5 (17/07/2026): sol ausente", text)

    def test_errors_section_even_without_free_windows(self):
        error = ScanError(day_index=0, day_label="sol", message="sem sol")
        text = build_report([_day(resources=())], [error])
        self.assertIn("nenhuma janela livre", text)
        self.assertIn("sem sol", text)

    def test_no_errors_no_error_section(self):
        self.assertNotIn("Dias com erro", build_report([_sample_day()]))


class BuildOpeningsMessageTest(unittest.TestCase):
    def test_table_with_short_day_and_models(self):
        text = build_openings_message(
            [
                ("2026-07-11", "PP-AYB", "06:30", "09:30"),
                ("2026-07-12", "Stand By", "07:00", "12:00"),
            ],
            {"PP-AYB": "C152", "PT-JTK": "C172"},
        )
        expected = (
            "🔔 **Abriu horário!**\n"
            "```\n"
            "Sáb 11/07  PP-AYB C152  06:30 - 09:30\n"
            "Dom 12/07  Stand By     07:00 - 12:00\n"
            "```"
        )
        self.assertEqual(text, expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Assert novo em `tests/test_main.py`**

Em `test_new_window_notifies_openings_only`, logo após a linha
`self.assertIn("Abriu horário", notifier.send_message.call_args.args[0])`,
acrescentar:

```python
        self.assertIn("PT-ABC C-152", notifier.send_message.call_args.args[0])
```

(a fixture `_config()` tem `aircraft={"PT-ABC": "C-152"}` — prova que
`main.py` passa `config.aircraft` para a mensagem de aberturas.)

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_report tests.test_main -v`
Expected: FAIL/ERROR — formato antigo (✈️/🟢) não bate com as tabelas; `build_openings_message` não aceita 2º argumento (TypeError); assert de `PT-ABC C-152` falha.

- [ ] **Step 4: Reescrever `report.py`**

Substituir o arquivo inteiro por:

```python
"""Formatação das mensagens do Discord (PRD F8). Importa só models.

O relatório lista APENAS janelas livres, em tabelas monoespaçadas por
dia (specs 2026-07-10): dia ou aeronave sem 🟢 não aparece; ocupados e
vãos curtos ficam de fora. Emojis ficam FORA dos blocos ``` (dentro
perdem a renderização colorida do Discord).
"""
from __future__ import annotations

from datetime import date, time
from typing import Iterator, Mapping, Sequence

from models import (
    ClassifiedPeriod,
    DayAvailability,
    PeriodStatus,
    ResourceAvailability,
    ScanError,
)

WEEKDAY_ABBR = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
FENCE = "```"


def _fmt_time(value: time) -> str:
    return value.strftime("%H:%M")


def _fmt_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m/%Y')}"


def _fmt_short_date(value: date) -> str:
    return f"{WEEKDAY_ABBR[value.weekday()]} {value.strftime('%d/%m')}"


def _fmt_period(start: str, end: str) -> str:
    return f"{start} - {end}"


def _fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h{mins:02d}"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def _name_cell(name: str, model: str) -> str:
    return f"{name} {model}" if model else name


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
        width = max(
            len(_name_cell(resource.resource_name, resource.resource_model))
            for _, blocks in day_blocks
            for resource, _ in blocks
        )
        lines = [f"✅ **{len(days)} dias varridos — {total} janelas livres**", ""]
        for day, blocks in day_blocks:
            lines.append(f"📅 **{_fmt_date(day.day)}**")
            lines.append(FENCE)
            for resource, available in blocks:
                cell = _name_cell(resource.resource_name, resource.resource_model)
                for entry in available:
                    period = _fmt_period(
                        _fmt_time(entry.period.start), _fmt_time(entry.period.end)
                    )
                    duration = _fmt_duration(entry.period.duration_minutes())
                    lines.append(f"{cell:<{width}}  {period}  {duration}")
            lines.append(FENCE)
    if errors:
        lines.append("")
        lines.append("⚠️ **Dias com erro de leitura:**")
        for error in errors:
            lines.append(
                f"⚠️ dia {error.day_index + 1} ({error.day_label}): {error.message}"
            )
    return "\n".join(lines)


def build_openings_message(
    new_windows: Sequence[tuple[str, str, str, str]],
    models: Mapping[str, str],
) -> str:
    """Aviso de janelas 🟢 novas: tabela única, dia curto sem ano; o
    modelo vem de `models` (a WindowKey não o carrega)."""
    cells = [
        _name_cell(resource, models.get(resource, ""))
        for _, resource, _, _ in new_windows
    ]
    width = max(len(cell) for cell in cells)
    lines = ["🔔 **Abriu horário!**", FENCE]
    for (day_iso, _, start, end), cell in zip(new_windows, cells):
        lines.append(
            f"{_fmt_short_date(date.fromisoformat(day_iso))}  "
            f"{cell:<{width}}  {_fmt_period(start, end)}"
        )
    lines.append(FENCE)
    return "\n".join(lines)
```

- [ ] **Step 5: Ajustar `main.py` (1 linha)**

Trocar:

```python
                notifier.send_message(build_openings_message(new_windows))
```

por:

```python
                notifier.send_message(
                    build_openings_message(new_windows, config.aircraft)
                )
```

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS na suíte INTEIRA.

- [ ] **Step 7: Commit**

```bash
git add report.py main.py tests/test_report.py tests/test_main.py
git commit -m "feat(aeroes_monitor): table-style report and openings messages"
```

---

### Task 3: Validação ponta a ponta (ambiente real)

**Files:**
- Modify: `state.json` (LOCAL — deletado para re-baseline: as chaves NÃO mudaram, mas sem baseline nova não há mensagem para ver o formato; com ~43 janelas o relatório fragmenta e exercita as cercas balanceadas no Discord real)

- [ ] **Step 1: Suíte completa**

Run: `.venv\Scripts\python -m unittest -v`
Expected: PASS, 0 falhas.

- [ ] **Step 2: Re-baseline real com tabelas**

```
Remove-Item state.json -Confirm:$false
.venv\Scripts\python main.py --once
```

Expected: exit 0; UMA linha `Mensagem enviada ao Discord (N fragmento(s))`; no Discord, cabeçalho ✅, dias 📅 fora dos blocos, tabelas monoespaçadas alinhadas, TODO fragmento com blocos fechados (nenhum ``` órfão/aberto na emenda entre fragmentos); `state.json` recriado com `"version": 2`.

- [ ] **Step 3: Silêncio no diff imediato**

Run: `.venv\Scripts\python main.py --once`
Expected: exit 0; NENHUM `Mensagem enviada` no log.

- [ ] **Step 4: Confirmar com o usuário** que as tabelas chegaram alinhadas (desktop e celular) e as emendas entre fragmentos estão limpas; commit adicional só se o ambiente exigir ajuste documentável.

---

## Self-Review (executado na escrita)

- **Cobertura da spec:** §1 tabela por dia→Task 2 (`build_report` + `test_full_layout_single_day`, largura global, sem linha em branco entre dias, omissões, zero-janelas, erros fora de cerca); §2 aberturas→Task 2 (`build_openings_message` + `models` + dia curto + `main.py`); §3 split fence-aware→Task 1; §4 sem migração→Task 3 explica por que o delete manual mesmo assim (ver formato). Sem lacunas.
- **Placeholders:** nenhum TBD/TODO; todo step de código tem o código completo.
- **Consistência de tipos:** `build_openings_message(new_windows, models)` igual nos testes (Step 1), impl (Step 4) e main (Step 5); larguras dos testes conferidas na mão (`PT-ABC C152`/`PP-AYB C152` = 11 chars ⇒ `Stand By` + 3 de pad + 2 de gap = 5 espaços antes do horário); `_FENCE` local em `discord.py` e `FENCE` local em `report.py` (sem import cruzado — report importa só models, ADR-0004).
- **Riscos checados:** os 6 testes antigos de `split_message` não usam cercas — comportamento preservado (traçado caso a caso); `zip(new_windows, cells)` alinhado por construção; `max()` de `build_openings_message` nunca vê sequência vazia (main só chama com `new_windows` truthy); a acumulação com reserva garante `current + "\n```" ≤ limit` em qualquer flush dentro de bloco.
