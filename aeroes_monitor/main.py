"""Ponto de entrada do Aeroclube Schedule Monitor (PRD F11, F12).

Uso:
    python main.py --once     # uma varredura e sai (0 ok, 1 falha, 2 config)
    python main.py            # loop contínuo (ADR-0009), Ctrl+C encerra
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from availability import AvailabilityRules, enrich_day_schedule
from browser import create_driver, save_debug_artifacts
from config import AppConfig, ConfigError, config_to_safe_dict, load_config
from discord import DiscordNotifier
from login import login
from notifications import (
    NotifyState,
    diff_new_windows,
    extract_open_windows,
    extract_scanned_days,
    load_state,
    save_state,
)
from report import build_openings_message, build_report
from scheduler import ScheduleScanner

logger = logging.getLogger("aeroes_monitor")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor read-only da escala de voo do SAGA (Aeroclube-ES)"
    )
    parser.add_argument(
        "--once", action="store_true", help="executa uma única varredura e sai"
    )
    parser.add_argument(
        "--config", default="config.ini", help="caminho do config.ini (default: ./config.ini)"
    )
    return parser.parse_args(argv)


def setup_logging(cfg) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if cfg.file:
        handlers.append(logging.FileHandler(cfg.file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, cfg.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _quit_quietly(driver) -> None:
    try:
        driver.quit()
    except Exception:
        logger.warning("Falha ao encerrar o browser", exc_info=True)


def _notify_failure(notifier, previous, message: str) -> None:
    """Erro só na transição ok→falha (spec: sem spam de falha repetida)."""
    if previous is None or previous.last_scan_ok:
        notifier.send_error(message)
    else:
        logger.info("Falha repetida; Discord não notificado")


def _save_failure_state(state_path, previous) -> None:
    """Preserva janelas conhecidas; sem state prévio, baseline fica pendente."""
    if previous is not None:
        save_state(
            state_path,
            NotifyState(
                windows=previous.windows, days=previous.days, last_scan_ok=False
            ),
        )


def run_scan(config: AppConfig, state_path: Path) -> bool:
    """Uma varredura completa. Nunca propaga exceção (o loop sobrevive)."""
    notifier = DiscordNotifier(config.discord.webhook_url)
    previous = load_state(state_path)
    driver = None
    try:
        driver = create_driver(config.selenium)
        login(driver, config)
        result = ScheduleScanner(driver, config).scan()
        if not result.days and result.errors:
            message = "; ".join(e.message for e in result.errors)
            logger.error("Varredura degradada: %s", message)
            _notify_failure(notifier, previous, message)
            _save_failure_state(state_path, previous)
            return False
        rules = AvailabilityRules(
            turnaround_minutes=config.monitor.turnaround_minutes,
            min_flight_minutes=config.monitor.min_flight_minutes,
            max_flight_minutes=config.monitor.max_flight_minutes,
        )
        availabilities = [enrich_day_schedule(day, rules) for day in result.days]
        windows = extract_open_windows(availabilities)
        if previous is None:
            notifier.send_report(build_report(availabilities, result.errors))
        else:
            if not previous.last_scan_ok:
                notifier.send_message("✅ Varredura voltou a funcionar.")
            new_windows = diff_new_windows(previous, windows)
            if new_windows:
                notifier.send_message(
                    build_openings_message(new_windows, config.aircraft)
                )
        save_state(
            state_path,
            NotifyState(
                windows=windows,
                days=extract_scanned_days(availabilities),
                last_scan_ok=True,
            ),
        )
        logger.info(
            "Varredura concluída: %d dia(s), %d erro(s), %d janela(s) 🟢",
            len(result.days),
            len(result.errors),
            len(windows),
        )
        return True
    except Exception as exc:
        logger.exception("Falha fatal na varredura")
        if driver is not None:
            save_debug_artifacts(driver, config.selenium.debug_dir, tag="fatal")
        _notify_failure(notifier, previous, str(exc))
        _save_failure_state(state_path, previous)
        return False
    finally:
        if driver is not None:
            _quit_quietly(driver)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Erro de configuração: {exc}", file=sys.stderr)
        return 2
    setup_logging(config.logging)
    logger.info("Configuração carregada: %s", config_to_safe_dict(config))
    state_path = Path(args.config).resolve().parent / "state.json"
    if args.once:
        return 0 if run_scan(config, state_path) else 1
    logger.info(
        "Modo contínuo: varredura a cada %d s (Ctrl+C para encerrar)",
        config.monitor.check_interval_seconds,
    )
    try:
        while True:
            run_scan(config, state_path)
            logger.info(
                "Próxima varredura em %d s", config.monitor.check_interval_seconds
            )
            time.sleep(config.monitor.check_interval_seconds)
    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuário")
        return 0


if __name__ == "__main__":
    sys.exit(main())
