"""Login no SAGA e detecção de sessão expirada (PRD F1, F2).

Read-only exceto pelo formulário de LOGIN, único formulário que este
projeto submete (ADR-0001).
"""
from __future__ import annotations

import logging

from selenium.common.exceptions import TimeoutException

from browser import element_exists, wait_for_any_visible

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """Falha de autenticação no SAGA."""


def is_login_page(driver, selectors) -> bool:
    return element_exists(driver, selectors["login_form"])


def is_logged_in(driver, selectors) -> bool:
    return element_exists(driver, selectors["logged_in_marker"])


def login(driver, config) -> None:
    selectors = config.selectors
    timeout = config.selenium.element_timeout_seconds
    driver.get(config.selenium.base_url)
    if is_logged_in(driver, selectors) and not is_login_page(driver, selectors):
        logger.info("Sessão existente reaproveitada")
        return
    username_field = wait_for_any_visible(driver, selectors["login_username"], timeout)
    username_field.clear()
    username_field.send_keys(config.credentials.username)
    password_field = wait_for_any_visible(driver, selectors["login_password"], timeout)
    password_field.clear()
    password_field.send_keys(config.credentials.password)
    wait_for_any_visible(driver, selectors["login_submit"], timeout).click()
    try:
        wait_for_any_visible(driver, selectors["logged_in_marker"], timeout)
    except TimeoutException as exc:
        raise LoginError(
            "Login não confirmado: marcador de sessão não apareceu "
            "(verifique credenciais e o seletor logged_in_marker)"
        ) from exc
    logger.info("Login efetuado com sucesso")
