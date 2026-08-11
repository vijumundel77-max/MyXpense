"""
Expenzo — Masters Hub
Launcher for the master screens: Company, Groups, Ledgers (Chart of
Accounts), Parties, and Bank Accounts.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

import config
from services.company_service import CompanyService


class MastersFrame(ctk.CTkFrame):
    """Masters hub that swaps in individual master screens."""

    def __init__(self, parent, db=None, company_id: Optional[int] = None,
                 company_service: Optional[CompanyService] = None,
                 on_company_switched=None):
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.company_id = company_id
        self.on_company_switched = on_company_switched
        self.company_service = company_service or CompanyService(db) if db else None
        self.current_frame: Optional[tk.Widget] = None

        self.pack(fill="both", expand=True)

        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        self._build_header()
        self._build_cards()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Masters", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Companies, groups, ledgers, parties & bank accounts",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(config.SPACING_MD, 0))
        company_name = self._company_name()
        if company_name:
            ctk.CTkLabel(
                header, text=company_name, font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLOR_PRIMARY,
            ).pack(side="right")

    def _company_name(self) -> str:
        if self.company_service and self.company_id:
            company = self.company_service.get_company(self.company_id)
            if company:
                return company.company_name
        return ""

    def _build_cards(self) -> None:
        self.cards_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True)

        cards: List[Dict[str, object]] = [
            {
                "title": "Company",
                "subtitle": "Create & switch companies",
                "icon": "⌂",
                "open": self._open_company,
            },
            {
                "title": "Groups",
                "subtitle": "Chart of Accounts groups",
                "icon": "▦",
                "open": self._open_groups,
            },
            {
                "title": "Ledgers",
                "subtitle": "Chart of Accounts ledgers",
                "icon": "▤",
                "open": self._open_ledgers,
            },
            {
                "title": "Parties",
                "subtitle": "Debtors & creditors",
                "icon": "▥",
                "open": self._open_parties,
            },
            {
                "title": "Bank Accounts",
                "subtitle": "Bank account master",
                "icon": "▨",
                "open": self._open_bank_accounts,
            },
        ]

        for index, card in enumerate(cards):
            row = index // 2
            column = index % 2
            widget = self._create_card(self.cards_frame, card)
            widget.grid(row=row, column=column, sticky="nsew", padx=config.SPACING_SM,
                        pady=config.SPACING_SM)
        for column in range(2):
            self.cards_frame.grid_columnconfigure(column, weight=1)
        for row in range(3):
            self.cards_frame.grid_rowconfigure(row, weight=1)

    def _create_card(self, parent, card: Dict[str, object]) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )

        # The action button is packed FIRST and anchored to the bottom so it
        # always reserves its full height and stays readable even when the
        # card's available space is tight (labels then fill the remainder).
        ctk.CTkButton(
            frame, text="Open", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=card["open"],
        ).pack(side="bottom", anchor="e", padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_LG))

        icon = ctk.CTkLabel(
            frame, text=card["icon"], font=ctk.CTkFont(size=26),
            text_color=config.COLOR_PRIMARY,
        )
        icon.pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_XL, 0))

        ctk.CTkLabel(
            frame, text=card["title"], font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_SM, 0))

        ctk.CTkLabel(
            frame, text=card["subtitle"], font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(2, config.SPACING_LG))

        return frame

    # ------------------------------------------------------------------ #
    # navigation
    # ------------------------------------------------------------------ #
    def _show_screen(self, builder: Callable[[tk.Widget], tk.Widget]) -> None:
        self._destroy_current()
        # Hide the hub cards so they cannot sit on top of (or behind) the
        # master screen. The cards are built once and reused, never rebuilt.
        self.cards_frame.pack_forget()
        # Keep the UI object so keyboard shortcuts can dispatch to its real
        # methods; display its main_frame.
        self.current_ui = builder(self.main_frame)
        self.current_frame = getattr(self.current_ui, "main_frame", self.current_ui)
        self.current_frame.pack(fill="both", expand=True)
        # The Masters hub owns back navigation while a master screen is open:
        # route the child's Esc back to this hub instead of letting it jump
        # to the top-level app navigation and skip the hub entirely.
        self.current_ui.on_keyboard_back = self.on_keyboard_back

    def _destroy_current(self) -> None:
        if self.current_frame is not None:
            try:
                self.current_frame.destroy()
            except Exception:
                pass
            self.current_frame = None
        self.current_ui = None

    def _show_hub(self) -> None:
        """Close any open master screen and reveal the hub cards.

        The cards are built once in ``__init__`` and reused; returning from
        a master screen never stacks duplicate Open buttons.
        """
        self._destroy_current()
        self.cards_frame.pack(fill="both", expand=True)

    def _require_company_id(self) -> int:
        """Return the current company id, raising if context is missing.

        Masters operations must never silently operate on company 1 when no
        company context was supplied, so a missing context fails loudly
        instead of touching the wrong company's data.
        """
        if self.company_id:
            return int(self.company_id)
        raise ValueError("No company selected — cannot open master screens.")

    def _open_company(self) -> None:
        from ui.company_management import CompanyManagementUI
        self._show_screen(
            lambda parent: CompanyManagementUI(
                parent,
                self.company_service,
                current_company_id=self.company_id,
                on_company_switched=self._handle_company_switched,
            )
        )

    def _open_groups(self) -> None:
        from ui.group_master import GroupMasterUI
        self._show_screen(lambda parent: GroupMasterUI(parent, self._require_company_id()))

    def _open_ledgers(self) -> None:
        from ui.ledger_master import LedgerMasterUI
        self._show_screen(lambda parent: LedgerMasterUI(parent, self._require_company_id()))

    def _open_parties(self) -> None:
        from ui.party_master import PartyMasterUI
        self._show_screen(lambda parent: PartyMasterUI(parent, self._require_company_id()))

    def _open_bank_accounts(self) -> None:
        from ui.bank_account_management import BankAccountManagementUI
        self._show_screen(lambda parent: BankAccountManagementUI(parent, self._require_company_id()))

    def _handle_company_switched(self, company_id: int) -> None:
        self.company_id = int(company_id)
        if self.on_company_switched:
            self.on_company_switched(company_id)

    # ------------------------------------------------------------------ #
    # keyboard forwarding (the global manager sees this hub as the view)
    # ------------------------------------------------------------------ #
    def _forward(self, method_name: str):
        ui = getattr(self, "current_ui", None)
        if ui is None:
            return None
        method = getattr(ui, method_name, None)
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

    def on_keyboard_search(self) -> None:
        method = self._forward("on_keyboard_search")
        if method:
            method()
        else:
            from utils.keyboard import _focus_search
            _focus_search(self)

    def on_keyboard_delete(self) -> None:
        ui = getattr(self, "current_ui", None)
        if ui is None:
            return
        from utils.keyboard import _table_has_selection, _find_delete_method
        if _table_has_selection(ui):
            delete = _find_delete_method(ui)
            if delete:
                delete()

    def on_keyboard_back(self) -> None:
        """Esc: if a master screen is open, close it and show the hub.

        A child screen may own Esc handling for its internal sub-states (e.g.
        the Company Management form returns to the Company List before the hub
        is reached).  Such screens expose ``handle_escape()`` returning True
        when they consumed the Esc; otherwise the hub shows itself.
        """
        ui = getattr(self, "current_ui", None)
        if ui is not None:
            internal = getattr(ui, "handle_escape", None)
            if callable(internal):
                try:
                    if internal() is True:
                        return
                except Exception:
                    pass
        if self.current_frame is not None and getattr(self, "current_ui", None) is not None:
            self._show_hub()
        else:
            app = self.winfo_toplevel()
            if hasattr(app, "on_keyboard_back"):
                app.on_keyboard_back()
