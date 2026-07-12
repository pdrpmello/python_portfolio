# Design: guardas anti-ruído no diff de aberturas

**Data:** 2026-07-10 · **Status:** aprovado pelo usuário (conversa de 2026-07-10)

## Objetivo

A política "só aberturas novas" (spec 2026-07-09) é um diff de conjuntos:
`current - previous` sobre chaves `(dia, aeronave, início, fim)`. Dois
cenários geram "🔔 Abriu horário!" falso:

1. **Avanço do horizonte** — a cada dia um dia novo entra na varredura de
   30 dias; todas as janelas dele têm chave inédita e disparam aviso,
   embora nada tenha "aberto" (sempre estiveram livres, só não eram
   visíveis).
2. **Janela que encolhe** — alguém **reserva** parte de uma janela livre
   conhecida (livre `06:00 - 09:30`, reservam 07:00-08:00 → sobra
   `08:30 - 09:30`); a sobra tem chave nova e o monitor anuncia abertura
   exatamente quando um horário foi tomado. Sinal invertido.

## Decisões

### 1. Guarda de dias sobrepostos

`diff_new_windows` só considera chaves de dias **varridos com sucesso na
varredura anterior**. Dia recém-entrado no horizonte e dia que voltou de
erro de leitura entram em silêncio e passam a valer na varredura seguinte
(o snapshot novo os inclui).

### 2. `state.json` versão 2: campo `days`

O snapshot só guarda janelas 🟢 — dia varrido mas 100% ocupado não deixa
rastro. Se a guarda derivasse os dias das janelas, um dia lotado que ganha
vaga por cancelamento seria silenciado: exatamente a abertura mais valiosa.
Por isso `NotifyState` ganha `days: frozenset[str]` (datas ISO varridas com
sucesso, campo obrigatório, sem default) e o `state.json` grava
`"days": [...]` ordenado com `STATE_VERSION = 2`.

Migração: state v1 cai no caminho existente de versão desconhecida →
baseline automática (um relatório completo no Discord no primeiro run após
atualizar, sem apagar `state.json` na mão).

### 3. Guarda de subconjunto

Chave candidata é suprimida se existe janela livre anterior do **mesmo
dia+aeronave** que a contenha: `início_ant ≤ início` e `fim ≤ fim_ant`.
Comparação direta das strings `"HH:MM"` (zero-padded, ordem lexicográfica
= numérica; documentar no docstring).

- Janela idêntica: já saía no diff de conjuntos (sem mudança).
- Janela que **cresce** ou desloca ganhando tempo novo: **notifica**, com
  a janela inteira nova na mensagem (não fatiar o delta — o pedaço novo
  sozinho pode ser menor que a duração mínima reservável).
- Janela de outra aeronave nunca cobre a candidata (chave inclui recurso).

### 4. Interfaces (`notifications.py` + `main.py`)

- `diff_new_windows(previous: NotifyState, current: frozenset[WindowKey])
  -> tuple[WindowKey, ...]` — recebe o estado inteiro (antes recebia só
  `previous.windows`); continua pura e ordenada.
- Novo helper puro `extract_scanned_days(days: Sequence[DayAvailability])
  -> frozenset[str]` ao lado de `extract_open_windows`.
- `run_scan`: passa `previous` ao diff; grava
  `NotifyState(windows=…, days=extract_scanned_days(availabilities),
  last_scan_ok=True)`. `_save_failure_state` preserva `previous.days`
  como já preserva `windows`.
- `load_state` valida `days` (lista de strings; malformado → warning +
  baseline, caminho de erro existente).
- `report.py`, `discord.py`, `availability.py`: intocados.

### 5. Comportamentos aceitos (documentados, sem código)

- **Deriva do sol na grade (ADR-0008):** dias futuros usam o sol de hoje;
  quando o nascer cruza uma fronteira :00/:30, todos os dias re-chaveiam
  de uma vez. Direção "encolher": silenciada pela guarda de subconjunto.
  Direção "crescer" (nascer adiantando): burst de avisos **legítimos** —
  30 min novos reais em cada dia útil — raro (fronteira cruzada a cada
  algumas semanas, no máximo).
- **Dia com erro de leitura → recuperado:** cancelamento ocorrido durante
  a falha daquele dia não notifica (dia tratado como novo). Aceito:
  melhor silêncio raro que burst falso diário.
- **Janela que some:** segue silêncio (política original).

## Fora de escopo

- Histórico além do snapshot da última varredura (sem banco).
- Mudanças no formato das mensagens (`report.py`).
- Parametrizar as guardas em `config.ini` (YAGNI).

## Docs

README, parágrafo da política ("só aberturas novas"): acrescentar que dia
recém-entrado no horizonte e janela que apenas encolheu não contam como
abertura, e que a atualização re-baselineia sozinha (state v2).

## Testes (TDD)

- `test_notifications.py`:
  - dia ausente do snapshot anterior é silêncio (horizonte avançou);
  - dia varrido sem janelas ontem + janela hoje **notifica** (motivação do
    campo `days`);
  - janela encolhida/contida é silêncio; janela crescida notifica;
    deslocamento parcial (`06:00-08:00` → `07:00-09:00`) notifica;
  - subconjunto só vale para o mesmo dia+aeronave;
  - roundtrip do state v2 com `days`; v1 → baseline (`None`);
  - fixtures de shape malformado atualizadas para `"version": 2` (senão
    passam a falhar pela versão, não pelo shape) + caso `days` malformado.
- `test_main.py`: fixtures de `NotifyState` ganham `days`;
  `test_new_window_notifies_openings_only` (dia lotado que abre) e
  `test_recovery_notifies_and_diffs_against_preserved_windows` continuam
  passando — são a prova comportamental das decisões 2 e 4.
