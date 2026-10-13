# Python Portfolio

[![CI](https://github.com/pdrpmello/python_portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/pdrpmello/python_portfolio/actions/workflows/ci.yml)

Projetos em Python de automação, coleta de dados e integração com APIs, dos
primeiros exercícios a um serviço em produção na AWS.

## Projetos

| Projeto | O que faz | Stack |
|---|---|---|
| [aeroes_monitor](aeroes_monitor/) | Monitora a escala de voos do Aeroclube do Espírito Santo (sistema SAGA) e envia ao Discord as janelas livres de cada aeronave. Roda a cada 20 minutos na AWS Lambda | requests, AWS Lambda, DynamoDB, EventBridge Scheduler, SAM |
| [msu_scraper](msu_scraper/) | Coleta preços de NFTs, FTs e personagens no marketplace do MapleStory Universe e registra tudo no Google Sheets | Selenium, gspread |
| [running_monitor](running_monitor/) | Analisa treinos de corrida do Garmin Connect: zonas de FC, deriva cardíaca e paces-alvo | Python, numpy, Node.js, Playwright |
| [audio_transcriber](audio_transcriber/) | Transcreve áudio para texto localmente | Whisper |
| [exercicios](exercicios/) | Primeiros scripts: API da REDEMET, web scraping, jogos e algoritmos | requests, BeautifulSoup |

## Como rodar

Cada pasta é um projeto independente, com README, dependências e configuração
próprios. Em geral:

```bash
git clone https://github.com/pdrpmello/python_portfolio.git
cd python_portfolio/<projeto>
python -m venv .venv
.venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate
```

Depois, siga o README do projeto para instalar as dependências e configurar.

## Licença

[MIT](LICENSE)
