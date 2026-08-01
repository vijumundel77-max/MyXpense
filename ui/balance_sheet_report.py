"""
Balance Sheet Report UI Module
Disabled in Expenzo V1 migration.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any


class BalanceSheetReportUI:
    """Disabled balance sheet UI placeholder."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id


def show_balance_sheet_report(parent: tk.Widget, company_id: int) -> BalanceSheetReportUI:
    return BalanceSheetReportUI(parent, company_id)
