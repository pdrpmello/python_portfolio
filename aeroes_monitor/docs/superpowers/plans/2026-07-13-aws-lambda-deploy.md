# Deploy na AWS com Lambda — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rodar o aeroes_monitor na AWS Lambda (imagem de container) a cada 20 min, 06:00–23:40 BRT, com estado no S3, segredos no SSM e IaC (SAM) versionada — sem alterar o fluxo local.

**Architecture:** EventBridge Scheduler dispara um Lambda de container (Chrome for Testing pinado na imagem) que baixa `state.json` do S3, injeta segredos do SSM como overrides em `load_config` e chama o mesmo `run_scan` de hoje; depois devolve o estado ao S3. Erros tratados retornam `{"ok": false}`; exceções não tratadas viram métrica `Errors` e alarme SNS→e-mail.

**Tech Stack:** Python 3.13 (imagem `public.ecr.aws/lambda/python:3.13`), Selenium + Chrome for Testing pinado, boto3, AWS SAM (`template.yaml`), S3, SSM Parameter Store, EventBridge Scheduler, CloudWatch/SNS.

**Spec:** `docs/superpowers/specs/2026-07-12-aws-lambda-deploy-design.md`

## Global Constraints

- Suíte de testes: `.venv\Scripts\python -m unittest -v` rodada do diretório `aeroes_monitor` (PowerShell). Hoje passa com **135 testes**; nunca regredir. **pytest NÃO está no venv** — use apenas unittest.
- Repo git fica no diretório pai (`python_portfolio`); commits com prefixo `(aeroes_monitor)` no formato dos existentes (`feat(aeroes_monitor): …`, `test:`/`docs:`/`fix:` conforme o caso).
- Comentários, docstrings e mensagens de log em **pt-BR**, no estilo dos módulos existentes (docstring de módulo citando PRD/ADR quando fizer sentido).
- **Segredos jamais em arquivo commitado, log ou imagem Docker**: `config.ini` continua no `.gitignore`; `config.lambda.ini` (commitado) NÃO pode ter `[credentials]`/`[discord]`; segredos só no SSM (SecureString) e em memória.
- Fluxo local inalterado: campos novos têm default vazio; `load_config("config.ini")` sem overrides se comporta exatamente como hoje.
- Região AWS: **sa-east-1**. Nomes fixos: stack `aeroes-monitor`, bucket `aeroes-monitor-state-<account-id>`, parâmetros `/aeroes-monitor/saga-username|saga-password|discord-webhook-url`.
- Lambda: memória 2048 MB, timeout 300 s, concorrência reservada 1, `cron(0/20 6-23 * * ? *)` fuso `America/Sao_Paulo`, sem retry (Scheduler e async config).
- `TZ` é **chave reservada** de env var no Lambda (CloudFormation rejeita) — a spec pede `TZ=America/Sao_Paulo`; entra como `ENV` no Dockerfile (efeito idêntico). Não colocar `TZ` no `template.yaml`.
- Python local do venv é 3.14.5 — a imagem usa 3.13 (pin da spec); o código já é compatível com ambos.

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `config.py` | modificar | `load_config(path, overrides=None)`; campos `chrome_binary`/`chrome_extra_args` em `[selenium]` |
| `browser.py` | modificar | `create_driver` aplica binário/flags quando preenchidos |
| `saga_data.py` | modificar | `local_today()` — data no fuso do aeroclube |
| `scheduler.py` | modificar | troca `date.today()` por `local_today()` (2 usos) |
| `config.lambda.ini` | criar | config não-secreta da nuvem (commitada) |
| `handler.py` | criar | entrypoint Lambda: SSM + S3 ao redor de `run_scan` |
| `requirements.txt` | modificar | + `boto3>=1.34` |
| `Dockerfile`, `.dockerignore` | criar | imagem Lambda com Chrome for Testing pinado |
| `template.yaml` | criar | SAM: função, bucket, agendamento, alarme, SNS, IAM |
| `.gitignore` | modificar | + `.aws-sam/`, `locals.json` |
| `README.md` | modificar | seção "Deploy na AWS (Lambda)" com runbook |
| `tests/test_config.py`, `tests/test_browser.py`, `tests/test_saga_data.py`, `tests/test_scheduler.py`, `tests/test_handler.py` | modificar/criar | TDD de tudo acima |

Tasks 1–8 são código/documentação executáveis por subagente. Tasks 9–11 são o runbook interativo (precisam do Pedro: instaladores, console AWS, Docker) — não despachar para subagente.

---

### Task 1: `config.py` — overrides e campos de Chrome

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `load_config(path: str | Path, overrides: dict[tuple[str, str], str] | None = None) -> AppConfig`; `SeleniumConfig.chrome_binary: str = ""`; `SeleniumConfig.chrome_extra_args: tuple[str, ...] = ()`. Overrides são aplicados APÓS ler o .ini e ANTES da validação (criam a seção se faltar) — é assim que o handler injeta `[credentials]`/`[discord]` vindos do SSM.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_config.py`, adicionar após a constante `VALID_INI`:

```python
CHROME_INI = VALID_INI.replace(
    "base_url = https://saga.example.com/login",
    """base_url = https://saga.example.com/login
chrome_binary = /opt/chrome-linux64/chrome
chrome_extra_args =
    --no-sandbox
    --disable-dev-shm-usage""",
)
```

E dentro de `LoadConfigTest`, os métodos:

```python
    def test_overrides_fill_missing_sections_and_win_over_file(self):
        ini = """
[selenium]
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
        # Seções ausentes no .ini são criadas pelo override…
        self.assertEqual(config.credentials.username, "piloto@example.com")
        self.assertEqual(
            config.discord.webhook_url, "https://discord.com/api/webhooks/1/a"
        )
        # …e override vence valor existente no arquivo.
        self.assertEqual(config.monitor.max_days, 5)

    def test_no_overrides_keeps_current_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI), overrides=None)
        self.assertEqual(config.credentials.username, "piloto@example.com")

    def test_chrome_fields_default_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertEqual(config.selenium.chrome_binary, "")
        self.assertEqual(config.selenium.chrome_extra_args, ())

    def test_chrome_extra_args_one_per_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, CHROME_INI))
        self.assertEqual(config.selenium.chrome_binary, "/opt/chrome-linux64/chrome")
        self.assertEqual(
            config.selenium.chrome_extra_args,
            ("--no-sandbox", "--disable-dev-shm-usage"),
        )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_config -v`
Expected: FAIL — `TypeError: load_config() got an unexpected keyword argument 'overrides'` e `AttributeError: ... no attribute 'chrome_binary'`.

- [ ] **Step 3: Implementar em `config.py`**

3a. Novos campos em `SeleniumConfig` (após `debug_dir: str = "debug"`):

```python
    # Deploy em container (Lambda): binário do Chrome baked na imagem e
    # flags extras (--no-sandbox etc.). Vazios ⇒ comportamento local atual.
    chrome_binary: str = ""
    chrome_extra_args: tuple[str, ...] = ()
```

3b. Assinatura e aplicação dos overrides — trocar a linha `def load_config(path: str | Path) -> AppConfig:` e inserir o loop logo após `parser.read(path, encoding="utf-8")`:

```python
def load_config(
    path: str | Path, overrides: dict[tuple[str, str], str] | None = None
) -> AppConfig:
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

    # Overrides {(seção, chave): valor} aplicados antes da validação — é por
    # aqui que o handler Lambda injeta segredos do SSM sem tocar disco.
    for (section, key), value in (overrides or {}).items():
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, key, value)
```

3c. Parsing dos campos novos — na construção de `SeleniumConfig`, após o argumento `debug_dir=...`:

```python
        chrome_binary=parser.get("selenium", "chrome_binary", fallback="").strip(),
        chrome_extra_args=tuple(
            line.strip()
            for line in parser.get(
                "selenium", "chrome_extra_args", fallback=""
            ).splitlines()
            if line.strip()
        ),
```

3d. Atualizar a docstring do módulo (1ª linha continua igual) acrescentando ao final:

```python
No Lambda, segredos entram como `overrides` de load_config (SSM → memória),
nunca por arquivo (spec 2026-07-12).
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 139 testes (135 + 4).

- [ ] **Step 5: Commit**

```powershell
git add config.py tests/test_config.py
git commit -m "feat(aeroes_monitor): load_config overrides + chrome_binary/extra_args"
```

---

### Task 2: `browser.py` — aplicar binário e flags do Chrome

**Files:**
- Modify: `browser.py:19-28` (`create_driver`)
- Test: `tests/test_browser.py`

**Interfaces:**
- Consumes: `SeleniumConfig.chrome_binary`, `SeleniumConfig.chrome_extra_args` (Task 1).
- Produces: `create_driver(cfg)` inalterado na assinatura; com campos preenchidos, seta `options.binary_location` e adiciona cada flag.

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_browser.py`: adicionar aos imports do topo `from types import SimpleNamespace`, `from unittest import mock` e `create_driver` no import de `browser`. Nova classe ao final (antes do `if __name__`):

```python
class CreateDriverTest(unittest.TestCase):
    """create_driver com webdriver.Chrome mockado (sem browser real)."""

    def _cfg(self, **kw):
        base = dict(
            headless=True,
            page_load_timeout_seconds=30,
            chrome_binary="",
            chrome_extra_args=(),
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_chrome_binary_and_extra_args_applied(self):
        with mock.patch("browser.webdriver.Chrome") as chrome_cls:
            create_driver(
                self._cfg(
                    chrome_binary="/opt/chrome-linux64/chrome",
                    chrome_extra_args=("--no-sandbox", "--disable-dev-shm-usage"),
                )
            )
        options = chrome_cls.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, "/opt/chrome-linux64/chrome")
        self.assertIn("--no-sandbox", options.arguments)
        self.assertIn("--disable-dev-shm-usage", options.arguments)

    def test_defaults_leave_binary_unset(self):
        with mock.patch("browser.webdriver.Chrome") as chrome_cls:
            create_driver(self._cfg())
        options = chrome_cls.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, "")
        self.assertIn("--headless=new", options.arguments)
        self.assertNotIn("--no-sandbox", options.arguments)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_browser -v`
Expected: FAIL — `binary_location` fica `""` no primeiro teste (flags não aplicadas).

- [ ] **Step 3: Implementar**

Em `browser.py`, `create_driver` vira:

```python
def create_driver(cfg) -> webdriver.Chrome:
    """Chrome via Selenium Manager (sem gerenciar chromedriver — ADR-0002).

    Em container (Lambda), cfg.chrome_binary aponta o Chrome baked na imagem
    e cfg.chrome_extra_args traz as flags de sandbox/tmp — com chromedriver
    pinado no PATH, o Selenium Manager resolve local, sem baixar nada.
    """
    options = Options()
    if cfg.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    if cfg.chrome_binary:
        options.binary_location = cfg.chrome_binary
    for arg in cfg.chrome_extra_args:
        options.add_argument(arg)
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(cfg.page_load_timeout_seconds)
    return driver
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 141 testes.

- [ ] **Step 5: Commit**

```powershell
git add browser.py tests/test_browser.py
git commit -m "feat(aeroes_monitor): create_driver honra chrome_binary e chrome_extra_args"
```

---

### Task 3: data no fuso do aeroclube (`local_today`)

Follow-up nº 5 da revisão do PR #1: `date.today()` usa o relógio da máquina — no Lambda (UTC), entre 21:00 e 00:00 BRT a varredura olharia o dia errado.

**Files:**
- Modify: `saga_data.py` (nova função ao lado de `LOCAL_TZ`)
- Modify: `scheduler.py:11,61,115` (dois usos de `date.today()` + imports)
- Test: `tests/test_saga_data.py`, `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `saga_data.LOCAL_TZ` (existente).
- Produces: `saga_data.local_today() -> date` — importada por `scheduler.py`.

- [ ] **Step 1: Teste que falha em `tests/test_saga_data.py`**

Garantir que os imports do arquivo incluam `from unittest import mock`, `from datetime import date, datetime` e, do módulo, `from saga_data import LOCAL_TZ, UTC, local_today` (mesclar com o import existente de `saga_data`). Nova classe:

```python
class LocalTodayTest(unittest.TestCase):
    def test_converts_now_to_aeroclub_timezone(self):
        # 01:30 UTC de 13/07 ainda é 22:30 de 12/07 em São Paulo (UTC-3):
        # no Lambda (relógio UTC), date.today() retornaria 13/07 — errado.
        fake_now = datetime(2026, 7, 13, 1, 30, tzinfo=UTC)
        with mock.patch("saga_data.datetime") as dt:
            dt.now.side_effect = lambda tz: fake_now.astimezone(tz)
            self.assertEqual(local_today(), date(2026, 7, 12))
            dt.now.assert_called_once_with(LOCAL_TZ)
```

(O `side_effect` exige `tz` posicional: se a implementação chamar `datetime.now()` sem fuso, o teste quebra — é proposital.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_data -v`
Expected: FAIL — `ImportError: cannot import name 'local_today'`.

- [ ] **Step 3: Implementar em `saga_data.py`**

Logo após `UTC = ZoneInfo("UTC")`:

```python
def local_today() -> date:
    """Data atual no fuso do aeroclube, não no da máquina.

    Em servidor UTC (Lambda), date.today() viraria o dia seguinte entre
    21:00 e 00:00 BRT e a varredura olharia a grade errada.
    """
    return datetime.now(LOCAL_TZ).date()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv\Scripts\python -m unittest tests.test_saga_data -v`
Expected: PASS.

- [ ] **Step 5: Trocar os usos em `scheduler.py` (com teste antes)**

5a. Em `tests/test_scheduler.py`, fixar a data do `_scan` (fica determinístico — hoje o teste depende do relógio da máquina) e cobrar o uso de `local_today`:

```python
def _scan(driver, config=None, today=date(2026, 7, 9)):
    scanner = ScheduleScanner(driver, config or _config())
    with mock.patch("scheduler.is_login_page", return_value=False), \
         mock.patch("scheduler.local_today", return_value=today):
        return scanner.scan()
```

E em `test_happy_path_builds_days_from_all_schedules`, trocar a asserção
`self.assertEqual(result.days[0].day, date.today())` por:

```python
        self.assertEqual(result.days[0].day, date(2026, 7, 9))
```

Run: `.venv\Scripts\python -m unittest tests.test_scheduler -v`
Expected: FAIL — `AttributeError: <module 'scheduler'> does not have the attribute 'local_today'`.

5b. Em `scheduler.py`:
- Remover `from datetime import date` (linha 11 — fica sem uso).
- Trocar o import de saga_data por:

```python
from saga_data import build_day_schedules, local_today, parse_sun_xml, utc_time_to_local
```

- Em `scan()`, trocar `date.today(),` por `local_today(),`.
- Em `_read_sun_times()`, trocar `today = date.today()` por `today = local_today()`.

- [ ] **Step 6: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 142 testes.

- [ ] **Step 7: Commit**

```powershell
git add saga_data.py scheduler.py tests/test_saga_data.py tests/test_scheduler.py
git commit -m "fix(aeroes_monitor): varredura usa a data de Brasilia, nao a da maquina"
```

---

### Task 4: `config.lambda.ini` commitado (sem segredos)

**Files:**
- Create: `config.lambda.ini`
- Test: `tests/test_config.py` (classe nova)

**Interfaces:**
- Consumes: campos de Task 1.
- Produces: arquivo lido pelo handler (`CONFIG_FILE=config.lambda.ini`); `chrome_binary = /opt/chrome-linux64/chrome` **precisa casar com o unzip do Dockerfile (Task 6)**; `debug_dir = /tmp/debug` consumido pelo handler (Task 5).

- [ ] **Step 1: Teste que falha (higiene + validação)**

Em `tests/test_config.py`, nova classe (usa `Path` já importado):

```python
class LambdaIniTest(unittest.TestCase):
    """config.lambda.ini é COMMITADO: nunca pode conter segredos."""

    PATH = Path(__file__).resolve().parent.parent / "config.lambda.ini"

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
        self.assertEqual(
            config.selenium.chrome_binary, "/opt/chrome-linux64/chrome"
        )
        self.assertIn("--no-sandbox", config.selenium.chrome_extra_args)
        self.assertEqual(config.selenium.debug_dir, "/tmp/debug")
        self.assertIn("PP-AYB", config.aircraft)
        self.assertEqual(
            config.selectors["logged_in_marker"][0], "#navbarDropdownProfile"
        )
```

Run: `.venv\Scripts\python -m unittest tests.test_config -v`
Expected: FAIL — arquivo não existe.

- [ ] **Step 2: Criar `config.lambda.ini`**

```ini
; Config NÃO-secreta do deploy AWS Lambda — este arquivo é COMMITADO.
; Sem [credentials]/[discord]: segredos vivem no SSM Parameter Store e o
; handler os injeta como overrides de load_config (só em memória).
; Comentários usam ';' (o '#' é reservado para seletores CSS de id).

[monitor]
max_days = 30
; Irrelevante no Lambda (EventBridge agenda); mantido pela validação (>= 60).
check_interval_seconds = 900
turnaround_minutes = 30
min_flight_minutes = 60
max_flight_minutes = 120

[selenium]
base_url = https://aeroes.saga.aero/login
schedule_url = https://aeroes.saga.aero/schedules/personal
headless = true
page_load_timeout_seconds = 30
element_timeout_seconds = 15
; Artefatos de falha caem em /tmp (único FS gravável) e o handler sobe
; para s3://<bucket>/debug/.
debug_dir = /tmp/debug
; Chrome for Testing baked na imagem (Dockerfile) — Selenium Manager
; encontra binário+driver locais e não baixa nada em runtime.
chrome_binary = /opt/chrome-linux64/chrome
; Flags para Chrome dentro do Lambda (sem sandbox de user namespace,
; /dev/shm minúsculo, FS somente-leitura fora de /tmp).
chrome_extra_args =
    --no-sandbox
    --disable-dev-shm-usage
    --single-process
    --user-data-dir=/tmp/chrome-user-data
    --data-path=/tmp/chrome-data
    --disk-cache-dir=/tmp/chrome-cache

[aircraft]
; Espelho do config.ini local (matrículas não são segredo) — ADR-0007.
PP-AYB = C152
PT-JTK = C172

[logging]
level = INFO
file =

; Seletores calibrados com a página real em 2026-07-09 (iguais ao local).
[selectors]
logged_in_marker =
    #navbarDropdownProfile
    #menuSearch
    a.nav-link[href="/dashboard"]
```

- [ ] **Step 3: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 144 testes.

- [ ] **Step 4: Commit**

```powershell
git add config.lambda.ini tests/test_config.py
git commit -m "feat(aeroes_monitor): config.lambda.ini nao-secreto para o deploy AWS"
```

---

### Task 5: `handler.py` + boto3

**Files:**
- Create: `handler.py`
- Modify: `requirements.txt`
- Test: `tests/test_handler.py` (novo)

**Interfaces:**
- Consumes: `load_config(path, overrides)` (Task 1), `run_scan(config, state_path) -> bool` e `setup_logging(cfg)` de `main.py` (existentes), `config.lambda.ini` (Task 4).
- Produces: `handler.lambda_handler(event, context) -> dict` (`{"ok": bool}`) — referenciado pelo `CMD` do Dockerfile (Task 6). Env vars consumidas: `STATE_BUCKET` (obrigatória), `STATE_KEY`, `DEBUG_PREFIX`, `CONFIG_FILE`, `SSM_PREFIX`, `LOG_LEVEL` (com defaults) — o `template.yaml` (Task 7) define todas.
- Semântica de erro (spec): falha de varredura tratada ⇒ `{"ok": false}` sem exceção; exceção não tratada (SSM negado, S3 fora, bug) **propaga** ⇒ métrica `Errors` ⇒ alarme.

- [ ] **Step 1: Instalar boto3 no venv e registrar no requirements**

```powershell
.venv\Scripts\python -m pip install "boto3>=1.34"
```

`requirements.txt` vira:

```
selenium>=4.21
requests>=2.32
tzdata>=2024.1
boto3>=1.34
```

(A imagem Lambda já traz boto3; o pin garante a mesma versão local/nuvem.)

- [ ] **Step 2: Escrever `tests/test_handler.py` (falhando)**

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
    "STATE_BUCKET": "bucket-teste",
    "STATE_KEY": "state.json",
    "DEBUG_PREFIX": "debug/",
    "CONFIG_FILE": "config.lambda.ini",
    "SSM_PREFIX": "/aeroes-monitor",
    "LOG_LEVEL": "INFO",
}


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetObject")


class FakeSSM:
    def __init__(self):
        self.calls = []

    def get_parameter(self, Name, WithDecryption=False):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": f"segredo:{Name.rsplit('/', 1)[1]}"}}


class FakeS3:
    def __init__(self, has_state=False):
        self.has_state = has_state
        self.uploads = []

    def download_file(self, bucket, key, dest):
        if not self.has_state:
            raise _client_error("404")
        Path(dest).write_text('{"version": 2}', encoding="utf-8")

    def upload_file(self, src, bucket, key):
        self.uploads.append((src, bucket, key))


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = Path(tmp.name) / "state.json"
        self.debug_dir = Path(tmp.name) / "debug"
        self.ssm = FakeSSM()
        self.s3 = FakeS3()
        self.config = mock.Mock()
        self.config.selenium.debug_dir = str(self.debug_dir)
        for patcher in (
            mock.patch.dict(os.environ, ENV),
            mock.patch.object(handler, "STATE_PATH", self.state_path),
            mock.patch.object(handler, "_ssm_client", self.ssm),
            mock.patch.object(handler, "_s3_client", self.s3),
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

    def test_baseline_flow_returns_ok_and_uploads_state(self):
        def scan(config, state_path):
            state_path.write_text('{"version": 2}', encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": True})
        self.run_scan.assert_called_once_with(self.config, self.state_path)
        self.assertEqual(
            self.s3.uploads, [(str(self.state_path), "bucket-teste", "state.json")]
        )

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
        # SecureString exige WithDecryption=True nas 3 leituras.
        self.assertEqual([dec for _, dec in self.ssm.calls], [True, True, True])

    def test_secrets_cached_across_warm_invocations(self):
        handler.lambda_handler({}, None)
        handler.lambda_handler({}, None)
        self.assertEqual(len(self.ssm.calls), 3)

    def test_missing_state_in_s3_removes_stale_local_copy(self):
        self.state_path.write_text("velho", encoding="utf-8")
        self.run_scan.return_value = False  # varredura falhou: nada gravado
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": False})
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.s3.uploads, [])

    def test_existing_state_available_to_scan(self):
        self.s3.has_state = True
        seen = {}

        def scan(config, state_path):
            seen["state"] = state_path.read_text(encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        handler.lambda_handler({}, None)
        self.assertEqual(seen["state"], '{"version": 2}')

    def test_failed_scan_uploads_and_clears_debug_artifacts(self):
        self.run_scan.return_value = False
        self.debug_dir.mkdir()
        (self.debug_dir / "a-fatal.png").write_bytes(b"PNG")
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": False})
        self.assertEqual(
            self.s3.uploads,
            [
                (
                    str(self.debug_dir / "a-fatal.png"),
                    "bucket-teste",
                    "debug/a-fatal.png",
                )
            ],
        )
        # Limpa o /tmp local: warm start não re-sobe artefato antigo.
        self.assertEqual(list(self.debug_dir.iterdir()), [])

    def test_ok_scan_does_not_touch_debug(self):
        self.debug_dir.mkdir()
        (self.debug_dir / "antigo.png").write_bytes(b"PNG")
        handler.lambda_handler({}, None)
        self.assertEqual(self.s3.uploads, [])
        self.assertTrue((self.debug_dir / "antigo.png").exists())

    def test_unexpected_s3_error_propagates_to_lambda_errors_metric(self):
        def boom(bucket, key, dest):
            raise _client_error("AccessDenied")

        self.s3.download_file = boom
        with self.assertRaises(ClientError):
            handler.lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv\Scripts\python -m unittest tests.test_handler -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'handler'`.

- [ ] **Step 4: Escrever `handler.py`**

```python
"""Entrypoint AWS Lambda: SSM (segredos) e S3 (estado) ao redor de run_scan.

Fluxo por invocação (spec 2026-07-12): segredos do SSM (cache de módulo no
cold start) → GET state.json do S3 para /tmp → mesmo run_scan do modo local
→ PUT do state de volta → em falha, sobe artefatos de debug para debug/.

Semântica de erro: falha de varredura TRATADA retorna {"ok": false} sem
exceção (o app já avisou no Discord na transição). Exceção NÃO tratada
(SSM negado, S3 fora, bug) propaga de propósito — vira métrica Errors e
dispara o alarme, cobrindo exatamente o buraco em que o Discord não pôde
ser avisado.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from config import load_config
from main import run_scan, setup_logging

logger = logging.getLogger(__name__)

STATE_PATH = Path("/tmp/state.json")
SECRET_NAMES = ("saga-username", "saga-password", "discord-webhook-url")

_ssm_client = None
_s3_client = None
_secrets_cache: dict[str, str] | None = None


def _ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def _s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


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


def _download_state(bucket: str, key: str) -> None:
    """GET state.json → /tmp. Ausente = baseline (como no modo local).

    Remove cópia local obsoleta de invocação anterior (warm start); outros
    erros de S3 propagam (alarme).
    """
    try:
        _s3().download_file(bucket, key, str(STATE_PATH))
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in ("404", "NoSuchKey"):
            raise
        STATE_PATH.unlink(missing_ok=True)


def _upload_state(bucket: str, key: str) -> None:
    """PUT sempre que o arquivo existir (54 PUTs/dia custam nada)."""
    if STATE_PATH.exists():
        _s3().upload_file(str(STATE_PATH), bucket, key)


def _upload_debug_artifacts(bucket: str, prefix: str, debug_dir: Path) -> None:
    """Sobe e apaga artefatos locais (warm start não re-sobe os antigos).

    Melhor esforço: a varredura já falhou e o Discord já foi avisado;
    debug perdido não justifica derrubar o handler.
    """
    try:
        if not debug_dir.is_dir():
            return
        for artifact in sorted(debug_dir.iterdir()):
            if artifact.is_file():
                _s3().upload_file(str(artifact), bucket, f"{prefix}{artifact.name}")
                artifact.unlink()
                logger.info(
                    "Debug enviado: s3://%s/%s%s", bucket, prefix, artifact.name
                )
    except Exception:
        logger.exception("Falha ao subir artefatos de debug")


def lambda_handler(event, context) -> dict:
    bucket = os.environ["STATE_BUCKET"]
    key = os.environ.get("STATE_KEY", "state.json")
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
    _download_state(bucket, key)
    ok = run_scan(config, STATE_PATH)
    _upload_state(bucket, key)
    if not ok:
        _upload_debug_artifacts(
            bucket,
            os.environ.get("DEBUG_PREFIX", "debug/"),
            Path(config.selenium.debug_dir),
        )
    return {"ok": ok}
```

- [ ] **Step 5: Rodar a suíte inteira**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 152 testes (144 + 8).

- [ ] **Step 6: Commit**

```powershell
git add handler.py tests/test_handler.py requirements.txt
git commit -m "feat(aeroes_monitor): handler Lambda com estado no S3 e segredos no SSM"
```

---

### Task 6: `Dockerfile` + `.dockerignore`

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

**Interfaces:**
- Consumes: `handler.lambda_handler` (Task 5), `config.lambda.ini` (Task 4 — `chrome_binary = /opt/chrome-linux64/chrome` tem que casar com o unzip daqui).
- Produces: imagem com `CMD ["handler.lambda_handler"]`, Chrome em `/opt/chrome-linux64/chrome`, chromedriver em `/usr/local/bin/chromedriver`, `ENV TZ=America/Sao_Paulo`. Consumida pelo `sam build` (Metadata da função na Task 7).

Sem Docker instalado ainda (vem na Task 9), a validação real do build acontece na Task 10 — aqui o arquivo é escrito e commitado.

- [ ] **Step 1: Descobrir a versão estável corrente do Chrome for Testing**

Run (Git Bash/PowerShell):

```powershell
curl.exe -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE
```

Expected: uma versão no formato `NNN.0.NNNN.NN` (ex.: `138.0.7204.94`). Use **esse valor** como default do `ARG CHROME_VERSION` no passo 2 (o valor abaixo, `131.0.6778.204`, é um estável real e permanece baixável — o CfT arquiva todas as versões — mas prefira o corrente).

- [ ] **Step 2: Criar `Dockerfile`**

```dockerfile
# Imagem Lambda do aeroes_monitor: Python 3.13 + Chrome for Testing pinado.
# Chrome e chromedriver vêm JUNTOS e na MESMA versão (ARG abaixo): o
# Selenium Manager acha ambos locais e não baixa nada em runtime.
# Para atualizar o pin:
#   curl -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE
FROM public.ecr.aws/lambda/python:3.13

ARG CHROME_VERSION=131.0.6778.204
ARG CFT_BASE=https://storage.googleapis.com/chrome-for-testing-public

# Bibliotecas de sistema do Chrome headless em AL2023 (lista validada pela
# comunidade para imagens Lambda; enxugar depois, se quiser, medindo).
RUN dnf install -y unzip \
      atk at-spi2-atk cups-libs gtk3 pango alsa-lib nss mesa-libgbm \
      libXcomposite libXcursor libXdamage libXext libXi libXrandr \
      libXScrnSaver libXtst libXt libxkbcommon libdrm \
      dbus-glib xorg-x11-server-Xvfb \
    && dnf clean all

RUN curl -sSLo /tmp/chrome.zip "${CFT_BASE}/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && curl -sSLo /tmp/chromedriver.zip "${CFT_BASE}/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip -q /tmp/chrome.zip -d /opt \
    && unzip -q /tmp/chromedriver.zip -d /opt \
    && ln -s /opt/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -f /tmp/chrome.zip /tmp/chromedriver.zip

# TZ é chave RESERVADA nas env vars da função (CloudFormation rejeita);
# na imagem tem o mesmo efeito: timestamps de log/debug em BRT.
ENV TZ=America/Sao_Paulo

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY availability.py browser.py config.py discord.py handler.py login.py \
     main.py models.py notifications.py report.py saga_data.py scheduler.py \
     utils.py config.lambda.ini ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
```

- [ ] **Step 3: Criar `.dockerignore`**

O COPY já é explícito; o .dockerignore existe para (a) contexto de build pequeno (o .venv tem centenas de MB) e (b) defesa extra contra segredo em imagem:

```
config.ini
state.json
debug/
.venv/
.aws-sam/
__pycache__/
**/__pycache__/
tests/
docs/
*.md
locals.json
```

- [ ] **Step 4: Conferir consistência de caminhos**

Run: `Select-String -Path config.lambda.ini -Pattern "chrome_binary"`
Expected: `chrome_binary = /opt/chrome-linux64/chrome` — exatamente o diretório que o unzip de `chrome-linux64.zip` cria em `/opt`.

- [ ] **Step 5: Commit**

```powershell
git add Dockerfile .dockerignore
git commit -m "feat(aeroes_monitor): imagem Lambda com Chrome for Testing pinado"
```

---

### Task 7: `template.yaml` (SAM) + `.gitignore`

**Files:**
- Create: `template.yaml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: env vars do handler (Task 5), Dockerfile (Task 6).
- Produces: stack `aeroes-monitor` com função `MonitorFunction`, bucket `aeroes-monitor-state-<account-id>`, agendamento, alarme, SNS. Outputs `FunctionName`/`StateBucketName` usados no runbook (Tasks 10–11).

- [ ] **Step 1: Criar `template.yaml`**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: >-
  aeroes_monitor - varredura read-only da escala SAGA a cada 20 min
  (06:00-23:40 BRT), estado no S3, segredos no SSM, aviso no Discord.
  Spec: docs/superpowers/specs/2026-07-12-aws-lambda-deploy-design.md

Parameters:
  AlertEmail:
    Type: String
    Default: pedroh723@gmail.com
    Description: E-mail que recebe o alarme de Errors (assinatura SNS).

Resources:
  MonitorFunction:
    Type: AWS::Serverless::Function
    Metadata:
      Dockerfile: Dockerfile
      DockerContext: .
      DockerTag: aeroes-monitor
    Properties:
      FunctionName: aeroes-monitor
      PackageType: Image
      Architectures: [x86_64]   # Chrome for Testing só publica linux64
      MemorySize: 2048
      Timeout: 300
      # Nunca duas varreduras simultâneas: estado consistente, sem
      # notificação dupla (spec).
      ReservedConcurrentExecutions: 1
      # Sem retry do proprio Lambda em erro assincrono: a proxima varredura
      # (20 min) e o retry natural.
      EventInvokeConfig:
        MaximumRetryAttempts: 0
      Environment:
        Variables:
          STATE_BUCKET: !Ref StateBucket
          STATE_KEY: state.json
          DEBUG_PREFIX: debug/
          CONFIG_FILE: config.lambda.ini
          SSM_PREFIX: /aeroes-monitor
          LOG_LEVEL: INFO
          # TZ e chave reservada do Lambda: vive como ENV no Dockerfile.
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
                - s3:GetObject
                - s3:PutObject
              Resource:
                - !Sub arn:aws:s3:::aeroes-monitor-state-${AWS::AccountId}/state.json
                - !Sub arn:aws:s3:::aeroes-monitor-state-${AWS::AccountId}/debug/*

  StateBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub aeroes-monitor-state-${AWS::AccountId}
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      # Historico gratis do state.json; mitiga o save nao-atomico na nuvem.
      VersioningConfiguration:
        Status: Enabled
      LifecycleConfiguration:
        Rules:
          - Id: expire-debug
            Status: Enabled
            Prefix: debug/
            ExpirationInDays: 30

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
  StateBucketName:
    Value: !Ref StateBucket
  AlertTopicArn:
    Value: !Ref AlertTopic
```

- [ ] **Step 2: Validar com cfn-lint (dev tool, fora do requirements.txt)**

```powershell
.venv\Scripts\python -m pip install cfn-lint
.venv\Scripts\cfn-lint template.yaml
```

Expected: saída vazia (exit 0). Se reclamar de `EventInvokeConfig`/`ScheduleV2`, ler a mensagem — são propriedades válidas de `AWS::Serverless::Function`; ajuste apenas se a mensagem apontar erro de indentação/nome.

- [ ] **Step 3: `.gitignore` — artefatos do SAM**

Acrescentar ao final de `.gitignore`:

```
# Build do SAM e overrides locais de env
.aws-sam/
locals.json
```

- [ ] **Step 4: Rodar a suíte inteira (sanidade)**

Run: `.venv\Scripts\python -m unittest -v`
Expected: OK, 152 testes.

- [ ] **Step 5: Commit**

```powershell
git add template.yaml .gitignore
git commit -m "feat(aeroes_monitor): template SAM (Lambda + S3 + Scheduler + alarme)"
```

---

### Task 8: README — seção "Deploy na AWS (Lambda)"

**Files:**
- Modify: `README.md` (nova seção ao final do arquivo)

**Interfaces:**
- Consumes: nomes/comandos das Tasks 4–7 e runbook das Tasks 9–11.
- Produces: documentação; nada consumido por código.

- [ ] **Step 1: Acrescentar ao FINAL do `README.md`**

```markdown
## Deploy na AWS (Lambda)

O monitor roda sem PC ligado: EventBridge Scheduler dispara um Lambda de
container a cada 20 min (06:00–23:40, horário de Brasília), o estado vive
em `s3://aeroes-monitor-state-<account-id>/state.json` (versionado) e os
segredos em SSM Parameter Store (SecureString). Infra inteira em
`template.yaml` (SAM). Design completo:
`docs/superpowers/specs/2026-07-12-aws-lambda-deploy-design.md`.

O fluxo local (`python main.py` com `config.ini`) segue funcionando — mas
não rode os dois ao mesmo tempo: PC + AWS no mesmo webhook duplicam toda
notificação.

### Arquivos

- `handler.py` — entrypoint do Lambda (S3 + SSM ao redor de `run_scan`).
- `config.lambda.ini` — config **não-secreta** da nuvem (commitada; sem
  `[credentials]`/`[discord]` — o handler injeta segredos do SSM via
  `load_config(..., overrides=...)`).
- `Dockerfile` — Python 3.13 + Chrome for Testing **pinado** (`ARG
  CHROME_VERSION`); `TZ=America/Sao_Paulo` vai na imagem porque a env var
  `TZ` é reservada pelo Lambda.
- `template.yaml` — função (2048 MB / 300 s / concorrência 1), bucket
  versionado com `debug/` expirando em 30 dias, agendamento
  `cron(0/20 6-23 * * ? *)` no fuso `America/Sao_Paulo`, alarme
  `Errors >= 1` (3×20 min) → SNS → e-mail.

### Pré-requisitos (uma vez)

1. Instalar: `winget install -e --id Amazon.AWSCLI`,
   `winget install -e --id Amazon.SAM-CLI`,
   `winget install -e --id Docker.DockerDesktop` (exige WSL2).
2. Console AWS: usuário IAM de deploy dedicado com MFA + access key
   (**jamais** access key do root) → `aws configure` (região `sa-east-1`).
3. Criar os 3 segredos (senha via prompt, fora do histórico do shell):

   ```powershell
   aws ssm put-parameter --name /aeroes-monitor/saga-username --type SecureString --value (Read-Host "usuário SAGA")
   $sec = Read-Host "senha SAGA" -AsSecureString
   aws ssm put-parameter --name /aeroes-monitor/saga-password --type SecureString --value ([Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)))
   aws ssm put-parameter --name /aeroes-monitor/discord-webhook-url --type SecureString --value (Read-Host "webhook Discord")
   ```

### Build, teste local e deploy

```powershell
sam build

# Smoke test local (Docker): bucket descartável só para o teste —
# ATENÇÃO: publica um relatório baseline no canal Discord real.
$acct = aws sts get-caller-identity --query Account --output text
aws s3 mb "s3://aeroes-monitor-localtest-$acct"
Set-Content locals.json "{`"MonitorFunction`": {`"STATE_BUCKET`": `"aeroes-monitor-localtest-$acct`"}}"
sam local invoke MonitorFunction --no-event --env-vars locals.json
aws s3 rb "s3://aeroes-monitor-localtest-$acct" --force

sam deploy --guided   # 1ª vez (gera samconfig.toml); depois só: sam deploy
```

Após o primeiro deploy: confirmar a assinatura SNS no e-mail, invocar
manualmente (`aws lambda invoke --function-name aeroes-monitor out.json`),
conferir o baseline no Discord e **desligar o modo contínuo no PC**.
Logs: `sam logs --stack-name aeroes-monitor --tail`.
```

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs(aeroes_monitor): runbook do deploy AWS Lambda no README"
```

---

### Task 9 [com Pedro — interativo]: máquina e conta AWS

Não despachar para subagente: instaladores pedem UAC, o console AWS pede cliques e MFA, e a senha do SAGA é digitada pelo Pedro.

- [ ] **Step 1: Instalar ferramentas**

```powershell
winget install -e --id Amazon.AWSCLI
winget install -e --id Amazon.SAM-CLI
winget install -e --id Docker.DockerDesktop
```

Depois: abrir Docker Desktop 1x (ele termina o setup do WSL2; pode pedir logout/reboot). Verificar:

```powershell
aws --version; sam --version; docker info
```

Expected: três versões impressas; `docker info` sem erro de daemon.

- [ ] **Step 2: Usuário IAM de deploy (console AWS)**

No console (conta pessoal): IAM → Users → Create user `aeroes-deploy` → attach `AdministratorAccess` (usuário dedicado de deploy em conta pessoal; MFA obrigatório) → habilitar MFA → criar access key "CLI".

- [ ] **Step 3: `aws configure`**

```powershell
aws configure   # access key, secret, region: sa-east-1, output: json
aws sts get-caller-identity
```

Expected: JSON com `Arn` terminando em `user/aeroes-deploy`.

- [ ] **Step 4: Criar os 3 parâmetros SSM (segredos digitados em prompt)**

```powershell
aws ssm put-parameter --name /aeroes-monitor/saga-username --type SecureString --value (Read-Host "usuário SAGA")
$sec = Read-Host "senha SAGA" -AsSecureString
aws ssm put-parameter --name /aeroes-monitor/saga-password --type SecureString --value ([Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)))
aws ssm put-parameter --name /aeroes-monitor/discord-webhook-url --type SecureString --value (Read-Host "webhook Discord")
```

Verificar SEM descriptografar (não imprimir segredo no console):

```powershell
aws ssm describe-parameters --parameter-filters "Key=Name,Option=BeginsWith,Values=/aeroes-monitor/" --query "Parameters[].Name"
```

Expected: os 3 nomes.

---

### Task 10 [com Pedro — interativo]: build e smoke test local

Pré-requisito: Docker Desktop rodando. Ciclo de ajuste do Chrome acontece AQUI (rápido), não no deploy.

- [ ] **Step 1: (opcional) atualizar o pin do Chrome**

```powershell
curl.exe -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE
```

Se quiser a estável corrente, atualizar `ARG CHROME_VERSION=` no `Dockerfile` com a saída e commitar junto com eventuais ajustes desta task.

- [ ] **Step 2: `sam build`**

```powershell
sam build
```

Expected: `Build Succeeded` (primeira vez demora: baixa base image + Chrome).

- [ ] **Step 3: bucket descartável + invoke local**

**Atenção:** o happy path publica um relatório **baseline no canal Discord real** — avisar o Pedro antes.

```powershell
$acct = aws sts get-caller-identity --query Account --output text
aws s3 mb "s3://aeroes-monitor-localtest-$acct"
Set-Content locals.json "{`"MonitorFunction`": {`"STATE_BUCKET`": `"aeroes-monitor-localtest-$acct`"}}"
sam local invoke MonitorFunction --no-event --env-vars locals.json
```

Expected: logs de login/varredura como no modo local, `{"ok": true}` no final, baseline no Discord (2 fragmentos de tabela). O SSM é o real (creds do shell são repassadas ao container); o estado vai para o bucket de teste.

Falhas típicas e correção (iterar `Dockerfile`/`config.lambda.ini` + `sam build` + invoke):
- `session not created ... DevToolsActivePort file doesn't exist` → conferir que `--user-data-dir=/tmp/...` e `--no-sandbox` estão em `chrome_extra_args`; se persistir, remover `--single-process`.
- `error while loading shared libraries: libX.so` → `dnf install` da lib citada no RUN do Dockerfile.
- Timeout de página → aumentar `page_load_timeout_seconds` no `config.lambda.ini` (cold start do Chrome em container é mais lento).

- [ ] **Step 4: limpeza**

```powershell
aws s3 rb "s3://aeroes-monitor-localtest-$acct" --force
Remove-Item locals.json
```

- [ ] **Step 5: Commit (se houve ajuste de imagem/config)**

```powershell
git add Dockerfile config.lambda.ini
git commit -m "fix(aeroes_monitor): ajustes da imagem validados no sam local invoke"
```

(Pular se nada mudou.)

---

### Task 11 [com Pedro — interativo]: deploy, validação real e desligar o PC

- [ ] **Step 1: `sam deploy --guided` (primeira vez)**

```powershell
sam deploy --guided
```

Respostas: Stack Name `aeroes-monitor`; Region `sa-east-1`; Confirm changes `y`; Allow SAM CLI IAM role creation `y`; Disable rollback `n`; Save arguments to configuration file `y` (gera `samconfig.toml`). SAM cria o repositório ECR gerenciado sozinho.

Expected: `Successfully created/updated stack - aeroes-monitor`. **Nota:** o agendamento começa a disparar já no próximo tick de 20 min dentro de 06:00–23:40 BRT.

- [ ] **Step 2: Commitar `samconfig.toml` (sem segredos — conferir antes)**

```powershell
Get-Content samconfig.toml   # inspecionar: stack, região, ECR — nada secreto
git add samconfig.toml
git commit -m "chore(aeroes_monitor): samconfig do primeiro deploy"
```

- [ ] **Step 3: Confirmar a assinatura SNS**

Pedro clica em "Confirm subscription" no e-mail da AWS (pedroh723@gmail.com). Sem isso o alarme não chega.

- [ ] **Step 4: Invocação manual com bucket zerado**

```powershell
aws lambda invoke --function-name aeroes-monitor "$env:TEMP\aeroes-out.json"
Get-Content "$env:TEMP\aeroes-out.json"
```

Expected: `{"ok": true}` e o relatório baseline no Discord. Conferir o estado:

```powershell
$acct = aws sts get-caller-identity --query Account --output text
aws s3 ls "s3://aeroes-monitor-state-$acct/"
```

Expected: `state.json` listado.

- [ ] **Step 5: Observar 1–2 ciclos do agendamento real**

```powershell
sam logs --stack-name aeroes-monitor --tail
```

Expected: a cada 20 min (06:00–23:40 BRT), log `Varredura concluída: ...` sem relatório novo no Discord (diff silencioso; aberturas só quando surgirem).

- [ ] **Step 6: Desligar o modo contínuo no PC**

Pedro encerra o `python main.py` local (Ctrl+C) — AWS e PC juntos duplicam toda notificação no mesmo canal. A partir daqui, só a nuvem varre.

- [ ] **Step 7: Push e PR**

```powershell
git push -u origin feat/aeroes-aws-lambda
gh pr create --title "feat(aeroes_monitor): deploy AWS Lambda (SAM + container)" --fill
```

Expected: PR aberto contra `main` com todo o trabalho das Tasks 1–10.

---

## Cobertura da spec (self-review)

| Item da spec | Task |
|---|---|
| `load_config(path, overrides)` + `chrome_binary`/`chrome_extra_args` | 1 |
| `create_driver` usa os campos novos | 2 |
| Fix `date.today()` → fuso `America/Sao_Paulo` (follow-up nº 5) | 3 |
| `config.lambda.ini` commitado, sem `[credentials]`/`[discord]` | 4 |
| `handler.py` (SSM cache, GET/PUT state, debug/, `{"ok"}`), semântica de erro | 5 |
| `requirements.txt` + boto3 | 5 |
| Dockerfile (python:3.13, Chrome for Testing pinado por ARG), `.dockerignore` | 6 |
| `TZ=America/Sao_Paulo` (env reservada → ENV na imagem, desvio documentado) | 6, 7, 8 |
| template.yaml: 2048 MB/300 s/concorrência 1, ScheduleV2 cron BRT sem retry, S3 versionado + lifecycle debug/ 30d, SSM/S3 least privilege, Logs 30d, alarme 3×20min → SNS e-mail | 7 |
| `samconfig.toml` gerado no 1º deploy e commitado | 11 |
| Runbook (CLIs, IAM+MFA, SSM via prompt, build/deploy) | 8, 9 |
| `sam local invoke` até a imagem estar certa | 10 |
| Deploy → invocação manual → baseline → observar ciclos → desligar PC | 11 |
| Fora de escopo: GitHub Actions/OIDC, dashboards, demais follow-ups | — (não tocados) |
