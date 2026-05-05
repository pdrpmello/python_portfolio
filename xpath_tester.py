from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


URL = "https://msu.io/marketplace/character?sort=CharacterExploreSorting_LOWEST_PRICE&level=140%2C250&jobs=warrior%2Chero&price=0%2C10000000000"


def get_prices(driver):
    elements = driver.find_elements(
        By.XPATH,
        "//span[contains(@class,'CardPrice_number')]//span"
    )
    return [el.text for el in elements if el.text]


def main():
    driver = webdriver.Chrome()
    driver.get(URL)

    # 🔥 espera os preços aparecerem (ESSENCIAL)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[contains(@class,'CardPrice_number')]")
        )
    )

    prices = get_prices(driver)

    if prices:
        print(prices[0])
    else:
        print("Nenhum preço encontrado")

        driver.quit()


if __name__ == "__main__":
    main()