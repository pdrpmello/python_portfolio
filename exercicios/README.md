# Exercícios

Scripts curtos dos primeiros passos em Python. Cada um resolve um problema
só e foca num conceito: consumo de API, web scraping, validação de entrada e
laços.

| Script | O que faz | Dependências |
|---|---|---|
| `br_meteorological_report.py` | Consulta o METAR atual de um aeródromo brasileiro na API da REDEMET (DECEA) | `requests` |
| `exchange_rate_usd.py` | Busca a cotação do dólar em reais no site da Wise (web scraping) | `requests`, `beautifulsoup4` |
| `even_odd_game.py` | Jogo de par ou ímpar contra o computador, com validação de entrada | — |
| `fibonacci_numbers.py` | Gera a sequência de Fibonacci a partir de um número inicial | — |

## Como rodar

```bash
cd exercicios
pip install -r requirements.txt
python even_odd_game.py
```

### Chave da API da REDEMET

O `br_meteorological_report.py` lê a chave da variável de ambiente
`REDEMET_API_KEY`. Ela nunca fica no código:

```powershell
$env:REDEMET_API_KEY = "sua-chave"
python br_meteorological_report.py
```
