import gspread
from config import SPREADSHEET_ID_CLASSES


def get_sheets_client():
    return gspread.service_account(filename="credentials.json")

client = get_sheets_client()
spreadsheet = client.open_by_key(SPREADSHEET_ID_CLASSES)

for ws in spreadsheet.worksheets():
    print(f"'{ws.title}'")