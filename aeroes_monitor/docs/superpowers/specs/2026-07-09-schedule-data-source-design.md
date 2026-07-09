# Design: varredura via `allSchedules` + política de sol para dias futuros

Data: 2026-07-09 · Status: aprovado pelo usuário

## Contexto e evidências (calibração de 2026-07-09)

Primeira execução real contra o SAGA (`https://aeroes.saga.aero/`) revelou que a
página da escala difere do que os defaults do ADR-0003 supunham:

- Login: os seletores padrão de formulário **funcionam**; o `logged_in_marker`
  padrão (`a[href*="logout"]`) existe mas fica oculto no dropdown do perfil —
  corrigido via `[selectors]` no `config.ini` com marcadores visíveis
  (`#navbarDropdownProfile`, `#menuSearch`, `a.nav-link[href="/dashboard"]`).
- A escala fica em `/schedules/personal` (o item de menu "Escala → Meus Voos" e o
  botão "Agendar Voo" do dashboard apontam para lá). URL direta funciona sem
  clicar menu — vai no `schedule_url` do `config.ini`.
- A aba "Agenda das Aeronaves" **não** pagina por dia no servidor: a página
  embute `var allSchedules = [...]` (na captura: 433 agendamentos, 2026-07-03 →
  2026-08-08) e re-filtra no cliente. Campos por item: `start_at`/`end_at`
  (UTC, ISO com Z), `start_at_raw`/`end_at_raw` (**hora local**,
  `YYYY-MM-DD HH:MM:SS`), `status` (`PENDING|CONFIRMED|PLANNED|CANCELED`),
  `aircraft {registration, icao}`, `student`, `instructor`, `notes`. O UI
  descarta `CANCELED`.
- Não há botão "próximo dia": há `input[type=date]#aircraftScheduleDate`
  (min=hoje, max=hoje+30d). Os eventos renderizados são divs sem classe —
  scraping DOM seria frágil e exigiria código novo do mesmo jeito.
- Sol: a página busca `GET /aisweb/sun/SBVT` (proxy do clube para o AISWEB) e
  exibe em **UTC** ("09:17Z"). O endpoint **ignora parâmetro de data** — só
  serve o dia atual. XML: `<aisweb><day><date>…</date><sunrise>09:17</sunrise>
  <sunset>20:15</sunset>…</day></aisweb>`.

## Decisões

1. **Fonte dos agendamentos: `driver.execute_script("return allSchedules")`.**
   Uma leitura cobre a janela inteira; dados estruturados com hora local pronta
   (`*_raw`); imune a mudanças de CSS/layout dos eventos. Continua read-only
   (ADR-0001): apenas lê uma variável que a própria página expõe.
2. **Sol dos dias futuros: valor de hoje (SAGA/AISWEB) aplicado à janela toda**,
   rotulado como aproximado no relatório. Desvio máximo ~7 min no dia 30 para
   SBVT. O dado continua vindo exclusivamente do SAGA (emenda mínima ao
   ADR-0008). Rejeitadas: cálculo local por efeméride (revoga o ADR) e o modo
   estrito (29 dias de ⚠️ inutilizam o relatório).

## Fluxo da varredura

1. `login()` (inalterado; marcador calibrado via config).
2. `driver.get(schedule_url)` — `https://aeroes.saga.aero/schedules/personal`.
3. Esperar a página e ler `allSchedules` via `execute_script`.
4. Buscar sol uma vez: `fetch('/aisweb/sun/SBVT')` na sessão autenticada
   (mesma fonte que a página usa); converter UTC→local com
   `zoneinfo("America/Sao_Paulo")` (stdlib, correto se DST voltar).
5. Construir `DaySchedule` de hoje até `min(max_days, dias cobertos pelos
   dados)` em **Python puro**: descartar `CANCELED`; casar
   `aircraft.registration` com `[aircraft]` do config (ADR-0007);
   `SLOT STAND-BY` mapeia para o recurso Stand By; usar `*_raw` como hora local.
   Dia sem eventos = dia livre (não é erro).
6. Pipeline inalterado daí em diante: `availability.py` → `report.py` →
   `discord.py` (ADR-0004 preservado).

## Impacto por módulo

| Módulo | Mudança |
|--------|---------|
| `scheduler.py` | Encolhe: adquirir JSON + sol, delegar construção a funções puras novas (testáveis sem browser). Some o loop next-day/`_advance_day`. Relogin (F2) preservado. |
| `aircraft.py` | Aposentado (parsing DOM não usado no caminho principal) — removido com seus testes. |
| `config.py` | `DEFAULT_SELECTORS`: saem chaves de escala não usadas; ficam login/sessão e o necessário p/ "página da escala carregou". |
| `login.py`, `browser.py`, `models.py`, `availability.py`, `report.py`, `discord.py` | Intactos. |
| `utils.py` | `extract_sunrise/extract_sunset` de texto de página saem se nada mais usar; parse do XML do sol entra como função pura. |
| `config.ini.example` | Atualizado: `schedule_url` preenchido de exemplo, seção `[selectors]` enxuta, comentário sobre marcador visível. |

## Tratamento de erros

- `allSchedules` ausente/malformado → falha fatal + screenshot/HTML em `debug/`
  (fluxo atual de artefatos mantido).
- Sol indisponível (endpoint falhou/`Indisponível`) → dias sem janela, ⚠️ no
  relatório (ADR-0008); varredura não aborta.
- `max_days` além da janela dos dados → trunca e anota no relatório.
- Sessão expirada durante a varredura → `is_login_page` + relogin (F2).

## Relatório

- Dias futuros: nota única de sol aproximado (valor oficial de hoje, fonte
  SAGA/AISWEB SBVT; desvio ≤ ~7 min no fim da janela).

## Documentação

- **ADR-0010** (novo): agendamentos lidos da variável JS `allSchedules`;
  registra a evidência acima e por que o DOM foi preterido.
- **ADR-0003** (emenda): seletores calibráveis restritos a login/sessão/
  presença da página; eventos não são mais raspados do DOM.
- **ADR-0008** (emenda): sol de hoje aplicado à janela, rotulado aproximado;
  endpoint só serve o dia atual.
- README: seções de uso/calibração/solução de problemas atualizadas.

## Testes

- Novas funções puras com `unittest`, sem browser (padrão do projeto):
  JSON→`DaySchedule` (filtros de status/matrícula, Stand By, dia vazio,
  janela/truncamento), parse do XML do sol, conversão UTC→local.
- Camada Selenium continua testada com fakes (execute_script/fetch fakeados).
- Testes do parsing DOM removidos junto com `aircraft.py`.
- Validação final: `python main.py --once` ponta a ponta com relatório
  conferido no Discord.

## Critérios de sucesso

1. `main.py --once` sai com código 0 e publica no Discord o relatório 🟢/🔴
   dos 30 dias para PP-AYB e PT-JTK (+ Stand By), sem ⚠️ espúrios.
2. Suíte `unittest` verde, sem abrir Chrome nem tocar o SAGA real.
3. ADRs/README refletem a arquitetura real.
