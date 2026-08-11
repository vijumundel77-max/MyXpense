"""
Expenzo — Account Book Report
Account statement view from Expenzo voucher data.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.account_book_service import account_book_service
from services.account_service import account_service
from ui.report_base import (
    ReportHeader,
    FilterBar,
    ReportTable,
    ReportStatusBar,
    make_date_entry,
    make_readonly_combo,
    make_button,
)
from utils import dialogs


class AccountBookReportUI:
    """Account Book report screen (Expenzo voucher data)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None
        self.account_map: Dict[str, int] = {}

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportHeader(self.main_frame, "Account Book", "Account statement view")

        filters = FilterBar(self.main_frame)
        self.account_var = tk.StringVar(value="All Accounts")
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var = tk.StringVar()

        self.account_combo = make_readonly_combo(filters.body, ["All Accounts"], self.account_var, 220)
        filters.add("Account", self.account_combo)
        filters.add("From Date", make_date_entry(filters.body, self.from_date_var))
        filters.add("To Date", make_date_entry(filters.body, self.to_date_var))
        self.search_entry = ctk.CTkEntry(filters.body, textvariable=self.search_var, width=170,
                                         corner_radius=config.INPUT_CORNER_RADIUS)
        filters.add("Search", self.search_entry)
        make_button(filters.body, "Generate", self._generate_report, accent=True).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export CSV", self._export_to_csv).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export JSON", self._export_to_json).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export PNG", self._export_to_png, width=100).pack(side="left")

        columns = [
            {"id": "date", "heading": "Date", "width": 100},
            {"id": "reference", "heading": "Reference", "width": 130},
            {"id": "type", "heading": "Type", "width": 100},
            {"id": "narration", "heading": "Narration", "width": 240},
            {"id": "debit", "heading": "Debit", "width": 110, "anchor": "e"},
            {"id": "credit", "heading": "Credit", "width": 110, "anchor": "e"},
            {"id": "balance", "heading": "Running Balance", "width": 130, "anchor": "e"},
            {"id": "dr_cr", "heading": "Dr/Cr", "width": 60, "anchor": "center"},
        ]
        self.table = ReportTable(self.main_frame, columns)
        self.table.show_empty("Select an account and generate to begin.")

        self.status = ReportStatusBar(self.main_frame)
        self._load_accounts()

    def _load_accounts(self) -> None:
        accounts = account_service.search_accounts(self.company_id, include_inactive=False)
        self.account_map = {
            f"{a['name']} ({a['code']})" if a.get('code') else a['name']: a['id']
            for a in accounts
        }
        self.account_combo.configure(values=["All Accounts"] + list(self.account_map.keys()))

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _selected_account_id(self) -> Optional[int]:
        value = self.account_var.get().strip()
        if value == "All Accounts":
            return None
        return self.account_map.get(value)

    def _generate_report(self) -> None:
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Account Book", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Account Book", "From Date cannot be after To Date.", parent=self.parent)
            return
        account_id = self._selected_account_id()
        if not account_id:
            dialogs.warn("Account Book", "Select a specific account for the statement.", parent=self.parent)
            return
        report = account_book_service.generate_account_book(
            self.company_id, account_id, from_date, to_date)
        if not report.get('success'):
            dialogs.error("Account Book", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        self.table.hide_empty()
        search = self.search_var.get().strip().lower()
        rows = []
        for txn in report.get('transactions', []):
            if search and not any(
                search in str(txn.get(field, '')).lower()
                for field in ('reference_number', 'narration', 'transaction_type')
            ):
                continue
            rows.append((
                txn.get('transaction_date', ''),
                txn.get('reference_number', ''),
                txn.get('transaction_type', ''),
                txn.get('narration', ''),
                f"{txn.get('debit_amount', 0):,.2f}",
                f"{txn.get('credit_amount', 0):,.2f}",
                f"{txn.get('running_balance', 0):,.2f}",
                txn.get('balance_type', ''),
            ))
        self.table.set_rows(rows)
        opening = report.get('opening_balance', {})
        closing = report.get('closing_balance', {})
        self.table.set_totals(
            f"Opening: {opening.get('amount', 0):,.2f} {opening.get('type', '')}   |   "
            f"Receipts: {report.get('receipts', 0):,.2f}   |   "
            f"Payments: {report.get('payments', 0):,.2f}   |   "
            f"Closing: {closing.get('amount', 0):,.2f} {closing.get('type', '')}"
        )
        self.status.set(
            f"Account book generated: {report.get('transaction_count', 0)} transactions "
            f"({report.get('from_date', '')} to {report.get('to_date', '')})"
        )

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "account_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = account_book_service.export_account_book_to_csv(self.current_report_data)
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = account_book_service.export_to_json(self.current_report_data, "account_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_account_book_report(parent: tk.Widget, company_id: int) -> AccountBookReportUI:
    return AccountBookReportUI(parent, company_id)
