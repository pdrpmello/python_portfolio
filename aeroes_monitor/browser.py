"""Camada Selenium: driver Chrome, esperas tolerantes a múltiplos seletores
candidatos (ADR-0003) e artefatos de debug (PRD F10)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)


def create_driver(cfg) -> webdriver.Chrome:
    """Chrome via Selenium Manager (sem gerenciar chromedriver — ADR-0002)."""
    options = Options()
    if cfg.headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(cfg.page_load_timeout_seconds)
    return driver


def find_all_first_match(context, selectors: Iterable[str]) -> list:
    """Elementos do primeiro seletor candidato que retornar algo.

    `context` pode ser o driver ou um elemento (busca escopada em linha).
    """
    for selector in selectors:
        try:
            elements = context.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue
        if elements:
            return list(elements)
    return []


def read_text_from_selectors(context, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        try:
            elements = context.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue
        for element in elements:
            text = (element.text or "").strip()
            if text:
                return text
    return None


def element_exists(context, selectors: Iterable[str]) -> bool:
    return bool(find_all_first_match(context, selectors))


def wait_for_any_visible(driver, selectors: Iterable[str], timeout_seconds):
    selectors = list(selectors)

    def _first_visible(drv):
        for selector in selectors:
            try:
                for element in drv.find_elements(By.CSS_SELECTOR, selector):
                    if element.is_displayed():
                        return element
            except WebDriverException:
                continue
        return False

    try:
        return WebDriverWait(driver, timeout_seconds).until(_first_visible)
    except TimeoutException as exc:
        raise TimeoutException(
            f"Nenhum seletor visível em {timeout_seconds}s: {selectors}"
        ) from exc


def save_debug_artifacts(driver, debug_dir, tag: str = "failure") -> None:
    """Screenshot + HTML para recalibração manual de seletores (PRD §11).

    Melhor esforço: nunca propaga exceção (roda dentro de handlers de erro).
    """
    try:
        directory = Path(debug_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        driver.save_screenshot(str(directory / f"{stamp}-{tag}.png"))
        (directory / f"{stamp}-{tag}.html").write_text(
            driver.page_source, encoding="utf-8"
        )
        logger.info("Artefatos de debug salvos em %s (%s-%s.*)", directory, stamp, tag)
    except Exception:
        logger.exception("Falha ao salvar artefatos de debug")
