# ADR-0007: Lista manual de aeronaves operacionais (ignora status do sistema)

## Status
Aceito

## Contexto
O SAGA provavelmente expõe algum indicador de status por aeronave (ex.: em manutenção, inativa), mas esse indicador pode não refletir com precisão quais aeronaves o usuário de fato quer monitorar, ou pode não ser exposto de forma parseável de maneira confiável.

## Decisão
As aeronaves monitoradas vêm de uma lista configurada explicitamente pelo usuário em `[aircraft]` no `config.ini` (registro → modelo), carregada por `_load_aircraft` em `config.py`. `AircraftService.build_aircraft_schedules` constrói o relatório apenas para essas aeronaves, independentemente de qualquer status exibido pelo sistema para outras aeronaves da frota.

## Consequências
**Positivas**
- Comportamento previsível e sob controle total do usuário: nunca reporta uma aeronave que ele não pediu para monitorar.
- Evita depender de parsing de um indicador de status do SAGA que pode ser ambíguo, inconsistente ou ausente no HTML.
- Simplifica o parsing: `build_aircraft_schedules` sempre produz um `ResourceSchedule` por aeronave configurada, mesmo sem período ocupado nenhum (lista vazia), facilitando teste e leitura do relatório.

**Negativas / trade-offs**
- Requer manutenção manual: uma aeronave nova na frota do clube não aparece no relatório até o usuário editar `config.ini`.
- Se uma aeronave configurada sair de operação (manutenção prolongada, venda), o monitor continua reportando-a como se estivesse disponível, a menos que o usuário atualize a configuração.

## Alternativas consideradas
- **Confiar no status exibido pelo sistema** para decidir quais aeronaves incluir: rejeitado por depender de um sinal de terceiros potencialmente não confiável/parseável, quando uma lista estática de poucas aeronaves é trivial de manter manualmente.
