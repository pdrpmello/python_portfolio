# Design Spec — Aeroclube Schedule Monitor

**Data:** 2026-07-09
**Status:** Aprovado pelo usuário (design verbal aprovado; spec em revisão)
**Fontes normativas:** [PRD](../../PRD.md) e [ADRs 0001–0009](../../adr/README.md). Esta spec não repete o conteúdo delas — registra as decisões de implementação que elas não cobrem. Em caso de conflito, PRD/ADRs prevalecem.

## 1. Decisões fechadas nesta spec

| Decisão | Escolha |
|---|---|
| Dependências | `requirements.txt` (selenium, requests) — sem packaging |
| Versionamento | Subpasta `aeroes_monitor/` do repo `python_portfolio` existente; branch de feature, merge em `main` ao final |
| Test runner | `unittest` puro (ADR-0004), diretório `tests/` |
| Layout | Módulos planos na raiz do projeto (nomes exatamente como citados nas ADRs) |
| Python | 3.13+ (PRD §7) |
| Duração máxima de voo | Usada apenas como informação/validação de config. A classificação 🟢 depende só da duração **mínima**; janelas livres maiores que a máxima aparecem como um único 🟢 (não são fatiadas) |
| Buffer de turnaround | Expande cada período ocupado em ±`turnaround_minutes` e mescla sobreposições, **antes** de calcular vãos livres. Não se aplica contra as bordas da janela operacional |
| Escopo do timeline no relatório | Restrito à janela operacional do dia. Períodos ocupados são exibidos com horários **originais** (recortados à janela); vãos livres são calculados sobre os ocupados **bufferizados** |
| Candidatos de seletor | Valor de cada chave em `[selectors]` = 1+ seletores CSS separados por **quebra de linha** (continuação indentada do INI). Vírgula não serve como separador porque é sintaxe válida de CSS |

## 2. Estrutura de arquivos

```
aeroes_monitor/
├── main.py                # CLI, logging, run_scan(), loop
├── config.py              # config.ini → AppConfig (dataclasses frozen)
├── models.py              # dataclasses de domínio (sem dependências)
├── availability.py        # regras puras (só importa models)
├── report.py              # formatação do relatório (só importa models)
├── discord.py             # DiscordNotifier + split_message (requests)
├── browser.py             # driver factory + helpers Selenium + debug artifacts
├── login.py               # autenticação e detecção de sessão expirada
├── scheduler.py           # ScheduleScanner (varredura multi-dia)
├── aircraft.py            # AircraftService (parsing das agendas)
├── utils.py               # parsing puro de texto (horários, sol, períodos)
├── tests/                 # test_availability, test_report, test_config, test_utils, test_discord
├── config.ini.example
├── requirements.txt
├── .gitignore             # config.ini, debug/, *.log, __pycache__/
└── README.md              # setup, garantia read-only, guia de calibração de seletores
```

Regra de dependência (ADR-0004): `models.py` não importa nada do projeto; `availability.py` e `report.py` importam apenas `models.py`; nenhum dos três importa Selenium. `utils.py` é texto→domínio puro. Só `browser.py`, `login.py`, `scheduler.py`, `aircraft.py` conhecem WebDriver.

## 3. Modelos de domínio (`models.py`)

Todas as dataclasses são `frozen=True`; coleções internas são tuplas.

- `TimePeriod(start: time, end: time, label: str = "")` — invariante `start < end`; helper `duration_minutes() -> int`. Períodos não cruzam meia-noite (agenda é por dia).
- `ResourceSchedule(name: str, model: str = "", busy_periods: tuple[TimePeriod, ...] = ())` — `name` é matrícula (ex.: `PT-ABC`) ou `"Stand By"`.
- `DaySchedule(day: date, sunrise: time, sunset: time, resources: tuple[ResourceSchedule, ...])` — dia da semana derivado de `day.weekday()`.
- `PeriodStatus` (Enum): `AVAILABLE` / `BUSY`.
- `ClassifiedPeriod(period: TimePeriod, status: PeriodStatus, reason: str)` — `reason` legível: `"reservado"`, `"livre"`, `"vão curto (20min < 60min)"`.
- `ResourceAvailability(resource_name: str, resource_model: str, periods: tuple[ClassifiedPeriod, ...])`.
- `DayAvailability(day: date, sunrise: time, sunset: time, window: TimePeriod | None, resources: tuple[ResourceAvailability, ...])` — `window=None` ⇒ dia sem janela operacional.
- `ScanError(day_index: int, day_label: str, message: str)` — erro recuperável de um dia.
- `ScanResult(days: tuple[DaySchedule, ...], errors: tuple[ScanError, ...])`.

## 4. Configuração (`config.py`)

`load_config(path: str) -> AppConfig`. Erros de validação lançam `ConfigError` com mensagem listando todas as chaves faltantes/inválidas de uma vez.

| Seção | Chaves (defaults) |
|---|---|
| `[credentials]` | `username`*, `password`* |
| `[discord]` | `webhook_url`* |
| `[monitor]` | `max_days=30`, `check_interval_seconds=3600`, `turnaround_minutes=30`, `min_flight_minutes=60`, `max_flight_minutes=120` |
| `[selenium]` | `base_url`* (URL de login do SAGA), `schedule_url` (opcional; vazio = a página pós-login já é a escala), `headless=true`, `page_load_timeout_seconds=30`, `element_timeout_seconds=15`, `debug_dir=debug` |
| `[selectors]` | ver §4.1 — seção inteira opcional, defaults embutidos |
| `[aircraft]` | `MATRÍCULA = modelo` (1+ entradas obrigatórias) |
| `[logging]` | `level=INFO`, `file=` (vazio = só console) |

\* obrigatórias. Validações: `min_flight_minutes <= max_flight_minutes`, `turnaround_minutes >= 0`, `max_days >= 1`, `check_interval_seconds >= 60`.

Helpers internos: `_require`, `_get_int`, `_get_bool`, `_load_selectors`, `_load_aircraft`. `config_to_safe_dict(config) -> dict` substitui `password` e `webhook_url` por `"***"` para log seguro (PRD §7).

### 4.1 Chaves de seletores (defaults embutidos em `_load_selectors`)

`login_username`, `login_password`, `login_submit`, `login_form` (marcador "estou na tela de login"), `logged_in_marker`, `schedule_container`, `schedule_date` (rótulo do dia exibido), `next_day_button`, `sunrise_text`, `sunset_text`, `resource_row`, `resource_name`, `event_item`.

Cada chave aceita múltiplos candidatos (um por linha); helpers do `browser.py` tentam na ordem. Defaults são um melhor palpite e **exigem calibração** com a página real (PRD §12, ADR-0003) — o README documenta o processo via DevTools.

## 5. Regras de disponibilidade (`availability.py`)

Parâmetros chegam via `AvailabilityRules(turnaround_minutes, min_flight_minutes, max_flight_minutes)` (dataclass própria — o módulo não importa `config.py`).

- `operating_window(day: date, sunrise: time, sunset: time) -> TimePeriod | None`
  - seg–sex: `sunrise → min(09:30, sunset)`; sáb: `sunrise → sunset`; dom: `sunrise → min(12:00, sunset)` (PRD §6).
  - Retorna `None` se fim ≤ início (ex.: nascer do sol após o horário-limite).
- `apply_turnaround_buffer(periods, buffer_minutes) -> tuple[TimePeriod, ...]` — expande cada período em ±buffer (clamp em 00:00/23:59), ordena e mescla sobrepostos/adjacentes.
- `subtract_periods(window, busy) -> tuple[TimePeriod, ...]` — vãos livres dentro da janela.
- `filter_bookable_periods(free, min_minutes) -> tuple[bookable, too_short]`.
- `classify_day_periods(window, raw_busy, rules) -> tuple[ClassifiedPeriod, ...]` — timeline ordenado contendo: ocupados originais recortados à janela (🔴 `reservado`), livres ≥ mín (🟢 `livre`), livres < mín (🔴 `vão curto`).
- `enrich_day_schedule(day: DaySchedule, rules) -> DayAvailability` — aplica o pipeline acima a cada recurso do dia.

Casos de borda cobertos por teste: sem ocupados (janela inteira 🟢); ocupados cobrindo a janela toda; ocupado fora da janela (ignorado); ocupado atravessando borda da janela (recortado); ocupados sobrepostos (mesclados); buffer fundindo vizinhos; vão exatamente igual ao mínimo (🟢); janela `None`; domingo/sábado/dia útil; pôr do sol antes das 09:30 num dia útil.

## 6. Camada Selenium

### `browser.py`
- `create_driver(cfg: SeleniumConfig) -> WebDriver` — Chrome via Selenium Manager; headless opcional (`--headless=new`), `--window-size=1920,1080`, page load timeout.
- `wait_for_any_visible(driver, selectors, timeout) -> WebElement` — espera o primeiro candidato visível; `TimeoutException` menciona todos os candidatos tentados.
- `read_text_from_selectors(driver, selectors) -> str | None` — texto do primeiro candidato presente com texto não vazio.
- `find_all_first_match(driver, selectors) -> list[WebElement]` — lista do primeiro candidato que retornar elementos.
- `save_debug_artifacts(driver, debug_dir, tag) -> None` — `debug/<timestamp>-<tag>.png` + `.html`; cria o diretório; nunca propaga exceção (melhor esforço, apenas loga).

### `login.py`
- `is_login_page(driver, selectors) -> bool` / `is_logged_in(driver, selectors) -> bool`.
- `login(driver, config) -> None` — navega para `base_url`; se `logged_in_marker` já visível, retorna (sessão reaproveitada, F1); senão preenche credenciais, submete e espera `logged_in_marker`; `LoginError` em falha.

### `scheduler.py`
- `ScheduleScanner(driver, config).scan() -> ScanResult`:
  1. Navega para a escala (`schedule_url` se configurada) e espera `schedule_container`.
  2. Para cada dia até `max_days`: `_ensure_session()` (se voltou ao login, reautentica e retorna à escala — F2); lê rótulo do dia (`parse_day_date` em `utils.py`; se não parsear: última data conhecida + dias decorridos, ou data local de hoje + i se nenhuma foi parseada ainda — sempre com warning); `_read_sunrise()`/`_read_sunset()` (seletores → fallback regex no texto da página; ausência ⇒ `ValueError`, ADR-0008); `AircraftService.build_aircraft_schedules()`; monta `DaySchedule`.
  3. Falha em um dia ⇒ `ScanError` registrado, varredura continua (F10). **3 falhas consecutivas ⇒ aborta** o restante com erro de truncamento (evita insistir com browser morto).
  4. Avança com `next_day_button` e espera o rótulo do dia mudar; falha ao avançar ⇒ registra erro de truncamento e retorna o parcial.

### `aircraft.py`
- `AircraftService(driver, selectors, allowlist: dict[str, str])`.
- `build_aircraft_schedules() -> tuple[ResourceSchedule, ...]` — lê `resource_row`s; extrai nome (`resource_name`) e eventos (`event_item` → `extract_period` + label); casa nome com a allowlist por matrícula normalizada (`normalize_registration`: só alfanuméricos, uppercase). Emite **sempre** um `ResourceSchedule` por aeronave configurada (vazio se linha ausente — ADR-0007) + **sempre** um para Stand By (linha cujo nome casa com `/stand\s*-?\s*by/i`; vazio se ausente — F5), por último.

## 7. Notificação (`discord.py`)

- `split_message(text, limit=2000) -> list[str]` — preserva quebras de linha quando possível; corte duro se uma linha exceder o limite; nunca retorna chunk vazio.
- `DiscordNotifier(webhook_url, timeout=10)`:
  - `send_message(content)` — fragmenta e posta cada chunk (`requests.post`, JSON `{"content": ...}`, `raise_for_status`); pausa de 0,5 s entre chunks (rate limit de webhook).
  - `send_scan_started()`, `send_summary(days, errors)`, `send_report(text)` — propagam `RequestException` (ADR-0006).
  - `send_error(message)` — **engole e loga** falha do próprio envio (último recurso; não pode mascarar o erro original).
- Falha ao enviar a mensagem de início aborta o ciclo (sem canal de reporte, varrer é inútil); no modo loop, o próximo ciclo tenta de novo.

## 8. Orquestração (`main.py`)

- CLI: `--once` (uma varredura) e `--config PATH` (default `config.ini`).
- `setup_logging(cfg)` — nível/arquivo do `[logging]`; loga `config_to_safe_dict` no boot.
- `run_scan(config) -> bool`:
  ```
  try: notifier.send_scan_started() → driver = create_driver → login → scan → enrich → report →
       send_summary + send_report; return True
  except Exception: log.exception; save_debug_artifacts (se driver existe); notifier.send_error(...); return False
  finally: driver.quit() (se driver existe)
  ```
  `send_scan_started()` fica **dentro** do `try`: se o Discord estiver fora, o ciclo falha (return False) sem derrubar o loop — consistente com §7.
- Loop: `while True: run_scan(config); time.sleep(check_interval_seconds)` — sem `except` extra no loop (trade-off aceito da ADR-0009); `KeyboardInterrupt` encerra limpo. `--once` sai com código 0/1 conforme `run_scan`.

## 9. Formato do relatório (`report.py`)

- `build_summary(days, errors) -> str` — total de dias lidos/com erro e lista compacta das janelas 🟢 encontradas (dia → recurso → horários), ou "nenhum horário disponível"; erros recuperáveis listados com ⚠️.
- `build_report(days, errors) -> str` — por dia:
  ```
  📅 Seg 14/07/2026 — 🌅 05:45 · 🌇 17:30 · janela 05:45–09:30
  ✈️ PT-ABC (C-152)
    🟢 05:45–07:00 — livre (1h15)
    🔴 07:00–08:00 — reservado
    🔴 08:30–08:50 — vão curto (20min < 60min)
  ✈️ Stand By
    🟢 05:45–09:30 — livre (3h45)
  ```
  Dia sem janela operacional: linha única explicando. Dias com erro: bloco ⚠️ com a mensagem.

## 10. Estratégia de testes (TDD, `unittest`)

Ordem de implementação test-first: `models` → `utils` → `availability` → `report` → `config` → `discord` (com `unittest.mock` no `requests`). Camada Selenium (browser/login/scheduler/aircraft) fica fina, sem testes de browser real (recorte da PRD §7); toda lógica extraível dela vive em `utils.py`/`availability.py`, que são testados.

Casos mínimos por módulo: §5 para availability; `test_utils`: `parse_time` ("06:15", "6:15", "06h15"), `extract_sunrise/sunset` sobre texto pt-BR realista ("Nascer do sol: 05:45"), `extract_period` ("06:00 - 07:00", "06:00–07:00", "06:00 às 07:00"), `parse_day_date` ("14/07/2026", "Segunda-feira, 14/07/2026", texto sem data → None), `normalize_registration` ("pt-abc" ≡ "PTABC"); `test_config`: carga completa, defaults, obrigatórias ausentes (todas reportadas juntas), redação de segredos, seletores multilinha, validações numéricas; `test_report`: presença de 🟢/🔴/cabeçalhos, dia sem janela, bloco de erros; `test_discord`: split (curto, quebra em linha, corte duro, exatamente 2000, nunca vazio), postagem de chunks em ordem, propagação de erro HTTP, `send_error` que não propaga.

## 11. Fora de escopo (reafirmação)

Sem escrita no SAGA (ADR-0001), sem multi-usuário, sem GUI, sem API de astronomia (ADR-0008), sem banco de dados, sem agendador externo (ADR-0009). Roadmap (diffs incrementais etc.) fica fora desta implementação.
