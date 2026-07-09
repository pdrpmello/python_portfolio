# Aeroclube Schedule Monitor

Monitor **read-only** da escala de horários de voo do sistema SAGA do
Aeroclube do Espírito Santo. Varre a agenda dos próximos dias, aplica as
regras operacionais do clube e envia ao Discord um relatório do que está
🟢 livre e 🔴 ocupado, por aeronave e por dia.

## Garantia read-only

Este programa **não faz reservas e não altera nada no SAGA** (ADR-0001).
Ele apenas: autentica → navega → lê o HTML exibido → calcula localmente →
reporta no Discord. O único formulário que ele submete é o de **login**.
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

## Regras de disponibilidade (PRD §6)

| Dia | Janela permitida |
|-----|------------------|
| Segunda a sexta | nascer do sol → 09:30 |
| Sábado | nascer do sol → pôr do sol |
| Domingo | nascer do sol → 12:00 |

- Nascer/pôr do sol vêm **da própria página do SAGA** (ADR-0008), nunca de
  API externa.
- Buffer de turnaround entre voos da mesma aeronave: `turnaround_minutes`
  (padrão 30 min).
- Vão livre menor que `min_flight_minutes` aparece como 🔴 "vão curto":
  não é reservável.

## Calibração de seletores (primeiro uso)

Os seletores CSS padrão são um palpite razoável — o SAGA real quase
certamente usa outros. Para calibrar (ADR-0003):

1. Rode com `headless = false` para ver o browser.
2. Abra o SAGA manualmente no Chrome, faça login e vá até a escala.
3. F12 (DevTools) → botão de inspecionar → clique no elemento desejado
   (campo de e-mail, linha de aeronave, texto do nascer do sol, botão de
   próximo dia, etc.).
4. Anote um seletor CSS estável (prefira `name`, `id` ou classes
   descritivas; evite classes geradas/aleatórias).
5. Descomente `[selectors]` no `config.ini` e preencha as chaves — um
   seletor por linha; a ordem é a ordem de tentativa.
6. Rode `python main.py --once` e ajuste até a varredura completar.

Em caso de falha, o monitor salva screenshot + HTML em `debug/` — use-os
para descobrir o que mudou.

## Arquitetura

| Módulo | Papel |
|--------|-------|
| `main.py` | CLI, logging, orquestração e loop (ADR-0009) |
| `config.py` | `config.ini` → dataclasses validadas (ADR-0005) |
| `models.py` | dataclasses de domínio, sem dependências |
| `availability.py` | regras de disponibilidade puras (ADR-0004) |
| `report.py` | formatação 🟢/🔴 do relatório |
| `discord.py` | webhook + fragmentação em 2000 chars (ADR-0006) |
| `browser.py` | Chrome/Selenium, esperas, artefatos de debug |
| `login.py` | autenticação e detecção de sessão expirada |
| `scheduler.py` | varredura dia a dia, erros recuperáveis |
| `aircraft.py` | parsing das agendas (aeronaves + Stand By) |
| `utils.py` | parsing puro de texto (horários, datas, sol) |

Decisões registradas em [`docs/adr/`](docs/adr/README.md); requisitos em
[`docs/PRD.md`](docs/PRD.md).

## Testes

```
.venv\Scripts\python -m unittest -v
```

Toda a lógica de negócio roda sem browser (ADR-0004). A camada Selenium é
testada com fakes; nenhum teste abre Chrome nem toca o SAGA real.

## Solução de problemas

- **`TimeoutException: Nenhum seletor visível`** — seletor desatualizado;
  recalibre (seção acima) usando os artefatos de `debug/`.
- **`Nascer do sol não encontrado`** — a página do dia não exibiu o
  horário; o dia é pulado e reportado com ⚠️ (ADR-0008).
- **Nada chega no Discord** — teste o webhook com
  `curl -X POST -H "Content-Type: application/json" -d "{\"content\": \"teste\"}" URL_DO_WEBHOOK`.
- **Sessão expira no meio** — reautenticação é automática (F2); veja o log.

## Limitações conhecidas

- Polling por intervalo, sem notificação em tempo real (fora de escopo).
- Sem histórico entre execuções (sem banco de dados).
- Uma mudança de layout do SAGA exige recalibração manual de seletores.
