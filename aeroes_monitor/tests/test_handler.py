"""Testes do handler Lambda com boto3/run_scan falsos (sem AWS nem browser)."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from botocore.exceptions import ClientError

import handler

ENV = {
    "STATE_TABLE": "aeroes-monitor-state",
    "CONFIG_FILE": "config.lambda.ini",
    "SSM_PREFIX": "/aeroes-monitor",
    "LOG_LEVEL": "INFO",
}


class FakeSSM:
    def __init__(self):
        self.calls = []

    def get_parameter(self, Name, WithDecryption=False):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": f"segredo:{Name.rsplit('/', 1)[1]}"}}


class FakeDDB:
    def __init__(self, item=None):
        self.item = item
        self.puts = []

    def get_item(self, TableName, Key, ConsistentRead=False):
        return {"Item": self.item} if self.item is not None else {}

    def put_item(self, TableName, Item):
        self.puts.append(Item)
        self.item = Item


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = Path(tmp.name) / "state.json"
        self.ssm = FakeSSM()
        self.ddb = FakeDDB()
        self.config = mock.Mock()
        for patcher in (
            mock.patch.dict(os.environ, ENV),
            mock.patch.object(handler, "STATE_PATH", self.state_path),
            mock.patch.object(handler, "_ssm_client", self.ssm),
            mock.patch.object(handler, "_ddb_client", self.ddb),
            mock.patch.object(handler, "_secrets_cache", None),
            mock.patch.object(handler, "setup_logging"),
        ):
            patcher.start()
        self.load_config = mock.patch.object(
            handler, "load_config", return_value=self.config
        ).start()
        self.run_scan = mock.patch.object(
            handler, "run_scan", return_value=True
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_baseline_writes_state_to_ddb(self):
        def scan(config, state_path):
            state_path.write_text('{"version": 2}', encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": True})
        self.run_scan.assert_called_once_with(self.config, self.state_path)
        self.assertEqual(len(self.ddb.puts), 1)
        self.assertEqual(self.ddb.puts[0]["id"]["S"], "state")
        self.assertEqual(self.ddb.puts[0]["payload"]["S"], '{"version": 2}')

    def test_overrides_carry_ssm_secrets_and_log_level(self):
        handler.lambda_handler({}, None)
        overrides = self.load_config.call_args.kwargs["overrides"]
        self.assertEqual(
            overrides[("credentials", "username")], "segredo:saga-username"
        )
        self.assertEqual(
            overrides[("credentials", "password")], "segredo:saga-password"
        )
        self.assertEqual(
            overrides[("discord", "webhook_url")], "segredo:discord-webhook-url"
        )
        self.assertEqual(overrides[("logging", "level")], "INFO")
        self.assertEqual([dec for _, dec in self.ssm.calls], [True, True, True])

    def test_secrets_cached_across_warm_invocations(self):
        handler.lambda_handler({}, None)
        handler.lambda_handler({}, None)
        self.assertEqual(len(self.ssm.calls), 3)

    def test_existing_item_available_to_scan(self):
        self.ddb.item = {"id": {"S": "state"}, "payload": {"S": '{"version": 2}'}}
        seen = {}

        def scan(config, state_path):
            seen["state"] = state_path.read_text(encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        handler.lambda_handler({}, None)
        self.assertEqual(seen["state"], '{"version": 2}')

    def test_missing_item_removes_stale_local_copy(self):
        self.state_path.write_text("velho", encoding="utf-8")
        self.run_scan.return_value = False  # varredura falhou: nada gravado
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": False})
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.ddb.puts, [])

    def test_unexpected_ddb_error_propagates_to_errors_metric(self):
        def boom(TableName, Key, ConsistentRead=False):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "x"}}, "GetItem"
            )

        self.ddb.get_item = boom
        with self.assertRaises(ClientError):
            handler.lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
