# Aquisição via HTTP direto (requests) e Lambda zip — design

**Data:** 2026-07-13
**Status:** aprovado pelo Pedro (decisões e seções validadas em conversa)
**Contexto:** revisa a spec `2026-07-12-aws-lambda-deploy-design.md` na parte de
computação/estado (container+ECR+S3 → zip+DynamoDB). Agendamento, segredos no
SSM, alarme e semântica de erro daquela spec permanecem válidos.

## Objetivo

Custo **R$ 0,00/mês permanente** na AWS (motivação: pedido do Pedro de "Lambda
sem custo nenhum"). O único custo estrutural do desenho anterior era o ECR,
exigido pelo container, exigido pelo Chrome. Este design remove o browser da
aquisição: a escala e o sol saem por HTTP direto (`requests`), o Lambda vira
zip (sem ECR) e o estado vai para o DynamoDB (always-free).

## Evidências (2026-07-13)

1. **HTML é server-rendered**: `debug/20260709-180932-schedule-probe.html`
   contém `const allSchedules = [{...}]` com todos os registros embutidos
   (187 KB de JSON inline) — não há JS a executar.
2. **Login é form Laravel padrão**: `<form method="post" action="/login">` com
   `_token` oculto; campos `email` e `password`; sem captcha/desafio de WAF.
3. **Probe ao vivo 4/4 PASS** (requests puro, sem browser): GET /login
   (_token + cookies `XSRF-TOKEN`/`saga_session`) → POST /login (redirect
   /dashboard) → GET /schedules/personal (440 registros extraídos, campos
   `start_at_raw`/`end_at_raw`/`status`/`aircraft` ok) → GET /aisweb/sun/SBVT
   (XML parseado). Total 21 s; User-Agent de Chrome aceito.

## Decisões (e alternativas descartadas)

| Decisão | Escolha | Alternativas descartadas |
|---|---|---|
| Aquisição | **`requests` em tudo** (nuvem E modo local); Selenium/Chrome aposentados | Manter Selenium no PC (2 caminhos = 2× manutenção/fragilidade); fallback automático (no Lambda zip não existe Chrome — complexidade só para o PC) |
| Estrutura | **módulo novo `saga_http.py`** com o mesmo contrato `scan() -> ScanResult` | Reescrever `scheduler.py` in-place (rewrite disfarçado); camada de aquisição plugável (YAGNI) |
| Computação | **Lambda zip** (`Runtime: python3.13`, 256 MB, timeout 120 s — 4 chamadas × 30 s de timeout cada exigem folga) | Container+ECR (**plano B documentado**: rota completa e lint-validada até o commit `cf0f83f` deste branch — Dockerfile `859c48f`, template imagem `2e24b69`; nunca buildada com Docker; custo ~R$ 1/mês) |
| Estado | **DynamoDB** `aeroes-monitor-state`, **provisioned 1 RCU/1 WCU** (always-free cobre 25/25; on-demand NÃO é grátis), item único `id="state"` com `payload` = JSON v2 do state + `updated_at`; PutItem atômico | S3 (~R$ 0,10–0,15/mês em requests; versionamento vira desnecessário com put atômico) |
| Debug em falha | **HTML salvo em `debug_dir`** (PC e `/tmp` no Lambda) **+ logado no CloudWatch** (evento < 256 KB; ingestão no free tier) | Upload para S3 `debug/` (exigia bucket) |
| User-Agent | UA de Chrome pinado (o validado no probe) | UA custom "aeroes-monitor" (não testado; risco novo sem ganho) |
| Sessão | Nova sessão + login por varredura (igual ao browser hoje: 54 logins/dia) | Cache de cookie entre varreduras (YAGNI; 2 requests extras custam nada) |
| Layout | **código de runtime move para `src/`** e `CodeUri: src/` — com `CodeUri: .` o `sam build` ziparia a pasta inteira, INCLUINDO `config.ini` (segredos!) e `.venv`. `config.ini`/`state.json`/`debug/` ficam na raiz, fisicamente fora do pacote | `CodeUri: .` (vaza segredo no zip); Makefile builder custom (exige make no Windows) |

## Arquitetura

```
EventBridge Scheduler ──▶ Lambda (ZIP python3.13, 256 MB, timeout 120 s,
  cron(0/20 6-23 * * ? *)    concorrência reservada = 1, sem retry)
  America/Sao_Paulo            │
                               ├──▶ SSM Parameter Store (3 segredos; cache no cold start)
                               ├──▶ DynamoDB (GetItem antes / PutItem depois)
                               ├──▶ SAGA via requests (login + HTML + sol; read-only,
                               │      POST /login segue sendo o ÚNICO form — ADR-0001)
                               ├──▶ Discord (webhook — como hoje)
                               └──▶ CloudWatch Logs (stdout; HTML de falha; retenção 30 d)
```

## `saga_http.py` (módulo novo)

Uma varredura = uma sessão. Contrato público: `scan(config) -> ScanResult`
(mesma fronteira do `ScheduleScanner` atual; `main.run_scan` só troca a
chamada). Internamente:

1. `GET {base_url}` → extrai `_token` (`name="_token" value="..."`). Sem
   token ou sem form de login na resposta ⇒ `LoginError` (layout mudou).
2. `POST {origin}/login` com `_token`/`email`/`password` (redirects on). Se a
   resposta ainda contém o form de login ⇒ `LoginError` (credencial/fluxo).
3. `GET {schedule_url}` → se a resposta contém form de login ⇒ `LoginError`;
   extrai a linha `const allSchedules = [...];` (regex multiline ancorada) e
   faz `json.loads`. Ausente ou JSON inválido ⇒ `ScanHttpError` com a mesma
   mensagem-guia do scanner atual ("layout do SAGA mudou?").
4. `GET {origin}/aisweb/sun/SBVT` → `parse_sun_xml` (existente). Falha ⇒
   mesmo comportamento de hoje: `ScanResult` degradado com `ScanError` do sol
   (recuperável; ADR-0008).
5. `build_day_schedules(raw, aircraft, sunrise, sunset, local_today(), max_days)`
   — inalterado.

Requisitos transversais: `timeout=30` por chamada; sem retry (a próxima
varredura é o retry); UA de Chrome pinado em constante; nenhum segredo em log
(`config_to_safe_dict` continua).

**Exceções e debug (dono único):** `saga_http` define
`ScanHttpError(Exception)` com atributo `page_html: str | None` e
`LoginError(ScanHttpError)`; quem SALVA o HTML é o handler de falha existente
em `main.run_scan` (grava em `debug_dir` e loga no CloudWatch quando
`page_html` está presente na exceção). `saga_http` não escreve em disco.

## Mudanças no código

**Novos:**
- `saga_http.py` + `tests/test_saga_http.py` (sessão mockada; fixtures
  recortadas do HTML real: form de login e linha `allSchedules`).
- `docs/adr/0011-http-direto-sem-browser.md` — registra a decisão, marca
  **ADR-0002 (Selenium) e ADR-0003 (seletores CSS) como superseded** e
  documenta o plano B container (hashes acima).

**Removidos:** `browser.py`, `login.py`, `scheduler.py`, `Dockerfile`,
`.dockerignore`, `tests/test_browser.py`, `tests/test_login.py`,
`tests/test_scheduler.py` (casos de aquisição renascem em
`test_saga_http.py`). Selenium sai do `requirements.txt`.

**Alterados:**
- `config.py` — seção `[selenium]` vira **`[saga]`**: ficam `base_url`
  (obrigatório), `schedule_url`, `request_timeout_seconds` (default 30),
  `debug_dir`. Morrem: `headless`, `page_load_timeout_seconds`,
  `element_timeout_seconds`, `chrome_binary`, `chrome_extra_args`, seção
  `[selectors]` e `DEFAULT_SELECTORS`. `AppConfig.selenium` vira
  `AppConfig.saga` (dataclass `SagaConfig`); `overrides` de runtime ficam.
- `main.py` — `run_scan` sem driver: chama `saga_http.scan(config)`; o bloco
  de falha salva `exc.page_html` (quando presente) em `debug_dir` e o loga.
  Transições de notificação/estado intactas. `tests/test_main.py` adapta os
  mocks (create_driver/login/ScheduleScanner → saga_http.scan).
- `handler.py` — troca S3 por DynamoDB: `GetItem(id="state")` → grava
  `/tmp/state.json` (ausente ⇒ baseline) → `run_scan` → se o arquivo existe,
  `PutItem` com o conteúdo. Env vars: `STATE_TABLE` substitui
  `STATE_BUCKET`/`STATE_KEY`/`DEBUG_PREFIX`. Upload de debug para S3 morre
  (o HTML já está no CloudWatch via log).
- **layout**: os 11 módulos de runtime + `config.lambda.ini` movem para
  `src/` (git mv; imports internos ficam iguais — pacote flat).
  `tests/__init__.py` insere `src/` no `sys.path` (uma linha); modo local
  vira `python src/main.py`; `config.ini`/`state.json`/`debug/` seguem na
  raiz (fora do pacote).
- `template.yaml` — função zip (`CodeUri: src/`, `Handler: handler.lambda_handler`,
  `Runtime: python3.13`, 256 MB, 120 s); recurso `StateTable`
  (`AWS::DynamoDB::Table`, provisioned 1/1, PK `id` string); IAM:
  `dynamodb:GetItem`/`PutItem` na tabela + os 3 `ssm:GetParameter`; bucket S3
  sai. Scheduler/SNS/alarme/log group ficam.
- `config.ini.example`, `config.ini` local (renomear seção; sem tocar nos
  segredos), `config.lambda.ini` (enxuga), `README.md` (calibração de
  seletores sai; troubleshooting aponta para o HTML de debug; runbook sem
  Docker Desktop).

**Empacotamento zip:** `sam build` resolve `requirements.txt` puro-Python
(`requests`, `tzdata`, `boto3`) — sem Docker em nenhuma etapa.

## Segurança

- Igual à spec anterior: segredos só no SSM (SecureString) → memória via
  `load_config(overrides)`; nunca em arquivo/env/log/repo.
- Least privilege: `ssm:GetParameter` nos 3 paths + `dynamodb:GetItem/PutItem`
  na tabela. Nada de S3/ECR.
- Read-only no SAGA preservado (ADR-0001): único POST é o login.

## Erros e observabilidade

- Semântica intacta: falha tratada ⇒ `{"ok": false}` + aviso no Discord na
  transição; exceção não tratada ⇒ métrica `Errors` ⇒ alarme (3×20 min) ⇒
  SNS ⇒ e-mail.
- Falha de aquisição: HTML da resposta em `debug_dir` + no CloudWatch Logs
  (retenção 30 d) — substitui screenshot+S3.
- DynamoDB `PutItem` atômico fecha o follow-up "save_state não-atômico" na
  nuvem (no PC continua arquivo local, risco aceito como hoje).

## Custo (estrutural, pós-créditos, qualquer conta)

Lambda ~1.650 invocações × ~10 s × 0,25 GB ≈ 4.100 GB-s (~1% do always-free) +
DynamoDB provisioned 1/1 (≪ 25/25 free) + SSM/KMS/SNS/CloudWatch/Scheduler nas
faixas gratuitas + **ECR: inexistente** = **R$ 0,00/mês**.

## Validação e rollout

1. TDD nos módulos novos/alterados; suíte `unittest` completa verde.
2. `python main.py --once` local (state.json existente ⇒ diff silencioso, sem
   spam) — valida o fluxo requests ao vivo de ponta a ponta.
3. Replanejar Tasks 9–11 do plano de deploy **sem Docker Desktop**: AWS CLI +
   SAM CLI + conta (plano pago com créditos) + SSM + `sam build`/`deploy`.
4. Invocação manual com tabela vazia ⇒ baseline; observar 1–2 ciclos;
   desligar modo contínuo do PC.

## Riscos e plano B

- **SAGA adotar anti-bot/Cloudflare**: rota requests morre; plano B container
  (commit `cf0f83f`) volta com custo ~R$ 1/mês. O monitor avisa no Discord na
  transição ok→falha, como em qualquer quebra.
- **Form de login mudar**: `LoginError` + HTML no debug — recalibração agora é
  "conferir nomes dos campos no HTML" (antes: seletores CSS).
- **`allSchedules` sair do HTML**: mesmo risco/mensagem de hoje (ADR-0010).

## Fora de escopo

- GitHub Actions com OIDC (etapa 2 — fica ainda mais simples com zip).
- Follow-ups menores restantes da revisão do PR #1 (PRD, `max_flight_minutes`,
  matching de matrícula, "1 dias varridos", alerta repetido pré-baseline).
