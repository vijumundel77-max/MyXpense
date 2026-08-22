"""
Expenzo — Outstanding Report
Receivables / payables outstanding with ageing summary and overdue invoices.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.outstanding_report_service import outstanding_report_service
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

OUTSTANDING_TYPES = ("Receivable", "Payable", "All")
REPORT_TYPES = ("Outstanding", "Ageing Summary", "Overdue Invoices")


class OutstandingReportUI:
    """Outstanding report screen (Expenzo voucher data)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Outstanding Report", "Receivables, payables and ageing",
                         on_back=self._back)

        filters = FilterBar(self.main_frame)
        self.report_type_var = tk.StringVar(value="Outstanding")
        self.outstanding_type_var = tk.StringVar(value="Receivable")
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.include_zero_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self._search_debouncer = Debouncer(self.main_frame, delay_ms=250)

        self.report_type_combo = make_readonly_combo(filters.body, list(REPORT_TYPES), self.report_type_var, 160)
        filters.add("Report", self.report_type_combo)
        self.outstanding_type_combo = make_readonly_combo(filters.body, list(OUTSTANDING_TYPES), self.outstanding_type_var, 130)
        filters.add("Type", self.outstanding_type_combo)
        filters.add("As On Date", make_date_picker(filters.body, self.as_on_date_var))
        ctk.CTkCheckBox(
            filters.body, text="Include zero balance", variable=self.include_zero_var,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=6, columnspan=3, sticky="w", padx=(0, config.SPACING_LG),
               pady=(config.SPACING_XS, config.SPACING_XS))
        self.search_entry = ctk.CTkEntry(filters.body, textvariable=self.search_var, width=180,
                                         corner_radius=config.INPUT_CORNER_RADIUS, height=30)
        filters.add("Search", self.search_entry)
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        self.outstanding_table = ReportTable(self.main_frame, [
            {"id": "code", "heading": "Code", "width": 100},
            {"id": "name", "heading": "Party Name", "width": 220},
            {"id": "group", "heading": "Group", "width": 150},
            {"id": "outstanding", "heading": "Outstanding Amount", "width": 150, "anchor": "e"},
            {"id": "type", "heading": "Type", "width": 90, "anchor": "center"},
            {"id": "invoices", "heading": "Invoices", "width": 80, "anchor": "center"},
        ])
        self.outstanding_table.show_empty("Generate the outstanding report to begin.")
        self.outstanding_table.tree.bind("<Double-1>", self._on_party_double_click)

        self.ageing_table = ReportTable(self.main_frame, [
            {"id": "bucket", "heading": "Ageing Bucket", "width": 180},
            {"id": "amount", "heading": "Amount", "width": 160, "anchor": "e"},
        ])
        self.ageing_table.show_empty("Generate the ageing summary to begin.")
        self.ageing_table.pack_forget()

        self.overdue_table = ReportTable(self.main_frame, [
            {"id": "code", "heading": "Party Code", "width": 100},
            {"id": "name", "heading": "Party Name", "width": 180},
            {"id": "number", "heading": "Voucher No.", "width": 120},
            {"id": "date", "heading": "Invoice Date", "width": 100},
            {"id": "due", "heading": "Due Date", "width": 100},
            {"id": "amount", "heading": "Amount", "width": 120, "anchor": "e"},
            {"id": "days", "heading": "Overdue Days", "width": 100, "anchor": "center"},
        ])
        self.overdue_table.show_empty("Generate the overdue report to begin.")
        self.overdue_table.pack_forget()

        self.status = ReportStatusBar(self.main_frame)

        ReportActionBar(
            self.main_frame,
            refresh=self._generate_report,
            exports=[("Export CSV", self._export_to_csv),
                     ("Export JSON", self._export_to_json),
                     ("Export PNG", self._export_to_png)],
            clear=self._clear_filters,
            back=self._back,
        )

        self.report_type_combo.configure(command=lambda _: self._on_report_type_changed())
        self.search_entry.bind("<KeyRelease>", lambda _e: self._search_debouncer.schedule(self._on_search_changed))
        wire_report_keyboard(self)

    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def on_global_single_date(self, day) -> None:
        """Global F2 hook: set the As-On date and regenerate."""
        try:
            self.as_on_date_var.set(day.strftime(config.DISPLAY_DATE_FORMAT))
            self._generate_report()
        except Exception:
            pass

    def on_global_date_period(self, from_date, to_date) -> None:
        """Global Alt+F2 hook: use the period's end date as As-On, regenerate."""
        try:
            self.as_on_date_var.set(to_date.strftime(config.DISPLAY_DATE_FORMAT))
            self._generate_report()
        except Exception:
            pass

    def _clear_filters(self) -> None:
        self.report_type_var.set("Outstanding")
        self.outstanding_type_var.set("Receivable")
        self.as_on_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.include_zero_var.set(False)
        self.search_var.set("")
        self.outstanding_table.show_empty("Generate the outstanding report to begin.")
        self.ageing_table.show_empty("Generate the ageing summary to begin.")
        self.overdue_table.show_empty("Generate the overdue report to begin.")
        self._on_report_type_changed()
        self.status.set("Filters cleared")

    def _on_report_type_changed(self) -> None:
        report_type = self.report_type_var.get()
        self.outstanding_table.pack_forget()
        self.ageing_table.pack_forget()
        self.overdue_table.pack_forget()
        if report_type == "Outstanding":
            self.outstanding_table.pack(fill="both", expand=True)
        elif report_type == "Ageing Summary":
            self.ageing_table.pack(fill="both", expand=True)
        else:
            self.overdue_table.pack(fill="both", expand=True)

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _generate_report(self) -> None:
        report_type = self.report_type_var.get()
        if report_type == "Outstanding":
            self._generate_outstanding()
        elif report_type == "Ageing Summary":
            self._generate_ageing_summary()
        else:
            self._generate_overdue()

    def _generate_outstanding(self) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Outstanding", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        report = outstanding_report_service.generate_outstanding_report(
            self.company_id, self.outstanding_type_var.get(), as_on, self.include_zero_var.get())
        if not report.get('success'):
            dialogs.error("Outstanding", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render_outstanding(report)

    def _render_outstanding(self, report: Dict[str, Any]) -> None:
        self.ageing_table.pack_forget()
        self.overdue_table.pack_forget()
        self.outstanding_table.pack(fill="both", expand=True)
        self.outstanding_table.hide_empty()
        rows = []
        for party in report.get('parties', []):
            rows.append((
                party.get('account_code', ''),
                party.get('account_name', ''),
                party.get('account_group', ''),
                f"{party.get('outstanding_balance', 0):,.2f}",
                party.get('balance_type', ''),
                party.get('invoice_count', 0),
            ))
        self.outstanding_table.set_rows(rows)
        totals = report.get('totals', {})
        self.outstanding_table.set_totals(
            f"Total Outstanding: {totals.get('total_outstanding', 0):,.2f}   |   "
            f"Receivable: {totals.get('total_receivable', 0):,.2f}   |   "
            f"Payable: {totals.get('total_payable', 0):,.2f}   |   "
            f"Parties: {report.get('party_count', 0)}"
        )
        self.status.set(f"Outstanding report generated: {report.get('party_count', 0)} parties")

    def _generate_ageing_summary(self) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Outstanding", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        report = outstanding_report_service.generate_ageing_summary(
            self.company_id, self.outstanding_type_var.get(), as_on)
        if not report.get('success'):
            dialogs.error("Outstanding", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render_ageing(report)

    def _render_ageing(self, report: Dict[str, Any]) -> None:
        self.outstanding_table.pack_forget()
        self.overdue_table.pack_forget()
        self.ageing_table.pack(fill="both", expand=True)
        self.ageing_table.hide_empty()
        rows = [(name, f"{amount:,.2f}") for name, amount in report.get('ageing_buckets', {}).items()]
        self.ageing_table.set_rows(rows)
        self.ageing_table.set_totals(
            f"Total Outstanding: {report.get('total_outstanding', 0):,.2f}   |   "
            f"Parties: {report.get('party_count', 0)}"
        )
        self.status.set("Ageing summary generated")

    def _generate_overdue(self) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Outstanding", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        report = outstanding_report_service.get_overdue_invoices(
            self.company_id, self.outstanding_type_var.get(), as_on)
        if not report.get('success'):
            dialogs.error("Outstanding", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render_overdue(report)

    def _render_overdue(self, report: Dict[str, Any]) -> None:
        self.outstanding_table.pack_forget()
        self.ageing_table.pack_forget()
        self.overdue_table.pack(fill="both", expand=True)
        self.overdue_table.hide_empty()
        rows = []
        for party in report.get('parties', []):
            for invoice in party.get('invoices', []):
                rows.append((
                    party.get('account_code', ''),
                    party.get('account_name', ''),
                    invoice.get('voucher_number', ''),
                    invoice.get('voucher_date', ''),
                    invoice.get('due_date', 'N/A'),
                    f"{invoice.get('outstanding_amount', 0):,.2f}",
                    invoice.get('overdue_days', 0),
                ))
        self.overdue_table.set_rows(rows)
        self.overdue_table.set_totals(
            f"Total Overdue: {report.get('total_overdue', 0):,.2f}   |   "
            f"Overdue Invoices: {report.get('invoice_count', 0)}"
        )
        self.status.set(f"Overdue report generated: {report.get('invoice_count', 0)} invoices")

    def _on_party_double_click(self, event=None) -> None:
        selection = self.outstanding_table.tree.selection()
        if not selection:
            return
        if not self.current_report_data or self.report_type_var.get() != "Outstanding":
            return
        values = self.outstanding_table.tree.item(selection[0])['values']
        if not values:
            return
        party_code = values[0]
        party = next(
            (p for p in self.current_report_data.get('parties', [])
             if p.get('account_code') == party_code),
            None)
        if party:
            self._show_invoice_details(party)

    def _show_invoice_details(self, party: Dict[str, Any]) -> None:
        popup = tk.Toplevel(self.parent)
        popup.title(f"Invoice Details — {party.get('account_name', '')}")
        popup.geometry("900x500")
        popup.configure(bg=config.COLOR_BG_PRIMARY)

        ctk.CTkLabel(
            popup,
            text=f"Party: {party.get('account_name', '')} ({party.get('account_code', '')})\n"
                 f"Outstanding: {party.get('outstanding_balance', 0):,.2f} {party.get('balance_type', '')}",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        columns = ("number", "date", "due", "amount", "ageing_days", "ageing_category")
        tree = ttk.Treeview(popup, columns=columns, show="headings")
        for col, heading, width in [
            ("number", "Voucher No.", 130),
            ("date", "Date", 110),
            ("due", "Due Date", 110),
            ("amount", "Amount", 130),
            ("ageing_days", "Ageing Days", 110),
            ("ageing_category", "Ageing Category", 150),
        ]:
            tree.heading(col, text=heading)
            tree.column(col, width=width, anchor="e" if col == "amount" else "w")
        tree.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        for invoice in party.get('invoices', []):
            tree.insert("", tk.END, values=(
                invoice.get('voucher_number', ''),
                invoice.get('voucher_date', ''),
                invoice.get('due_date', 'N/A'),
                f"{invoice.get('outstanding_amount', 0):,.2f}",
                invoice.get('ageing_days', 0),
                invoice.get('ageing_category', ''),
            ))
        ctk.CTkButton(
            popup, text="Close", width=90, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=popup.destroy,
        ).pack(pady=config.SPACING_MD)

    def _on_search_changed(self, *args) -> None:
        if not self.current_report_data:
            return
        search = self.search_var.get().strip()
        if not search:
            self._display_current()
            return
        filtered = outstanding_report_service.search_parties(self.current_report_data, search)
        if filtered.get('success'):
            self._display(filtered)
            self.status.set(f"Found {filtered.get('party_count', 0)} parties")

    def _display_current(self) -> None:
        if self.current_report_data:
            self._display(self.current_report_data)

    def _display(self, report: Dict[str, Any]) -> None:
        report_type = report.get('report_type', '')
        if 'Outstanding Report' in report_type:
            self._render_outstanding(report)
        elif 'Ageing Summary' in report_type:
            self._render_ageing(report)
        elif 'Overdue' in report_type:
            self._render_overdue(report)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = outstanding_report_service.export_outstanding_report_to_csv(
            self.current_report_data, "outstanding_report")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        report_type = self.report_type_var.get()
        if report_type == "Outstanding":
            widget, filename = self.outstanding_table, "outstanding_report"
        elif report_type == "Ageing Summary":
            widget, filename = self.ageing_table, "ageing_summary"
        else:
            widget, filename = self.overdue_table, "overdue_invoices"
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
        report_type = self.current_report_data.get('report_type', 'outstanding')
        filename = report_type.lower().replace(' ', '_')
        success, path = report_exporter.export_to_json(self.current_report_data, filename)
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_outstanding_report(parent: tk.Widget, company_id: int) -> OutstandingReportUI:
    return OutstandingReportUI(parent, company_id)
