"""Notificações via Discord Webhook (ADR-0006).

Mensagens acima de 2000 caracteres são fragmentadas por split_message.
Falhas de envio propagam RequestException — exceto em send_error, que é
o último recurso e não pode mascarar o erro original.
"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000
_CHUNK_PAUSE_SECONDS = 0.5
_FENCE = "```"
# Reserva para o fechamento "\n```" caber quando o corte cai dentro de um bloco.
_FENCE_RESERVE = len("\n" + _FENCE)


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Fragmenta preservando quebras de linha e cercas ``` balanceadas:
    corte dentro de um bloco fecha a cerca no fragmento e a reabre no
    seguinte (linha exatamente ``` alterna o estado; o gerador só emite
    cercas nuas). Corte duro só quando uma única linha excede o limite
    (não ocorre com o gerador; aí as cercas ficam por conta do chamador).
    Nunca produz chunk vazio."""
    if not text:
        return []
    chunks: list[str] = []
    current = ""
    in_fence = False
    for line in text.split("\n"):
        line_in_fence = in_fence != (line == _FENCE)  # estado APÓS esta linha
        reserve = _FENCE_RESERVE if line_in_fence else 0
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit - reserve:
            if current:
                chunks.append(f"{current}\n{_FENCE}" if in_fence else current)
                current = _FENCE if in_fence else ""
                candidate = f"{current}\n{line}" if current else line
            while len(candidate) > limit - reserve:
                chunks.append(candidate[:limit])
                candidate = candidate[limit:]
        current = candidate
        in_fence = line_in_fence
    if current:
        chunks.append(current)
    return chunks


class DiscordNotifier:
    def __init__(self, webhook_url: str, timeout_seconds: int = 10) -> None:
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds

    def _post(self, content: str) -> None:
        response = requests.post(
            self.webhook_url, json={"content": content}, timeout=self.timeout_seconds
        )
        response.raise_for_status()

    def send_message(self, content: str) -> None:
        chunks = split_message(content)
        for index, chunk in enumerate(chunks):
            self._post(chunk)
            if index < len(chunks) - 1:
                time.sleep(_CHUNK_PAUSE_SECONDS)  # rate limit do webhook
        logger.info("Mensagem enviada ao Discord (%d fragmento(s))", len(chunks))

    def send_report(self, text: str) -> None:
        self.send_message(text)

    def send_error(self, message: str) -> None:
        try:
            self.send_message(f"🚨 **Erro na varredura:** {message}")
        except requests.RequestException:
            logger.exception("Falha ao enviar notificação de erro ao Discord")
