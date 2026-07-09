# ADR-0004: Regras de negócio isoladas em `availability.py`, sem dependência de browser

## Status
Aceito

## Contexto
O cálculo de disponibilidade (janela por dia da semana, buffer de turnaround, duração mín/máx de voo) é a lógica de maior valor e maior risco de bug do sistema — um erro aqui reporta um horário como livre quando não está, ou vice-versa. Testar essa lógica exercitando o Selenium real seria lento e frágil.

## Decisão
Toda a lógica de classificação de disponibilidade (`operating_window`, `apply_turnaround_buffer`, `filter_bookable_periods`, `classify_day_periods`, `enrich_day_schedule`) vive em `availability.py`, operando exclusivamente sobre dataclasses de domínio (`TimePeriod`, `ResourceSchedule`, `DaySchedule` em `models.py`) — sem nenhuma referência a `WebDriver` ou Selenium. O parsing HTML (`aircraft.py`, `scheduler.py`) apenas produz essas dataclasses; `availability.py` as consome.

## Consequências
**Positivas**
- Regras de negócio são testáveis com `unittest` puro (`tests/test_availability.py`), sem browser, sem rede, execução rápida e determinística.
- Mudança de layout do SAGA (ADR [[0002-selenium-over-api]], [[0003-configurable-css-selectors]]) não exige retestar as regras de disponibilidade.
- Separação clara de responsabilidades: parsing (frágil, depende de terceiros) vs. regras (estável, sob controle total).

**Negativas / trade-offs**
- Exige manter o contrato de dados (`models.py`) estável entre as duas camadas; mudanças nas dataclasses afetam ambos os lados.
- O parsing HTML em si (`aircraft.py`) continua dependente do Selenium e não se beneficia diretamente desse isolamento.

## Alternativas consideradas
- **Lógica de disponibilidade embutida em `scheduler.py`/`aircraft.py`**: rejeitada por acoplar regra de negócio testável a código que só roda com browser real, dificultando testes unitários rápidos.
