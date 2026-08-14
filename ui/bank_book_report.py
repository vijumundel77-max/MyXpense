"""
Expenzo — Bank Book Report
Bank movement from Expenzo vouchers.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.cash_book_service import cash_book_service
from ui.report_base import (
    ReportBackHeader,
    FilterBar,
    ReportTable,
    ReportStatusBar,
    ReportActionBar,
    make_date_picker,
    make_readonly_combo,
    make_button,
    wire_report_keyboard,
)
from utils import dialogs


class BankBookReportUI:
    """Bank Book report screen (Expenzo voucher data)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Bank Book", "Bank movement from vouchers",
                         on_back=self._back)

        filters = FilterBar(self.main_frame)
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.account_var = tk.StringVar(value="All Accounts")
        self.search_var = tk.StringVar()

        filters.add("From Date", make_date_picker(filters.body, self.from_date_var))
        filters.add("To Date", make_date_picker(filters.body, self.to_date_var))
        self.account_combo = make_readonly_combo(filters.body, ["All Accounts"], self.account_var, 200)
        filters.add("Account", self.account_combo)
        self.search_entry = ctk.CTkEntry(
            filters.body, textvariable=self.search_var, width=200,
            corner_radius=config.INPUT_CORNER_RADIUS, height=30)
        filters.add("Search", self.search_entry)
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        columns = [
            {"id": "date", "heading": "Date", "width": 100},
            {"id": "number", "heading": "Voucher No.", "width": 110},
            {"id": "type", "heading": "Type", "width": 90},
            {"id": "reference", "heading": "Reference", "width": 120},
            {"id": "narration", "heading": "Narration", "width": 220},
            {"id": "debit", "heading": "Deposits", "width": 110, "anchor": "e"},
            {"id": "credit", "heading": "Withdrawals", "width": 110, "anchor": "e"},
            {"id": "balance", "heading": "Running Balance", "width": 130, "anchor": "e"},
            {"id": "dr_cr", "heading": "Dr/Cr", "width": 60, "anchor": "center"},
        ]
        self.table = ReportTable(self.main_frame, columns)
        self.table.show_empty("Select dates and generate the Bank Book to begin.")

        ReportActionBar(
            self.main_frame,
            refresh=self._generate_report,
            exports=[("Export CSV", self._export_to_csv),
                     ("Export JSON", self._export_to_json),
                     ("Export PNG", self._export_to_png)],
            clear=self._clear_filters,
            back=self._back,
        )

        self.status = ReportStatusBar(self.main_frame)
        self._load_accounts()
        wire_report_keyboard(self)

    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _clear_filters(self) -> None:
        self.from_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.account_var.set("All Accounts")
        self.search_var.set("")
        self.table.show_empty("Select dates and generate the Bank Book to begin.")
        self.status.set("Filters cleared")

    def _load_accounts(self) -> None:
        from services.cash_book_service import GROUP_BANK, CashBookService
        banks = CashBookService._book_accounts(self.company_id, GROUP_BANK)
        self.account_map = {f"{b['name']} ({b['code']})": b['id'] for b in banks}
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
            dialogs.warn("Bank Book", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Bank Book", "From Date cannot be after To Date.", parent=self.parent)
            return
        report = cash_book_service.generate_bank_book(
            self.company_id, from_date, to_date, self._selected_account_id())
        if not report.get('success'):
            dialogs.error("Bank Book", report.get('error', 'Failed to generate report'), parent=self.parent)
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
                for field in ('reference_number', 'narration', 'voucher_number', 'voucher_type')
            ):
                continue
            rows.append((
                txn.get('transaction_date', ''),
                txn.get('voucher_number', ''),
                txn.get('voucher_type', ''),
                txn.get('reference_number', ''),
                txn.get('narration', ''),
                f"{txn.get('debit_amount', 0):,.2f}",
                f"{txn.get('credit_amount', 0):,.2f}",
                f"{txn.get('running_balance', 0):,.2f}",
                txn.get('balance_type', ''),
            ))
        self.table.set_rows(rows)
        closing = report.get('closing_balance', {})
        self.table.set_totals(
            f"Opening: {report.get('opening_balance', 0):,.2f}   |   "
            f"Deposits: {report.get('receipts', 0):,.2f}   |   "
            f"Withdrawals: {report.get('payments', 0):,.2f}   |   "
            f"Closing: {closing.get('amount', 0):,.2f} {closing.get('type', '')}"
        )
        self.status.set(
            f"Bank Book generated: {report.get('transaction_count', 0)} transactions "
            f"({report.get('from_date', '')} to {report.get('to_date', '')})"
        )

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "bank_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = cash_book_service.export_cash_book_to_csv(self.current_report_data, "bank_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = cash_book_service.export_to_json(self.current_report_data, "bank_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_bank_book_report(parent: tk.Widget, company_id: int) -> BankBookReportUI:
    return BankBookReportUI(parent, company_id)
