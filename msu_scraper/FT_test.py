"""Teste isolado de scraping de FT."""

import time
import random
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    CHROME_PROFILE_DIR,
    CHROME_USER_DATA_DIR,
    MARKETPLACE_FT_BASE,
    FT_ITEMS,
    FT_NAMES,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

FT_PRICE_XPATH = "//div[contains(@class,'BidBottom_bidLowestPricePercent')]"


def _build_options():
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")
    options.add_argument(f"--profile-directory={CHROME_PROFILE_DIR}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return options


def _driver() -> WebDriver:
    options = _build_options()
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)
    return driver


def search_ft_url(name: str) -> str:
    item_id = FT_ITEMS[name]
    encoded = name.replace(" ", "+")
    return f"{MARKETPLACE_FT_BASE}{item_id}?keyword={encoded}"


def main():
    driver = _driver()
    try:
        for name in FT_NAMES:
            url = search_ft_url(name)
            log.info("Abrindo URL: %s", url)
            driver.get(url)
            time.sleep(5)

            wait = WebDriverWait(driver, 30)
            price_div = wait.until(
                EC.presence_of_element_located((By.XPATH, FT_PRICE_XPATH))
            )

            raw = price_div.text
            log.info("Texto bruto: %r", raw)

            price = raw.replace("\n", "").replace(",", ".").strip()
            log.info("💰 %s: %s", name, price)

    except Exception as e:
        log.error("Erro: %s", type(e).__name__, exc_info=True)
        # salva screenshot para inspecionar
        driver.save_screenshot("debug_ft.png")
        log.info("Screenshot salvo em debug_ft.png")
    finally:
        input("\nPressione ENTER para fechar...")
        driver.quit()


if __name__ == "__main__":
    main()