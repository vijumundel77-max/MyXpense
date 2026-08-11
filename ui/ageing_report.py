"""
Expenzo — Ageing Report
Ageing buckets with FIFO payment allocation, from Expenzo voucher data.
"""
from __future__ import annotations

import re
import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk

import config
from services.ageing_report_service import ageing_report_service
from ui.report_base import (
    ReportHeader,
    FilterBar,
    ReportStatusBar,
    make_date_entry,
    make_readonly_combo,
    make_button,
)
from utils import dialogs

AGEING_TYPES = ("Receivable", "Payable")
DEFAULT_BUCKETS_STRING = "0-30, 31-60, 61-90, 91-180, 181-999"


class AgeingReportUI:
    """Ageing report screen (Expenzo voucher data, FIFO allocation)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportHeader(self.main_frame, "Ageing Report", "Ageing buckets with FIFO allocation")

        filters = FilterBar(self.main_frame)
        self.ageing_type_var = tk.StringVar(value="Receivable")
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.use_custom_buckets_var = tk.BooleanVar(value=False)
        self.custom_buckets_var = tk.StringVar(value=DEFAULT_BUCKETS_STRING)
        self.search_var = tk.StringVar()

        self.ageing_type_combo = make_readonly_combo(filters.body, list(AGEING_TYPES), self.ageing_type_var, 130)
        filters.add("Ageing Type", self.ageing_type_combo)
        filters.add("As On Date", make_date_entry(filters.body, self.as_on_date_var))
        ctk.CTkCheckBox(
            filters.body, text="Custom buckets", variable=self.use_custom_buckets_var,
            command=self._toggle_custom_buckets, font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, config.SPACING_LG))

        self.custom_buckets_entry = ctk.CTkEntry(
            filters.body, textvariable=self.custom_buckets_var, width=240,
            corner_radius=config.INPUT_CORNER_RADIUS)
        self.custom_buckets_entry.pack(side="left", padx=(0, config.SPACING_LG))
        self.custom_buckets_entry.pack_forget()

        self.search_entry = ctk.CTkEntry(filters.body, textvariable=self.search_var, width=150,
                                         corner_radius=config.INPUT_CORNER_RADIUS)
        filters.add("Search", self.search_entry)
        make_button(filters.body, "Generate", self._generate_report, accent=True).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export CSV", self._export_to_csv).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export JSON", self._export_to_json).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export PNG", self._export_to_png, width=100).pack(side="left")

        # Dynamic-column table (buckets change per report).
        self.table = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        self.table.pack(fill="both", expand=True)
        self.table.pack_propagate(False)

        self.totals_label = ctk.CTkLabel(
            self.table, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY, anchor="w",
        )
        self.totals_label.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_MD, config.SPACING_SM))

        tree_frame = ctk.CTkFrame(self.table, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)
        self.ageing_tree = tk.ttk.Treeview(tree_frame, show="headings", selectmode="browse")
        vsb = tk.ttk.Scrollbar(tree_frame, orient="vertical", command=self.ageing_tree.yview)
        hsb = tk.ttk.Scrollbar(tree_frame, orient="horizontal", command=self.ageing_tree.xview)
        self.ageing_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.ageing_tree.pack(side="left", fill="both", expand=True,
                              padx=(config.SPACING_LG, 0), pady=(0, config.SPACING_LG))
        vsb.pack(side="right", fill="y", pady=(0, config.SPACING_LG))
        hsb.pack(side="bottom", fill="x")
        self.ageing_tree.bind("<Double-1>", self._on_party_double_click)

        self.status = ReportStatusBar(self.main_frame)
        self.search_entry.bind("<KeyRelease>", lambda _e: self._on_search_changed())

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _toggle_custom_buckets(self) -> None:
        if self.use_custom_buckets_var.get():
            self.custom_buckets_entry.pack(
                side="left", padx=(0, config.SPACING_LG))
        else:
            self.custom_buckets_entry.pack_forget()

    @staticmethod
    def _bucket_upper_bound(bucket_name: str) -> Optional[int]:
        name = bucket_name.strip()
        if name.lower().startswith('above'):
            match = re.search(r'(\d+)', name)
            return int(match.group(1)) if match else None
        match = re.search(r'-(\d+)', name)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_custom_buckets(bucket_string: str) -> List[Tuple[int, int, str]]:
        buckets: List[Tuple[int, int, str]] = []
        parts = [p.strip() for p in bucket_string.split(',')]
        for part in parts:
            if '-' not in part:
                raise ValueError(f"Invalid bucket format: {part}")
            min_val, max_val = part.split('-')
            min_val = int(min_val.strip())
            max_val = int(max_val.strip())
            if min_val >= max_val:
                raise ValueError(f"Invalid range: {min_val}-{max_val}")
            bucket_name = f"{min_val}-{max_val} days" if max_val < 999 else f"Above {min_val} days"
            buckets.append((min_val, max_val, bucket_name))
        return buckets

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    # generation
    # ------------------------------------------------------------------ #
    def _generate_report(self) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Ageing", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        custom_buckets = None
        if self.use_custom_buckets_var.get():
            try:
                custom_buckets = self._parse_custom_buckets(self.custom_buckets_var.get())
            except ValueError as exc:
                dialogs.error("Ageing", str(exc), parent=self.parent)
                return
        report = ageing_report_service.generate_ageing_report(
            self.company_id, self.ageing_type_var.get(), as_on, custom_buckets)
        if not report.get('success'):
            dialogs.error("Ageing", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        buckets = report.get('buckets', [])
        columns = ['code', 'name'] + buckets + ['total']
        self.ageing_tree.configure(columns=columns)
        self.ageing_tree.heading('code', text='Code')
        self.ageing_tree.heading('name', text='Party Name')
        for bucket in buckets:
            self.ageing_tree.heading(bucket, text=bucket)
        self.ageing_tree.heading('total', text='Total')
        self.ageing_tree.column('code', width=100)
        self.ageing_tree.column('name', width=200)
        for bucket in buckets:
            self.ageing_tree.column(bucket, width=120, anchor='e')
        self.ageing_tree.column('total', width=120, anchor='e')

        for item in self.ageing_tree.get_children():
            self.ageing_tree.delete(item)

        for party in report.get('parties', []):
            values = [party.get('account_code', ''), party.get('account_name', '')]
            for bucket in buckets:
                values.append(f"{party.get('buckets', {}).get(bucket, 0):,.2f}")
            values.append(f"{party.get('total', 0):,.2f}")
            self.ageing_tree.insert("", tk.END, values=values)

        total_values = ['', 'TOTAL']
        for bucket in buckets:
            total_values.append(f"{report.get('totals', {}).get(bucket, 0):,.2f}")
        total_values.append(f"{report.get('grand_total', 0):,.2f}")
        total_item = self.ageing_tree.insert("", tk.END, values=total_values)
        self.ageing_tree.item(total_item, tags=('total',))

        self.totals_label.configure(
            text=f"As on: {report.get('as_on_date', '')}   |   "
                 f"Type: {report.get('ageing_type', '')}   |   "
                 f"Parties: {report.get('party_count', 0)}   |   "
                 f"Grand Total: {report.get('grand_total', 0):,.2f}"
        )
        self.status.set(f"Ageing report generated: {report.get('party_count', 0)} parties")

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "ageing_report")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    # ------------------------------------------------------------------ #
    # interactions
    # ------------------------------------------------------------------ #
    def _on_party_double_click(self, event=None) -> None:
        selection = self.ageing_tree.selection()
        if not selection:
            return
        item = selection[0]
        if self.ageing_tree.item(item, 'tags') and 'total' in self.ageing_tree.item(item, 'tags'):
            return
        if not self.current_report_data:
            return
        values = self.ageing_tree.item(item, 'values')
        if not values:
            return
        party_code = values[0]
        party = next(
            (p for p in self.current_report_data.get('parties', [])
             if p.get('account_code') == party_code),
            None)
        if party:
            self._show_party_ageing_details(party)

    def _show_party_ageing_details(self, party: Dict[str, Any]) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            return
        details = ageing_report_service.get_party_ageing_details(
            self.company_id, party.get('account_id'), self.ageing_type_var.get(), as_on)
        if not details.get('success'):
            dialogs.error("Ageing", details.get('error', 'Failed to get details'), parent=self.parent)
            return
        self._show_details_popup(details)

    def _show_details_popup(self, details: Dict[str, Any]) -> None:
        popup = tk.Toplevel(self.parent)
        popup.title(f"Ageing Details — {details.get('account', {}).get('name', '')}")
        popup.geometry("1000x600")
        popup.configure(bg=config.COLOR_BG_PRIMARY)

        account = details.get('account', {})
        ctk.CTkLabel(
            popup,
            text=f"Party: {account.get('name', '')} ({account.get('code', '')})\n"
                 f"Total Outstanding: {details.get('total', 0):,.2f}",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        columns = ("number", "type", "date", "due", "amount", "days", "bucket")
        tree = tk.ttk.Treeview(popup, columns=columns, show="headings")
        for col, heading, width in [
            ("number", "Voucher No.", 130),
            ("type", "Type", 110),
            ("date", "Date", 100),
            ("due", "Due Date", 100),
            ("amount", "Outstanding", 120),
            ("days", "Ageing Days", 100),
            ("bucket", "Ageing Bucket", 150),
        ]:
            tree.heading(col, text=heading)
            tree.column(col, width=width, anchor="e" if col == "amount" else "w")
        tree.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        for invoice in details.get('invoices', []):
            tree.insert("", tk.END, values=(
                invoice.get('voucher_number', ''),
                invoice.get('voucher_type', 'Invoice'),
                invoice.get('voucher_date', ''),
                invoice.get('due_date', 'N/A'),
                f"{invoice.get('outstanding_amount', 0):,.2f}",
                invoice.get('ageing_days', 0),
                invoice.get('ageing_bucket', ''),
            ))
        ctk.CTkLabel(
            popup,
            text=f"Total Invoices: {details.get('invoice_count', 0)}   |   "
                 f"Total Outstanding: {details.get('total', 0):,.2f}",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=config.SPACING_LG, pady=config.SPACING_MD)
        ctk.CTkButton(
            popup, text="Close", width=90, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=popup.destroy,
        ).pack(side="right", padx=config.SPACING_LG, pady=config.SPACING_MD)

    def _on_search_changed(self, *args) -> None:
        if not self.current_report_data:
            return
        search = self.search_var.get().strip()
        if not search:
            self._render(self.current_report_data)
            return
        filtered = ageing_report_service.search_parties(self.current_report_data, search)
        if filtered.get('success'):
            self._render(filtered)
            self.status.set(f"Found {filtered.get('party_count', 0)} parties")

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = ageing_report_service.export_ageing_report_to_csv(
            self.current_report_data, "ageing_report")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_to_json(self.current_report_data, "ageing_report")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_ageing_report(parent: tk.Widget, company_id: int) -> AgeingReportUI:
    return AgeingReportUI(parent, company_id)
