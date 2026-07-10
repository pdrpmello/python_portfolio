# Design: relatório e aberturas em tabela monoespaçada

**Data:** 2026-07-10 · **Status:** aprovado pelo usuário (conversa de 2026-07-10)

Substitui o formato de LISTA do corpo do relatório definido na spec
`2026-07-10-report-layout-design.md` §2 (cabeçalho de contagem, omissões,
caso zero-janelas e bloco de erros daquela spec continuam valendo).

## Objetivo

O usuário quer o layout das mensagens do Discord em **estilo tabela**, não
lista. O Discord não renderiza tabelas markdown em mensagens — colunas
alinhadas exigem bloco de código monoespaçado (```). Emojis dentro de
bloco perdem a renderização colorida, então 📅/✅/🔔 ficam FORA dos blocos.

## Decisões

### 1. Relatório: tabela por dia (`build_report`)

Formato aprovado (larguras ilustrativas):

````text
✅ **30 dias varridos — 43 janelas livres**

📅 **Qui 10/07/2026**
```
PP-AYB C152   07:30 - 09:30  2h
PT-JTK C172   06:30 - 09:30  3h
Stand By      06:00 - 12:00  6h
```
📅 **Sex 11/07/2026**
```
PP-AYB C152   06:30 - 09:30  3h
```
````

Regras:

- Cabeçalho `✅ **N dias varridos — M janelas livres**` + linha em branco
  antes do primeiro dia (inalterado); caso zero janelas continua a
  mensagem de uma linha `✅ **N dias varridos — nenhuma janela livre. 😕**`;
  bloco `⚠️ **Dias com erro de leitura:**` ao final inalterado (fora de
  qualquer cerca, precedido de linha em branco).
- Cabeçalho do dia `📅 **Qui 10/07/2026**` fora do bloco; a cerca ```
  abre na linha seguinte e fecha antes do próximo dia. SEM linha em
  branco entre o fechamento de um dia e o 📅 do próximo (o Discord já dá
  margem ao bloco).
- Uma linha por janela 🟢, SEM linha de cabeçalho de colunas:
  `<nome preenchido>  <início> - <fim>  <duração>` (gap de 2 espaços
  entre colunas; período com hífen espaçado como hoje; duração
  `_fmt_duration` existente: `2h`, `3h30`, `45min`).
- Célula de nome = `matrícula modelo` (`PP-AYB C152`); modelo vazio →
  só a matrícula (`Stand By`), sem espaço pendurado. Preenchida (à
  esquerda) até a largura da MAIOR célula de nome do relatório inteiro —
  alinhamento consistente entre todos os dias.
- Linhas ✈️ e 🟢 deixam de existir no corpo. Omissões inalteradas: dia
  sem janela livre não aparece; aeronave sem janela livre naquele dia
  não aparece; ocupados/vãos curtos nunca aparecem. Ordem inalterada
  (recursos na ordem do scanner; janelas por horário).

### 2. Aberturas: tabela única (`build_openings_message`)

Formato aprovado:

````text
🔔 **Abriu horário!**
```
Sáb 11/07  PP-AYB C152  06:30 - 09:30
Dom 12/07  Stand By     07:00 - 12:00
```
````

- Bloco único; colunas: dia curto `Sáb 11/07` (SEM ano), célula de nome
  como no relatório (preenchida até a maior do aviso), período. Sem
  coluna de duração (alerta enxuto).
- A `WindowKey` não carrega modelo ⇒ assinatura nova:
  `build_openings_message(new_windows, models)` com
  `models: Mapping[str, str]` (matrícula → modelo); recurso fora do
  mapa (ex.: Stand By) fica só com o nome. `main.py` passa
  `config.aircraft`.

### 3. `split_message` fence-aware (`discord.py`)

Com ~43 janelas o relatório passa de 2000 chars e fragmenta; o split
atual quebra por linhas sem saber de cercas — um corte dentro de um bloco
deixa a cerca aberta no fragmento 1 e órfã no 2 (markdown quebrado).

- Linha exatamente igual a ` ``` ` alterna o estado de cerca (o gerador
  só emite cercas nuas, sem linguagem).
- Ao fechar um fragmento com cerca aberta: anexa linha ` ``` ` de
  fechamento e o fragmento seguinte reabre com linha ` ``` `.
- O empacotamento reserva 4 chars (`\n` + ` ``` `) para o fechamento
  caber sempre no limite.
- Corte duro de linha única maior que o limite: comportamento atual
  (não ocorre com o gerador; docstring continua honesta a respeito).
- Nenhum fragmento sai com número ímpar de linhas-cerca.

### 4. Sem migração de estado

As `WindowKey` não mudam (a mudança é só apresentação): `state.json` v2
atual continua válido, sem re-baseline e sem falso "🔔 Abriu horário!"
no deploy.

## Fora de escopo

- Embeds do Discord (payload continua `{"content": ...}`).
- Regras de disponibilidade, política de diff, README (a linha do
  `report.py` na tabela de arquitetura continua correta).

## Testes (TDD)

- `test_report.py` (reescrever a parte de formato):
  - relatório: linha exata com padding global (`PP-AYB C152   06:00 - 07:00  1h`
    com largura ditada pela maior célula), nome sem modelo sem espaço
    extra, cerca abre/fecha por dia, sem linha em branco entre dias,
    ausência de ✈️/🟢/cabeçalho de colunas, omissões, zero janelas,
    bloco de erros fora de cerca;
  - aberturas: dia curto sem ano, modelo via `models`, recurso fora do
    mapa, alinhamento, bloco único.
- `test_discord.py`: bloco atravessando o limite → todo fragmento com
  número PAR de cercas, fragmento seguinte começa com ` ``` `, conteúdo
  íntegro (nenhuma linha perdida); mensagens sem cerca mantêm o
  comportamento atual (testes existentes seguem passando).
- `test_main.py`: chamada de aberturas passa `config.aircraft`
  (fixture tem `{"PT-ABC": "C-152"}` — mensagem contém `PT-ABC C-152`).
