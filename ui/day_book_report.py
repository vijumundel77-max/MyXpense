"""
Expenzo — Day Book Report (Voucher Register)
Shows every voucher detail line in a date range with type filters.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.voucher_register_service import voucher_register_service
from services.voucher_service import VOUCHER_TYPES
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


class DayBookReportUI:
    """Day Book (voucher register) report screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ReportHeader(self.main_frame, "Day Book", "Voucher register")

        filters = FilterBar(self.main_frame)
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.type_var = tk.StringVar(value="All Types")
        self.search_var = tk.StringVar()

        filters.add("From Date", make_date_entry(filters.body, self.from_date_var))
        filters.add("To Date", make_date_entry(filters.body, self.to_date_var))
        filters.add(
            "Type",
            make_readonly_combo(filters.body, ["All Types"] + list(VOUCHER_TYPES), self.type_var, 150),
        )
        filters.add("Search", ctk.CTkEntry(
            filters.body, textvariable=self.search_var, width=180,
            corner_radius=config.INPUT_CORNER_RADIUS))
        make_button(filters.body, "Generate", self._generate_report, accent=True).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export CSV", self._export_to_csv).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export JSON", self._export_to_json).pack(
            side="left", padx=(0, config.SPACING_SM))
        make_button(filters.body, "Export PNG", self._export_to_png, width=100).pack(side="left")

        columns = [
            {"id": "date", "heading": "Date", "width": 100},
            {"id": "number", "heading": "Voucher No.", "width": 110},
            {"id": "type", "heading": "Type", "width": 90},
            {"id": "reference", "heading": "Reference", "width": 120},
            {"id": "account", "heading": "Account", "width": 180},
            {"id": "narration", "heading": "Narration", "width": 220},
            {"id": "debit", "heading": "Debit", "width": 110, "anchor": "e"},
            {"id": "credit", "heading": "Credit", "width": 110, "anchor": "e"},
        ]
        self.table = ReportTable(self.main_frame, columns)
        self.table.show_empty("Select dates and generate the Day Book to begin.")

        self.status = ReportStatusBar(self.main_frame)

    def _parse_date(self, raw: str) -> Optional[date]:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return None

    def _generate_report(self) -> None:
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Day Book", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Day Book", "From Date cannot be after To Date.", parent=self.parent)
            return
        report = voucher_register_service.generate_day_book(
            self.company_id,
            from_date,
            to_date,
            voucher_type="" if self.type_var.get() == "All Types" else self.type_var.get(),
            search_term=self.search_var.get().strip(),
        )
        if not report.get('success'):
            dialogs.error("Day Book", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        self.table.hide_empty()
        rows = []
        for entry in report.get('entries', []):
            rows.append((
                entry.get('voucher_date', ''),
                entry.get('voucher_number', ''),
                entry.get('voucher_type', ''),
                entry.get('reference_number', ''),
                entry.get('account_name', ''),
                entry.get('detail_narration', '') or entry.get('narration', ''),
                f"{entry.get('debit_amount', 0):,.2f}",
                f"{entry.get('credit_amount', 0):,.2f}",
            ))
        self.table.set_rows(rows)
        totals = report.get('totals', {})
        self.table.set_totals(
            f"Total Debit: {totals.get('debit', 0):,.2f}    "
            f"Total Credit: {totals.get('credit', 0):,.2f}    "
            f"({report.get('entry_count', 0)} lines)"
        )
        self.status.set(
            f"Day Book generated: {report.get('entry_count', 0)} lines "
            f"({report.get('from_date', '')} to {report.get('to_date', '')})"
        )

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "day_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = voucher_register_service.export_day_book_to_csv(
            self.current_report_data, "day_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_to_json(self.current_report_data, "day_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_day_book_report(parent: tk.Widget, company_id: int) -> DayBookReportUI:
    return DayBookReportUI(parent, company_id)
