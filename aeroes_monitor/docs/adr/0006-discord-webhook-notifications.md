# ADR-0006: Discord Webhook como único canal de notificação

## Status
Aceito

## Contexto
O resultado de cada varredura (início, resumo, relatório completo, erros) precisa chegar ao usuário sem que ele precise consultar logs ou rodar o programa interativamente.

## Decisão
Usar um webhook de Discord (`DiscordNotifier` em `discord.py`) como canal exclusivo de notificação, enviando mensagens via `requests.post`. Mensagens acima do limite de 2000 caracteres do Discord são fragmentadas por `split_message`, respeitando quebras de linha quando possível.

## Consequências
**Positivas**
- Webhook é trivial de configurar (uma URL), não exige bot, tokens OAuth ou infraestrutura de servidor.
- Discord já é usado pelo autor no dia a dia — notificação chega em tempo real no celular/desktop.
- `split_message` resolve de forma simples o limite de 2000 caracteres sem truncar conteúdo do relatório.

**Negativas / trade-offs**
- Acoplamento a um único canal: se o webhook for revogado ou o Discord ficar indisponível, não há fallback (e-mail, SMS, etc.).
- Falha ao enviar é apenas logada/relançada (`_post` propaga `RequestException`) — não há fila de retry persistente entre execuções.

## Alternativas consideradas
- **E-mail (SMTP)**: mais universal, porém exige gerenciar credenciais de envio e é menos imediato que uma notificação push do Discord. Não adotado.
- **Bot do Discord (vs. Webhook)**: um bot permitiria interações bidirecionais (ex.: comandos para forçar varredura), mas adiciona complexidade (gerenciamento de conexão, permissões) desnecessária para uma notificação unidirecional. Rejeitado por desproporcional ao escopo atual.
