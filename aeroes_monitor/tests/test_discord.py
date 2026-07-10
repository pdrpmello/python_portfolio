"""Testes do notificador Discord (ADR-0006)."""
import unittest
from unittest import mock

import requests

from discord import DISCORD_MESSAGE_LIMIT, DiscordNotifier, split_message

WEBHOOK = "https://discord.com/api/webhooks/123/abc"


class SplitMessageTest(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(split_message("olá"), ["olá"])

    def test_exactly_limit_single_chunk(self):
        text = "a" * DISCORD_MESSAGE_LIMIT
        self.assertEqual(split_message(text), [text])

    def test_splits_on_line_boundaries(self):
        text = "\n".join(["linha-" + str(i) for i in range(10)])
        chunks = split_message(text, limit=30)
        self.assertTrue(all(len(c) <= 30 for c in chunks))
        self.assertEqual("\n".join(chunks), text)  # nada perdido

    def test_hard_split_for_giant_line(self):
        text = "x" * 45
        chunks = split_message(text, limit=20)
        self.assertEqual(chunks, ["x" * 20, "x" * 20, "x" * 5])

    def test_no_empty_chunks(self):
        text = "x" * 40  # múltiplo exato do limite
        chunks = split_message(text, limit=20)
        self.assertEqual(chunks, ["x" * 20, "x" * 20])
        self.assertTrue(all(chunks))

    def test_empty_text(self):
        self.assertEqual(split_message(""), [])


class DiscordNotifierTest(unittest.TestCase):
    def _response(self, status=204):
        response = mock.Mock()
        response.raise_for_status = mock.Mock()
        return response

    @mock.patch("discord.time.sleep")
    @mock.patch("discord.requests.post")
    def test_send_message_posts_chunks_in_order(self, post, _sleep):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        text = ("A" * 1500) + "\n" + ("B" * 1500)
        notifier.send_message(text)
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]["content"]
        second_payload = post.call_args_list[1].kwargs["json"]["content"]
        self.assertTrue(first_payload.startswith("A"))
        self.assertTrue(second_payload.startswith("B"))
        for call in post.call_args_list:
            self.assertEqual(call.args[0], WEBHOOK)
            self.assertEqual(call.kwargs["timeout"], 10)

    @mock.patch("discord.requests.post")
    def test_http_error_propagates(self, post):
        response = mock.Mock()
        response.raise_for_status.side_effect = requests.HTTPError("400")
        post.return_value = response
        notifier = DiscordNotifier(WEBHOOK)
        with self.assertRaises(requests.RequestException):
            notifier.send_message("oi")

    @mock.patch("discord.requests.post")
    def test_send_error_swallows_failure(self, post):
        post.side_effect = requests.ConnectionError("sem rede")
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_error("boom")  # não deve levantar

    @mock.patch("discord.requests.post")
    def test_send_error_prefixes_message(self, post):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_error("falha X")
        content = post.call_args.kwargs["json"]["content"]
        self.assertIn("🚨", content)
        self.assertIn("falha X", content)

    @mock.patch("discord.requests.post")
    def test_convenience_methods(self, post):
        post.return_value = self._response()
        notifier = DiscordNotifier(WEBHOOK)
        notifier.send_summary("resumo")
        notifier.send_report("relatório")
        contents = [c.kwargs["json"]["content"] for c in post.call_args_list]
        self.assertEqual(contents[0], "resumo")
        self.assertEqual(contents[1], "relatório")


if __name__ == "__main__":
    unittest.main()
