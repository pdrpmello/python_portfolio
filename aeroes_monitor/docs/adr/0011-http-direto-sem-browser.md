# ADR-0011: Aquisição por HTTP direto (requests), sem browser

## Status
Aceito (2026-07-13). Supersede [[0002-selenium-over-api]] e a parte de
seletores de [[0003-configurable-css-selectors]].

## Contexto
[[0002-selenium-over-api]] adotou Selenium por supor que a página exigia
renderização client-side e que HTTP puro seria inviável. Para rodar na AWS
sem custo (pedido do Pedro), o Chrome forçava Lambda por container e ECR — o
único item pago do desenho (~R$ 1/mês, permanente).

Um probe ao vivo (2026-07-13) refutou a suposição de 0002:
- O HTML de `/schedules/personal` é server-rendered: `const allSchedules =
  [...]` vem embutido no fonte (187 KB de JSON inline), sem JS a executar.
- O login é um form Laravel padrão (`_token` + `email` + `password`), sem
  captcha nem desafio de WAF.
- Fluxo completo em `requests` puro: GET login → POST login → GET escala
  (440 registros extraídos) → GET /aisweb/sun/SBVT. 4/4 OK em 21 s.

## Decisão
`saga_http.py` faz a varredura inteira numa sessão `requests`, expondo
`scan(config) -> ScanResult` (a mesma fronteira do antigo `ScheduleScanner`).
Login segue sendo o único POST — [[0001-read-only-scope]] intacto. A escala
sai da variável `allSchedules` do HTML ([[0010-allschedules-js-variable]]) e o
sol do XML de /aisweb/sun/SBVT ([[0008-sunrise-sunset-from-saga-page]]). O
Lambda vira zip (sem ECR); o estado, DynamoDB. Selenium/Chrome e a seção
`[selectors]` são removidos; a config de rede fica em `[saga]`.

## Consequências
**Positivas**
- Custo estrutural R$ 0/mês: sem ECR, sem container. Lambda zip 256 MB/~10 s
  (contra 2 GB/~90 s). Sem Docker Desktop no fluxo de deploy.
- Menos superfície frágil: sem esperas de DOM, sem calibração de seletores,
  sem `TimeoutException`. Recalibração agora é conferir o form de login no
  HTML salvo em falha.
- `python src/main.py` local também fica mais rápido e sem dependência de
  Chrome instalado.

**Negativas / trade-offs**
- Depende do form de login e do contrato `allSchedules` continuarem estáveis
  (mesma classe de risco que [[0010-allschedules-js-variable]] já assumia).
- Se o SAGA adotar anti-bot/Cloudflare, a rota HTTP quebra. Plano B: a rota
  container está preservada no git (branch `feat/aeroes-aws-lambda`, commit
  `cf0f83f` — Dockerfile `859c48f`, template imagem `2e24b69`), reabilitável
  com custo ~R$ 1/mês. A quebra é avisada no Discord na transição ok→falha.

## Alternativas consideradas
- **Manter Selenium (container+ECR)**: robustez marginal a mais (browser real
  tolera JS/anti-bot) ao custo de ~R$ 1/mês permanente e de todo o aparato
  Docker/ECR. Vira o plano B, não o padrão.
- **Selenium só no modo local, HTTP na nuvem**: dois caminhos de aquisição
  para manter e ver divergir — descartado por manutenção dobrada.
