# ADR-0008: Nascer/pôr do sol lidos exclusivamente da página do SAGA

## Status
Aceito

## Contexto
As janelas de disponibilidade (ver PRD, seção 6) dependem do horário de nascer e pôr do sol de cada dia. Essa informação poderia vir de uma API de astronomia externa (calculada por latitude/longitude e data) ou ser lida diretamente do valor que o próprio SAGA exibe para o dia.

## Decisão
`ScheduleScanner._read_sunrise` / `_read_sunset` extraem esses horários exclusivamente do texto renderizado na página do SAGA (via `extract_sunrise`/`extract_sunset` em `utils.py`, com fallback para seletores configuráveis `sunrise_text`/`sunset_text`). Se a página não exibir esses valores para um dia, a leitura daquele dia falha explicitamente (`ValueError`) em vez de calcular um valor alternativo.

## Consequências
**Positivas**
- Garante consistência com a fonte que o próprio Aeroclube usa operacionalmente — se o clube usa uma referência específica (ex.: horário local ajustado, regra própria), o monitor replica exatamente isso em vez de divergir por causa de uma biblioteca de astronomia diferente.
- Elimina uma dependência externa (API de astronomia, coordenadas geográficas, fuso horário) e a superfície de erro que ela traria.

**Negativas / trade-offs**
- Se o SAGA não exibir nascer/pôr do sol para um dia específico (ex.: mudança de layout, campo ausente), aquele dia é reportado como erro recuperável e fica de fora do relatório, em vez de usar um valor calculado como fallback.
- Acopla essa informação, novamente, ao parsing HTML (mesma fragilidade de [[0002-selenium-over-api]]).

## Alternativas consideradas
- **API de astronomia externa** (ex.: cálculo por coordenadas fixas do aeródromo): mais resiliente a mudanças de layout, mas introduz risco de divergência silenciosa em relação à referência real usada pelo clube, e uma dependência de rede adicional. Rejeitada em favor de fidelidade à fonte oficial.

## Emenda (2026-07-09)
A página da escala deixou de ser raspada ([[0010-allschedules-js-variable]]) e não exibe nascer/pôr do sol como texto; o dado vem agora do endpoint do próprio SAGA `/aisweb/sun/SBVT`, consultado na mesma sessão autenticada (fetch same-origin em `scheduler.py`, parse puro em `saga_data.py`). O princípio da decisão — fidelidade à fonte que o clube usa, nada de API de astronomia externa — permanece. Limitações do endpoint:

- Ele só serve o **dia atual**, em **UTC**. O valor de hoje, convertido para hora local (America/Sao_Paulo), aplica-se à janela inteira de varredura e é rotulado como aproximado — desvio ≤ ~7 min no dia 30 da janela.
- Sol indisponível (endpoint fora do ar, XML inválido) ⇒ varredura **degradada, sem janelas**: nenhum dia é relatado e um erro recuperável (⚠️) explica o motivo — mantendo o espírito de "falhar explicitamente em vez de calcular um valor alternativo".
