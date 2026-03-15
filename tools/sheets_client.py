from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import gspread
from gspread import Worksheet
from tenacity import retry, stop_after_attempt, wait_fixed

from core.config import get_settings
from tools.schema_map import PRIMARY_KEYS, SHEET_SCHEMAS


class SheetValidationError(ValueError):
    pass


class SheetsClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_sheets_spreadsheet_id:
            raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is required for Sheets operations")

        if settings.google_sheets_credentials_json_b64:
            decoded = base64.b64decode(settings.google_sheets_credentials_json_b64).decode("utf-8")
            service_account_info = json.loads(decoded)
            self._client = gspread.service_account_from_dict(service_account_info)
        else:
            base_dir = Path(__file__).resolve().parents[1]
            credentials_path = base_dir / settings.google_sheets_credentials_file
            if not credentials_path.exists():
                raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
            self._client = gspread.service_account(filename=str(credentials_path))

        self._spreadsheet = self._client.open_by_key(settings.google_sheets_spreadsheet_id)

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def get_worksheet(self, sheet_name: str) -> Worksheet:
        return self._spreadsheet.worksheet(sheet_name)

    def validate_payload(self, sheet_name: str, payload: dict[str, Any], *, for_create: bool = True) -> None:
        schema = SHEET_SCHEMAS.get(sheet_name)
        if not schema:
            raise SheetValidationError(f"Unknown sheet: {sheet_name}")

        missing = [field for field in schema if for_create and field not in payload]
        if missing:
            raise SheetValidationError(f"Missing required fields for {sheet_name}: {missing}")

        unknown = [field for field in payload.keys() if field not in schema]
        if unknown:
            raise SheetValidationError(f"Unknown fields for {sheet_name}: {unknown}")

    def read_all(self, sheet_name: str) -> list[dict[str, Any]]:
        worksheet = self.get_worksheet(sheet_name)
        return worksheet.get_all_records()

    def append_row(self, sheet_name: str, payload: dict[str, Any]) -> None:
        self.validate_payload(sheet_name, payload, for_create=True)
        worksheet = self.get_worksheet(sheet_name)
        schema = SHEET_SCHEMAS[sheet_name]
        row = [payload.get(column, "") for column in schema]
        worksheet.append_row(row, value_input_option="USER_ENTERED")

    def update_by_primary_key(self, sheet_name: str, key_value: str, payload: dict[str, Any]) -> None:
        self.validate_payload(sheet_name, payload, for_create=False)

        pk_name = PRIMARY_KEYS[sheet_name]
        if pk_name in payload:
            raise SheetValidationError(f"Primary key mutation is not allowed for {sheet_name}")

        worksheet = self.get_worksheet(sheet_name)
        records = worksheet.get_all_records()
        headers = worksheet.row_values(1)

        target_row = None
        for index, record in enumerate(records, start=2):
            if str(record.get(pk_name)) == str(key_value):
                target_row = index
                break

        if target_row is None:
            raise SheetValidationError(f"Record with {pk_name}={key_value} not found")

        for field, value in payload.items():
            col_index = headers.index(field) + 1
            worksheet.update_cell(target_row, col_index, value)
