"""Testes do handler Lambda com boto3/run_scan falsos (sem AWS nem browser)."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from botocore.exceptions import ClientError

import handler

ENV = {
    "STATE_BUCKET": "bucket-teste",
    "STATE_KEY": "state.json",
    "DEBUG_PREFIX": "debug/",
    "CONFIG_FILE": "config.lambda.ini",
    "SSM_PREFIX": "/aeroes-monitor",
    "LOG_LEVEL": "INFO",
}


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetObject")


class FakeSSM:
    def __init__(self):
        self.calls = []

    def get_parameter(self, Name, WithDecryption=False):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": f"segredo:{Name.rsplit('/', 1)[1]}"}}


class FakeS3:
    def __init__(self, has_state=False):
        self.has_state = has_state
        self.uploads = []

    def download_file(self, bucket, key, dest):
        if not self.has_state:
            raise _client_error("404")
        Path(dest).write_text('{"version": 2}', encoding="utf-8")

    def upload_file(self, src, bucket, key):
        self.uploads.append((src, bucket, key))


class LambdaHandlerTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_path = Path(tmp.name) / "state.json"
        self.debug_dir = Path(tmp.name) / "debug"
        self.ssm = FakeSSM()
        self.s3 = FakeS3()
        self.config = mock.Mock()
        self.config.selenium.debug_dir = str(self.debug_dir)
        for patcher in (
            mock.patch.dict(os.environ, ENV),
            mock.patch.object(handler, "STATE_PATH", self.state_path),
            mock.patch.object(handler, "_ssm_client", self.ssm),
            mock.patch.object(handler, "_s3_client", self.s3),
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

    def test_baseline_flow_returns_ok_and_uploads_state(self):
        def scan(config, state_path):
            state_path.write_text('{"version": 2}', encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": True})
        self.run_scan.assert_called_once_with(self.config, self.state_path)
        self.assertEqual(
            self.s3.uploads, [(str(self.state_path), "bucket-teste", "state.json")]
        )

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
        # SecureString exige WithDecryption=True nas 3 leituras.
        self.assertEqual([dec for _, dec in self.ssm.calls], [True, True, True])

    def test_secrets_cached_across_warm_invocations(self):
        handler.lambda_handler({}, None)
        handler.lambda_handler({}, None)
        self.assertEqual(len(self.ssm.calls), 3)

    def test_missing_state_in_s3_removes_stale_local_copy(self):
        self.state_path.write_text("velho", encoding="utf-8")
        self.run_scan.return_value = False  # varredura falhou: nada gravado
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": False})
        self.assertFalse(self.state_path.exists())
        self.assertEqual(self.s3.uploads, [])

    def test_existing_state_available_to_scan(self):
        self.s3.has_state = True
        seen = {}

        def scan(config, state_path):
            seen["state"] = state_path.read_text(encoding="utf-8")
            return True

        self.run_scan.side_effect = scan
        handler.lambda_handler({}, None)
        self.assertEqual(seen["state"], '{"version": 2}')

    def test_failed_scan_uploads_and_clears_debug_artifacts(self):
        self.run_scan.return_value = False
        self.debug_dir.mkdir()
        (self.debug_dir / "a-fatal.png").write_bytes(b"PNG")
        result = handler.lambda_handler({}, None)
        self.assertEqual(result, {"ok": False})
        self.assertEqual(
            self.s3.uploads,
            [
                (
                    str(self.debug_dir / "a-fatal.png"),
                    "bucket-teste",
                    "debug/a-fatal.png",
                )
            ],
        )
        # Limpa o /tmp local: warm start não re-sobe artefato antigo.
        self.assertEqual(list(self.debug_dir.iterdir()), [])

    def test_ok_scan_does_not_touch_debug(self):
        self.debug_dir.mkdir()
        (self.debug_dir / "antigo.png").write_bytes(b"PNG")
        handler.lambda_handler({}, None)
        self.assertEqual(self.s3.uploads, [])
        self.assertTrue((self.debug_dir / "antigo.png").exists())

    def test_unexpected_s3_error_propagates_to_lambda_errors_metric(self):
        def boom(bucket, key, dest):
            raise _client_error("AccessDenied")

        self.s3.download_file = boom
        with self.assertRaises(ClientError):
            handler.lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
