"""
Expenzo — Trial Balance Report
Per-account debit/credit balances as of a date from Expenzo voucher data.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.trial_balance_service import trial_balance_service
from ui.report_base import (
    ReportBackHeader,
    FilterBar,
    ReportTable,
    ReportStatusBar,
    ReportActionBar,
    make_date_picker,
    make_button,
    wire_report_keyboard,
)
from utils import dialogs
from utils.debounce import Debouncer


class TrialBalanceReportUI:
    """Trial Balance report screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Trial Balance", "Debit and credit balances as of a date",
                         on_back=self._back)

        filters = FilterBar(self.main_frame)
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var = tk.StringVar()
        self._search_debouncer = Debouncer(self.main_frame, delay_ms=250)

        filters.add("As On Date", make_date_picker(filters.body, self.as_on_date_var))
        self.search_entry = ctk.CTkEntry(filters.body, textvariable=self.search_var, width=200,
                                         corner_radius=config.INPUT_CORNER_RADIUS, height=30)
        filters.add("Search", self.search_entry)
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        self.table = ReportTable(self.main_frame, [
            {"id": "code", "heading": "Code", "width": 110},
            {"id": "account", "heading": "Account", "width": 220},
            {"id": "group", "heading": "Group", "width": 180},
            {"id": "debit", "heading": "Debit", "width": 140, "anchor": "e"},
            {"id": "credit", "heading": "Credit", "width": 140, "anchor": "e"},
        ])
        self.table.show_empty("Select a date and generate the Trial Balance to begin.")

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
        self.search_entry.bind("<KeyRelease>", lambda _e: self._search_debouncer.schedule(self._on_search_changed))
        wire_report_keyboard(self)

    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _clear_filters(self) -> None:
        self.as_on_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var.set("")
        self.table.show_empty("Select a date and generate the Trial Balance to begin.")
        self.status.set("Filters cleared")

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _generate_report(self) -> None:
        as_on = self._parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Trial Balance", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        report = trial_balance_service.generate_trial_balance(self.company_id, as_on)
        if not report.get('success'):
            dialogs.error("Trial Balance", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        self.table.hide_empty()
        rows = []
        for row in report.get('rows', []):
            rows.append((
                row.get('account_code', ''),
                row.get('account_name', ''),
                row.get('account_group', ''),
                f"{row.get('debit', 0):,.2f}",
                f"{row.get('credit', 0):,.2f}",
            ))
        self.table.set_rows(rows)
        totals = report.get('totals', {})
        balanced = report.get('is_balanced', False)
        status_text = "Balanced ✓" if balanced else "NOT balanced ✗"
        self.table.set_totals(
            f"Total Debit: {totals.get('debit', 0):,.2f}   |   "
            f"Total Credit: {totals.get('credit', 0):,.2f}   |   "
            f"{status_text}"
        )
        self.status.set(
            f"Trial Balance as of {report.get('as_on_date', '')}: "
            f"{report.get('row_count', 0)} accounts — {status_text}")

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "trial_balance")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _on_search_changed(self, *args) -> None:
        if not self.current_report_data:
            return
        filtered = trial_balance_service.search_rows(
            self.current_report_data, self.search_var.get().strip())
        self._render(filtered)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = trial_balance_service.export_trial_balance_to_csv(
            self.current_report_data, "trial_balance")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_to_json(self.current_report_data, "trial_balance")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_trial_balance_report(parent: tk.Widget, company_id: int) -> TrialBalanceReportUI:
    return TrialBalanceReportUI(parent, company_id)
