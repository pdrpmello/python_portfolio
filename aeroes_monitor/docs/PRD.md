# PRD — Aeroclube Schedule Monitor

| | |
|---|---|
| **Status** | Em produção (uso pessoal) |
| **Autor** | Pedro Mello |
| **Última atualização** | 2026-07-09 |
| **Repositório** | `aeroes_monitor/` |

## 1. Resumo

O Aeroclube Schedule Monitor é uma aplicação Python **read-only** que monitora automaticamente a escala de horários de voo do sistema SAGA do Aeroclube do Espírito Santo e notifica, via Discord, quais horários estão livres para reserva. O programa não realiza reservas nem altera qualquer dado no sistema de origem — sua única função é ler, calcular e reportar.

## 2. Problema

Verificar manualmente a disponibilidade de horários de voo no SAGA é repetitivo e propenso a erro humano:

- A disponibilidade real depende de regras que não são explícitas na UI (janela por dia da semana, intervalo mínimo de turnaround entre voos, nascer/pôr do sol do dia).
- Um aluno/piloto precisa abrir o sistema, navegar dia a dia (até 30 dias), e cruzar mentalmente a agenda de cada aeronave com o Stand By para achar uma janela livre.
- Horários vagos podem surgir a qualquer momento (cancelamentos), e não há como saber sem checar o sistema repetidamente.

## 3. Objetivo

Eliminar a checagem manual: rodar uma varredura (uma vez ou em loop) que leia a escala, aplique as regras operacionais e envie um relatório legível para um canal do Discord, com o mínimo de intervenção humana e zero risco de alterar dados no SAGA.

## 4. Público-alvo

- Usuário único (o autor), piloto/aluno do Aeroclube do Espírito Santo com credenciais válidas no SAGA.
- Não é um produto multi-tenant; credenciais e webhook são de uso pessoal via `config.ini` local.

## 5. Escopo funcional

| # | Requisito | Descrição |
|---|-----------|-----------|
| F1 | Login automatizado | Autentica no SAGA via Selenium (Chrome + Selenium Manager), reaproveitando sessão quando válida. |
| F2 | Reautenticação | Detecta sessão expirada (retorno ao form de login) e reautentica automaticamente durante a varredura. |
| F3 | Varredura multi-dia | Percorre a escala a partir do dia atual exibido, avançando dia a dia até `max_days` (padrão 30). |
| F4 | Filtro de aeronaves operacionais | Considera apenas aeronaves de uma lista configurada manualmente (`[aircraft]` no `config.ini`), ignorando o status exibido pelo sistema. |
| F5 | Stand By como recurso independente | Lê a agenda de Stand By separadamente das aeronaves. |
| F6 | Nascer/pôr do sol | Usa exclusivamente os horários exibidos pela página do SAGA para o dia (nunca uma API externa de astronomia). |
| F7 | Cálculo de disponibilidade | Aplica janela permitida por dia da semana, buffer mínimo de turnaround entre voos, e duração mín/máx de voo configuráveis. |
| F8 | Relatório formatado | Gera texto com 🟢 disponível / 🔴 ocupado por aeronave e por dia. |
| F9 | Notificação Discord | Envia início de varredura, resumo, relatório completo (dividido se >2000 caracteres) e erros via Webhook. |
| F10 | Tratamento de erros | Erros recuperáveis por dia (ex.: falha ao ler um dia específico) não interrompem a varredura inteira; erros fatais disparam notificação de erro e salvam artefatos de debug (screenshot + HTML). |
| F11 | Execução única ou contínua | CLI com `--once` para uma varredura, ou loop contínuo com intervalo configurável (`check_interval_seconds`). |
| F12 | Logging | Log estruturado via módulo `logging`, nível e arquivo configuráveis. |

## 6. Regras de negócio (disponibilidade)

| Dia | Janela permitida |
|-----|-------------------|
| Segunda a sexta | Nascer do sol → até 09:30 |
| Sábado | Nascer do sol → pôr do sol |
| Domingo | Nascer do sol → 12:00 |

- Intervalo mínimo entre voos consecutivos da mesma aeronave: 30 minutos (configurável).
- Duração mínima/máxima de voo: configurável em `[monitor]`.
- Um período livre só é classificado como disponível (🟢) se sua duração ≥ duração mínima de voo; caso contrário é tratado como ocupado (🔴) no relatório, pois não é reservável.

## 7. Requisitos não funcionais

| Categoria | Requisito |
|-----------|-----------|
| Segurança | Credenciais e webhook nunca commitados (`config.ini` no `.gitignore`); log redigido (`config_to_safe_dict`) nunca expõe senha/webhook. |
| Confiabilidade | Falha em um dia específico não derruba a varredura inteira; falha fatal ainda encerra o browser (`finally: browser.quit()`) e notifica. |
| Observabilidade | Logging completo de cada etapa (login, navegação, parsing por dia, envio Discord); artefatos de debug (screenshot + HTML) salvos em `debug/` em falhas. |
| Manutenibilidade | Seletores CSS ficam em configuração, não em código, para acompanhar mudanças de layout do SAGA sem deploy. |
| Portabilidade | Requer apenas Python 3.13+, Google Chrome e Selenium Manager (sem infraestrutura extra). |
| Testabilidade | Regras de negócio (`availability.py`) e formatação (`report.py`) são testáveis sem browser real. |

## 8. Fora de escopo (não-objetivos)

- Realizar reservas ou qualquer escrita no SAGA.
- Suporte multi-usuário / multi-tenant.
- Interface gráfica ou dashboard.
- Notificação em tempo real orientada a evento (hoje é polling por intervalo).
- Fonte alternativa de nascer/pôr do sol (API externa de astronomia).

## 9. Configuração e deployment

- Configuração única em `config.ini` (a partir de `config.ini.example`): credenciais, webhook, aeronaves operacionais, seletores CSS, parâmetros de monitoramento e Selenium.
- Execução local (`python main.py` ou `python main.py --once`), sem dependência de infraestrutura de nuvem.
- Nenhum banco de dados; estado é efêmero por varredura (sem histórico persistido entre execuções).

## 10. Métricas de sucesso

- Notificação chega ao Discord em toda varredura (sucesso ou erro) — sem "silêncio" indicando falha silenciosa.
- Zero incidentes de escrita indevida no SAGA (é a invariante mais crítica do produto).
- Tempo de varredura completo (30 dias) dentro de um intervalo aceitável para rodar em loop horário (`check_interval_seconds` padrão 3600s).

## 11. Riscos e premissas

| Risco | Mitigação atual |
|-------|-----------------|
| SAGA muda o layout HTML/CSS | Seletores externalizados em `config.ini`; artefatos de debug salvos em falha para recalibração manual. |
| Sessão expira durante varredura longa | `_ensure_session()` reautentica automaticamente entre dias. |
| Credenciais vazarem via commit acidental | `config.ini` no `.gitignore`; apenas `config.ini.example` versionado. |
| Mensagem de relatório excede limite do Discord (2000 chars) | `split_message()` fragmenta em múltiplos envios. |
| Nascer/pôr do sol ausente na página | Varredura do dia falha com erro recuperável e é reportada, não interrompe os demais dias. |

## 12. Roadmap sugerido (não compromissado)

- Calibrar seletores CSS com a escala real após primeiro login em produção.
- Notificação incremental (somente diffs) em vez de relatório completo a cada ciclo.
- Interface gráfica ou dashboard.
- Módulo de automação de reservas, explicitamente opt-in e desacoplado do monitor read-only.
