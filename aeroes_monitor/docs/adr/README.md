# Architecture Decision Records

| ADR | Título |
|-----|--------|
| [0001](0001-read-only-scope.md) | Aplicação estritamente read-only (sem automação de reservas) |
| [0002](0002-selenium-over-api.md) | Selenium em vez de integração por API — superado por [0011](0011-http-direto-sem-browser.md) |
| [0003](0003-configurable-css-selectors.md) | Seletores CSS externalizados em `config.ini` — superado por [0011](0011-http-direto-sem-browser.md) |
| [0004](0004-decoupled-availability-rules.md) | Regras de negócio isoladas em `availability.py` |
| [0005](0005-config-ini-over-dotenv.md) | `config.ini` em vez de `.env` |
| [0006](0006-discord-webhook-notifications.md) | Discord Webhook como único canal de notificação |
| [0007](0007-manual-aircraft-allowlist.md) | Lista manual de aeronaves operacionais |
| [0008](0008-sunrise-sunset-from-saga-page.md) | Nascer/pôr do sol lidos exclusivamente da página do SAGA |
| [0009](0009-in-process-polling-loop.md) | Loop de polling in-process em vez de agendador externo |
| [0010](0010-allschedules-js-variable.md) | Agendamentos lidos da variável JS allSchedules |
| [0011](0011-http-direto-sem-browser.md) | Aquisição por HTTP direto (requests), sem browser |
