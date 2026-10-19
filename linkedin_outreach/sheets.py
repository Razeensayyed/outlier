"""Google Sheets helpers shared by both scripts."""
import gspread
import config


def get_sheet() -> gspread.Worksheet:
    gc = gspread.service_account(filename=config.GOOGLE_SHEETS_CREDENTIALS_FILE)
    sh = gc.open_by_key(config.SPREADSHEET_ID)
    return sh.worksheet(config.SHEET_NAME)


def get_col_index(sheet: gspread.Worksheet, column_name: str) -> int:
    headers = sheet.row_values(1)
    return headers.index(column_name) + 1  # 1-indexed


def update_cell_by_username(sheet: gspread.Worksheet, username: str, column: str, value: str) -> bool:
    records = sheet.get_all_records()
    col_index = get_col_index(sheet, column)
    for i, row in enumerate(records):
        if str(row.get("Username", "")).strip().lower() == username.strip().lower():
            row_num = i + 2  # header row + 0-indexed
            sheet.update_cell(row_num, col_index, value)
            return True
    return False
