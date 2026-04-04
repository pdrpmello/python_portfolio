"""Automação de conexão MetaMask e coleta de preços no marketplace NFT."""

import os
import time
import random
import logging
import gspread
from datetime import date
from typing import List

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys

from config import (
    CHROME_PROFILE_DIR,
    CHROME_USER_DATA_DIR,
    MAPLESTORY_BASE,
    MARKETPLACE_NFT_BASE,
    METAMASK_EXTENSION_URL,
    METAMASK_PASSWORD,
    SPREADSHEET_ID,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

NFT_NAMES: List[str] = [
    "Neophyte Ring",
    "Shooting Star",
]

DEFAULT_TIMEOUT = 30

# ================= XPATHS =================
METAMASK_INITIAL_CONNECTION = "//button[contains(@class,'ConnectBtn_connect-btn__kCpIh')]"
METAMASK_SIGN_IN_XPATH = "//button[contains(@class,'w3a--btn') and contains(@class,'w3a--rounded-full') and .//*[normalize-space()='MetaMask']]"
METAMASK_SIGN_IN_IFRAME = "//div[contains(@class,'w3a--relative w3a--h-screen w3a--overflow-hidden w3a--transition-all w3a--duration-[400ms] w3a--ease-in-out')]"
METAMASK_PW_XPATH = "//input[@data-testid='unlock-password']"
METAMASK_CONNECT_BUTTON = "//button[@data-testid='confirm-btn']"
METAMASK_CONFIRM_BUTTON = "//button[@data-testid='confirm-footer-button']"
NFT_CARD_XPATH = "//div[contains(@class,'BaseCard_nesoBoxStyle__6hv_Q')]"
NFT_PRICE_XPATH = "//span[contains(@class,'CardPrice_number__OYpdb')]"


# ================= DRIVER =================
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


def human_wait(min_seconds: float = 1.5, max_seconds: float = 3.5):
    time.sleep(random.uniform(min_seconds, max_seconds))


def js_click(driver: WebDriver, element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    human_wait(0.5, 1.5)
    driver.execute_script("""
        arguments[0].dispatchEvent(new MouseEvent('click', {
            bubbles: true, cancelable: true, view: window
        }));
    """, element)


def debug_page(driver: WebDriver, label: str = ""):
    import tempfile
    ts = int(time.time())
    path = os.path.join(tempfile.gettempdir(), f"debug_{label}_{ts}")
    driver.save_screenshot(f"{path}.png")
    with open(f"{path}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    log.info("Debug '%s' salvo em %s.png e %s.html", label, path, path)


def open_metamask(driver: WebDriver):
    """Abre a MetaMask em nova aba a partir da janela principal."""
    driver.switch_to.window(driver.window_handles[0])
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(METAMASK_EXTENSION_URL)
    human_wait(3, 5)
    log.info("MetaMask aberta: %s", driver.current_url)


# ================= FLUXO =================
def is_wallet_connected(driver: WebDriver) -> bool:
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, METAMASK_INITIAL_CONNECTION))
        )
        return False  # botão existe → não conectado
    except TimeoutException:
        return True   # botão não existe → já conectado


def main():
    driver = _driver()
    try:
        log.info("1️⃣  Desbloqueando MetaMask...")
        driver.get(METAMASK_EXTENSION_URL)
        human_wait(3, 5)
        wallet_password(driver)
        human_wait(3, 5)

        log.info("2️⃣  Abrindo MapleStory...")
        driver.get(MAPLESTORY_BASE)
        human_wait(3, 5)

        if is_wallet_connected(driver):
            log.info("✅ Carteira já conectada, pulando etapas de conexão...")
        else:
            log.info("3️⃣  Clicando em Connect Wallet...")
            inital_connection(driver)
            human_wait()

            log.info("4️⃣  Clicando em Sign In MetaMask...")
            sign_in_wallet(driver)
            human_wait(3, 5)

            log.info("5️⃣  Conectando carteira...")
            open_metamask(driver)
            connect_wallet(driver)
            human_wait()

            log.info("6️⃣  Confirmando...")
            open_metamask_and_confirm(driver)
            human_wait(2, 4)

        driver.switch_to.window(driver.window_handles[0])
        human_wait(2, 4)

        prices = {}
        for name in NFT_NAMES:
            prices[name] = get_lowest_price(driver, name)

        save_to_sheets(prices)

    except Exception as e:
        log.error("Erro: %s", type(e).__name__, exc_info=True)
        debug_page(driver, "erro")
    finally:
        input("\nPressione ENTER para fechar...")
        driver.quit()



def wallet_password(driver: WebDriver):
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    password_input = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_PW_XPATH)))
    log.info("Campo de senha encontrado")
    ActionChains(driver).move_to_element(password_input).click().send_keys(METAMASK_PASSWORD).perform()
    human_wait(0.5, 1.5)
    ActionChains(driver).send_keys(Keys.ENTER).perform()


def inital_connection(driver: WebDriver):
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    start = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_INITIAL_CONNECTION)))
    human_wait()
    js_click(driver, start)


def sign_in_wallet(driver: WebDriver):
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    sign_in_button = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_SIGN_IN_XPATH)))
    log.info("Botão encontrado: %s", sign_in_button.text.strip())
    human_wait()
    sign_in_button.click()


def connect_wallet(driver: WebDriver):
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    connect = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_CONNECT_BUTTON)))
    human_wait()
    ActionChains(driver).move_to_element(connect).click().perform()


def confirm_wallet(driver: WebDriver):
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    confirm = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_CONFIRM_BUTTON)))
    log.info("Botão confirmar encontrado")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", confirm)
    human_wait()
    ActionChains(driver).move_to_element(confirm).click().perform()
    human_wait(2, 3)
    driver.switch_to.window(driver.window_handles[0])


def open_metamask_and_confirm(driver: WebDriver):
    open_metamask(driver)
    confirm_wallet(driver)


def search_marketplace_url(keyword: str) -> str:
    encoded = keyword.title().replace(" ", "+")
    return f"{MARKETPLACE_NFT_BASE}?keyword={encoded}&page=1&sort=ExploreSorting_LOWEST_PRICE"


def get_marketplace_items_lowest_price(driver: WebDriver) -> list:
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    items = wait.until(
        EC.presence_of_all_elements_located((By.XPATH, NFT_CARD_XPATH))
    )
    return items


def get_lowest_price(driver: WebDriver, name: str) -> str:
    driver.get(search_marketplace_url(name))
    human_wait(3, 5)
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    first_price = wait.until(
        EC.presence_of_element_located((By.XPATH, NFT_PRICE_XPATH))
    )
    raw = first_price.text.strip()  # ex: "220,000" ou "3,919,400"
    price = raw.replace(",", ".")   # ex: "220.000" ou "3.919.400"
    log.info("💰 %s: %s", name, price)
    return price


def get_sheets_client() -> gspread.Client:
    creds = gspread.service_account(filename="credentials.json")
    return creds


def save_to_sheets(prices: dict):
    client = get_sheets_client()
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1

    # cria cabeçalhos se a planilha estiver vazia
    if not sheet.row_values(1):
        headers = ["Data"] + NFT_NAMES
        sheet.append_row(headers, value_input_option="USER_ENTERED")
        log.info("Cabeçalhos criados: %s", headers)

    today = date.today().strftime("%d/%m/%Y")
    row = [today] + [prices.get(name, "N/A") for name in NFT_NAMES]
    sheet.append_row(row, value_input_option="USER_ENTERED")
    log.info("✅ Dados salvos na planilha: %s", row)


if __name__ == "__main__":
    main()