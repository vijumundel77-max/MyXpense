"""
Expenzo — Party Ledger Report
Party-wise ledger and summary from Expenzo voucher data.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.party_ledger_service import party_ledger_service
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
from utils.debounce import Debouncer

PARTY_TYPES = ("Debtor", "Creditor", "All")
REPORT_TYPES = ("Ledger", "Summary")


class PartyLedgerReportUI:
    """Party Ledger report screen (Expenzo voucher data)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None
        self.all_parties: List[Dict[str, Any]] = []
        self.party_map: Dict[str, int] = {}

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Party Ledger", "Party-wise ledger and summary",
                         on_back=self._back)

        filters = FilterBar(self.main_frame)
        self.report_type_var = tk.StringVar(value="Ledger")
        self.party_type_var = tk.StringVar(value="Debtor")
        self.party_var = tk.StringVar()
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var = tk.StringVar()
        self._search_debouncer = Debouncer(self.main_frame, delay_ms=250)

        self.report_type_combo = make_readonly_combo(filters.body, list(REPORT_TYPES), self.report_type_var, 110)
        filters.add("Report", self.report_type_combo)
        self.party_type_combo = make_readonly_combo(filters.body, list(PARTY_TYPES), self.party_type_var, 110)
        filters.add("Party Type", self.party_type_combo)
        self.party_combo = make_readonly_combo(filters.body, [], self.party_var, 220)
        filters.add("Party", self.party_combo)
        filters.add("From Date", make_date_picker(filters.body, self.from_date_var))
        filters.add("To Date", make_date_picker(filters.body, self.to_date_var))
        self.search_entry = ctk.CTkEntry(filters.body, textvariable=self.search_var, width=180,
                                         corner_radius=config.INPUT_CORNER_RADIUS, height=30)
        filters.add("Search", self.search_entry)
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        # Party selector refresh on party-type / search changes.
        self.party_type_combo.configure(command=lambda _: self._load_parties())
        self.search_entry.bind("<KeyRelease>", lambda _e: self._search_debouncer.schedule(self._load_parties))
        self.report_type_combo.configure(command=lambda _: self._on_report_type_changed())

        self.ledger_table = ReportTable(self.main_frame, [
            {"id": "date", "heading": "Date", "width": 100},
            {"id": "number", "heading": "Voucher No.", "width": 110},
            {"id": "type", "heading": "Type", "width": 90},
            {"id": "reference", "heading": "Reference", "width": 110},
            {"id": "particulars", "heading": "Particulars", "width": 220},
            {"id": "debit", "heading": "Debit", "width": 110, "anchor": "e"},
            {"id": "credit", "heading": "Credit", "width": 110, "anchor": "e"},
            {"id": "balance", "heading": "Balance", "width": 120, "anchor": "e"},
            {"id": "dr_cr", "heading": "Dr/Cr", "width": 60, "anchor": "center"},
        ])
        self.ledger_table.show_empty("Select a party and generate the ledger to begin.")

        self.summary_table = ReportTable(self.main_frame, [
            {"id": "code", "heading": "Code", "width": 90},
            {"id": "name", "heading": "Party Name", "width": 190},
            {"id": "group", "heading": "Group", "width": 140},
            {"id": "opening", "heading": "Opening", "width": 110, "anchor": "e"},
            {"id": "opening_type", "heading": "Type", "width": 60, "anchor": "center"},
            {"id": "debit", "heading": "Debit", "width": 110, "anchor": "e"},
            {"id": "credit", "heading": "Credit", "width": 110, "anchor": "e"},
            {"id": "closing", "heading": "Closing", "width": 110, "anchor": "e"},
            {"id": "closing_type", "heading": "Type", "width": 60, "anchor": "center"},
        ])
        self.summary_table.show_empty("Generate a party summary to begin.")
        self.summary_table.pack_forget()

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
        self._load_parties()
        wire_report_keyboard(self)

    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _clear_filters(self) -> None:
        self.report_type_var.set("Ledger")
        self.party_type_var.set("Debtor")
        self.party_var.set("")
        self.from_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var.set("")
        self._load_parties()
        self.ledger_table.show_empty("Select a party and generate the ledger to begin.")
        self.summary_table.show_empty("Generate a party summary to begin.")
        self.status.set("Filters cleared")

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _on_report_type_changed(self) -> None:
        if self.report_type_var.get() == "Summary":
            self.ledger_table.pack_forget()
            self.summary_table.pack(fill="both", expand=True)
        else:
            self.summary_table.pack_forget()
            self.ledger_table.pack(fill="both", expand=True)

    def _load_parties(self) -> None:
        try:
            party_type = self.party_type_var.get()
            search = self.search_var.get().strip()
            results = party_ledger_service.search_parties(
                self.company_id, party_type, search)
            self.all_parties = results
            values = [f"{p['code']} - {p['name']}" for p in results]
            self.party_map = {f"{p['code']} - {p['name']}": p['id'] for p in results}
            self.party_combo.configure(values=values)
            if values:
                self.party_combo.set(values[0])
        except Exception as exc:
            self.status.set(f"Error loading parties: {exc}")

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _generate_report(self) -> None:
        if self.report_type_var.get() == "Ledger":
            self._generate_ledger()
        else:
            self._generate_summary()

    def _generate_ledger(self) -> None:
        party_text = self.party_var.get().strip()
        if not party_text:
            dialogs.warn("Party Ledger", "Select a party first.", parent=self.parent)
            return
        party_id = self.party_map.get(party_text)
        if not party_id:
            dialogs.warn("Party Ledger", "Invalid party selection.", parent=self.parent)
            return
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Party Ledger", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Party Ledger", "From Date cannot be after To Date.", parent=self.parent)
            return

        report = party_ledger_service.generate_party_ledger(
            self.company_id, party_id, from_date, to_date)
        if not report.get('success'):
            dialogs.error("Party Ledger", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render_ledger(report)

    def _render_ledger(self, report: Dict[str, Any]) -> None:
        self.summary_table.pack_forget()
        self.ledger_table.pack(fill="both", expand=True)
        self.ledger_table.hide_empty()
        rows = []
        for txn in report.get('transactions', []):
            rows.append((
                txn.get('voucher_date', ''),
                txn.get('voucher_number', ''),
                txn.get('voucher_type', ''),
                txn.get('reference_number', ''),
                txn.get('contra_account_name', '') or txn.get('narration', ''),
                f"{txn.get('debit_amount', 0):,.2f}",
                f"{txn.get('credit_amount', 0):,.2f}",
                f"{txn.get('running_balance', 0):,.2f}",
                txn.get('balance_type', ''),
            ))
        self.ledger_table.set_rows(rows)
        account = report.get('account', {})
        totals = report.get('totals', {})
        closing = report.get('closing_balance', {})
        opening = report.get('opening_balance', {})
        self.ledger_table.set_totals(
            f"Party: {account.get('name', '')} ({account.get('code', '')})   |   "
            f"Opening: {opening.get('amount', 0):,.2f} {opening.get('type', '')}   |   "
            f"Debit: {totals.get('debit', 0):,.2f}   Credit: {totals.get('credit', 0):,.2f}   |   "
            f"Closing: {closing.get('amount', 0):,.2f} {closing.get('type', '')}"
        )
        self.status.set(f"Ledger generated: {report.get('transaction_count', 0)} transactions")

    def _generate_summary(self) -> None:
        to_date = self._parse_date(self.to_date_var.get())
        if not to_date:
            dialogs.warn("Party Ledger", "Invalid To Date.", parent=self.parent)
            return
        report = party_ledger_service.generate_party_summary(
            self.company_id, self.party_type_var.get(), to_date)
        if not report.get('success'):
            dialogs.error("Party Ledger", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render_summary(report)

    def _render_summary(self, report: Dict[str, Any]) -> None:
        self.ledger_table.pack_forget()
        self.summary_table.pack(fill="both", expand=True)
        self.summary_table.hide_empty()
        rows = []
        for party in report.get('parties', []):
            rows.append((
                party.get('account_code', ''),
                party.get('account_name', ''),
                party.get('account_group', ''),
                f"{party.get('opening_balance', 0):,.2f}",
                party.get('opening_type', ''),
                f"{party.get('debit_total', 0):,.2f}",
                f"{party.get('credit_total', 0):,.2f}",
                f"{party.get('closing_balance', 0):,.2f}",
                party.get('closing_type', ''),
            ))
        self.summary_table.set_rows(rows)
        totals = report.get('totals', {})
        self.summary_table.set_totals(
            f"Total Debit: {totals.get('total_debit', 0):,.2f}   |   "
            f"Total Credit: {totals.get('total_credit', 0):,.2f}   |   "
            f"Net Receivable: {totals.get('net_receivable', 0):,.2f}   |   "
            f"Net Payable: {totals.get('net_payable', 0):,.2f}"
        )
        self.status.set(f"Summary generated: {report.get('party_count', 0)} parties")

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        if self.report_type_var.get() == "Ledger":
            success, path = party_ledger_service.export_party_ledger_to_csv(
                self.current_report_data, "party_ledger")
        else:
            success, path = party_ledger_service.export_party_summary_to_csv(
                self.current_report_data, "party_summary")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        if self.report_type_var.get() == "Ledger":
            widget = self.ledger_table
            filename = "party_ledger"
        else:
            widget = self.summary_table
            filename = "party_summary"
        success, path = report_exporter.export_table_to_png(widget, filename)
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        report_type = self.report_type_var.get().lower()
        success, path = report_exporter.export_to_json(
            self.current_report_data, f"party_{report_type}")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_party_ledger_report(parent: tk.Widget, company_id: int) -> PartyLedgerReportUI:
    return PartyLedgerReportUI(parent, company_id)
