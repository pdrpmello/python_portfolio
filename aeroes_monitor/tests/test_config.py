"""Testes da carga/validação de configuração (ADR-0005)."""
import tempfile
import unittest
from pathlib import Path

from config import (
    DEFAULT_SELECTORS,
    AppConfig,
    ConfigError,
    config_to_safe_dict,
    load_config,
)

VALID_INI = """
[credentials]
username = piloto@example.com
password = s3cr3t

[discord]
webhook_url = https://discord.com/api/webhooks/123/abc

[selenium]
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
        self.assertEqual(config.monitor.check_interval_seconds, 3600)
        self.assertEqual(config.monitor.turnaround_minutes, 30)
        self.assertEqual(config.monitor.min_flight_minutes, 60)
        self.assertEqual(config.monitor.max_flight_minutes, 120)
        self.assertTrue(config.selenium.headless)
        self.assertEqual(config.selenium.debug_dir, "debug")
        self.assertEqual(config.logging.level, "INFO")
        self.assertEqual(config.selectors, DEFAULT_SELECTORS)

    def test_aircraft_preserves_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, VALID_INI))
        self.assertEqual(
            config.aircraft, {"PT-ABC": "Cessna 152", "PT-XYZ": "Cessna 172"}
        )

    def test_selector_override_multiline(self):
        ini = VALID_INI + """
[selectors]
login_username =
    input[name="email"]
    #campo-email
"""
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_ini(tmp, ini))
        self.assertEqual(
            config.selectors["login_username"],
            ('input[name="email"]', "#campo-email"),
        )
        # Chaves não sobrescritas mantêm o default.
        self.assertEqual(
            config.selectors["login_password"], DEFAULT_SELECTORS["login_password"]
        )

    def test_missing_required_lists_all_errors(self):
        ini = """
[credentials]
username = x
"""
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as ctx:
                load_config(_write_ini(tmp, ini))
        message = str(ctx.exception)
        self.assertIn("credentials.password", message)
        self.assertIn("discord.webhook_url", message)
        self.assertIn("selenium.base_url", message)
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


if __name__ == "__main__":
    unittest.main()
