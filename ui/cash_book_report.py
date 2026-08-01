"""
Cash Book Report UI
Tkinter-based UI for Cash Book report.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date, datetime
from typing import Any, Dict, Optional

import config
from services.cash_book_service import cash_book_service


class CashBookReportUI:
    """UI for Cash Book report."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._create_header()
        self._create_filters()
        self._create_report_area()
        self._create_status_bar()

    def _create_header(self) -> None:
        header = ttk.Frame(self.main_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Cash Book Report", font=("Arial", 16, "bold")).pack(side=tk.LEFT)

    def _create_filters(self) -> None:
        filter_frame = ttk.LabelFrame(self.main_frame, text="Filters", padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        row = ttk.Frame(filter_frame)
        row.pack(fill=tk.X)

        ttk.Label(row, text="Account:", width=12).pack(side=tk.LEFT)
        self.account_var = tk.StringVar(value="All")
        self.account_combo = ttk.Combobox(row, textvariable=self.account_var, state="readonly", width=20)
        self.account_combo.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(row, text="From Date:", width=12).pack(side=tk.LEFT)
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        ttk.Entry(row, textvariable=self.from_date_var, width=15).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(row, text="To Date:", width=10).pack(side=tk.LEFT)
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        ttk.Entry(row, textvariable=self.to_date_var, width=15).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Button(row, text="Generate", command=self._generate_report).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row, text="Export CSV", command=self._export_to_csv).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row, text="Export JSON", command=self._export_to_json).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row, text="Refresh", command=self._refresh).pack(side=tk.LEFT)

        self._load_accounts()

    def _create_report_area(self) -> None:
        self.report_frame = ttk.Frame(self.main_frame)
        self.report_frame.pack(fill=tk.BOTH, expand=True)

        self.summary_label = ttk.Label(self.report_frame, text="Generate a cash book report to begin.")
        self.summary_label.pack(anchor="w", pady=(0, 5))

        tree_frame = ttk.Frame(self.report_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        columns = ("date", "reference", "type", "narration", "debit", "credit", "running_balance", "dr_cr")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        headings = {
            "date": "Date",
            "reference": "Reference",
            "type": "Type",
            "narration": "Narration",
            "debit": "Debit",
            "credit": "Credit",
            "running_balance": "Running Balance",
            "dr_cr": "Dr/Cr",
        }
        widths = {"date": 100, "reference": 120, "type": 120, "narration": 260, "debit": 120, "credit": 120, "running_balance": 140, "dr_cr": 60}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="e" if col in {"debit", "credit", "running_balance"} else "w")

        self.tree.pack(fill=tk.BOTH, expand=True)

    def _create_status_bar(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w").pack(fill=tk.X, pady=(8, 0))

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.parent.update_idletasks()

    def _parse_date(self, value: str) -> date:
        return datetime.strptime(value, config.DISPLAY_DATE_FORMAT).date()

    def _generate_report(self) -> None:
        try:
            from_date = self._parse_date(self.from_date_var.get())
            to_date = self._parse_date(self.to_date_var.get())
            account_id = None
            account_text = self.account_var.get().strip()
            if account_text and account_text != "All":
                account_id = int(account_text.split(" - ", 1)[0])
            self._set_status("Generating cash book...")
            report = cash_book_service.generate_cash_book(self.company_id, from_date, to_date, account_id)
            if not report.get("success"):
                messagebox.showerror("Error", report.get("error", "Failed to generate report"))
                return
            self.current_report_data = report
            self._render_report(report)
            self._set_status(f"Cash book generated: {report['transaction_count']} transactions")
        except Exception as exc:
            messagebox.showerror("Error", f"Invalid date or report error: {exc}")
            self._set_status("Report generation failed")

    def _render_report(self, report: Dict[str, Any]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.summary_label.config(
            text=(
                f"Opening: {report['opening_balance']:,.2f} | "
                f"Receipts: {report['receipts']:,.2f} | "
                f"Payments: {report['payments']:,.2f} | "
                f"Closing: {report['closing_balance']['amount']:,.2f} {report['closing_balance']['type']}"
            )
        )
        for txn in report.get("transactions", []):
            self.tree.insert("", tk.END, values=(
                txn.get("transaction_date", ""),
                txn.get("reference_number", ""),
                txn.get("transaction_type", ""),
                txn.get("narration", ""),
                f"{txn.get('debit_amount', 0):,.2f}",
                f"{txn.get('credit_amount', 0):,.2f}",
                f"{txn.get('running_balance', 0):,.2f}",
                txn.get("balance_type", ""),
            ))

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Generate a report first")
            return
        success, result = cash_book_service.export_cash_book_to_csv(self.current_report_data)
        if success:
            messagebox.showinfo("Success", f"Exported to {result}")
        else:
            messagebox.showerror("Error", result)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Generate a report first")
            return
        success, result = cash_book_service.export_to_json(self.current_report_data, "cash_book")
        if success:
            messagebox.showinfo("Success", f"Exported to {result}")
        else:
            messagebox.showerror("Error", result)

    def _refresh(self) -> None:
        self.current_report_data = None
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.summary_label.config(text="Generate a cash book report to begin.")
        self._set_status("Refreshed")
        self._load_accounts()

    def _load_accounts(self) -> None:
        bank_items = cash_book_service._get_cash_sources(self.company_id)
        values = ["All"] + [f"{item.get('id')} - {item.get('name', '')}" for item in bank_items]
        self.account_combo["values"] = values
        if values:
            self.account_combo.current(0)


def show_cash_book_report(parent: tk.Widget, company_id: int) -> CashBookReportUI:
    return CashBookReportUI(parent, company_id)
