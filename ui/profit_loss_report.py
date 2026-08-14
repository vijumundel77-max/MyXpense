"""
Expenzo — Profit & Loss Report
Total Income vs Total Expense with Net Profit/Loss for a date range.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.profit_loss_service import profit_loss_service
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


class ProfitLossReportUI:
    """Profit & Loss report screen (Expenzo voucher data)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL,
                             pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Profit & Loss",
                         "Income vs Expense for the period", on_back=self._back)

        filters = FilterBar(self.main_frame)
        self.from_date_var = tk.StringVar(
            value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(
            value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var = tk.StringVar()

        filters.add("From Date", make_date_picker(filters.body, self.from_date_var))
        filters.add("To Date", make_date_picker(filters.body, self.to_date_var))
        self.search_entry = ctk.CTkEntry(
            filters.body, textvariable=self.search_var, width=200,
            placeholder_text="Search account...",
            corner_radius=config.INPUT_CORNER_RADIUS, height=30)
        filters.add("Search", self.search_entry)
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        columns = [
            {"id": "particulars", "heading": "Particulars", "width": 300},
            {"id": "debit", "heading": "Debit", "width": 140, "anchor": "e"},
            {"id": "credit", "heading": "Credit", "width": 140, "anchor": "e"},
        ]
        self.table = ReportTable(self.main_frame, columns)
        self.table.show_empty("Select dates and generate the Profit & Loss to begin.")

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
        wire_report_keyboard(self)

    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _clear_filters(self) -> None:
        self.from_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var.set("")
        self.table.show_empty("Select dates and generate the Profit & Loss to begin.")
        self.status.set("Filters cleared")

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _generate_report(self) -> None:
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Profit & Loss", "Invalid date. Use DD-MM-YYYY format.",
                         parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Profit & Loss", "From Date cannot be after To Date.",
                         parent=self.parent)
            return
        report = profit_loss_service.generate_profit_loss(
            self.company_id, from_date, to_date)
        if not report.get('success'):
            dialogs.error("Profit & Loss",
                          report.get('error', 'Failed to generate report'),
                          parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        self.table.hide_empty()
        search = self.search_var.get().strip().lower()
        rows = []

        def _match(row: Dict[str, Any]) -> bool:
            if not search:
                return True
            return (search in str(row.get('account_name', '')).lower()
                    or search in str(row.get('account_code', '')).lower()
                    or search in str(row.get('account_group', '')).lower())

        income_rows = [r for r in report.get('income_rows', []) if _match(r)]
        expense_rows = [r for r in report.get('expense_rows', []) if _match(r)]

        if income_rows:
            rows.append(("INCOME", "", ""))
            for row in income_rows:
                rows.append((
                    f"    {row.get('account_name', '')}",
                    "",
                    f"{row.get('credit', 0):,.2f}",
                ))
            rows.append(("    Total Income", "",
                         f"{sum(r.get('credit', 0) for r in income_rows):,.2f}"))
        if expense_rows:
            rows.append(("EXPENSE", "", ""))
            for row in expense_rows:
                rows.append((
                    f"    {row.get('account_name', '')}",
                    f"{row.get('debit', 0):,.2f}",
                    "",
                ))
            rows.append(("    Total Expense",
                         f"{sum(r.get('debit', 0) for r in expense_rows):,.2f}", ""))

        self.table.set_rows(rows)
        net = report.get('net_profit_loss', 0)
        net_label = "Net Profit" if report.get('is_profit', True) else "Net Loss"
        self.table.set_totals(
            f"Income: {report.get('income_total', 0):,.2f}   |   "
            f"Expense: {report.get('expense_total', 0):,.2f}   |   "
            f"{net_label}: {abs(net):,.2f}"
        )
        self.status.set(
            f"Profit & Loss generated for "
            f"{report.get('from_date', '')} to {report.get('to_date', '')} "
            f"({len(income_rows) + len(expense_rows)} accounts)"
        )

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "profit_loss")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = profit_loss_service.export_profit_loss_to_csv(
            self.current_report_data, "profit_loss")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_to_json(self.current_report_data,
                                                       "profit_loss")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_profit_loss_report(parent: tk.Widget, company_id: int) -> ProfitLossReportUI:
    return ProfitLossReportUI(parent, company_id)
