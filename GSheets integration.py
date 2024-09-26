# This code allows the connection between Python and a fictional Investment Google Spreadsheet.

import gspread
import pandas as pd

CODE = "1aQ-CGPysh8C3h0Z8w8Q4LLJOaLUpekcJRTXLupZuUIY"

google_client = gspread.service_account(filename='key.json')
spreadsheet = google_client.open_by_key(CODE)
worksheet = spreadsheet.worksheet('Investimentos')

expected_headers = ['Ativos', 'Tipo', 'Ramo', 'Valor Atual', 'V. Compra', 'Variação', 'Operação', 'Quantidade', 'Valor Investido']
data = worksheet.get_all_records(expected_headers=expected_headers)
df = pd.DataFrame(data)

print(df)