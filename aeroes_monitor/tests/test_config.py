"""Testes da carga/validação de configuração (ADR-0005)."""
import tempfile
import unittest
from pathlib import Path

from config import AppConfig, ConfigError, config_to_safe_dict, load_config

VALID_INI = """
[credentials]
username = piloto@example.com
password = s3cr3t

[discord]
webhook_url = https://discord.com/api/webhooks/123/abc

[saga]
base_url = https://saga.example.com/login

[aircraft]
PT-ABC = Cessna 152
PT-XYZ = Cessna 172
"""


def _write_ini(directory: str, content: str) -> Path:
    path = Path(directory) / "config.ini"
    path.write_text(content, encoding="utf-8")
    return path


class LoadConfigTest(unittest.TestCase):
    def test_minimal_valid_config_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.credentials.username, "piloto@example.com")
        self.assertEqual(config.monitor.max_days, 30)
        self.assertEqual(config.saga.base_url, "https://saga.example.com/login")
        self.assertEqual(config.saga.schedule_url, "")
        self.assertEqual(config.saga.request_timeout_seconds, 30)
        self.assertEqual(config.saga.debug_dir, "debug")
        self.assertEqual(config.logging.level, "INFO")

    def test_aircraft_preserves_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertEqual(
            config.aircraft, {"PT-ABC": "Cessna 152", "PT-XYZ": "Cessna 172"}
        )

    def test_saga_fields_parsed(self):
        ini = """
[credentials]
username = piloto@example.com
password = s3cr3t

[discord]
webhook_url = https://discord.com/api/webhooks/123/abc

[saga]
base_url = https://saga.example.com/login
schedule_url = https://saga.example.com/schedules/personal
request_timeout_seconds = 45
debug_dir = /tmp/debug

[aircraft]
PT-ABC = Cessna 152
"""
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, ini))
        self.assertEqual(
            config.saga.schedule_url, "https://saga.example.com/schedules/personal"
        )
        self.assertEqual(config.saga.request_timeout_seconds, 45)
        self.assertEqual(config.saga.debug_dir, "/tmp/debug")

    def test_overrides_fill_missing_sections_and_win_over_file(self):
        ini = """
[saga]
base_url = https://saga.example.com/login

[aircraft]
PT-ABC = C152

[monitor]
max_days = 10
"""
        overrides = {
            ("credentials", "username"): "piloto@example.com",
            ("credentials", "password"): "s3cr3t",
            ("discord", "webhook_url"): "https://discord.com/api/webhooks/1/a",
            ("monitor", "max_days"): "5",
        }
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, ini), overrides=overrides)
        self.assertEqual(config.credentials.username, "piloto@example.com")
        self.assertEqual(
            config.discord.webhook_url, "https://discord.com/api/webhooks/1/a"
        )
        self.assertEqual(config.monitor.max_days, 5)

    def test_no_overrides_keeps_current_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI), overrides=None)
        self.assertEqual(config.credentials.username, "piloto@example.com")

    def test_missing_required_lists_all_errors(self):
        ini = """
[credentials]
username = so-usuario
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        message = str(ctx.exception)
        self.assertIn("credentials.password", message)
        self.assertIn("discord.webhook_url", message)
        self.assertIn("saga.base_url", message)
        self.assertIn("aircraft", message)

    def test_numeric_validations(self):
        ini = VALID_INI + """
[monitor]
max_days = 0
min_flight_minutes = 120
max_flight_minutes = 60
check_interval_seconds = 5
turnaround_minutes = -1
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        message = str(ctx.exception)
        self.assertIn("max_days", message)
        self.assertIn("min_flight_minutes", message)
        self.assertIn("check_interval_seconds", message)
        self.assertIn("turnaround_minutes", message)

    def test_invalid_int_reported(self):
        ini = VALID_INI + """
[monitor]
max_days = trinta
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        self.assertIn("max_days", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config(r"C:\caminho\que\nao\existe\config.ini")
        self.assertIn("config.ini.example", str(ctx.exception))


class SafeDictTest(unittest.TestCase):
    def test_secrets_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        safe = config_to_safe_dict(config)
        self.assertEqual(safe["credentials"]["password"], "***")
        self.assertEqual(safe["discord"]["webhook_url"], "***")
        self.assertEqual(safe["credentials"]["username"], "piloto@example.com")
        self.assertNotIn("s3cr3t", str(safe))
        self.assertNotIn("webhooks/123", str(safe))


class LambdaIniTest(unittest.TestCase):
    """config.lambda.ini é COMMITADO: nunca pode conter segredos."""

    PATH = Path(__file__).resolve().parent.parent / "src" / "config.lambda.ini"

    def test_has_no_secret_sections(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertNotIn("[credentials]", text)
        self.assertNotIn("[discord]", text)

    def test_validates_with_runtime_overrides(self):
        config = load_config(
            self.PATH,
            overrides={
                ("credentials", "username"): "piloto@example.com",
                ("credentials", "password"): "s3cr3t",
                ("discord", "webhook_url"): "https://discord.com/api/webhooks/1/a",
            },
        )
        self.assertEqual(config.saga.base_url, "https://aeroes.saga.aero/login")
        self.assertEqual(config.saga.request_timeout_seconds, 30)
        self.assertEqual(config.saga.debug_dir, "/tmp/debug")
        self.assertIn("PP-AYB", config.aircraft)


if __name__ == "__main__":
    unittest.main()
