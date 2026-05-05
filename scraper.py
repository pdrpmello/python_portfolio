"""Automação de conexão MetaMask e coleta de preços no marketplace."""

import keyword
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
    MARKETPLACE_FT_BASE,
    CHARS_BASE,
    CHARACTER_JOBS,
    METAMASK_EXTENSION_URL,
    METAMASK_PASSWORD,
    SPREADSHEET_ID,
    SUBJOB_TO_SHEET,
    NFT_NAMES,
    FT_ITEMS,
    FT_NAMES,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

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
FT_PRICE_XPATH = "//div[contains(@class,'BidBottom_bidLowestPricePercent')]"
CHARACTER_PRICE_XPATH = "//span[contains(@class,'CardPrice_number__OYpdb')]"


# ================= DRIVER =================
def _build_options():
    """Return configured ChromeOptions."""
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")
    options.add_argument(f"--profile-directory={CHROME_PROFILE_DIR}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    return options


def _driver() -> WebDriver:
    """Return initialized Chrome WebDriver."""
    options = _build_options()
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)
    return driver


def human_wait(min_seconds: float = 1.5, max_seconds: float = 3.5):
    """Sleep for a random interval."""
    time.sleep(random.uniform(min_seconds, max_seconds))


def js_click(driver: WebDriver, element):
    """Click element via JavaScript."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    human_wait(0.5, 1.5)
    driver.execute_script("""
        arguments[0].dispatchEvent(new MouseEvent('click', {
            bubbles: true, cancelable: true, view: window
        }));
    """, element)


def debug_page(driver: WebDriver, label: str = ""):
    """Save screenshot and HTML for debugging."""
    import tempfile
    ts = int(time.time())
    path = os.path.join(tempfile.gettempdir(), f"debug_{label}_{ts}")
    driver.save_screenshot(f"{path}.png")
    with open(f"{path}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    log.info("Debug '%s' salvo em %s.png e %s.html", label, path, path)


def open_metamask(driver: WebDriver):
    """Open MetaMask in a new tab."""
    driver.switch_to.window(driver.window_handles[0])
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[-1])
    driver.get(METAMASK_EXTENSION_URL)
    human_wait(3, 5)
    log.info("MetaMask aberta: %s", driver.current_url)


# ================= FLUXO =================
def is_wallet_connected(driver: WebDriver) -> bool:
    """Return True if wallet is connected."""
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, METAMASK_INITIAL_CONNECTION))
        )
        return False
    except TimeoutException:
        return True


def main():
    """Run full automation workflow."""
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
            prices[name] = get_nft_lowest_price(driver, name)

        for name in FT_NAMES:
            prices[name] = get_ft_lowest_price(driver, name)

        save_to_sheets(prices)

        log.info("🎮 Coletando preços de Characters...")
        character_prices = {}
        for job, subjobs in CHARACTER_JOBS.items():
            for subjob in subjobs:
                character_prices[subjob] = get_character_lowest_price(driver, job, subjob)

        save_characters_to_sheets(character_prices)

    except Exception as e:
        log.error("Erro: %s", type(e).__name__, exc_info=True)
        debug_page(driver, "erro")
    finally:
        input("\nPressione ENTER para fechar...")
        driver.quit()


def wallet_password(driver: WebDriver):
    """Unlock MetaMask wallet."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    password_input = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_PW_XPATH)))
    log.info("Campo de senha encontrado")
    ActionChains(driver).move_to_element(password_input).click().send_keys(METAMASK_PASSWORD).perform()
    human_wait(0.5, 1.5)
    ActionChains(driver).send_keys(Keys.ENTER).perform()


def inital_connection(driver: WebDriver):
    """Click 'Connect Wallet'."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    start = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_INITIAL_CONNECTION)))
    human_wait()
    js_click(driver, start)


def sign_in_wallet(driver: WebDriver):
    """Click 'Sign in with MetaMask'."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    sign_in_button = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_SIGN_IN_XPATH)))
    log.info("Botão encontrado: %s", sign_in_button.text.strip())
    human_wait()
    sign_in_button.click()


def connect_wallet(driver: WebDriver):
    """Approve wallet connection."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    connect = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_CONNECT_BUTTON)))
    human_wait()
    ActionChains(driver).move_to_element(connect).click().perform()


def confirm_wallet(driver: WebDriver):
    """Confirm MetaMask action."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    confirm = wait.until(EC.element_to_be_clickable((By.XPATH, METAMASK_CONFIRM_BUTTON)))
    log.info("Botão confirmar encontrado")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", confirm)
    human_wait()
    ActionChains(driver).move_to_element(confirm).click().perform()
    human_wait(2, 3)
    driver.switch_to.window(driver.window_handles[0])


def open_metamask_and_confirm(driver: WebDriver):
    """Open MetaMask and confirm action."""
    open_metamask(driver)
    confirm_wallet(driver)


def search_nft_marketplace_url(keyword: str) -> str:
    """Return NFT search URL."""
    encoded = keyword.title().replace(" ", "+")
    return f"{MARKETPLACE_NFT_BASE}?sort=ExploreSorting_LOWEST_PRICE&categories=0&potential=0%2C0&bonusPotential=0%&keyword={encoded}"


def search_ft_marketplace_url(name: str) -> str:
    """Return FT search URL."""
    item_id = FT_ITEMS[name]
    encoded = name.replace(" ", "+")
    return f"{MARKETPLACE_FT_BASE}{item_id}?keyword={encoded}"


def search_character_url(job: str, subjob: str) -> str:
    """Return character search URL."""
    return (
        f"{CHARS_BASE}"
        f"?level=140%2C150"
        f"&price=0%2C10000000000"
        f"&jobs={job}%2C{subjob}"
        f"&attackPower=0&options=%25220%253A0%252C0%253A0%252C0%253A0%252C0%253A0%252C0%253A0%2522&page=1&sort=CharacterExploreSorting_LOWEST_PRICE"
    )
     

def get_marketplace_items_lowest_price(driver: WebDriver) -> list:
    """Return marketplace item elements."""
    wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
    items = wait.until(
        EC.presence_of_all_elements_located((By.XPATH, NFT_CARD_XPATH))
    )
    return items


def get_nft_lowest_price(driver: WebDriver, name: str) -> str:
    """Return lowest NFT price or 'N/A'."""
    try:
        driver.get(search_nft_marketplace_url(name))
        human_wait(3, 5)
        wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
        first_price = wait.until(
            EC.presence_of_element_located((By.XPATH, NFT_PRICE_XPATH))
        )
        raw = first_price.text.strip()
        price = raw.replace(",", ".")
        log.info("💰 %s: %s", name, price)
        return price
    except TimeoutException:
        log.warning("⚠️ Preço não encontrado para NFT %s", name)
        return "N/A"


def get_ft_lowest_price(driver: WebDriver, name: str) -> str:
    """Return lowest FT price or 'N/A'."""
    try:
        driver.get(search_ft_marketplace_url(name))
        human_wait(3, 5)
        wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
        price_div = wait.until(
            EC.presence_of_element_located((By.XPATH, FT_PRICE_XPATH))
        )
        price = price_div.text.replace("\n", "").replace(",", ".").strip()
        log.info("💰 %s: %s", name, price)
        return price
    except TimeoutException:
        log.warning("⚠️ Preço não encontrado para FT %s", name)
        return "N/A"


def get_character_lowest_price(driver: WebDriver, job: str, subjob: str) -> str:
    """Return lowest character price or 'N/A'."""
    try:
        driver.get(search_character_url(job, subjob))
        human_wait(3, 5)
        wait = WebDriverWait(driver, DEFAULT_TIMEOUT)
        first_price = wait.until(
            EC.presence_of_element_located((By.XPATH, CHARACTER_PRICE_XPATH))
        )
        raw = first_price.text.strip()
        price = raw.replace(",", ".")
        log.info("💰 %s/%s: %s", job, subjob, price)
        return price
    except TimeoutException:
        log.warning("⚠️ Preço não encontrado para %s/%s", job, subjob)
        return "N/A"


def get_sheets_client() -> gspread.Client:
    """Return authenticated Sheets client."""
    creds = gspread.service_account(filename="credentials.json")
    return creds


def save_to_sheets(prices: dict):
    """Save prices to main sheet."""
    for tentativa in range(3):
        try:
            client = get_sheets_client()
            sheet = client.open_by_key(SPREADSHEET_ID).sheet1

            headers = sheet.get("2:2")[0]
            log.info("Cabeçalhos encontrados (%d): %s", len(headers), headers)
            today = date.today().strftime("%d/%m/%Y")

            # adiciona cabeçalhos ausentes no final da linha 2
            for name in prices:
                if name not in headers:
                    headers.append(name)
                    col = len(headers)
                    sheet.update(range_name=f"{chr(64 + col)}2", values=[[name]])
                    log.info("Cabeçalho '%s' adicionado na coluna %d", name, col)

            row = [""] * len(headers)

            if "Data" in headers:
                row[headers.index("Data")] = today

            for name, price in prices.items():
                if name in headers:
                    row[headers.index(name)] = price

            # encontra a próxima linha vazia após os dados
            all_values = sheet.get_all_values()
            next_row = len(all_values) + 1
            log.info("Inserindo na linha %d", next_row)

            sheet.insert_row(row, next_row)
            log.info("✅ Dados salvos na planilha: %s", row)
            return

        except Exception as e:
            log.warning("Tentativa %d falhou: %s", tentativa + 1, type(e).__name__)
            if tentativa < 2:
                time.sleep(5)

    log.error("❌ Falha ao salvar na planilha após 3 tentativas")


def save_characters_to_sheets(prices: dict):
    """Save character prices to 'Classes' sheet."""
    for tentativa in range(3):
        try:
            client = get_sheets_client()
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Classes")

            all_values = sheet.get_all_values()
            headers = all_values[1]

            header_index = {name: i for i, name in enumerate(headers)}
            today = date.today().strftime("%d/%m/%Y")

            row = [""] * len(headers)

            if "Data" in header_index:
                row[header_index["Data"]] = today

            for subjob, price in prices.items():
                sheet_name = SUBJOB_TO_SHEET.get(subjob)

                if not sheet_name:
                    log.warning("⚠️ Subjob '%s' sem mapping", subjob)
                    continue

                if sheet_name in header_index:
                    row[header_index[sheet_name]] = price
                else:
                    log.warning("⚠️ Coluna '%s' não encontrada", sheet_name)

            next_row = len(sheet.col_values(1)) + 1
            sheet.insert_row(row, next_row)

            log.info("✅ Characters salvos na planilha")
            return

        except Exception as e:
            log.warning("Tentativa %d falhou: %s", tentativa + 1, type(e).__name__)
            if tentativa < 2:
                time.sleep(5)

    log.error("❌ Falha ao salvar characters após 3 tentativas")


if __name__ == "__main__":
    main()