"""
Expenzo — Reports Hub
Launcher for the report modules with Expenzo design-system cards.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

import config
from ui.day_book_report import show_day_book_report
from ui.cash_book_report import show_cash_book_report
from ui.bank_book_report import show_bank_book_report
from ui.party_ledger_report import show_party_ledger_report
from ui.account_book_report import show_account_book_report
from ui.outstanding_report import show_outstanding_report
from ui.ageing_report import show_ageing_report
from ui.trial_balance_report import show_trial_balance_report
from ui.balance_sheet_report import show_balance_sheet_report


class ReportsHubUI:
    """Reports hub that opens individual report screens."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_frame: Optional[tk.Widget] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        self._build_header()
        self._build_controls()
        self._build_cards()

    def _open_report(self, opener: Callable[[tk.Widget, int], tk.Widget]) -> None:
        self._destroy_current_report()
        report_ui = opener(self.parent, self.company_id)
        self.current_report_ui = report_ui
        self.current_frame = report_ui.main_frame
        self._install_back_button(report_ui)

    def _destroy_current_report(self) -> None:
        if self.current_frame is not None:
            try:
                self.current_frame.destroy()
            except Exception:
                pass
            self.current_frame = None
        self.current_report_ui = None

    def _install_back_button(self, report_ui: tk.Widget) -> None:
        """Add a 'Back to Reports' button to a report screen's header."""
        try:
            main_frame = getattr(report_ui, "main_frame", None)
            if main_frame is None:
                return
            header = ctk.CTkFrame(main_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, config.SPACING_SM))
            ctk.CTkButton(
                header,
                text="← Back to Reports",
                width=130,
                height=28,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                command=self._close_report,
            ).pack(side="left")
        except Exception:
            pass

    def _close_report(self) -> None:
        self._destroy_current_report()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Reports", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Open a report module",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

    def _build_controls(self) -> None:
        controls = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        controls.pack(fill="x", pady=(0, config.SPACING_LG))
        row = ctk.CTkFrame(controls, fg_color="transparent")
        row.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_MD)
        ctk.CTkLabel(row, text="Search", font=ctk.CTkFont(size=12)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._refresh_cards)
        self.search_entry = ctk.CTkEntry(
            row, textvariable=self.search_var, width=260,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.search_entry.pack(side="left", padx=(config.SPACING_SM, config.SPACING_MD))
        ctk.CTkLabel(
            row, text="Open a report module",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="right")

    def on_keyboard_back(self) -> None:
        """Esc on the hub (no report open) returns to the previous screen."""
        try:
            app = self.winfo_toplevel()
            if hasattr(app, "on_keyboard_back"):
                app.on_keyboard_back()
        except Exception:
            pass

    def _forward(self, method_name: str):
        """Forward a shortcut to the currently open report UI if any."""
        ui = getattr(self, "current_report_ui", None)
        if ui is None:
            return None
        method = getattr(ui, method_name, None)
        if callable(method):
            return method
        # Fall back to common report conventions.
        fallbacks = {
            "on_keyboard_refresh": "_generate_report",
            "on_keyboard_search": "_focus_search",
        }
        fallback = fallbacks.get(method_name)
        if fallback:
            method = getattr(ui, fallback, None)
            if callable(method):
                return method
        return None

    def on_keyboard_save(self) -> None:
        method = self._forward("on_keyboard_save")
        if method:
            method()

    def on_keyboard_new(self) -> None:
        method = self._forward("on_keyboard_new")
        if method:
            method()

    def on_keyboard_refresh(self) -> None:
        method = self._forward("on_keyboard_refresh")
        if method:
            method()
        else:
            # Refresh the hub itself.
            self._refresh_cards()

    def on_keyboard_search(self) -> None:
        method = self._forward("on_keyboard_search")
        if method:
            method()
        else:
            from utils.keyboard import _focus_search
            _focus_search(self)

    def _build_cards(self) -> None:
        self.cards_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True)

        self.card_definitions = [
            {
                "title": "Day Book",
                "subtitle": "Voucher register",
                "icon": "▤",
                "open": lambda: self._open_report(show_day_book_report),
            },
            {
                "title": "Cash Book",
                "subtitle": "Cash movement",
                "icon": "₹",
                "open": lambda: self._open_report(show_cash_book_report),
            },
            {
                "title": "Bank Book",
                "subtitle": "Bank movement",
                "icon": "▨",
                "open": lambda: self._open_report(show_bank_book_report),
            },
            {
                "title": "Party Ledger",
                "subtitle": "Party-wise ledger and summary",
                "icon": "▥",
                "open": lambda: self._open_report(show_party_ledger_report),
            },
            {
                "title": "Account Book",
                "subtitle": "Account statement view",
                "icon": "▦",
                "open": lambda: self._open_report(show_account_book_report),
            },
            {
                "title": "Outstanding Report",
                "subtitle": "Receivables and payables overview",
                "icon": "▧",
                "open": lambda: self._open_report(show_outstanding_report),
            },
            {
                "title": "Ageing Report",
                "subtitle": "Ageing buckets and overdue analysis",
                "icon": "◔",
                "open": lambda: self._open_report(show_ageing_report),
            },
            {
                "title": "Trial Balance",
                "subtitle": "Debit and credit balances",
                "icon": "▤",
                "open": lambda: self._open_report(show_trial_balance_report),
            },
            {
                "title": "Balance Sheet",
                "subtitle": "Assets = Liabilities + Capital",
                "icon": "▦",
                "open": lambda: self._open_report(show_balance_sheet_report),
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
            ctk.CTkLabel(
                self.cards_frame,
                text="No matching reports found.",
                font=ctk.CTkFont(size=14),
                text_color=config.COLOR_TEXT_MUTED,
            ).pack(pady=config.SPACING_XXL)
            return

        for index, item in enumerate(filtered):
            row = index // 2
            column = index % 2
            card = self._create_card(self.cards_frame, item)
            card.grid(row=row, column=column, sticky="nsew", padx=config.SPACING_SM,
                      pady=config.SPACING_SM)

        for column in range(2):
            self.cards_frame.grid_columnconfigure(column, weight=1)
        for row in range((len(filtered) + 1) // 2):
            self.cards_frame.grid_rowconfigure(row, weight=1)

    def _create_card(self, parent, item: Dict[str, str]) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        frame.grid_propagate(False)

        ctk.CTkLabel(
            frame, text=item["icon"], font=ctk.CTkFont(size=26),
            text_color=config.COLOR_PRIMARY,
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_XL, 0))
        ctk.CTkLabel(
            frame, text=item["title"], font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_SM, 0))
        ctk.CTkLabel(
            frame, text=item["subtitle"], font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(2, config.SPACING_LG))
        open_handler = item.get("open")
        if callable(open_handler):
            ctk.CTkButton(
                frame, text="Open", width=90, height=32,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                command=open_handler,
            ).pack(anchor="e", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))

        return frame


def show_reports(parent: tk.Widget, company_id: int) -> ReportsHubUI:
    return ReportsHubUI(parent, company_id)
