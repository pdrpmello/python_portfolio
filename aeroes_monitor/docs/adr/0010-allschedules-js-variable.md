# ADR-0010: Agendamentos lidos da variável JS `allSchedules`

## Status
Aceito

## Contexto
A página da escala (`/schedules/personal`) não é uma grade raspável: os eventos são divs sem classes estáveis, não há botão de "próximo dia" (a janela inteira já está na página) e o markup é Material Dashboard genérico. Por outro lado, a própria página embute em uma variável JavaScript global — `allSchedules` — o JSON completo dos agendamentos da janela de ~30 dias (o input de data limita min=hoje, max=hoje+30d): exatamente os dados que o UI usa para se desenhar.

## Decisão
`ScheduleScanner` lê a variável diretamente, via `driver.execute_script("return allSchedules")`, depois de esperar que ela exista. Uma única leitura cobre a varredura inteira — não há navegação dia a dia. Os horários vêm dos campos `start_at_raw`/`end_at_raw` (já em hora local); agendamentos com `status == "CANCELED"` são descartados, como o próprio UI faz. A conversão JSON → domínio é pura e vive em `saga_data.py` (ver [[0004-decoupled-availability-rules]]). O caráter read-only de [[0001-read-only-scope]] é preservado: apenas GETs e leitura de variável — o único formulário submetido continua sendo o de login.

## Consequências
**Positivas**
- Aposenta o parsing de DOM da escala (`aircraft.py` e os seletores de agenda de [[0003-configurable-css-selectors]]): menos superfície frágil e nenhuma calibração de seletores para a escala.
- Dados estruturados na fonte: horários exatos, status e aeronave vêm do JSON, sem regex sobre texto renderizado.
- Uma navegação por varredura (a página expõe a janela inteira) — mais rápido e com menos requisições ao SAGA.

**Negativas / trade-offs**
- Acopla o monitor ao contrato JS interno da página (nome da variável, campos `*_raw`, semântica de `status`) — tão não documentado quanto o DOM. Se o SAGA remover ou renomear a variável, a varredura falha por inteiro (erro fatal com artefatos de debug em `debug/`), em vez de degradar dia a dia.
- A janela fica limitada aos ~30 dias que a página expõe; `max_days` maior é truncado e reportado.

## Alternativas consideradas
- **Raspar o DOM da escala** (abordagem original do projeto): inviável na prática — eventos sem classes estáveis e sem paginação por dia; era a opção mais frágil e mais lenta.
- **Chamar a API interna do SAGA por HTTP puro**: exigiria engenharia reversa de endpoints e gestão de sessão fora do browser, contrariando [[0002-selenium-over-api]]; a variável embutida entrega o mesmo dado dentro da sessão já autenticada.
