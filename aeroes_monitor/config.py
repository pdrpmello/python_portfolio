"""Carrega e valida config.ini → dataclasses frozen (ADR-0005).

Seletores CSS ficam em [selectors] com defaults embutidos (ADR-0003):
um seletor por linha (vírgula é sintaxe CSS válida, não separador).
Hoje cobrem só login/sessão — a leitura da agenda usa a variável
allSchedules exposta pela página, não mais scraping de DOM (ADR-0010).
"""
from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Configuração ausente ou inválida."""


DEFAULT_SELECTORS: dict[str, tuple[str, ...]] = {
    "login_username": (
        'input[name="email"]',
        'input[type="email"]',
        'input[name="username"]',
        "#email",
    ),
    "login_password": ('input[name="password"]', 'input[type="password"]', "#password"),
    "login_submit": ('button[type="submit"]', 'input[type="submit"]', ".btn-login"),
    "login_form": ("form.login", "form#login", 'input[type="password"]'),
    # Precisa estar VISÍVEL pós-login (o a[href*="logout"] fica oculto no
    # dropdown do perfil do SAGA) — calibrado em 2026-07-09.
    "logged_in_marker": (
        "#navbarDropdownProfile",
        "#menuSearch",
        'a.nav-link[href="/dashboard"]',
        ".user-menu",
    ),
}


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
class SeleniumConfig:
    base_url: str
    schedule_url: str = ""
    headless: bool = True
    page_load_timeout_seconds: int = 30
    element_timeout_seconds: int = 15
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
    selenium: SeleniumConfig
    selectors: dict[str, tuple[str, ...]]
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


def _load_selectors(parser: configparser.ConfigParser) -> dict[str, tuple[str, ...]]:
    selectors = dict(DEFAULT_SELECTORS)
    if parser.has_section("selectors"):
        for key, raw in parser.items("selectors"):
            candidates = tuple(
                line.strip() for line in raw.splitlines() if line.strip()
            )
            if candidates:
                selectors[key] = candidates
    return selectors


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


def load_config(path: str | Path) -> AppConfig:
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
    selenium = SeleniumConfig(
        base_url=_require(parser, "selenium", "base_url", errors),
        schedule_url=parser.get("selenium", "schedule_url", fallback="").strip(),
        headless=_get_bool(parser, "selenium", "headless", True, errors),
        page_load_timeout_seconds=_get_int(
            parser, "selenium", "page_load_timeout_seconds", 30, errors
        ),
        element_timeout_seconds=_get_int(
            parser, "selenium", "element_timeout_seconds", 15, errors
        ),
        debug_dir=parser.get("selenium", "debug_dir", fallback="debug").strip()
        or "debug",
    )
    logging_config = LoggingConfig(
        level=parser.get("logging", "level", fallback="INFO").strip() or "INFO",
        file=parser.get("logging", "file", fallback="").strip(),
    )
    selectors = _load_selectors(parser)
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
        selenium=selenium,
        selectors=selectors,
        aircraft=aircraft,
        logging=logging_config,
    )


def config_to_safe_dict(config: AppConfig) -> dict[str, Any]:
    """Versão logável da config: segredos redigidos (PRD §7)."""
    data = asdict(config)
    data["credentials"]["password"] = "***"
    data["discord"]["webhook_url"] = "***"
    return data
