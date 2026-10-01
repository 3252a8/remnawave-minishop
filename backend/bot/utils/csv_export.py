"""Preserve text cells as data when a CSV is opened by a spreadsheet."""

import csv
from collections.abc import Iterable
from typing import Any, TextIO


def spreadsheet_cell(value: object) -> object:
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


class SpreadsheetWriter:
    """Apply the same cell boundary to each administrative CSV export."""

    def __init__(self, output: TextIO, **fmtparams: Any) -> None:
        self._writer = csv.writer(output, **fmtparams)

    def writerow(self, row: Iterable[object]) -> int:
        return self._writer.writerow(spreadsheet_cell(value) for value in row)
