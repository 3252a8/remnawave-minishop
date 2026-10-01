import csv
import io
from decimal import Decimal

import pytest

from bot.utils.csv_export import SpreadsheetWriter, spreadsheet_cell


@pytest.mark.parametrize("value", ["=1+2@example.com", "+CMD", "-CMD", "@SUM(1)", " =1", "\t1"])
def test_spreadsheet_text_cannot_become_a_formula(value: str) -> None:
    assert spreadsheet_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["alice@example.com", "Текст", 123, -20, Decimal("-1.50"), ""])
def test_regular_text_and_numeric_amounts_keep_their_values(value: object) -> None:
    assert spreadsheet_cell(value) == value


def test_export_keeps_csv_quoting_and_numeric_values_while_neutralizing_formulas() -> None:
    output = io.StringIO()
    SpreadsheetWriter(output).writerow(["=CMD()", 'name,"quoted"\nline', -20, Decimal("1.50")])
    assert list(csv.reader(io.StringIO(output.getvalue()))) == [
        ["'=CMD()", 'name,"quoted"\nline', "-20", "1.50"]
    ]
