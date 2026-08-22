"""
Expenzo — Cash Book Report (Compact UI)
Cash and bank movement from Expenzo vouchers.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.cash_book_service import cash_book_service
from services.date_control_service import date_control
from ui.report_base import CompactReportUI, wire_report_keyboard
from utils import dialogs


class CashBookReportUI(CompactReportUI):
    """Cash Book report screen using the compact high‑density layout."""

    _REPORT_TITLE = "Cash Book"
    _REPORT_SUBTITLE = "Cash movement from vouchers"
    _FILTER_TYPES = ["All Accounts"]  # will be populated after loading accounts

    _COLUMNS = [
        {"id": "date", "heading": "Date", "width": 95, "anchor": "w", "stretch": False},
        {"id": "number", "heading": "Vch No.", "width": 110, "anchor": "center", "stretch": False},
        {"id": "type", "heading": "Vch Type", "width": 110, "anchor": "center", "stretch": False},
        {"id": "reference", "heading": "Reference", "width": 120, "anchor": "w", "stretch": False},
        {"id": "narration", "heading": "Particulars", "width": 280, "anchor": "w", "stretch": True},
        {"id": "debit", "heading": "Debit (₹)", "width": 110, "anchor": "e", "stretch": False},
        {"id": "credit", "heading": "Credit (₹)", "width": 110, "anchor": "e", "stretch": False},
        {"id": "balance", "heading": "Balance (₹)", "width": 120, "anchor": "e", "stretch": False},
    ]

    def __init__(self, parent: tk.Widget, company_id: int):
        # load account list before UI builds filter bar
        self._load_accounts()
        super().__init__(parent, company_id)

    # ------------------------------------------------------------------
    # CompactReportUI abstract hooks
    # ------------------------------------------------------------------
    def _new_voucher(self) -> None:
        # navigate to voucher entry screen
        self._route_to_vouchers()

    def _open_selected(self) -> None:
        # not used for cash book (read‑only), keep stub
        pass

    def _view_selected(self) -> None:
        pass

    def _generate_report(self) -> None:
        from_date = self._parse_date(self.from_var.get())
        to_date = self._parse_date(self.to_var.get())
        if not from_date or not to_date:
            dialogs.warn("Cash Book", "Invalid date. Use DD‑MM‑YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Cash Book", "From Date cannot be after To Date.", parent=self.parent)
            return

        account_id = self._selected_account_id()
        report = cash_book_service.generate_cash_book(
            self.company_id, from_date, to_date, account_id)
        if not report.get('success'):
            dialogs.error("Cash Book", report.get('error', 'Failed to generate report'), parent=self.parent)
            return

        self.current_report_data = report
        self._render_rows(report)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_accounts(self) -> None:
        sources = cash_book_service._get_cash_sources(self.company_id)
        self.account_map = {f"{s['name']} ({s['code']})": s['id'] for s in sources}
        # after UI is built we will set the combo values
        # but filter bar is built in base __init__, so we update later
        # store for later
        self._account_names = ["All Accounts"] + list(self.account_map.keys())

    def _selected_account_id(self) -> Optional[int]:
        value = self.type_var.get().strip()
        if value == "All Accounts":
            return None
        return self.account_map.get(value)

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _render_rows(self, report: Dict[str, Any]) -> None:
        self._hide_empty()
        search = self.search_var.get().strip().lower()
        total_debit = total_credit = 0.0

        for iid in self.tree.get_children():
            self.tree.delete(iid)

        for idx, txn in enumerate(report.get('transactions', [])):
            if search and not any(
                search in str(txn.get(field, '')).lower()
                for field in ('reference_number', 'narration', 'voucher_number', 'voucher_type')
            ):
                continue

            debit = float(txn.get('debit_amount', 0) or 0)
            credit = float(txn.get('credit_amount', 0) or 0)
            total_debit += debit
            total_credit += credit

            # colour tag based on debit/credit
            tag = "debit" if debit else ("credit" if credit else "odd")
            if idx % 2:
                tag = (tag, "odd") if isinstance(tag, str) else tag + ("odd",)

            self.tree.insert(
                "", tk.END,
                values=(
                    txn.get('transaction_date', ''),
                    txn.get('voucher_number', ''),
                    txn.get('voucher_type', ''),
                    txn.get('reference_number', ''),
                    txn.get('narration', ''),
                    f"{debit:,.2f}" if debit else "—",
                    f"{credit:,.2f}" if credit else "—",
                    f"{txn.get('running_balance', 0):,.2f}",
                ),
                tags=(tag,)
            )

        closing = report.get('closing_balance', {})
        diff = total_debit - total_credit
        self._update_footer(
            txn_count=report.get('transaction_count', 0),
            debit=total_debit,
            credit=total_credit,
            diff=diff
        )

        # opening / receipts / payments line could be shown in status if needed
        # self.status.set(...)

    # ------------------------------------------------------------------
    # Navigation helpers (same as Day Book)
    # ------------------------------------------------------------------
    def _route_to_vouchers(self) -> None:
        try:
            app = self.winfo_toplevel()
            if hasattr(app, "show_vouchers"):
                app.show_vouchers()
        except Exception:
            pass

    # after UI built, update the type menu with account list
    def _build_filter_bar(self) -> None:
        super()._build_filter_bar()
        # replace the type menu values now that accounts are known
        self.type_menu.configure(values=self._account_names)
        self.type_var.set("All Accounts")


def show_cash_book_report(parent: tk.Widget, company_id: int) -> CashBookReportUI:
    return CashBookReportUI(parent, company_id)