# This program retrieves the latest Dollar exchange rate.

import requests
from bs4 import BeautifulSoup as bs

url = requests.get('https://www.remessaonline.com.br/cotacao/cotacao-dolar')
soup = bs(url.text, 'html.parser')

# Adjust the selector according to the actual structure of the HTML
dollar = soup.find('div', {'class': 'style__Text-sc-1a6mtr6-2 ljisZu'}).text[:4]
dollar = dollar.replace(',', '.')

print(f"The current USD exchange rate to BRL is: R$ {dollar}")