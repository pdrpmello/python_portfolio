# Design: relatório só de janelas livres + grade de 30 min

**Data:** 2026-07-10 · **Status:** aprovado pelo usuário (conversa de 2026-07-10)

## Objetivo

O relatório no Discord existe para responder "onde tem buraco na escala?".
Hoje ele lista a timeline inteira (ocupados 🔴 + livres 🟢) de 30 dias — 9
fragmentos de rolagem — e duplica a lista de livres num resumo separado.
Além disso as janelas começam em horários quebrados (ex.: 06:17, o nascer
do sol exato), que não correspondem a horários reserváveis no clube.

## Decisões

### 1. Janela operacional arredondada na grade de 30 min (`availability.py`)

`operating_window` passa a arredondar as pontas na grade :00/:30:

- **Início** = nascer do sol arredondado **para cima**: 06:17→06:30,
  05:47→06:00, 05:05→05:30; horário já redondo não muda (06:00→06:00).
- **Fim** = arredondado **para baixo**, incondicionalmente: só muda algo
  quando o fim é o pôr do sol (sábado: 17:23→17:00, 17:45→17:30), pois os
  limites fixos de semana (09:30) e domingo (12:00) já estão na grade
  (arredondar para baixo é no-op).
- Se o arredondamento colapsar a janela (início ≥ fim), o dia fica sem
  janela operacional — caminho já existente (`None`).

Isso muda a disponibilidade **real** (não só exibição): janelas 🟢,
chaves do `state.json` e notificações já saem redondas.

### 2. Relatório = só janelas livres, em UMA mensagem (`report.py`)

`build_report` passa a listar apenas períodos `AVAILABLE`, agrupados por
dia e aeronave, com cabeçalho de contagem. `build_summary` é aposentada
(a lista dela é o próprio relatório novo); a baseline envia **uma**
mensagem em vez de duas.

Formato aprovado:

```
✅ **30 dias varridos — 43 janelas livres**

📅 **Qui 10/07/2026**

✈️ **PP-AYB** (C152)
🟢 07:30 - 09:30 (2h)

✈️ **PT-JTK** (C172)
🟢 06:30 - 09:30 (3h)

📅 **Sex 11/07/2026**
…
```

Regras do formato:

- Cabeçalho do dia sem 🌅/🌇/janela: `📅 **Qui 10/07/2026**`.
- **Dia sem janela livre não aparece**; aeronave sem janela livre naquele
  dia também não. Nenhum 🔴, "reservado", "vão curto" ou "sem janela
  operacional" na mensagem.
- Linha em branco após o cabeçalho do dia, entre blocos de aeronave e
  entre dias.
- Período com hífen espaçado e duração: `🟢 07:30 - 09:30 (2h)`
  (`_fmt_duration` existente: 1h, 1h30, 45min).
- Zero janelas livres na varredura: mensagem vira
  `✅ **30 dias varridos — nenhuma janela livre. 😕**` (uma linha; o bloco
  de erros ⚠️ ainda é anexado se houver erros).
- Erros de leitura continuam num bloco `⚠️ **Dias com erro de leitura:**`
  ao final, quando existirem.

O mesmo separador ` - ` vale para `build_openings_message`
(`🟢 Qui 10/07/2026: PP-AYB 07:30 - 09:30`), sem duração — mensagem de
alerta continua enxuta. Helper compartilhado `_fmt_period`.

### 3. Modelo abreviado via configuração (sem código)

O modelo é texto livre de `[aircraft]` no `config.ini`. Trocar os valores
para `C152`/`C172` no config local do usuário e nos exemplos do
`config.ini.example`. Alternativa rejeitada: abreviar no código
("Cessna 152"→"C152") — frágil para modelos fora do padrão (ex.:
"Piper PA-28").

### 4. Orquestração (`main.py` + `discord.py`)

- Baseline (`previous is None`): só `notifier.send_report(build_report(...))`.
- `DiscordNotifier.send_summary` e `build_summary` são deletadas (mesmo
  destino do `send_scan_started` na mudança anterior).
- Diff e recuperação ("✅ Varredura voltou a funcionar.") inalterados.

### 5. Migração do `state.json`

O arredondamento muda as chaves das janelas (06:17→06:30) — a primeira
execução após o deploy dispararia um falso "🔔 Abriu horário!" para
janelas re-arredondadas. Mitigação documentada: apagar `state.json` uma
vez após atualizar → nova baseline (relatório completo, sem alarme falso).
Anotar no README (Uso / Solução de problemas).

## Fora de escopo

- Mudar a mensagem de aberturas além do separador ` - `.
- Qualquer visão "timeline completa" com ocupados (se voltar a ser útil,
  é feature nova).

## Testes (TDD)

- `test_availability.py`: arredondamento de início (para cima, inclusive
  caso exato na grade) e fim de sábado (para baixo); janela que colapsa
  vira `None`; dias de semana/domingo mantêm limites fixos.
- `test_report.py`: reescrever para o formato novo — cabeçalho com
  contagens, só livres, omissão de dias/aeronaves vazios, duração,
  hífen espaçado, caso zero janelas, bloco de erros; remover testes de
  `build_summary`; `build_openings_message` com ` - `.
- `test_main.py`: baseline envia exatamente 1 mensagem (report);
  nenhum uso de `send_summary`.
- `test_discord.py`: remover `send_summary` da contagem de conveniência.
- `test_notifications.py`: sem mudança (interface de
  `extract_open_windows` intacta).
