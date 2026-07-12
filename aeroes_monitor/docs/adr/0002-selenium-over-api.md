# ADR-0002: Automação via Selenium em vez de integração por API

## Status
Aceito

## Contexto
O SAGA não expõe uma API pública documentada para consulta de escala. A única interface disponível é a aplicação web renderizada para o usuário final.

## Decisão
Usar Selenium WebDriver (Chrome, via Selenium Manager) para automatizar login e navegação, e extrair dados por parsing de texto/HTML/CSS renderizado (`browser.py`, `login.py`, `scheduler.py`, `aircraft.py`).

## Consequências
**Positivas**
- Única forma viável de acessar os dados sem engenharia reversa de um endpoint privado não documentado.
- Selenium Manager elimina gerenciamento manual de driver binário.

**Negativas / trade-offs**
- Acoplamento forte ao layout HTML da página: qualquer mudança de UI no SAGA pode quebrar seletores.
- Mais lento e mais frágil que uma chamada HTTP/API direta (timeouts, elementos não carregados, `TimeoutException`).
- Depende de um navegador Chrome instalado no ambiente de execução.
- Superfície de erro maior, mitigada por artefatos de debug (`save_debug_artifacts`) e por tornar os seletores configuráveis (ver [[0003-configurable-css-selectors]]).

## Alternativas consideradas
- **Engenharia reversa de uma API interna do SAGA** (chamadas XHR usadas pelo frontend): mais rápida e estável, mas não documentada, potencialmente instável entre versões, e com risco maior de violar termos de uso ao depender de contratos não públicos. Não adotada.
- **Scraping de HTML estático via `requests`/`httpx`**: inviável porque a página exige autenticação de sessão e provavelmente renderização client-side.
