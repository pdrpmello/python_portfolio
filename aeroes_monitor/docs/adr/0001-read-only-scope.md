# ADR-0001: Aplicação estritamente read-only (sem automação de reservas)

## Status
Aceito

## Contexto
O SAGA é o sistema oficial do Aeroclube usado para gerenciar reservas reais de aeronaves. Qualquer automação que escreva nesse sistema (criar, alterar ou cancelar reservas) tem consequências operacionais e financeiras diretas — uma reserva indevida pode conflitar com outro piloto, gerar cobrança ou violar regras do clube.

## Decisão
O monitor **nunca** interage com formulários de escrita do SAGA. Ele apenas:
1. Autentica.
2. Navega até a página de escala.
3. Lê texto/HTML exibido.
4. Calcula disponibilidade localmente.
5. Reporta via Discord.

Nenhuma função do código submete reservas. Isso é reforçado na documentação (README) como garantia explícita ao usuário.

## Consequências
**Positivas**
- Elimina a classe de risco mais grave do projeto: reserva indevida ou perda de dados no sistema de origem.
- Permite rodar o monitor com confiança em loop contínuo e sem supervisão constante.
- Simplifica testes: não é necessário simular nem validar transações de escrita.

**Negativas / trade-offs**
- O usuário ainda precisa entrar manualmente no SAGA para de fato reservar um horário identificado como disponível.
- Nenhum "clique automático" quando surge uma vaga — a ação final permanece manual.

## Alternativas consideradas
- **Automação completa de reservas**: rejeitada para a versão atual. Documentada como possível módulo futuro, mas explicitamente opt-in e separado do monitor (ver seção "Próximos passos" do README), justamente para não misturar o núcleo read-only com uma superfície de risco maior.
