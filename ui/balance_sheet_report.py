"""
Expenzo — Balance Sheet Report
Assets = Liabilities + Capital, as of a date, from Expenzo voucher data.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.balance_sheet_service import (
    balance_sheet_service,
    TYPE_ASSETS,
    TYPE_LIABILITIES,
    TYPE_CAPITAL,
)
from ui.report_base import (
    ReportHeader,
    FilterBar,
    ReportStatusBar,
    make_date_entry,
    make_button,
)
from utils import dialogs


class BalanceSheetReportUI:
    """Balance Sheet report screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportHeader(self.main_frame, "Balance Sheet", "Assets = Liabilities + Capital")

        filters = FilterBar(self.main_frame)
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        filters.add("As On Date", make_date_entry(filters.body, self.as_on_date_var))
        make_button(filters.body, "Generate", self._generate_report, accent=True).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export CSV", self._export_to_csv).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export JSON", self._export_to_json).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export PNG", self._export_to_png, width=100).pack(side="left")

        # Side-by-side layout: Liabilities & Capital | Assets
        self.body = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        self.left_frame = self._build_section(
            self.body, "Liabilities & Capital", [TYPE_LIABILITIES, TYPE_CAPITAL])
        self.left_frame.pack(side="left", fill="both", expand=True, padx=(0, config.SPACING_MD))

        self.right_frame = self._build_section(self.body, "Assets", [TYPE_ASSETS])
        self.right_frame.pack(side="left", fill="both", expand=True, padx=(config.SPACING_MD, 0))

        self.status = ReportStatusBar(self.main_frame)

    def _build_section(self, parent, title: str, section_keys) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        frame.pack_propagate(False)

        ctk.CTkLabel(
            frame, text=title, font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        tree_frame = ctk.CTkFrame(frame, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        columns = ("account", "amount")
        tree = tk.ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("account", text="Account")
        tree.heading("amount", text="Amount")
        tree.column("account", width=220, anchor="w")
        tree.column("amount", width=130, anchor="e")
        vsb = tk.ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        total_label = ctk.CTkLabel(
            frame, text="Total: ₹ 0.00", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="w",
        )
        total_label.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))

        setattr(frame, "_tree", tree)
        setattr(frame, "_total_label", total_label)
        setattr(frame, "_section_keys", section_keys)
        return frame

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _generate_report(self) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Balance Sheet", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        report = balance_sheet_service.generate_balance_sheet(self.company_id, as_on)
        if not report.get('success'):
            dialogs.error("Balance Sheet", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        sections = report.get('sections', {})
        totals = report.get('totals', {})

        # Left: Liabilities & Capital (with section sub-headers)
        tree = self.left_frame._tree
        for item in tree.get_children():
            tree.delete(item)
        for section_key, heading in [
            (TYPE_LIABILITIES, "Liabilities"),
            (TYPE_CAPITAL, "Capital & Equity"),
        ]:
            entries = sections.get(section_key, [])
            if entries:
                tree.insert("", tk.END, values=(heading, ""), tags=("header",))
                for entry in entries:
                    tree.insert("", tk.END, values=(
                        entry.get('account_name', ''),
                        f"{entry.get('net_balance', 0):,.2f}",
                    ), tags=("even",))
        self.left_frame._total_label.configure(
            text=f"Total: ₹ {totals.get('total_liabilities_capital', 0):,.2f}")

        # Right: Assets
        tree = self.right_frame._tree
        for item in tree.get_children():
            tree.delete(item)
        for entry in sections.get(TYPE_ASSETS, []):
            tree.insert("", tk.END, values=(
                entry.get('account_name', ''),
                f"{entry.get('net_balance', 0):,.2f}",
            ), tags=("even",))
        self.right_frame._total_label.configure(
            text=f"Total: ₹ {totals.get('total_assets', 0):,.2f}")

        balanced = report.get('is_balanced', False)
        status_text = "Balanced ✓" if balanced else "NOT balanced ✗"
        self.status.set(
            f"Balance Sheet as of {report.get('as_on_date', '')} — "
            f"Assets {totals.get('total_assets', 0):,.2f} = "
            f"Liab+Capital {totals.get('total_liabilities_capital', 0):,.2f} — {status_text}")

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.body, "balance_sheet")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = balance_sheet_service.export_balance_sheet_to_csv(
            self.current_report_data, "balance_sheet")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_to_json(self.current_report_data, "balance_sheet")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_balance_sheet_report(parent: tk.Widget, company_id: int) -> BalanceSheetReportUI:
    return BalanceSheetReportUI(parent, company_id)
