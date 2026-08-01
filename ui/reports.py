"""
Reports Hub
Launcher screen for the available report modules.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from ui.ageing_report import show_ageing_report
from ui.account_book_report import show_account_book_report
from ui.cash_book_report import show_cash_book_report
from ui.outstanding_report import show_outstanding_report
from ui.party_ledger_report import show_party_ledger_report


class ReportsHubUI:
    """Reports hub that opens individual report screens."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_frame: Optional[tk.Widget] = None
        self.report_cards: List[Dict[str, str]] = []

        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._build_header()
        self._build_controls()
        self._build_cards()

    def _build_header(self) -> None:
        header = ttk.Frame(self.main_frame)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="Reports", font=("Arial", 18, "bold")).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Open a report module from the hub",
            font=("Arial", 10),
        ).pack(side=tk.LEFT, padx=(10, 0))

    def _build_controls(self) -> None:
        controls = ttk.Frame(self.main_frame)
        controls.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(controls, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._refresh_cards)
        ttk.Entry(controls, textvariable=self.search_var, width=28).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Button(controls, text="Refresh", command=self._refresh_cards).pack(side=tk.LEFT)

    def _build_cards(self) -> None:
        self.cards_frame = ttk.Frame(self.main_frame)
        self.cards_frame.pack(fill=tk.BOTH, expand=True)

        self.card_definitions = [
            {
                "title": "Party Ledger",
                "subtitle": "Party-wise ledger and summary",
                "open": lambda: show_party_ledger_report(self.parent, self.company_id),
            },
            {
                "title": "Outstanding Report",
                "subtitle": "Receivables and payables overview",
                "open": lambda: show_outstanding_report(self.parent, self.company_id),
            },
            {
                "title": "Ageing Report",
                "subtitle": "Ageing buckets and overdue analysis",
                "open": lambda: show_ageing_report(self.parent, self.company_id),
            },
            {
                "title": "Cash Book",
                "subtitle": "Cash and bank movement",
                "open": lambda: show_cash_book_report(self.parent, self.company_id),
            },
            {
                "title": "Account Book",
                "subtitle": "Account statement view",
                "open": lambda: show_account_book_report(self.parent, self.company_id),
            },
            {
                "title": "Balance Sheet",
                "subtitle": "Coming Soon",
                "open": None,
            },
            {
                "title": "Profit & Loss",
                "subtitle": "Coming Soon",
                "open": None,
            },
            {
                "title": "Trial Balance",
                "subtitle": "Coming Soon",
                "open": None,
            },
        ]

        self._refresh_cards()

    def _clear_cards(self) -> None:
        for child in self.cards_frame.winfo_children():
            child.destroy()

    def _refresh_cards(self, *args) -> None:
        self._clear_cards()
        search_term = self.search_var.get().strip().lower()
        filtered = [
            item for item in self.card_definitions
            if search_term in item["title"].lower() or search_term in item["subtitle"].lower()
        ]

        if not filtered:
            ttk.Label(self.cards_frame, text="No matching reports found.").pack(anchor="w")
            return

        for index, item in enumerate(filtered):
            row = index // 2
            column = index % 2
            card = self._create_card(self.cards_frame, item)
            card.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)

        for column in range(2):
            self.cards_frame.grid_columnconfigure(column, weight=1)

    def _create_card(self, parent: tk.Widget, item: Dict[str, str]) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=14, relief=tk.RIDGE)
        title = ttk.Label(frame, text=item["title"], font=("Arial", 13, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(frame, text=item["subtitle"], font=("Arial", 10))
        subtitle.pack(anchor="w", pady=(4, 10))

        open_handler = item.get("open")
        if callable(open_handler):
            ttk.Button(frame, text="Open", command=open_handler).pack(anchor="e")
        else:
            ttk.Label(frame, text="Coming Soon", foreground="gray").pack(anchor="e")

        return frame


def show_reports(parent: tk.Widget, company_id: int) -> ReportsHubUI:
    return ReportsHubUI(parent, company_id)
