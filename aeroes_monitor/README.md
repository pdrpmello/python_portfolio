# Aeroclube Schedule Monitor

Monitor **read-only** da escala de horários de voo do sistema SAGA do
Aeroclube do Espírito Santo. Varre a agenda dos próximos dias, aplica as
regras operacionais do clube e envia ao Discord as janelas 🟢 livres de
cada aeronave, dia a dia — avisando quando abre horário novo.

## Garantia read-only

Este programa **não faz reservas e não altera nada no SAGA** (ADR-0001).
Ele apenas: autentica → navega → lê os dados que a página carrega →
calcula localmente → reporta no Discord. O único formulário que ele submete é o de **login**.
A ação de reservar continua 100% manual, no próprio SAGA.

## Requisitos

- Python 3.13+
- Um webhook de Discord

A aquisição é por HTTP direto (`requests`) — não há browser nem Chrome a
instalar (ADR-0011).

## Instalação

```
python -m venv .venv
.venv\Scripts\python -m pip install -r src\requirements.txt
```

## Configuração

1. Copie `config.ini.example` para `config.ini`.
2. Preencha `[credentials]`, `[discord] webhook_url` e `[saga] base_url`.
3. Liste em `[aircraft]` as aeronaves a monitorar (`MATRICULA = modelo`).
   Só elas aparecem no relatório (ADR-0007).

`config.ini` está no `.gitignore` — **nunca** o versione. Os logs redigem
senha e webhook automaticamente.

## Uso

```
.venv\Scripts\python src\main.py --once   # uma varredura e sai
.venv\Scripts\python src\main.py          # loop contínuo (intervalo do config.ini)
```

Códigos de saída de `--once`: `0` sucesso, `1` varredura falhou, `2` erro
de configuração.

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

## Regras de disponibilidade (PRD §6)

| Dia | Janela permitida |
|-----|------------------|
| Segunda a sexta | nascer do sol → 09:30 |
| Sábado | nascer do sol → pôr do sol |
| Domingo | nascer do sol → 12:00 |

- Nascer/pôr do sol vêm **do próprio SAGA** (endpoint interno, ADR-0008),
  nunca de API de astronomia externa.
- Buffer de turnaround entre voos da mesma aeronave: `turnaround_minutes`
  (padrão 30 min).
- Vão livre menor que `min_flight_minutes` não é reservável e fica de
  fora do relatório (só janelas 🟢 reserváveis são listadas).
- A janela é arredondada na grade de 30 min: começa no nascer do sol
  arredondado para cima (06:17 → 06:30) e, no sábado, termina no pôr do
  sol arredondado para baixo (17:23 → 17:00).

## Aquisição da escala (HTTP direto)

A varredura é uma sessão `requests`: login (único POST — ADR-0001), leitura
da variável `allSchedules` embutida no HTML da página (ADR-0010) e do XML de
nascer/pôr do sol (ADR-0008). Não há browser nem seletores CSS a calibrar
(ADR-0011). Em falha de login ou de layout, o HTML da resposta é salvo em
`debug/` (e vai ao log no Lambda) — é por ele que se confere o que mudou.

## Arquitetura

Os módulos de runtime vivem em `src/` (é o que o `sam build` empacota; o
`config.ini` com segredos fica fora, na raiz do projeto).

| Módulo | Papel |
|--------|-------|
| `main.py` | CLI, logging, orquestração e loop (ADR-0009) |
| `config.py` | `config.ini` → dataclasses validadas (ADR-0005) |
| `models.py` | dataclasses de domínio, sem dependências |
| `availability.py` | regras de disponibilidade puras (ADR-0004) |
| `notifications.py` | política "só aberturas novas" + `state.json` |
| `report.py` | formatação das janelas livres (relatório e aberturas) |
| `discord.py` | webhook + fragmentação em 2000 chars (ADR-0006) |
| `saga_http.py` | aquisição HTTP: login + `allSchedules` + sol numa sessão `requests` (ADR-0011) |
| `saga_data.py` | JSON/XML brutos do SAGA → domínio, puro (ADR-0010) |
| `utils.py` | parsing puro de texto (horários, matrículas) |

Decisões registradas em [`docs/adr/`](docs/adr/README.md); requisitos em
[`docs/PRD.md`](docs/PRD.md).

## Testes

```
.venv\Scripts\python -m unittest -v
```

Toda a lógica de negócio roda sem browser (ADR-0004). A aquisição HTTP é
testada com uma sessão `requests` falsa; nenhum teste toca a rede nem o
SAGA real.

## Solução de problemas

- **`LoginError` / login não confirmado** — o form de login do SAGA mudou ou
  as credenciais estão erradas. O HTML da página no momento da falha é salvo
  em `debug/` (e vai ao log no Lambda); confira os campos `_token`, `email`,
  `password` contra `saga_http.py`.
- **`allSchedules não encontrado na página da escala`** — confira
  `saga.schedule_url` (deve apontar para Escala → Meus Voos). Se a URL
  está certa, o SAGA mudou o contrato da página (ADR-0010) — inspecione o
  HTML de `debug/`.
- **Sol indisponível** — o endpoint `/aisweb/sun/SBVT` falhou; a varredura
  sai sem janelas e reporta ⚠️ (ADR-0008). Normaliza sozinho quando o
  endpoint voltar.
- **Nada chega no Discord** — teste o webhook com
  `curl -X POST -H "Content-Type: application/json" -d "{\"content\": \"teste\"}" URL_DO_WEBHOOK`.

## Limitações conhecidas

- Polling por intervalo, sem notificação em tempo real (fora de escopo).
- Histórico mínimo: só o snapshot da última varredura em `state.json`
  (sem banco de dados).
- Nascer/pôr do sol dos dias futuros é aproximação do valor de hoje —
  desvio ≤ ~7 min no fim da janela de 30 dias (ADR-0008).
- Uma mudança no form de login do SAGA ou no contrato `allSchedules` pode
  quebrar a aquisição (ADR-0011 / ADR-0010) — o monitor avisa no Discord.

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
