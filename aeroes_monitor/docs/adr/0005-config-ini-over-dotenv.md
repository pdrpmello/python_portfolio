# ADR-0005: `config.ini` em vez de `.env` / variáveis de ambiente

## Status
Aceito

## Contexto
A aplicação precisa de configuração heterogênea: credenciais simples (usuário/senha), uma URL de webhook, um dicionário de aeronaves operacionais (registro → modelo), seletores CSS (uma dúzia de chaves de texto) e parâmetros numéricos de monitoramento/Selenium. Boa parte não é um simples par chave-valor plano.

## Decisão
Usar `configparser` (`config.ini`) com seções (`[credentials]`, `[discord]`, `[monitor]`, `[selenium]`, `[selectors]`, `[aircraft]`, `[logging]`), carregado e validado em `config.py` para dataclasses frozen tipadas (`AppConfig` e afins).

## Consequências
**Positivas**
- Um único arquivo agrupa credenciais, webhook, aeronaves e seletores — mais fácil de versionar mentalmente e documentar via `config.ini.example`.
- Seções mapeiam naturalmente para as dataclasses de configuração, dando validação e defaults centralizados (`_require`, `_get_int`, `_get_bool`).
- Dicionário arbitrário de aeronaves (`[aircraft]`) é trivial em INI; seria menos natural como lista de variáveis de ambiente.

**Negativas / trade-offs**
- Foge do padrão 12-factor (`.env`) mais comum em deploys containerizados/cloud — documentado explicitamente como trade-off aceito no README.
- `config.ini` contém segredos em texto plano no disco, como um `.env` teria; a proteção depende inteiramente do `.gitignore` (mesma exposição que `.env` teria).

## Alternativas consideradas
- **`.env` + variáveis de ambiente**: mais idiomático para 12-factor apps e deploys em nuvem, mas modelar seletores CSS e o dicionário de aeronaves como variáveis de ambiente seria mais verboso (chaves prefixadas ou JSON serializado em uma única variável). Rejeitado para uso local de portfólio single-user.
