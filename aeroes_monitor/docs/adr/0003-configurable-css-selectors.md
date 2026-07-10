# ADR-0003: Seletores CSS externalizados em `config.ini`

## Status
Aceito

## Contexto
Como consequência de [[0002-selenium-over-api]], o monitor depende de seletores CSS para localizar elementos na página do SAGA. O layout é mantido por terceiros e pode mudar sem aviso.

## Decisão
Todos os seletores usados pelo Selenium (`login_email`, `schedule_container`, `aircraft_row`, `sunrise_text`, etc.) ficam na seção `[selectors]` do `config.ini`, com defaults razoáveis embutidos em `config.py` (`_load_selectors`) usados apenas quando a seção está ausente.

## Consequências
**Positivas**
- Uma mudança de layout no SAGA pode ser corrigida editando configuração, sem alterar ou reimplantar código.
- Defaults com múltiplos seletores candidatos por chave (`wait_for_any_visible`, `read_text_from_selectors`) toleram pequenas variações de markup sem qualquer alteração.

**Negativas / trade-offs**
- Requer calibração manual inicial inspecionando a página real via DevTools (documentado no README).
- Nenhuma validação automática de que os seletores configurados continuam corretos — a primeira indicação de quebra é uma falha em tempo de execução.

## Alternativas consideradas
- **Seletores hardcoded no código**: mais simples, mas exigiria alteração de código a cada mudança de layout do SAGA, contrariando o objetivo de manutenção de baixo esforço para uma dependência externa fora de controle do autor.

## Emenda (2026-07-09)
Com [[0010-allschedules-js-variable]], a escala não é mais raspada do DOM: os seletores de agenda (`schedule_container`, `resource_row`, `event_item`, `sunrise_text`, etc.) foram removidos dos defaults e do `config.ini.example`. A seção `[selectors]` passa a cobrir **apenas login/sessão** (`login_username`, `login_password`, `login_submit`, `login_form`, `logged_in_marker`). A decisão em si — seletores externalizados com defaults embutidos — permanece válida para o que restou.
