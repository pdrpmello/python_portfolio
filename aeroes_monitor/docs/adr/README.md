# Architecture Decision Records

| ADR | Título |
|-----|--------|
| [0001](0001-read-only-scope.md) | Aplicação estritamente read-only (sem automação de reservas) |
| [0002](0002-selenium-over-api.md) | Selenium em vez de integração por API |
| [0003](0003-configurable-css-selectors.md) | Seletores CSS externalizados em `config.ini` |
| [0004](0004-decoupled-availability-rules.md) | Regras de negócio isoladas em `availability.py` |
| [0005](0005-config-ini-over-dotenv.md) | `config.ini` em vez de `.env` |
| [0006](0006-discord-webhook-notifications.md) | Discord Webhook como único canal de notificação |
| [0007](0007-manual-aircraft-allowlist.md) | Lista manual de aeronaves operacionais |
| [0008](0008-sunrise-sunset-from-saga-page.md) | Nascer/pôr do sol lidos exclusivamente da página do SAGA |
| [0009](0009-in-process-polling-loop.md) | Loop de polling in-process em vez de agendador externo |
