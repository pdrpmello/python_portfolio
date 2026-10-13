"""Carrega e valida config.ini → dataclasses frozen (ADR-0005).

A aquisição da escala é por HTTP direto (ADR-0011): a seção [saga] traz a
URL de login, a da escala e o timeout. Sem seletores CSS (o antigo
[selectors] saiu com o Selenium). No Lambda, segredos entram como
`overrides` de load_config (SSM → memória), nunca por arquivo.
"""
from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Configuração ausente ou inválida."""


@dataclass(frozen=True)
class CredentialsConfig:
    username: str
    password: str


@dataclass(frozen=True)
class DiscordConfig:
    webhook_url: str


@dataclass(frozen=True)
class MonitorConfig:
    max_days: int = 30
    check_interval_seconds: int = 3600
    turnaround_minutes: int = 30
    min_flight_minutes: int = 60
    max_flight_minutes: int = 120


@dataclass(frozen=True)
class SagaConfig:
    base_url: str
    schedule_url: str = ""
    request_timeout_seconds: int = 30
    debug_dir: str = "debug"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    file: str = ""


@dataclass(frozen=True)
class AppConfig:
    credentials: CredentialsConfig
    discord: DiscordConfig
    monitor: MonitorConfig
    saga: SagaConfig
    aircraft: dict[str, str]
    logging: LoggingConfig


def _require(
    parser: configparser.ConfigParser, section: str, key: str, errors: list[str]
) -> str:
    value = parser.get(section, key, fallback="").strip()
    if not value:
        errors.append(f"{section}.{key} é obrigatório")
    return value


def _get_int(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: int,
    errors: list[str],
) -> int:
    raw = parser.get(section, key, fallback=str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        errors.append(f"{section}.{key} deve ser um inteiro (recebido: {raw!r})")
        return default


def _get_bool(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: bool,
    errors: list[str],
) -> bool:
    try:
        return parser.getboolean(section, key, fallback=default)
    except ValueError:
        errors.append(f"{section}.{key} deve ser booleano (true/false)")
        return default


def _load_aircraft(
    parser: configparser.ConfigParser, errors: list[str]
) -> dict[str, str]:
    if not parser.has_section("aircraft"):
        errors.append("seção [aircraft] é obrigatória, com ao menos uma aeronave")
        return {}
    aircraft = {
        registration.strip(): model.strip()
        for registration, model in parser.items("aircraft")
        if registration.strip()
    }
    if not aircraft:
        errors.append("seção [aircraft] precisa de ao menos uma aeronave (MATRÍCULA = modelo)")
    return aircraft


def load_config(
    path: str | Path, overrides: dict[tuple[str, str], str] | None = None
) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"Arquivo de configuração não encontrado: {path}. "
            "Copie config.ini.example para config.ini e preencha."
        )
    # comment_prefixes só com ';': o default inclui '#', que engoliria
    # linhas de continuação com seletores CSS de id (ex.: "#email").
    parser = configparser.ConfigParser(interpolation=None, comment_prefixes=(";",))
    parser.optionxform = str  # preserva maiúsculas nas matrículas de [aircraft]
    parser.read(path, encoding="utf-8")

    # Overrides {(seção, chave): valor} aplicados antes da validação — é por
    # aqui que o handler Lambda injeta segredos do SSM sem tocar disco.
    for (section, key), value in (overrides or {}).items():
        if not parser.has_section(section):
            parser.add_section(section)
        parser.set(section, key, value)

    errors: list[str] = []
    credentials = CredentialsConfig(
        username=_require(parser, "credentials", "username", errors),
        password=_require(parser, "credentials", "password", errors),
    )
    discord = DiscordConfig(
        webhook_url=_require(parser, "discord", "webhook_url", errors)
    )
    monitor = MonitorConfig(
        max_days=_get_int(parser, "monitor", "max_days", 30, errors),
        check_interval_seconds=_get_int(
            parser, "monitor", "check_interval_seconds", 3600, errors
        ),
        turnaround_minutes=_get_int(
            parser, "monitor", "turnaround_minutes", 30, errors
        ),
        min_flight_minutes=_get_int(
            parser, "monitor", "min_flight_minutes", 60, errors
        ),
        max_flight_minutes=_get_int(
            parser, "monitor", "max_flight_minutes", 120, errors
        ),
    )
    saga = SagaConfig(
        base_url=_require(parser, "saga", "base_url", errors),
        schedule_url=parser.get("saga", "schedule_url", fallback="").strip(),
        request_timeout_seconds=_get_int(
            parser, "saga", "request_timeout_seconds", 30, errors
        ),
        debug_dir=parser.get("saga", "debug_dir", fallback="debug").strip()
        or "debug",
    )
    logging_config = LoggingConfig(
        level=parser.get("logging", "level", fallback="INFO").strip() or "INFO",
        file=parser.get("logging", "file", fallback="").strip(),
    )
    aircraft = _load_aircraft(parser, errors)

    if monitor.max_days < 1:
        errors.append("monitor.max_days deve ser >= 1")
    if monitor.check_interval_seconds < 60:
        errors.append("monitor.check_interval_seconds deve ser >= 60")
    if monitor.turnaround_minutes < 0:
        errors.append("monitor.turnaround_minutes deve ser >= 0")
    if monitor.min_flight_minutes > monitor.max_flight_minutes:
        errors.append(
            "monitor.min_flight_minutes deve ser <= monitor.max_flight_minutes"
        )

    if errors:
        raise ConfigError("Configuração inválida:\n- " + "\n- ".join(errors))

    return AppConfig(
        credentials=credentials,
        discord=discord,
        monitor=monitor,
        saga=saga,
        aircraft=aircraft,
        logging=logging_config,
    )


def config_to_safe_dict(config: AppConfig) -> dict[str, Any]:
    """Versão logável da config: segredos redigidos (PRD §7)."""
    data = asdict(config)
    data["credentials"]["password"] = "***"
    data["discord"]["webhook_url"] = "***"
    return data
