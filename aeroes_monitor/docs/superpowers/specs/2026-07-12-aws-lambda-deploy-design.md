# Deploy na AWS com Lambda — design

**Data:** 2026-07-12
**Status:** aprovado pelo Pedro (seções 1–3 validadas em conversa)
**Pré-requisito:** PR #1 mesclado (`caa1e62`) — monitor validado no SAGA real

## Objetivo

Rodar o aeroes_monitor na AWS sem depender do PC ligado: varredura a cada
**20 minutos, das 06:00 às 23:40** (horário de Brasília), com boas práticas
de AWS (IaC versionado, segredos fora do repo, least privilege) e infra
publicada no GitHub junto do código. O fluxo local (`python main.py` com
`config.ini` e `state.json` no disco) continua funcionando inalterado.

## Decisões (e alternativas descartadas)

| Decisão | Escolha | Alternativas descartadas |
|---|---|---|
| Computação | **Lambda por imagem de container** (pedido explícito; Chrome não cabe em zip) | Fargate/EC2 (fora do pedido); zip+layer de Chrome (frágil) |
| IaC | **AWS SAM** (`template.yaml` no repo) | Terraform/CDK (mais peso sem ganho aqui) |
| Agendamento | **EventBridge Scheduler**, `cron(0/20 6-23 * * ? *)` fuso `America/Sao_Paulo` (54 varreduras/dia, 06:00→23:40), sem retry (`MaximumRetryAttempts=0` — a próxima varredura é o retry natural) | EventBridge Rules legado (sem fuso nativo) |
| Estado | **S3** com versionamento (histórico grátis de `state.json`; mitiga o save não-atômico na nuvem) | DynamoDB (overkill para 1 blob JSON) |
| Segredos | **SSM Parameter Store** SecureString: `/aeroes-monitor/saga-username`, `/aeroes-monitor/saga-password`, `/aeroes-monitor/discord-webhook-url` (criados 1x via CLI, fora do template) | Secrets Manager (US$ 0,40/segredo/mês sem ganho); env vars (visíveis no console) |
| Build/deploy | **Etapa 1 (esta): build local** com Docker Desktop + `sam build/deploy`. Etapa 2 (futura): GitHub Actions com OIDC | Só Actions (ciclo de debug de ~10 min por tentativa na fase de ajuste do Chrome) |
| Região | **sa-east-1** | us-east-1 (indiferente dentro do free tier) |

## Arquitetura

```
EventBridge Scheduler ──▶ Lambda (container, 2048 MB, timeout 300 s,
  cron 06:00–23:40           concorrência reservada = 1)
  a cada 20 min, BRT           │
                               ├──▶ SSM Parameter Store (segredos; cache no cold start)
                               ├──▶ S3  (GET state.json antes / PUT depois; debug/ em falha)
                               ├──▶ SAGA via Selenium/Chrome (read-only, ADR-0001 intacto)
                               ├──▶ Discord (webhook — relatório/aberturas/erros, como hoje)
                               └──▶ CloudWatch Logs (stdout existente; retenção 30 dias)
```

- **Concorrência reservada = 1**: nunca duas varreduras simultâneas (estado
  consistente, sem notificação dupla).
- **Imagem**: base `public.ecr.aws/lambda/python:3.13` + **Chrome for
  Testing + chromedriver pinados** (versão exata registrada como `ARG` no
  Dockerfile; Selenium Manager não baixa nada em runtime).
- **Bucket**: `aeroes-monitor-state-<account-id>`, BlockPublicAccess total,
  versionamento ligado, lifecycle: `debug/` expira em 30 dias.
- **Memória/armazenamento**: 2048 MB / ephemeral padrão 512 MB com caches do
  Chrome em `/tmp`; ajustar após medir no CloudWatch se preciso.

## Fluxo de uma invocação (`handler.py`)

1. Cold start: lê os 3 parâmetros do SSM e guarda em cache de módulo.
2. `GET s3://bucket/state.json` → `/tmp/state.json` (ausente = baseline,
   como hoje).
3. Monta config: `load_config("config.lambda.ini", overrides={credenciais,
   webhook})` — segredo entra por memória, nunca toca disco.
4. Chama **o mesmo `run_scan(config, Path("/tmp/state.json"))`** de hoje.
5. `PUT` do `state.json` de volta no S3 sempre que o arquivo existir após a
   varredura (sem otimização de "mudou?" — 54 PUTs/dia custam nada).
6. Se a varredura falhou e há artefatos em `/tmp` de debug, sobe para
   `s3://bucket/debug/` .
7. Retorna `{"ok": bool}`.

**Semântica de erro do handler (importante para o alarme):** falha de
varredura tratada pelo app (SAGA fora, etc.) retorna `{"ok": false}` **sem
exceção** — o app já avisa no Discord na transição. Exceção não tratada no
handler (SSM negado, bug) deixa o Lambda registrar erro na métrica `Errors`
— é isso que o alarme observa. Assim o alarme cobre exatamente o buraco em
que o Discord não pôde ser avisado.

## Mudanças no código (núcleo intocado)

**Novos:**
- `handler.py` — fluxo acima (S3/SSM via boto3).
- `config.lambda.ini` (commitado) — config não-secreta da nuvem:
  `[monitor]`, `[aircraft]`, `[selectors]` calibrados (copiados do
  config.ini local — seletores não são segredo) e `[selenium]` com
  `chrome_binary` apontando para o Chrome da imagem, `chrome_extra_args`
  (`--no-sandbox`, `--disable-dev-shm-usage`, `--user-data-dir=/tmp/...`,
  caches em `/tmp`) e `debug_dir = /tmp/debug`. Sem
  `[credentials]`/`[discord]`.
- `Dockerfile`, `.dockerignore`, `template.yaml` (SAM), `samconfig.toml`
  (gerado no primeiro deploy; sem segredos).

**Alterados:**
- `config.py` — `load_config(path, overrides=None)`: dict opcional
  `{(seção, chave): valor}` aplicado após ler o .ini; campos novos opcionais
  em `[selenium]`: `chrome_binary` (str, default vazio) e
  `chrome_extra_args` (lista por linhas, default vazia). Defaults vazios ⇒
  comportamento local idêntico ao atual.
- `browser.py` — `create_driver` usa `chrome_binary`/`chrome_extra_args`
  quando preenchidos.
- `scheduler.py` — `date.today()` → data no fuso `America/Sao_Paulo`
  (follow-up nº 5 da revisão do PR #1, que em servidor UTC vira bug real:
  entre 21:00 e 00:00 BRT varreria o dia errado).
- `requirements.txt` — `boto3` (runtime Lambda já tem; local é para testes).

**Variáveis de ambiente do Lambda (template, não-secretas):**
`STATE_BUCKET`, `STATE_KEY=state.json`, `DEBUG_PREFIX=debug/`,
`CONFIG_FILE=config.lambda.ini`, `SSM_PREFIX=/aeroes-monitor`,
`LOG_LEVEL=INFO`, `TZ=America/Sao_Paulo`.

## Segurança

- Role do Lambda (least privilege): `ssm:GetParameter` nos 3 paths,
  `s3:GetObject`/`s3:PutObject` no bucket específico (`state.json` e
  `debug/*`), CloudWatch Logs. Nada além.
- Segredos: só SecureString no SSM; nunca em env var, template, repo ou log
  (`config_to_safe_dict` já redige senha/webhook).
- Deploy local: usuário IAM dedicado com MFA; **access key de root, jamais**.
- ECR privado; bucket privado.

## Erros e observabilidade

- Comportamento do app inalterado (transição ok→falha avisa no Discord;
  recuperação avisa; diff at-least-once).
- Lambda morto no meio (timeout/OOM): `PUT` do estado não acontece → próxima
  varredura re-diffa a partir do estado anterior. Pior caso: notificação
  repetida; nunca perdida.
- **Alarme CloudWatch**: `Errors >= 1` em 3 períodos consecutivos de 20 min
  → SNS → e-mail do Pedro (assinatura confirmada por e-mail no primeiro
  deploy). Cobre morte silenciosa do handler.
- CloudWatch Logs: retenção 30 dias. Debug no S3: expira em 30 dias.

## Validação e rollout

1. TDD nos módulos novos/alterados (S3/SSM mockados; suíte local completa).
2. `sam build` + `sam local invoke` com evento vazio até a imagem estar
   certa (Chrome dentro do container local).
3. `sam deploy` → invocação manual (`aws lambda invoke`) com bucket zerado →
   baseline esperado no Discord.
4. Observar 1–2 ciclos do agendamento real.
5. **Desligar o modo contínuo no PC** — AWS e PC juntos duplicam toda
   notificação no mesmo canal.

## Pré-requisitos de máquina/conta (runbook da etapa de setup)

1. Instalar AWS CLI, SAM CLI e Docker Desktop (WSL2) — winget/instaladores.
2. Console AWS: criar usuário IAM de deploy com MFA + access key →
   `aws configure` (região `sa-east-1`).
3. Criar os 3 parâmetros SSM via CLI (senha digitada em prompt, fora do
   histórico do shell).
4. `sam build && sam deploy --guided` (primeira vez); depois, `sam deploy`.

## Custo estimado

Lambda ~R$ 0 (≈74% do free tier: 54/dia × ~90 s × 2 GB) + ECR ~R$ 1/mês
(imagem ~2 GB) + S3/SSM/EventBridge/SNS grátis ou centavos ≈ **R$ 1–2/mês**.

## Fora de escopo (etapa 2 e além)

- GitHub Actions com OIDC (CI/CD) — o template/Dockerfile desta etapa são
  reaproveitados sem retrabalho.
- Dashboards/alarmes além do descrito.
- Follow-ups menores restantes da revisão do PR #1 (PRD desatualizado,
  `max_flight_minutes`, matching de matrícula, "1 dias varridos",
  alerta repetido pré-baseline) — **exceto** o fix de `date.today()`, que
  entra nesta etapa.
