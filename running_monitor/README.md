# Running Monitor

Analisa treinos de corrida a partir do histórico do Garmin Connect: volume
semanal, tempo em cada zona de frequência cardíaca, deriva de FC nas parciais
e paces-alvo para treinar abaixo de uma FC de referência.

## Fluxo

1. **Coleta** (`scripts/fetch_garmin.mjs`): baixa para `data/raw/` as
   atividades, as parciais por km das corridas recentes e os dados de wellness
   (FC de repouso, HRV, sono e prontidão).
2. **Análise** (`scripts/analyze.py`): lê `data/raw/` e imprime um retrato do
   treino. Roda offline.
3. **Modelo de pace** (`scripts/pace_model.py`): estima paces-alvo para uma FC
   de referência a partir das parciais por km.

## Requisitos

- Node.js e o servidor MCP
  [`@etweisberg/garmin-connect-mcp`](https://www.npmjs.com/package/@etweisberg/garmin-connect-mcp),
  que fornece a sessão autenticada e o Playwright. Ele já está configurado em `.mcp.json`.
- Python 3.10+ com as dependências de `requirements.txt`

## Uso

Rode tudo a partir desta pasta:

```bash
node scripts/fetch_garmin.mjs --days=90 --splits=15
python scripts/analyze.py
python scripts/pace_model.py --sens 5.0
```

- A sessão vem de `~/.garmin-connect-mcp/session.json` e expira em poucas
  horas, por isso a coleta baixa tudo de uma vez e a análise roda offline.
- Desde março de 2026 o Garmin bloqueia clientes HTTP comuns pela impressão
  digital do TLS. Por isso a coleta faz as chamadas de dentro de um Chromium,
  via Playwright.
- Se o Playwright não estiver no caminho padrão do garmin-connect-mcp, aponte
  a variável `GARMIN_PLAYWRIGHT_PATH` para ele.
- `--sens` é a premissa de quantos segundos por km o pace cai a cada bpm. Com
  6 ou mais parciais abaixo de 150 bpm, o script passa a usar uma regressão
  sobre os dados reais.

## Privacidade

A pasta `data/` guarda dados pessoais de saúde e está no `.gitignore`. Só o
código vai para o repositório.
