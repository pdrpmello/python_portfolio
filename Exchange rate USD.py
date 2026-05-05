# This program retrieves the latest Dollar exchange rate.

import requests
from bs4 import BeautifulSoup as bs

url = requests.get('https://wise.com/br/currency-converter/dolar-hoje')

soup = bs(url.text, 'html.parser')

dollar = soup.find('div', {'class': '_midMarketRateAmount_14arr_139'}).text
dollar = dollar.replace(',', '.')
print(f"The current USD exchange rate to BRL is: R$ {dollar}")




