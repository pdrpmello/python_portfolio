# Aeroclube Schedule Monitor

Monitor **read-only** da escala de horários de voo do sistema SAGA do
Aeroclube do Espírito Santo. Varre a agenda dos próximos dias, aplica as
regras operacionais do clube e envia ao Discord um relatório do que está
🟢 livre e 🔴 ocupado, por aeronave e por dia.

## Garantia read-only

Este programa **não faz reservas e não altera nada no SAGA** (ADR-0001).
Ele apenas: autentica → navega → lê os dados que a página carrega →
calcula localmente → reporta no Discord. O único formulário que ele submete é o de **login**.
A ação de reservar continua 100% manual, no próprio SAGA.

## Requisitos

- Python 3.13+
- Google Chrome instalado (o chromedriver é resolvido automaticamente pelo
  Selenium Manager — nada para baixar)
- Um webhook de Discord

## Instalação

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Configuração

1. Copie `config.ini.example` para `config.ini`.
2. Preencha `[credentials]`, `[discord] webhook_url` e `[selenium] base_url`.
3. Liste em `[aircraft]` as aeronaves a monitorar (`MATRICULA = modelo`).
   Só elas aparecem no relatório (ADR-0007).

`config.ini` está no `.gitignore` — **nunca** o versione. Os logs redigem
senha e webhook automaticamente.

## Uso

```
.venv\Scripts\python main.py --once   # uma varredura e sai
.venv\Scripts\python main.py          # loop contínuo (intervalo do config.ini)
```

Códigos de saída de `--once`: `0` sucesso, `1` varredura falhou, `2` erro
de configuração.

A primeira varredura estabelece a **baseline**: envia o resumo e o
relatório completo e grava o snapshot das janelas 🟢 em `state.json`
(não versionado). Das varreduras seguintes em diante vale a política
"**só aberturas novas**": o Discord só recebe mensagem quando surge uma
janela 🟢 que não existia no snapshot anterior — janela que some é
silêncio. Apague `state.json` para forçar uma nova baseline.

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
- Vão livre menor que `min_flight_minutes` aparece como 🔴 "vão curto":
  não é reservável.

## Calibração de seletores (só login/sessão)

Os seletores CSS cobrem **apenas login e detecção de sessão** — a escala
não é raspada do DOM: ela é lida da variável `allSchedules` que a própria
página carrega (ADR-0010). Os defaults de login já batem com o SAGA real
(calibrados em 2026-07-09); só recalibre se o login quebrar (ADR-0003):

1. Rode com `headless = false` para ver o browser.
2. Abra o SAGA manualmente no Chrome e vá até a tela de login.
3. F12 (DevTools) → botão de inspecionar → clique no elemento desejado
   (campo de e-mail, senha, botão de entrar; para `logged_in_marker`,
   algo sempre **visível** após o login).
4. Anote um seletor CSS estável (prefira `name`, `id` ou classes
   descritivas; evite classes geradas/aleatórias).
5. Descomente `[selectors]` no `config.ini` e preencha as chaves — um
   seletor por linha; a ordem é a ordem de tentativa.
6. Rode `python main.py --once` e ajuste até o login completar.

Em caso de falha, o monitor salva screenshot + HTML em `debug/` — use-os
para descobrir o que mudou.

## Arquitetura

| Módulo | Papel |
|--------|-------|
| `main.py` | CLI, logging, orquestração e loop (ADR-0009) |
| `config.py` | `config.ini` → dataclasses validadas (ADR-0005) |
| `models.py` | dataclasses de domínio, sem dependências |
| `availability.py` | regras de disponibilidade puras (ADR-0004) |
| `notifications.py` | política "só aberturas novas" + `state.json` |
| `report.py` | formatação 🟢/🔴 do relatório e das aberturas |
| `discord.py` | webhook + fragmentação em 2000 chars (ADR-0006) |
| `browser.py` | Chrome/Selenium, esperas, artefatos de debug |
| `login.py` | autenticação e detecção de sessão expirada |
| `scheduler.py` | aquisição: `allSchedules` + sol, na sessão autenticada (ADR-0010) |
| `saga_data.py` | JSON/XML brutos do SAGA → domínio, puro (ADR-0010) |
| `utils.py` | parsing puro de texto (horários, matrículas) |

Decisões registradas em [`docs/adr/`](docs/adr/README.md); requisitos em
[`docs/PRD.md`](docs/PRD.md).

## Testes

```
.venv\Scripts\python -m unittest -v
```

Toda a lógica de negócio roda sem browser (ADR-0004). A camada Selenium é
testada com fakes; nenhum teste abre Chrome nem toca o SAGA real.

## Solução de problemas

- **`TimeoutException: Nenhum seletor visível`** — seletor de login
  desatualizado; recalibre (seção acima) usando os artefatos de `debug/`.
- **`allSchedules não encontrado na página da escala`** — confira
  `selenium.schedule_url` (deve apontar para Escala → Meus Voos). Se a URL
  está certa, o SAGA mudou o contrato da página (ADR-0010) — inspecione os
  artefatos de `debug/`.
- **Sol indisponível** — o endpoint `/aisweb/sun/SBVT` falhou; a varredura
  sai sem janelas e reporta ⚠️ (ADR-0008). Normaliza sozinho quando o
  endpoint voltar.
- **Nada chega no Discord** — teste o webhook com
  `curl -X POST -H "Content-Type: application/json" -d "{\"content\": \"teste\"}" URL_DO_WEBHOOK`.
- **Sessão expira no meio** — reautenticação é automática (F2); veja o log.

## Limitações conhecidas

- Polling por intervalo, sem notificação em tempo real (fora de escopo).
- Histórico mínimo: só o snapshot da última varredura em `state.json`
  (sem banco de dados).
- Nascer/pôr do sol dos dias futuros é aproximação do valor de hoje —
  desvio ≤ ~7 min no fim da janela de 30 dias (ADR-0008).
- Uma mudança no SAGA exige recalibração dos seletores de login ou pode
  quebrar o contrato `allSchedules` (ADR-0010).
