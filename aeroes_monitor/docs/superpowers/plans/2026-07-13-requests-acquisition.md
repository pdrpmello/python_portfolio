# Aquisição via HTTP direto (requests) e Lambda zip — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a aquisição Selenium por HTTP direto (`requests`), empacotar o Lambda como zip (sem ECR) e mover o estado para DynamoDB — custo estrutural R$ 0,00/mês, fluxo local preservado.

**Architecture:** Um módulo novo `saga_http.py` faz login (único POST — ADR-0001), lê a variável `allSchedules` embutida no HTML server-rendered e o XML do sol, tudo numa sessão `requests` — expondo `scan(config) -> ScanResult`, a mesma fronteira do `ScheduleScanner` de hoje. `main.run_scan` só troca a chamada; o resto (regras, relatório, diff, notificação, estado) fica intacto. O handler Lambda troca S3 por DynamoDB.

**Tech Stack:** Python 3.13, `requests`, `boto3`, `tzdata`, AWS SAM (Lambda zip), DynamoDB, SSM, EventBridge Scheduler, CloudWatch/SNS.

**Spec:** `docs/superpowers/specs/2026-07-13-requests-acquisition-design.md`

## Global Constraints

- Suíte: `.venv\Scripts\python -m unittest -v` do diretório `aeroes_monitor` (PowerShell). Hoje **152 testes** OK; nunca regredir. **pytest não está no venv** — só unittest.
- Após a Task 1, os módulos de runtime vivem em `src/`; `tests/__init__.py` insere `src/` no `sys.path`, então o comando de teste **não muda**. Modo local vira `.venv\Scripts\python src/main.py --once`.
- Repo git no diretório pai (`python_portfolio`); commits com prefixo `(aeroes_monitor)` no estilo existente (`feat:`/`fix:`/`refactor:`/`docs:`/`test:`).
- Comentários, docstrings e logs em **pt-BR**, no estilo dos módulos atuais (citar PRD/ADR quando couber).
- **Segredos jamais em arquivo commitado, log ou pacote**: `config.ini` continua gitignored; `config.lambda.ini` (commitado) sem seções de credenciais/Discord; `CodeUri: src/` mantém `config.ini` fisicamente fora do zip. `config_to_safe_dict` redige senha/webhook.
- Fluxo local inalterado no comportamento: `load_config("config.ini")` sem overrides carrega e valida como hoje (só muda o nome da seção `[selenium]`→`[saga]`).
- Read-only no SAGA preservado (ADR-0001): o único POST é o login.
- Nomes AWS fixos: stack `aeroes-monitor`, tabela `aeroes-monitor-state`, parâmetros `/aeroes-monitor/saga-username|saga-password|discord-webhook-url`, região `sa-east-1`.
- User-Agent HTTP: o de Chrome validado no probe (constante `USER_AGENT` em `saga_http.py`), verbatim: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36`.

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/` (novo dir) | criar via `git mv` | raiz do código de runtime (fora do pacote zip fica só config.ini/state.json/debug) |
| `tests/__init__.py` | modificar | põe `src/` no `sys.path` |
| `src/saga_http.py` | criar | aquisição HTTP: login + allSchedules + sol → `ScanResult` |
| `src/main.py` | modificar | `run_scan` chama `saga_http.scan`; sem driver; debug = HTML |
| `src/config.py` | modificar | `[selenium]`→`[saga]` (`SagaConfig`); remove selectors/chrome |
| `src/handler.py` | modificar | S3 → DynamoDB (`GetItem`/`PutItem`) |
| `src/browser.py`, `src/login.py`, `src/scheduler.py` | remover | camada Selenium aposentada |
| `Dockerfile`, `.dockerignore` | remover | container vira plano B (recuperável no git) |
| `src/requirements.txt` | mover (git mv) + modificar | vai para `src/` porque `sam build` procura o manifesto na pasta do `CodeUri`; remove `selenium` |
| `template.yaml` | modificar | função zip + `StateTable` (DynamoDB); sem bucket/imagem |
| `config.ini.example`, `config.ini`, `src/config.lambda.ini` | modificar | seção `[saga]`; sem `[selectors]` |
| `docs/adr/0011-http-direto-sem-browser.md` | criar | decide a virada; supersede 0002/0003 |
| `docs/adr/0002-*.md`, `docs/adr/0003-*.md`, `docs/adr/README.md` | modificar | banner de superseded + índice |
| `README.md` | modificar | runbook zip/DynamoDB; troubleshooting sem seletores |
| `tests/test_saga_http.py` | criar | cobre `saga_http` (sessão fake) |
| `tests/test_main.py`, `tests/test_config.py`, `tests/test_handler.py` | modificar | adaptam aos novos contratos |
| `tests/test_browser.py`, `tests/test_login.py`, `tests/test_scheduler.py` | remover | módulos aposentados |

---

### Task 1: layout `src/` (mecânico, sem mudança de comportamento)

**Files:**
- Move (git mv): 13 módulos + `config.lambda.ini` + `requirements.txt` → `src/`
- Modify: `tests/__init__.py`, `tests/test_config.py` (path do LambdaIniTest), `README.md` (comando de install)

**Interfaces:**
- Consumes: nada novo.
- Produces: módulos de runtime importáveis como top-level (`config`, `main`, `handler`, …) via `src/` no `sys.path`; `config.lambda.ini` e `requirements.txt` em `src/` (o `CodeUri: src/` do SAM exige o manifesto ali).

- [ ] **Step 1: Criar `src/` e mover os arquivos**

`requirements.txt` vai junto: o `sam build` (Task 5) procura o manifesto na
pasta apontada por `CodeUri`, que será `src/`.

```powershell
New-Item -ItemType Directory src
git mv availability.py browser.py config.py discord.py handler.py login.py main.py models.py notifications.py report.py saga_data.py scheduler.py utils.py config.lambda.ini requirements.txt src/
```

- [ ] **Step 2: Shim de `sys.path` em `tests/__init__.py`**

Substituir o conteúdo de `tests/__init__.py` por:

```python
"""Pacote de testes: põe src/ no sys.path para achar os módulos de runtime."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
```

- [ ] **Step 3: Corrigir o caminho do `config.lambda.ini` no teste**

Em `tests/test_config.py`, na classe `LambdaIniTest`, trocar:

```python
    PATH = Path(__file__).resolve().parent.parent / "config.lambda.ini"
```

por:

```python
    PATH = Path(__file__).resolve().parent.parent / "src" / "config.lambda.ini"
```

- [ ] **Step 4: Atualizar o comando de install no README**

No `README.md`, na seção de setup, trocar:

```
.venv\Scripts\python -m pip install -r requirements.txt
```

por:

```
.venv\Scripts\python -m pip install -r src\requirements.txt
```

- [ ] **Step 5: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 152 testes (nenhuma mudança de comportamento).

- [ ] **Step 6: Smoke do entrypoint local**

Run: `.venv\Scripts\python src/main.py --help`
Expected: imprime o `usage:` do argparse (imports resolvidos a partir de `src/`).

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "refactor(aeroes_monitor): move runtime para src/ (zip nao vaza config.ini)"
```

---

### Task 2: `saga_http.py` — aquisição por HTTP direto

**Files:**
- Create: `src/saga_http.py`
- Test: `tests/test_saga_http.py`

**Interfaces:**
- Consumes: `saga_data.build_day_schedules`, `saga_data.local_today`, `saga_data.parse_sun_xml`, `saga_data.utc_time_to_local`; `models.ScanError`, `models.ScanResult`. Do `config` recebido lê: `config.saga.base_url`, `config.saga.schedule_url`, `config.saga.request_timeout_seconds`, `config.credentials.username/password`, `config.aircraft`, `config.monitor.max_days`. (Task 2 não altera `config.py`; os testes montam um `config` fake com esses atributos.)
- Produces: `scan(config) -> ScanResult`; `ScanHttpError(Exception)` com atributo `page_html: str | None`; `LoginError(ScanHttpError)`; constantes `SUN_ENDPOINT`, `USER_AGENT`.

- [ ] **Step 1: Escrever `tests/test_saga_http.py` (falhando)**

```python
"""Testes da aquisição HTTP com sessão requests fake (sem rede nem browser)."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest import mock

import saga_http

BASE_URL = "https://saga.example/login"
SCHEDULE_URL = "https://saga.example/schedules/personal"

LOGIN_HTML = (
    '<form method="post" action="/login">'
    '<input type="hidden" name="_token" value="TOK123">'
    '<input name="email"><input name="password"></form>'
)
DASHBOARD_HTML = '<div id="navbarDropdownProfile">Perfil</div>'
SCHEDULE_HTML = (
    "<html><body><script>\n"
    'const allSchedules = [{"start_at_raw":"2026-07-09 07:00:00",'
    '"end_at_raw":"2026-07-09 08:00:00","status":"CONFIRMED",'
    '"aircraft":{"registration":"PP-AYB"},"student":{"nickname":"Ana"}}];\n'
    "</script></body></html>"
)
SUN_XML = "<aisweb><day><sunrise>09:17</sunrise><sunset>20:15</sunset></day></aisweb>"


def _config(max_days=2):
    return SimpleNamespace(
        saga=SimpleNamespace(
            base_url=BASE_URL, schedule_url=SCHEDULE_URL, request_timeout_seconds=5
        ),
        credentials=SimpleNamespace(username="piloto@example.com", password="s3cr3t"),
        aircraft={"PP-AYB": "C152"},
        monitor=SimpleNamespace(max_days=max_days),
    )


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code


class FakeSession:
    """Sessão scriptada: responde por URL; registra chamadas."""

    def __init__(self, login_get=LOGIN_HTML, login_post=DASHBOARD_HTML,
                 schedule=SCHEDULE_HTML, sun=(SUN_XML, 200)):
        self.headers = {}
        self.calls = []
        self._login_get = login_get
        self._login_post = login_post
        self._schedule = schedule
        self._sun = sun

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        if url == BASE_URL:
            return FakeResponse(self._login_get)
        if url == SCHEDULE_URL:
            return FakeResponse(self._schedule)
        if url.endswith(saga_http.SUN_ENDPOINT):
            text, status = self._sun
            return FakeResponse(text, status)
        raise AssertionError(f"GET inesperado: {url}")

    def post(self, url, data=None, timeout=None, allow_redirects=True):
        self.calls.append(("POST", url, data))
        return FakeResponse(self._login_post)


def _run(session, config=None, today=date(2026, 7, 9)):
    with mock.patch("saga_http.requests.Session", return_value=session), \
         mock.patch("saga_http.local_today", return_value=today):
        return saga_http.scan(config or _config())


class ScanHappyPathTest(unittest.TestCase):
    def test_builds_days_from_all_schedules(self):
        result = _run(FakeSession())
        self.assertEqual(len(result.days), 2)
        self.assertEqual(result.days[0].day, date(2026, 7, 9))
        # 09:17Z -> 06:17 local.
        self.assertEqual(result.days[0].sunrise.strftime("%H:%M"), "06:17")
        self.assertIn("PP-AYB", [r.name for r in result.days[0].resources])

    def test_token_captured_and_posted_in_order(self):
        session = FakeSession()
        _run(session)
        self.assertEqual([c[0] for c in session.calls], ["GET", "POST", "GET", "GET"])
        post = next(c for c in session.calls if c[0] == "POST")
        self.assertEqual(post[2]["_token"], "TOK123")
        self.assertEqual(post[2]["email"], "piloto@example.com")

    def test_user_agent_is_set(self):
        session = FakeSession()
        _run(session)
        self.assertIn("Chrome", session.headers["User-Agent"])


class ScanLoginErrorTest(unittest.TestCase):
    def test_missing_token_raises_with_html(self):
        with self.assertRaises(saga_http.LoginError) as ctx:
            _run(FakeSession(login_get="<form>sem token</form>"))
        self.assertIsNotNone(ctx.exception.page_html)

    def test_post_still_shows_login_form_raises(self):
        with self.assertRaises(saga_http.LoginError):
            _run(FakeSession(login_post=LOGIN_HTML))

    def test_schedule_page_bounces_to_login_raises(self):
        with self.assertRaises(saga_http.LoginError):
            _run(FakeSession(schedule=LOGIN_HTML))


class ScanScheduleErrorTest(unittest.TestCase):
    def test_missing_all_schedules_raises_with_html(self):
        with self.assertRaises(saga_http.ScanHttpError) as ctx:
            _run(FakeSession(schedule="<html>sem variavel</html>"))
        self.assertIn("allSchedules", str(ctx.exception))
        self.assertIsNotNone(ctx.exception.page_html)

    def test_invalid_json_raises(self):
        with self.assertRaises(saga_http.ScanHttpError):
            _run(FakeSession(schedule="<script>const allSchedules = [nope];</script>"))


class ScanSunRecoverableTest(unittest.TestCase):
    def test_sun_http_error_is_recoverable(self):
        result = _run(FakeSession(sun=("", 500)))
        self.assertEqual(result.days, ())
        self.assertEqual(len(result.errors), 1)
        self.assertIn("sol", result.errors[0].message.lower())

    def test_sun_garbage_xml_is_recoverable(self):
        result = _run(FakeSession(sun=("<html>erro</html>", 200)))
        self.assertEqual(result.days, ())
        self.assertEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_http -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saga_http'`.

- [ ] **Step 3: Escrever `src/saga_http.py`**

```python
"""Aquisição da escala SAGA por HTTP direto, sem browser (ADR-0011).

Uma varredura = uma sessão requests: login (único POST — ADR-0001), leitura
da variável `allSchedules` embutida no HTML server-rendered (ADR-0010) e do
XML de nascer/pôr do sol (/aisweb/sun/SBVT, UTC — ADR-0008). Substitui a
antiga camada Selenium (browser/login/scheduler).
"""
from __future__ import annotations

import json
import logging
import re

import requests

from models import ScanError, ScanResult
from saga_data import (
    build_day_schedules,
    local_today,
    parse_sun_xml,
    utc_time_to_local,
)

logger = logging.getLogger(__name__)

SUN_ENDPOINT = "/aisweb/sun/SBVT"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
_TOKEN_RE = re.compile(r'name="_token"\s+value="([^"]+)"')
# allSchedules fica numa única linha `const allSchedules = [...];`; greedy até
# o `];` no fim da linha pega o fechamento real do array (ADR-0010).
_ALL_SCHEDULES_RE = re.compile(r"^\s*const allSchedules\s*=\s*(\[.*\]);", re.MULTILINE)
_LOGIN_MARKERS = ('action="/login"', 'name="_token"')

_SUN_UNAVAILABLE = (
    "Nascer/pôr do sol indisponível no SAGA — janelas não calculadas nesta "
    "varredura (ADR-0008)"
)


class ScanHttpError(Exception):
    """Falha de aquisição HTTP; page_html carrega o HTML para debug quando há."""

    def __init__(self, message: str, page_html: str | None = None) -> None:
        super().__init__(message)
        self.page_html = page_html


class LoginError(ScanHttpError):
    """Login não confirmado (credencial inválida ou fluxo do SAGA mudou)."""


def _looks_like_login(html: str) -> bool:
    return all(marker in html for marker in _LOGIN_MARKERS)


def _origin(base_url: str) -> str:
    return base_url.rsplit("/", 1)[0]


def _extract_all_schedules(html: str) -> list:
    match = _ALL_SCHEDULES_RE.search(html)
    if match is None:
        raise ScanHttpError(
            "allSchedules não encontrado na página da escala — layout do SAGA "
            "mudou? Verifique saga.schedule_url e o HTML de debug",
            page_html=html,
        )
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ScanHttpError(
            f"allSchedules com JSON inválido: {exc}", page_html=html
        ) from exc
    if not isinstance(data, list):
        raise ScanHttpError(
            f"allSchedules com formato inesperado: {type(data).__name__}",
            page_html=html,
        )
    logger.info("allSchedules lido: %d agendamento(s)", len(data))
    return data


def _read_sun_times(session, origin: str, timeout: int):
    """(nascer, pôr) LOCAIS de hoje, ou None se indisponível (recuperável)."""
    try:
        response = session.get(f"{origin}{SUN_ENDPOINT}", timeout=timeout)
        if response.status_code != 200:
            logger.warning("Endpoint do sol respondeu %s", response.status_code)
            return None
        parsed = parse_sun_xml(response.text)
        if parsed is None:
            logger.warning("XML do sol não parseável")
            return None
        today = local_today()
        return utc_time_to_local(parsed[0], today), utc_time_to_local(parsed[1], today)
    except Exception:
        logger.exception("Falha ao consultar o sol")
        return None


def scan(config) -> ScanResult:
    cfg = config.saga
    timeout = cfg.request_timeout_seconds
    origin = _origin(cfg.base_url)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    response = session.get(cfg.base_url, timeout=timeout)
    match = _TOKEN_RE.search(response.text)
    if match is None:
        raise LoginError(
            "Formulário de login sem _token — layout do SAGA mudou?",
            page_html=response.text,
        )

    response = session.post(
        f"{origin}/login",
        data={
            "_token": match.group(1),
            "email": config.credentials.username,
            "password": config.credentials.password,
        },
        timeout=timeout,
        allow_redirects=True,
    )
    if _looks_like_login(response.text):
        raise LoginError(
            "Login não confirmado (verifique credenciais).", page_html=response.text
        )
    logger.info("Login efetuado com sucesso")

    response = session.get(cfg.schedule_url or cfg.base_url, timeout=timeout)
    if _looks_like_login(response.text):
        raise LoginError(
            "Sessão não autenticada na página da escala.", page_html=response.text
        )
    raw = _extract_all_schedules(response.text)

    sun = _read_sun_times(session, origin, timeout)
    if sun is None:
        return ScanResult(
            days=(),
            errors=(ScanError(day_index=0, day_label="sol", message=_SUN_UNAVAILABLE),),
        )
    sunrise, sunset = sun
    return build_day_schedules(
        raw, config.aircraft, sunrise, sunset, local_today(), config.monitor.max_days
    )
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 163 testes (152 + 11).

- [ ] **Step 5: Commit**

```powershell
git add src/saga_http.py tests/test_saga_http.py
git commit -m "feat(aeroes_monitor): saga_http - aquisicao da escala por HTTP direto"
```

---

### Task 3: cutover — `main` usa `saga_http`, `[selenium]`→`[saga]`, Selenium sai

Mudança atômica: a camada de aquisição inteira vira HTTP. Config, orquestração e módulos Selenium mudam juntos porque um estado intermediário não fica verde.

**Files:**
- Modify: `src/config.py`, `src/main.py`, `requirements.txt`,
  `config.ini.example`, `config.ini`, `src/config.lambda.ini`
- Remove: `src/browser.py`, `src/login.py`, `src/scheduler.py`,
  `tests/test_browser.py`, `tests/test_login.py`, `tests/test_scheduler.py`
- Modify (testes): `tests/test_main.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `saga_http.scan(config)` (Task 2).
- Produces: `AppConfig.saga: SagaConfig` (sem `.selenium`/`.selectors`);
  `SagaConfig(base_url: str, schedule_url: str = "", request_timeout_seconds: int = 30, debug_dir: str = "debug")`;
  `main.run_scan(config, state_path) -> bool` sem driver, salvando `exc.page_html` em falha.

- [ ] **Step 1: Adaptar os testes (RED) — `tests/test_config.py`**

Substituir o arquivo inteiro por:

```python
"""Testes da carga/validação de configuração (ADR-0005)."""
import tempfile
import unittest
from pathlib import Path

from config import AppConfig, ConfigError, config_to_safe_dict, load_config

VALID_INI = """
[credentials]
username = piloto@example.com
password = s3cr3t

[discord]
webhook_url = https://discord.com/api/webhooks/123/abc

[saga]
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
        self.assertEqual(config.saga.base_url, "https://saga.example.com/login")
        self.assertEqual(config.saga.schedule_url, "")
        self.assertEqual(config.saga.request_timeout_seconds, 30)
        self.assertEqual(config.saga.debug_dir, "debug")
        self.assertEqual(config.logging.level, "INFO")

    def test_aircraft_preserves_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertEqual(
            config.aircraft, {"PT-ABC": "Cessna 152", "PT-XYZ": "Cessna 172"}
        )

    def test_saga_fields_parsed(self):
        ini = VALID_INI + """
schedule_url = https://saga.example.com/schedules/personal
request_timeout_seconds = 45
debug_dir = /tmp/debug
"""
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, ini))
        self.assertEqual(
            config.saga.schedule_url, "https://saga.example.com/schedules/personal"
        )
        self.assertEqual(config.saga.request_timeout_seconds, 45)
        self.assertEqual(config.saga.debug_dir, "/tmp/debug")

    def test_overrides_fill_missing_sections_and_win_over_file(self):
        ini = """
[saga]
base_url = https://saga.example.com/login

[aircraft]
PT-ABC = C152

[monitor]
max_days = 10
"""
        overrides = {
            ("credentials", "username"): "piloto@example.com",
            ("credentials", "password"): "s3cr3t",
            ("discord", "webhook_url"): "https://discord.com/api/webhooks/1/a",
            ("monitor", "max_days"): "5",
        }
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, ini), overrides=overrides)
        self.assertEqual(config.credentials.username, "piloto@example.com")
        self.assertEqual(
            config.discord.webhook_url, "https://discord.com/api/webhooks/1/a"
        )
        self.assertEqual(config.monitor.max_days, 5)

    def test_no_overrides_keeps_current_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI), overrides=None)
        self.assertEqual(config.credentials.username, "piloto@example.com")

    def test_missing_required_lists_all_errors(self):
        ini = """
[credentials]
username = so-usuario
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        message = str(ctx.exception)
        self.assertIn("credentials.password", message)
        self.assertIn("discord.webhook_url", message)
        self.assertIn("saga.base_url", message)
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


class LambdaIniTest(unittest.TestCase):
    """config.lambda.ini é COMMITADO: nunca pode conter segredos."""

    PATH = Path(__file__).resolve().parent.parent / "src" / "config.lambda.ini"

    def test_has_no_secret_sections(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertNotIn("[credentials]", text)
        self.assertNotIn("[discord]", text)

    def test_validates_with_runtime_overrides(self):
        config = load_config(
            self.PATH,
            overrides={
                ("credentials", "username"): "piloto@example.com",
                ("credentials", "password"): "s3cr3t",
                ("discord", "webhook_url"): "https://discord.com/api/webhooks/1/a",
            },
        )
        self.assertEqual(config.saga.base_url, "https://aeroes.saga.aero/login")
        self.assertEqual(config.saga.request_timeout_seconds, 30)
        self.assertEqual(config.saga.debug_dir, "/tmp/debug")
        self.assertIn("PP-AYB", config.aircraft)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Adaptar os testes (RED) — `tests/test_main.py`**

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
        saga=SimpleNamespace(
            base_url="https://saga.example.com/login",
            schedule_url="https://saga.example.com/schedules/personal",
            request_timeout_seconds=30,
            debug_dir="debug",
        ),
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


@mock.patch("main.saga_http")
@mock.patch("main.DiscordNotifier")
class RunScanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.state_path = Path(self._tmp.name) / "state.json"

    def test_first_run_sends_baseline_and_saves_state(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_report.assert_called_once()
        notifier.send_message.assert_not_called()
        state = load_state(self.state_path)
        self.assertTrue(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)
        self.assertEqual(state.days, frozenset({"2026-07-11"}))

    def test_no_changes_is_silent(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline
        notifier.reset_mock()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_report.assert_not_called()
        notifier.send_message.assert_not_called()
        notifier.send_error.assert_not_called()

    def test_new_window_notifies_openings_only(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result(
            busy=(TimePeriod(start=time(6, 0), end=time(17, 0)),)
        )
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        saga_http.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        notifier.send_message.assert_called_once()
        self.assertIn("Abriu horário", notifier.send_message.call_args.args[0])
        self.assertIn("PT-ABC C-152", notifier.send_message.call_args.args[0])
        notifier.send_report.assert_not_called()

    def test_error_notifies_only_on_transition(self, notifier_cls, saga_http):
        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline ok
        notifier.reset_mock()
        saga_http.scan.side_effect = RuntimeError("SAGA fora do ar")
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()  # transição ok→falha
        notifier.reset_mock()
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_not_called()  # falha repetida: silêncio
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # janelas preservadas

    def test_recovery_notifies_and_diffs_against_preserved_windows(
        self, notifier_cls, saga_http
    ):
        notifier = notifier_cls.return_value
        save_state(
            self.state_path,
            NotifyState(
                windows=frozenset({("2026-07-11", "PT-ABC", "06:00", "17:00")}),
                days=frozenset({"2026-07-11"}),
                last_scan_ok=False,
            ),
        )
        saga_http.scan.return_value = _scan_result()
        self.assertTrue(run_scan(_config(), self.state_path))
        sent = [c.args[0] for c in notifier.send_message.call_args_list]
        self.assertTrue(any("voltou a funcionar" in m for m in sent))
        self.assertFalse(any("Abriu horário" in m for m in sent))

    def test_degraded_scan_counts_as_failure(self, notifier_cls, saga_http):
        from models import ScanError

        notifier = notifier_cls.return_value
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)
        notifier.reset_mock()
        saga_http.scan.return_value = ScanResult(
            days=(), errors=(ScanError(day_index=0, day_label="sol", message="sem sol"),)
        )
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        state = load_state(self.state_path)
        self.assertFalse(state.last_scan_ok)
        self.assertEqual(len(state.windows), 1)  # preservadas

    def test_failure_without_state_notifies_but_keeps_baseline_pending(
        self, notifier_cls, saga_http
    ):
        notifier = notifier_cls.return_value
        saga_http.scan.side_effect = RuntimeError("boom")
        self.assertFalse(run_scan(_config(), self.state_path))
        notifier.send_error.assert_called_once()
        self.assertIsNone(load_state(self.state_path))  # baseline continua pendente

    def test_state_write_failure_does_not_propagate(self, notifier_cls, saga_http):
        """Contrato de run_scan: OSError persistente no save_state não estoura."""
        saga_http.scan.return_value = _scan_result()
        run_scan(_config(), self.state_path)  # baseline com estado gravado
        with mock.patch(
            "main.save_state", side_effect=OSError("state.json travado pelo OneDrive")
        ):
            self.assertFalse(run_scan(_config(), self.state_path))

    def test_discord_outage_does_not_propagate(self, notifier_cls, saga_http):
        """Discord fora do ar: send_* falhando (inclusive no handler) não estoura."""
        notifier = notifier_cls.return_value
        notifier.send_report.side_effect = ConnectionError("discord fora do ar")
        notifier.send_error.side_effect = ConnectionError("discord fora do ar")
        saga_http.scan.return_value = _scan_result()
        self.assertFalse(run_scan(_config(), self.state_path))
        self.assertIsNone(load_state(self.state_path))  # baseline continua pendente

    def test_failure_with_page_html_saves_debug(self, notifier_cls, saga_http):
        """Exceção com page_html: HTML salvo em debug_dir para recalibração."""
        with tempfile.TemporaryDirectory() as dbg:
            cfg = _config()
            cfg.saga.debug_dir = dbg
            exc = RuntimeError("layout mudou")
            exc.page_html = "<html>falha</html>"
            saga_http.scan.side_effect = exc
            self.assertFalse(run_scan(cfg, self.state_path))
            files = list(Path(dbg).glob("*-fatal.html"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(encoding="utf-8"), "<html>falha</html>")


class MainExitCodesTest(unittest.TestCase):
    def test_missing_config_returns_2(self):
        self.assertEqual(main(["--once", "--config", "nao_existe_123.ini"]), 2)


class MainLoopTest(unittest.TestCase):
    def test_loop_survives_run_scan_exception(self):
        """Regressão de bug futuro em run_scan não pode matar o modo contínuo."""
        with mock.patch("main.load_config", return_value=_config()), mock.patch(
            "main.config_to_safe_dict", return_value={}
        ), mock.patch(
            "main.run_scan", side_effect=RuntimeError("bug inesperado")
        ) as scan, mock.patch("main.time.sleep", side_effect=KeyboardInterrupt) as slp:
            self.assertEqual(main([]), 0)
        scan.assert_called_once()
        slp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Remover módulos e testes Selenium; tirar `selenium` do requirements**

```powershell
git rm src/browser.py src/login.py src/scheduler.py tests/test_browser.py tests/test_login.py tests/test_scheduler.py
```

`src/requirements.txt` vira:

```
requests>=2.32
tzdata>=2024.1
boto3>=1.34
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_config tests.test_main -v`
Expected: FAIL — `AttributeError: ... 'saga'` / `main` ainda importa `browser`/`login`/`scheduler` (ImportError). É o RED do cutover.

- [ ] **Step 5: `src/config.py` — `[selenium]`→`[saga]`, sem selectors/chrome**

5a. Remover o bloco inteiro `DEFAULT_SELECTORS = {...}` (as ~19 linhas do dicionário).

5b. Trocar a dataclass `SeleniumConfig` inteira por:

```python
@dataclass(frozen=True)
class SagaConfig:
    base_url: str
    schedule_url: str = ""
    request_timeout_seconds: int = 30
    debug_dir: str = "debug"
```

5c. Em `AppConfig`, trocar as linhas `selenium: SeleniumConfig` e
`selectors: dict[str, tuple[str, ...]]` por uma só:

```python
    saga: SagaConfig
```

5d. Remover a função `_load_selectors` inteira.

5e. No corpo de `load_config`, trocar o bloco `selenium = SeleniumConfig(...)`
por:

```python
    saga = SagaConfig(
        base_url=_require(parser, "saga", "base_url", errors),
        schedule_url=parser.get("saga", "schedule_url", fallback="").strip(),
        request_timeout_seconds=_get_int(
            parser, "saga", "request_timeout_seconds", 30, errors
        ),
        debug_dir=parser.get("saga", "debug_dir", fallback="debug").strip()
        or "debug",
    )
```

5f. Remover a linha `selectors = _load_selectors(parser)`.

5g. Na construção final `return AppConfig(...)`, trocar as linhas
`selenium=selenium,` e `selectors=selectors,` por `saga=saga,`.

5h. Atualizar a docstring do módulo: trocar a menção a `[selectors]`/ADR-0003
pelo texto:

```python
"""Carrega e valida config.ini → dataclasses frozen (ADR-0005).

A aquisição da escala é por HTTP direto (ADR-0011): a seção [saga] traz a
URL de login, a da escala e o timeout. Sem seletores CSS (o antigo
[selectors] saiu com o Selenium). No Lambda, segredos entram como
`overrides` de load_config (SSM → memória), nunca por arquivo.
"""
```

- [ ] **Step 6: `src/main.py` — `run_scan` sem driver**

6a. Trocar o bloco de imports (linhas ~14-29) por:

```python
from datetime import datetime

import saga_http
from availability import AvailabilityRules, enrich_day_schedule
from config import AppConfig, ConfigError, config_to_safe_dict, load_config
from discord import DiscordNotifier
from notifications import (
    NotifyState,
    diff_new_windows,
    extract_open_windows,
    extract_scanned_days,
    load_state,
    save_state,
)
from report import build_openings_message, build_report
```

(Some as importações de `browser`, `login`, `scheduler`; mantém
`argparse`, `logging`, `sys`, `time`, `Path` no topo do arquivo.)

6b. Remover a função `_quit_quietly` inteira.

6c. Trocar a função `_save_failure_state`… não: manter `_notify_failure` e
`_save_failure_state` como estão. Adicionar, logo após `_save_failure_state`,
a função:

```python
def _save_failure_debug(config, exc) -> None:
    """HTML da resposta no momento da falha: arquivo em debug_dir (útil no PC)
    e no log (única via de recuperação no Lambda — sem browser nem S3).

    Melhor esforço: roda dentro do handler de exceção de run_scan.
    """
    page_html = getattr(exc, "page_html", None)
    if not page_html:
        return
    try:
        directory = Path(config.saga.debug_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = directory / f"{stamp}-fatal.html"
        path.write_text(page_html, encoding="utf-8")
        logger.info("HTML de debug salvo em %s", path)
    except Exception:
        logger.exception("Falha ao salvar HTML de debug em disco")
    logger.info("HTML da página na falha (%d bytes):\n%s", len(page_html), page_html)
```

6d. Trocar a função `run_scan` inteira por:

```python
def run_scan(config: AppConfig, state_path: Path) -> bool:
    """Uma varredura completa. Nunca propaga exceção (o loop sobrevive)."""
    notifier = DiscordNotifier(config.discord.webhook_url)
    previous = load_state(state_path)
    try:
        result = saga_http.scan(config)
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
            notifier.send_report(build_report(availabilities, result.errors))
        else:
            if not previous.last_scan_ok:
                notifier.send_message("✅ Varredura voltou a funcionar.")
            new_windows = diff_new_windows(previous, windows)
            if new_windows:
                notifier.send_message(
                    build_openings_message(new_windows, config.aircraft)
                )
        save_state(
            state_path,
            NotifyState(
                windows=windows,
                days=extract_scanned_days(availabilities),
                last_scan_ok=True,
            ),
        )
        logger.info(
            "Varredura concluída: %d dia(s), %d erro(s), %d janela(s) 🟢",
            len(result.days),
            len(result.errors),
            len(windows),
        )
        return True
    except Exception as exc:
        logger.exception("Falha fatal na varredura")
        _save_failure_debug(config, exc)
        _notify_failure(notifier, previous, str(exc))
        _save_failure_state(state_path, previous)
        return False
```

- [ ] **Step 7: Renomear a seção nos arquivos de config**

7a. `config.ini.example` — trocar TODO o bloco `[selenium] ... debug_dir = debug`
e o bloco comentado `[selectors]` (até o fim do arquivo) por:

```ini
[saga]
; URL de login do SAGA
base_url = https://saga.example.com/login
; URL da página da escala (Escala → Meus Voos), de onde sai a variável
; allSchedules (ADR-0010). Vazio = usa a página pós-login.
schedule_url = https://aeroes.saga.aero/schedules/personal
; Timeout de cada requisição HTTP ao SAGA (segundos)
request_timeout_seconds = 30
; Pasta onde o HTML da página é salvo em falhas (para recalibração)
debug_dir = debug

[aircraft]
; Aeronaves monitoradas: MATRICULA = modelo (uma por linha) — ADR-0007.
; Somente estas aparecem no relatório, independente do status no SAGA.
; O modelo é texto livre exibido no relatório — prefira abreviado (C152).
PT-ABC = C152
PT-XYZ = C172

[logging]
; DEBUG | INFO | WARNING | ERROR
level = INFO
; Arquivo de log (vazio = somente console)
file =
```

(O arquivo perde as seções `[aircraft]`/`[logging]` antigas se estavam
depois de `[selenium]`; garanta que apareçam uma única vez, na ordem acima.)

7b. `config.ini` (LOCAL, com segredos — editar só as seções de infra): trocar
o cabeçalho `[selenium]` por `[saga]`, remover as chaves `headless`,
`page_load_timeout_seconds`, `element_timeout_seconds`, inserir
`request_timeout_seconds = 30`, manter `base_url`, `schedule_url`, `debug_dir`;
apagar a seção `[selectors]` inteira. Não tocar em `[credentials]`/`[discord]`.

7c. `src/config.lambda.ini` — trocar o bloco `[selenium]` (com chrome_*,
headless, timeouts) **e** a seção `[selectors]` por:

```ini
[saga]
base_url = https://aeroes.saga.aero/login
schedule_url = https://aeroes.saga.aero/schedules/personal
request_timeout_seconds = 30
; /tmp é o único FS gravável no Lambda; o HTML de falha também vai ao log.
debug_dir = /tmp/debug
```

Manter `[monitor]`, `[aircraft]`, `[logging]` como estão.

- [ ] **Step 8: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 158 testes (163 − 11 de browser/login/scheduler + 6 novos/ajustados em main/config; a contagem exata pode variar ±, o que importa é **OK sem falhas**).

- [ ] **Step 9: Verificar que Selenium sumiu do runtime**

Run: `.venv\Scripts\python -c "import ast,glob;[print(f) for f in glob.glob('src/*.py') if 'selenium' in open(f,encoding='utf-8').read()]"`
Expected: sem saída (nenhum módulo de runtime importa selenium).

- [ ] **Step 10: Commit**

```powershell
git add -A
git commit -m "refactor(aeroes_monitor): aquisicao HTTP direto; aposenta Selenium; [saga]"
```

---

### Task 4: `handler.py` — estado no DynamoDB

**Files:**
- Modify: `src/handler.py`
- Test: `tests/test_handler.py`

**Interfaces:**
- Consumes: `load_config(path, overrides)`, `run_scan`, `setup_logging` (existentes).
- Produces: `lambda_handler(event, context) -> {"ok": bool}`; env `STATE_TABLE` (obrigatória), `CONFIG_FILE`/`SSM_PREFIX`/`LOG_LEVEL` (com defaults). Item DynamoDB `{"id":{"S":"state"},"payload":{"S":<json>},"updated_at":{"S":<iso>}}`.

- [ ] **Step 1: Substituir `tests/test_handler.py` (RED)**

```python
"""Testes do handler Lambda com boto3/run_scan falsos (sem AWS nem browser)."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from botocore.exceptions import ClientError

import handler

ENV = {
    "STATE_TABLE": "aeroes-monitor-state",
    "CONFIG_FILE": "config.lambda.ini",
    "SSM_PREFIX": "/aeroes-monitor",
    "LOG_LEVEL": "INFO",
}


class FakeSSM:
    def __init__(self):
        self.calls = []

    def get_parameter(self, Name, WithDecryption=False):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": f"segredo:{Name.rsplit('/', 1)[1]}"}}


class FakeDDB:
    def __init__(self, item=None):
        self.item = item
        self.puts = []

    def get_item(self, TableName, Key, ConsistentRead=False):
        return {"Item": self.item} if self.item is not None else {}

    def put_item(self, TableName, Item):
        self.puts.append(Item)
        self.item = Item


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = Path(tmp.name) / "state.json"
        self.ssm = FakeSSM()
        self.ddb = FakeDDB()
        self.config = mock.Mock()
        for patcher in (
            mock.patch.dict(os.environ, ENV),
            mock.patch.object(handler, "STATE_PATH", self.state_path),
            mock.patch.object(handler, "_ssm_client", self.ssm),
            mock.patch.object(handler, "_ddb_client", self.ddb),
            mock.patch.object(handler, "_secrets_cache", None),
            mock.patch.object(handler, "setup_logging"),
        ):
            patcher.start()
        self.load_config = mock.patch.object(
            handler, "load_config", return_value=self.config
        ).start()
        self.run_scan = mock.patch.object(
            handler, "run_scan", return_value=True
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_baseline_writes_state_to_ddb(self):
        def scan(config, state_path):
            state_path.write_text('{"version": 2}', encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": True})
        self.run_scan.assert_called_once_with(self.config, self.state_path)
        self.assertEqual(len(self.ddb.puts), 1)
        self.assertEqual(self.ddb.puts[0]["id"]["S"], "state")
        self.assertEqual(self.ddb.puts[0]["payload"]["S"], '{"version": 2}')

    def test_overrides_carry_ssm_secrets_and_log_level(self):
        handler.lambda_handler({}, None)
        overrides = self.load_config.call_args.kwargs["overrides"]
        self.assertEqual(
            overrides[("credentials", "username")], "segredo:saga-username"
        )
        self.assertEqual(
            overrides[("credentials", "password")], "segredo:saga-password"
        )
        self.assertEqual(
            overrides[("discord", "webhook_url")], "segredo:discord-webhook-url"
        )
        self.assertEqual(overrides[("logging", "level")], "INFO")
        self.assertEqual([dec for _, dec in self.ssm.calls], [True, True, True])

    def test_secrets_cached_across_warm_invocations(self):
        handler.lambda_handler({}, None)
        handler.lambda_handler({}, None)
        self.assertEqual(len(self.ssm.calls), 3)

    def test_existing_item_available_to_scan(self):
        self.ddb.item = {"id": {"S": "state"}, "payload": {"S": '{"version": 2}'}}
        seen = {}

        def scan(config, state_path):
            seen["state"] = state_path.read_text(encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        handler.lambda_handler({}, None)
        self.assertEqual(seen["state"], '{"version": 2}')

    def test_missing_item_removes_stale_local_copy(self):
        self.state_path.write_text("velho", encoding="utf-8")
        self.run_scan.return_value = False  # varredura falhou: nada gravado
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": False})
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.ddb.puts, [])

    def test_unexpected_ddb_error_propagates_to_errors_metric(self):
        def boom(TableName, Key, ConsistentRead=False):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "x"}}, "GetItem"
            )

        self.ddb.get_item = boom
        with self.assertRaises(ClientError):
            handler.lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_handler -v`
Expected: FAIL — handler ainda usa S3 (`_download_state`/`STATE_BUCKET`); `handler._ddb_client` não existe.

- [ ] **Step 3: Substituir `src/handler.py`**

```python
"""Entrypoint AWS Lambda: SSM (segredos) e DynamoDB (estado) em volta de run_scan.

Fluxo por invocação: segredos do SSM (cache no cold start) → GetItem do
state.json no DynamoDB para /tmp → mesmo run_scan do modo local → PutItem do
estado. Debug de falha vai ao CloudWatch (run_scan loga o HTML), não mais S3.

Semântica de erro: falha de varredura TRATADA retorna {"ok": false} sem
exceção (o app já avisou no Discord na transição). Exceção NÃO tratada
(SSM/DDB negados, bug) propaga de propósito — vira métrica Errors e dispara o
alarme, cobrindo exatamente o buraco em que o Discord não pôde ser avisado.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from config import load_config
from main import run_scan, setup_logging

# Logs em BRT no Lambda (Linux). TZ é chave reservada nas env vars da função,
# então setamos aqui; no-op no Windows local (sem time.tzset).
if hasattr(time, "tzset"):
    os.environ.setdefault("TZ", "America/Sao_Paulo")
    time.tzset()

logger = logging.getLogger(__name__)

STATE_PATH = Path("/tmp/state.json")
STATE_ID = "state"
SECRET_NAMES = ("saga-username", "saga-password", "discord-webhook-url")

_ssm_client = None
_ddb_client = None
_secrets_cache: dict[str, str] | None = None


def _ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def _ddb():
    global _ddb_client
    if _ddb_client is None:
        _ddb_client = boto3.client("dynamodb")
    return _ddb_client


def _load_secrets() -> dict[str, str]:
    """3 SecureStrings do SSM; cache de módulo (1 leitura por cold start)."""
    global _secrets_cache
    if _secrets_cache is None:
        prefix = os.environ["SSM_PREFIX"].rstrip("/")
        _secrets_cache = {
            name: _ssm().get_parameter(
                Name=f"{prefix}/{name}", WithDecryption=True
            )["Parameter"]["Value"]
            for name in SECRET_NAMES
        }
    return _secrets_cache


def _load_state(table: str) -> None:
    """GetItem → /tmp/state.json. Item ausente = baseline (como no modo local).

    ConsistentRead: nunca diffar contra réplica atrasada. Remove cópia local
    obsoleta de invocação anterior (warm start) quando não há item.
    """
    resp = _ddb().get_item(
        TableName=table, Key={"id": {"S": STATE_ID}}, ConsistentRead=True
    )
    item = resp.get("Item")
    if item and "payload" in item:
        STATE_PATH.write_text(item["payload"]["S"], encoding="utf-8")
    else:
        STATE_PATH.unlink(missing_ok=True)


def _save_state(table: str) -> None:
    """PutItem sempre que o arquivo existir (item único, escrita atômica)."""
    if STATE_PATH.exists():
        _ddb().put_item(
            TableName=table,
            Item={
                "id": {"S": STATE_ID},
                "payload": {"S": STATE_PATH.read_text(encoding="utf-8")},
                "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
            },
        )


def lambda_handler(event, context) -> dict:
    table = os.environ["STATE_TABLE"]
    secrets = _load_secrets()
    config = load_config(
        os.environ.get("CONFIG_FILE", "config.lambda.ini"),
        overrides={
            ("credentials", "username"): secrets["saga-username"],
            ("credentials", "password"): secrets["saga-password"],
            ("discord", "webhook_url"): secrets["discord-webhook-url"],
            ("logging", "level"): os.environ.get("LOG_LEVEL", "INFO"),
        },
    )
    setup_logging(config.logging)
    _load_state(table)
    ok = run_scan(config, STATE_PATH)
    _save_state(table)
    return {"ok": ok}
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK (test_handler agora com 6 casos DynamoDB).

- [ ] **Step 5: Commit**

```powershell
git add src/handler.py tests/test_handler.py
git commit -m "feat(aeroes_monitor): handler guarda estado no DynamoDB (item unico atomico)"
```

---

### Task 5: `template.yaml` zip + DynamoDB; remover Dockerfile

**Files:**
- Modify: `template.yaml`
- Remove: `Dockerfile`, `.dockerignore`

**Interfaces:**
- Consumes: `handler.lambda_handler`, env `STATE_TABLE`/`CONFIG_FILE`/`SSM_PREFIX`/`LOG_LEVEL` (Task 4); `src/` como `CodeUri`.
- Produces: stack `aeroes-monitor` com função zip, tabela `aeroes-monitor-state`, agendamento, alarme, SNS. Outputs `FunctionName`/`StateTableName`.

- [ ] **Step 1: Substituir `template.yaml`**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: >-
  aeroes_monitor - varredura read-only da escala SAGA a cada 20 min
  (06:00-23:40 BRT) por HTTP direto, estado no DynamoDB, segredos no SSM,
  aviso no Discord. Custo estrutural R$ 0/mes.
  Spec: docs/superpowers/specs/2026-07-13-requests-acquisition-design.md

Parameters:
  AlertEmail:
    Type: String
    Default: pedroh723@gmail.com
    Description: E-mail que recebe o alarme de Errors (assinatura SNS).

Resources:
  MonitorFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: aeroes-monitor
      CodeUri: src/
      Handler: handler.lambda_handler
      Runtime: python3.13
      Architectures: [x86_64]
      MemorySize: 256
      Timeout: 120
      # Nunca duas varreduras simultaneas: estado consistente, sem
      # notificacao dupla (spec).
      ReservedConcurrentExecutions: 1
      # Sem retry do proprio Lambda em erro assincrono: a proxima varredura
      # (20 min) e o retry natural.
      EventInvokeConfig:
        MaximumRetryAttempts: 0
      Environment:
        Variables:
          STATE_TABLE: !Ref StateTable
          CONFIG_FILE: config.lambda.ini
          SSM_PREFIX: /aeroes-monitor
          LOG_LEVEL: INFO
          # TZ e chave reservada do Lambda: setada no proprio handler.
      Events:
        Every20Min:
          Type: ScheduleV2
          Properties:
            # 06:00, 06:20, ..., 23:40 BRT = 54 varreduras/dia.
            ScheduleExpression: cron(0/20 6-23 * * ? *)
            ScheduleExpressionTimezone: America/Sao_Paulo
            RetryPolicy:
              MaximumRetryAttempts: 0
      Policies:
        - Statement:
            - Sid: SsmSecretsReadOnly
              Effect: Allow
              Action: ssm:GetParameter
              Resource:
                - !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/aeroes-monitor/saga-username
                - !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/aeroes-monitor/saga-password
                - !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/aeroes-monitor/discord-webhook-url
            - Sid: StateReadWrite
              Effect: Allow
              Action:
                - dynamodb:GetItem
                - dynamodb:PutItem
              Resource: !GetAtt StateTable.Arn

  StateTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: aeroes-monitor-state
      # Provisioned 1/1 cabe na faixa always-free (25/25); on-demand NAO e gratis.
      BillingMode: PROVISIONED
      ProvisionedThroughput:
        ReadCapacityUnits: 1
        WriteCapacityUnits: 1
      AttributeDefinitions:
        - AttributeName: id
          AttributeType: S
      KeySchema:
        - AttributeName: id
          KeyType: HASH

  MonitorLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /aws/lambda/aeroes-monitor
      RetentionInDays: 30

  AlertTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: aeroes-monitor-alerts

  AlertSubscription:
    Type: AWS::SNS::Subscription
    Properties:
      TopicArn: !Ref AlertTopic
      Protocol: email
      Endpoint: !Ref AlertEmail

  ErrorsAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      AlarmName: aeroes-monitor-errors
      AlarmDescription: >-
        Handler morrendo sem conseguir avisar o Discord (excecao nao
        tratada) por 3 janelas seguidas de 20 min.
      Namespace: AWS/Lambda
      MetricName: Errors
      Dimensions:
        - Name: FunctionName
          Value: !Ref MonitorFunction
      Statistic: Sum
      Period: 1200
      EvaluationPeriods: 3
      Threshold: 1
      ComparisonOperator: GreaterThanOrEqualToThreshold
      TreatMissingData: notBreaching
      AlarmActions:
        - !Ref AlertTopic

Outputs:
  FunctionName:
    Value: !Ref MonitorFunction
  StateTableName:
    Value: !Ref StateTable
  AlertTopicArn:
    Value: !Ref AlertTopic
```

- [ ] **Step 2: Remover Dockerfile e .dockerignore**

```powershell
git rm Dockerfile .dockerignore
```

- [ ] **Step 3: Validar o template**

```powershell
.venv\Scripts\cfn-lint template.yaml
```

Expected: saída vazia (exit 0). (`cfn-lint` foi instalado na etapa anterior de deploy; se faltar: `.venv\Scripts\python -m pip install cfn-lint`.)

- [ ] **Step 4: Sanidade da suíte**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK.

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "feat(aeroes_monitor): template SAM zip + DynamoDB; remove container/ECR"
```

---

### Task 6: ADR-0011, banners de superseded e README

**Files:**
- Create: `docs/adr/0011-http-direto-sem-browser.md`
- Modify: `docs/adr/0002-selenium-over-api.md`, `docs/adr/0003-configurable-css-selectors.md`, `docs/adr/README.md`, `README.md`

**Interfaces:**
- Consumes: nomes/decisões das Tasks 1–5. Produces: documentação; nada consumido por código.

- [ ] **Step 1: Criar `docs/adr/0011-http-direto-sem-browser.md`**

```markdown
# ADR-0011: Aquisição por HTTP direto (requests), sem browser

## Status
Aceito (2026-07-13). Supersede [[0002-selenium-over-api]] e a parte de
seletores de [[0003-configurable-css-selectors]].

## Contexto
[[0002-selenium-over-api]] adotou Selenium por supor que a página exigia
renderização client-side e que HTTP puro seria inviável. Para rodar na AWS
sem custo (pedido do Pedro), o Chrome forçava Lambda por container e ECR — o
único item pago do desenho (~R$ 1/mês, permanente).

Um probe ao vivo (2026-07-13) refutou a suposição de 0002:
- O HTML de `/schedules/personal` é server-rendered: `const allSchedules =
  [...]` vem embutido no fonte (187 KB de JSON inline), sem JS a executar.
- O login é um form Laravel padrão (`_token` + `email` + `password`), sem
  captcha nem desafio de WAF.
- Fluxo completo em `requests` puro: GET login → POST login → GET escala
  (440 registros extraídos) → GET /aisweb/sun/SBVT. 4/4 OK em 21 s.

## Decisão
`saga_http.py` faz a varredura inteira numa sessão `requests`, expondo
`scan(config) -> ScanResult` (a mesma fronteira do antigo `ScheduleScanner`).
Login segue sendo o único POST — [[0001-read-only-scope]] intacto. A escala
sai da variável `allSchedules` do HTML ([[0010-allschedules-js-variable]]) e o
sol do XML de /aisweb/sun/SBVT ([[0008-sunrise-sunset-from-saga-page]]). O
Lambda vira zip (sem ECR); o estado, DynamoDB. Selenium/Chrome e a seção
`[selectors]` são removidos; a config de rede fica em `[saga]`.

## Consequências
**Positivas**
- Custo estrutural R$ 0/mês: sem ECR, sem container. Lambda zip 256 MB/~10 s
  (contra 2 GB/~90 s). Sem Docker Desktop no fluxo de deploy.
- Menos superfície frágil: sem esperas de DOM, sem calibração de seletores,
  sem `TimeoutException`. Recalibração agora é conferir o form de login no
  HTML salvo em falha.
- `python src/main.py` local também fica mais rápido e sem dependência de
  Chrome instalado.

**Negativas / trade-offs**
- Depende do form de login e do contrato `allSchedules` continuarem estáveis
  (mesma classe de risco que [[0010-allschedules-js-variable]] já assumia).
- Se o SAGA adotar anti-bot/Cloudflare, a rota HTTP quebra. Plano B: a rota
  container está preservada no git (branch `feat/aeroes-aws-lambda`, commit
  `cf0f83f` — Dockerfile `859c48f`, template imagem `2e24b69`), reabilitável
  com custo ~R$ 1/mês. A quebra é avisada no Discord na transição ok→falha.

## Alternativas consideradas
- **Manter Selenium (container+ECR)**: robustez marginal a mais (browser real
  tolera JS/anti-bot) ao custo de ~R$ 1/mês permanente e de todo o aparato
  Docker/ECR. Vira o plano B, não o padrão.
- **Selenium só no modo local, HTTP na nuvem**: dois caminhos de aquisição
  para manter e ver divergir — descartado por manutenção dobrada.
```

- [ ] **Step 2: Banner de superseded em `docs/adr/0002-selenium-over-api.md`**

Trocar as duas linhas:

```markdown
## Status
Aceito
```

por:

```markdown
## Status
Superado por [[0011-http-direto-sem-browser]] (2026-07-13): a aquisição
migrou para HTTP direto (requests), sem Selenium/Chrome. Contexto histórico
preservado abaixo.
```

- [ ] **Step 3: Banner em `docs/adr/0003-configurable-css-selectors.md`**

Trocar as duas linhas:

```markdown
## Status
Aceito
```

por:

```markdown
## Status
Superado por [[0011-http-direto-sem-browser]] (2026-07-13): com a aquisição
HTTP, não há mais DOM a selecionar; a seção `[selectors]` e os defaults foram
removidos. Contexto histórico preservado abaixo.
```

- [ ] **Step 4: Índice `docs/adr/README.md`**

Ler o arquivo e acrescentar, seguindo o formato das linhas existentes, uma
entrada para o ADR-0011 (título "Aquisição por HTTP direto (requests), sem
browser"). Se houver uma tabela/lista com status, marcar 0002 e 0003 como
"Superado por 0011".

- [ ] **Step 5: README — seção AWS e troubleshooting**

5a. Substituir a seção inteira que começa em `## Deploy na AWS (Lambda)` (até
o fim do arquivo) por:

```markdown
## Deploy na AWS (Lambda)

O monitor roda sem PC ligado e **sem custo** (R$ 0/mês estrutural):
EventBridge Scheduler dispara um Lambda **zip** a cada 20 min (06:00–23:40,
horário de Brasília), o estado vive em uma tabela DynamoDB
(`aeroes-monitor-state`, item único) e os segredos em SSM Parameter Store
(SecureString). A aquisição é por HTTP direto (`requests`), sem browser —
por isso não há container nem ECR. Infra inteira em `template.yaml` (SAM).
Design: `docs/superpowers/specs/2026-07-13-requests-acquisition-design.md`.

O fluxo local (`python src/main.py` com `config.ini`) segue funcionando — mas
não rode os dois ao mesmo tempo: PC + AWS no mesmo webhook duplicam toda
notificação.

### Arquivos

- `src/handler.py` — entrypoint do Lambda (DynamoDB + SSM em volta de
  `run_scan`).
- `src/config.lambda.ini` — config **não-secreta** da nuvem (commitada; sem
  seções de credenciais/Discord — o handler injeta os segredos do SSM via
  `load_config(..., overrides=...)`).
- `template.yaml` — função zip (`CodeUri: src/`, 256 MB / 120 s /
  concorrência 1), tabela DynamoDB provisioned 1/1 (dentro do always-free),
  agendamento `cron(0/20 6-23 * * ? *)` no fuso `America/Sao_Paulo`, alarme
  `Errors >= 1` (3×20 min) → SNS → e-mail.

### Pré-requisitos (uma vez)

1. Instalar AWS CLI e SAM CLI: `winget install -e --id Amazon.AWSCLI` e
   `winget install -e --id Amazon.SAM-CLI`. **Docker não é necessário** (zip).
2. Conta AWS nova: escolher o **plano pago** na inscrição (os créditos de
   boas-vindas valem 12 meses; o plano free fecha a conta em 6 meses).
   Usuário IAM de deploy dedicado com MFA + access key (**jamais** a do root)
   → `aws configure` (região `sa-east-1`).
3. Criar os 3 segredos (senha via prompt, fora do histórico do shell):

   ```powershell
   aws ssm put-parameter --name /aeroes-monitor/saga-username --type SecureString --value (Read-Host "usuário SAGA")
   $sec = Read-Host "senha SAGA" -AsSecureString
   aws ssm put-parameter --name /aeroes-monitor/saga-password --type SecureString --value ([Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)))
   aws ssm put-parameter --name /aeroes-monitor/discord-webhook-url --type SecureString --value (Read-Host "webhook Discord")
   ```

### Build e deploy

```powershell
sam build          # resolve requirements.txt puro-Python; sem Docker
sam deploy --guided   # 1ª vez (gera samconfig.toml); depois só: sam deploy
```

Após o primeiro deploy: confirmar a assinatura SNS no e-mail, invocar
manualmente (`aws lambda invoke --function-name aeroes-monitor out.json`),
conferir o baseline no Discord e **desligar o modo contínuo no PC**.
Logs: `sam logs --stack-name aeroes-monitor --tail`.

> **Plano B (container):** se o SAGA um dia bloquear clientes sem browser, a
> rota Selenium+container está preservada no git (commit `cf0f83f`) e volta
> com custo ~R$ 1/mês de ECR.
```

5b. No bloco `## Solução de problemas`, trocar o bullet do
`TimeoutException: Nenhum seletor visível` por:

```markdown
- **`LoginError` / login não confirmado** — o form de login do SAGA mudou ou
  as credenciais estão erradas. O HTML da página no momento da falha é salvo
  em `debug/` (e vai ao log no Lambda); confira os campos `_token`, `email`,
  `password` contra `saga_http.py`.
```

5c. Se houver uma seção de "Calibração de seletores" (referente ao antigo
`[selectors]`/ADR-0003), removê-la: com a aquisição HTTP não há seletores a
calibrar. Ajustar qualquer menção a `[selenium]` para `[saga]`.

- [ ] **Step 6: Sanidade final e commit**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK.

```powershell
git add -A
git commit -m "docs(aeroes_monitor): ADR-0011 (HTTP direto) e README do deploy zip/DynamoDB"
```

---

## Cobertura da spec (self-review)

| Item da spec | Task |
|---|---|
| `saga_http.py` com contrato `scan(config) -> ScanResult` | 2 |
| Login (_token/email/password), único POST — ADR-0001 | 2 |
| Extração de `allSchedules` (regex ancorada) + JSON | 2 |
| Sol recuperável (ScanError, ADR-0008) | 2 |
| `ScanHttpError(page_html)` / `LoginError`; quem salva HTML é `run_scan` | 2, 3 |
| UA de Chrome pinado; timeout por chamada; sem retry | 2 |
| `[selenium]`→`[saga]` (`SagaConfig`); some selectors/chrome/headless | 3 |
| `overrides` de runtime preservados | 3 (config), 4 (handler) |
| `main.run_scan` sem driver; debug = HTML em debug_dir + log | 3 |
| Remover browser/login/scheduler + testes; selenium fora do requirements | 3 |
| Selenium aposentado (fonte única HTTP) | 3 |
| Layout `src/` + `CodeUri: src/` (segredo fora do zip) | 1, 5 |
| `tests/__init__.py` no sys.path; `python src/main.py` local | 1 |
| handler S3→DynamoDB (`GetItem`/`PutItem`, item único, atômico) | 4 |
| env `STATE_TABLE` substitui `STATE_BUCKET`/`STATE_KEY`/`DEBUG_PREFIX` | 4, 5 |
| TZ setado no handler (reservada no Lambda), no-op no Windows | 4 |
| template zip 256 MB/120 s; `StateTable` provisioned 1/1; IAM DDB+SSM; sem S3/ECR | 5 |
| Remover Dockerfile/.dockerignore | 5 |
| Debug no CloudWatch (HTML logado); sem S3 debug/ | 3 (log), 4 (sem upload) |
| ADR-0011 supersede 0002/0003; plano B por hash | 6 |
| README runbook sem Docker; plano pago; troubleshooting sem seletores | 6 |
| Custo R$ 0/mês; read-only preservado | 4, 5 (infra), constraints |
| Fora de escopo: Actions/OIDC, follow-ups menores | — (não tocados) |
| Validação ao vivo `python src/main.py --once` | rollout (pós-plano, com Pedro) |
