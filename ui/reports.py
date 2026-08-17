"""
Expenzo — Reports Hub
Launcher for the report modules with an Expenzo design-system layout:

  header + advanced action  ->  search bar  ->  two-column report cards
  -> recently opened reports -> how-to-use panel -> bottom shortcut bar

This screen is a UI hub only: every card opens the existing report module
(service + calculations untouched), and nothing here writes accounting data.
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

import config
from services.recent_reports_service import recent_reports, record_report_open
from ui.day_book_report import show_day_book_report
from ui.cash_book_report import show_cash_book_report
from ui.bank_book_report import show_bank_book_report
from ui.ledger_report import show_ledger_report
from ui.account_book_report import show_account_book_report
from ui.outstanding_report import show_outstanding_report
from ui.ageing_report import show_ageing_report
from ui.trial_balance_report import show_trial_balance_report
from ui.balance_sheet_report import show_balance_sheet_report
from ui.profit_loss_report import show_profit_loss_report


class ReportsHubUI(ctk.CTkFrame):
    """Reports hub that opens individual report screens.

    Subclasses CTkFrame so the hub is a real managed widget: it can be
    packed/destroyed, owns ``winfo_toplevel``, and participates in keyboard
    focus exactly like the other view hubs (Masters, Vouchers).
    """

    # The real report registry: each entry maps to an existing report module.
    # ``actions`` lists the controls that report screen actually implements
    # (no fake buttons — a report only advertises what its screen provides).
    CARD_DEFINITIONS: List[Dict[str, object]] = [
        {
            "title": "Day Book",
            "subtitle": "View day-wise transaction summary",
            "icon": "▤",
            "open": lambda self: self._open_report(show_day_book_report, "Day Book"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Cash Book",
            "subtitle": "Cash receipts and payments",
            "icon": "₹",
            "open": lambda self: self._open_report(show_cash_book_report, "Cash Book"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Bank Book",
            "subtitle": "Bank transactions and statements",
            "icon": "▨",
            "open": lambda self: self._open_report(show_bank_book_report, "Bank Book"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Ledger",
            "subtitle": "Account ledger statement",
            "icon": "▥",
            "open": lambda self: self._open_report(show_ledger_report, "Ledger"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Account Book",
            "subtitle": "Account statement view",
            "icon": "▦",
            "open": lambda self: self._open_report(show_account_book_report, "Account Book"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Outstanding Report",
            "subtitle": "Receivables and payables overview",
            "icon": "▧",
            "open": lambda self: self._open_report(show_outstanding_report, "Outstanding Report"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Ageing Report",
            "subtitle": "Ageing buckets and overdue analysis",
            "icon": "◔",
            "open": lambda self: self._open_report(show_ageing_report, "Ageing Report"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Trial Balance",
            "subtitle": "Trial balance of accounts",
            "icon": "▤",
            "open": lambda self: self._open_report(show_trial_balance_report, "Trial Balance"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Balance Sheet",
            "subtitle": "Assets = Liabilities + Capital",
            "icon": "▦",
            "open": lambda self: self._open_report(show_balance_sheet_report, "Balance Sheet"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export", "Print"],
        },
        {
            "title": "Profit & Loss",
            "subtitle": "Income vs Expense, Net Profit/Loss",
            "icon": "▣",
            "open": lambda self: self._open_report(show_profit_loss_report, "Profit & Loss"),
            "actions": ["Open", "Modify Filters", "Refresh", "Export"],
        },
    ]

    def __init__(self, parent: tk.Widget, company_id: int):
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.parent = parent
        self.company_id = company_id
        self.pack(fill="both", expand=True)
        self.current_frame: Optional[tk.Widget] = None
        self.current_report_ui: Optional[object] = None
        self.selected_title: Optional[str] = None
        self._selected_card: Optional[ctk.CTkFrame] = None
        self._report_defs: List[Dict[str, object]] = []
        self._card_widgets: Dict[str, ctk.CTkFrame] = {}
        self._mouse_selected = False
        self._keyboard_selected = False

        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        self._build_header()
        self._build_search()
        self._build_body()
        self._build_shortcut_bar()

        # Keyboard access to the search box on this screen.
        self.search_entry.bind("<Control-f>", self._on_ctrl_f)
        self.search_entry.bind("<Control-F>", self._on_ctrl_f)
        self._bind_card_keyboard()

        # Enter / arrows pressed ANYWHERE inside the hub must move the
        # selection / open the report.  CTkFrame children do not receive key
        # focus reliably (the wrapper is not a real focus target and its
        # ``bind`` forwards to an internal canvas), and ``bind_all`` is
        # blocked on CTk child widgets — so the hub binds on its toplevel
        # window (whose bindtag fires for every descendant) and removes the
        # bindings when the hub is destroyed.
        self._toplevel = self.winfo_toplevel()
        self._hub_toplevel_binds: Dict[str, str] = {}
        for seq in ("<Return>", "<KP_Enter>", "<Up>", "<Down>", "<Left>", "<Right>"):
            try:
                self._hub_toplevel_binds[seq] = self._toplevel.bind(seq, self._on_hub_key)
            except Exception:
                pass
        self.bind("<Destroy>", self._on_hub_destroy, add="+")

        # A report just opened: hand keyboard focus to its first card (or, if
        # the search box already had focus, leave it there).
        self.after(40, self._focus_first_report)

    def _on_hub_destroy(self, _event=None) -> None:
        """Remove the toplevel key bindings so they never leak into other
        screens (the toplevel outlives the hub)."""
        try:
            if getattr(self, "_hub_toplevel_binds", None):
                for seq in self._hub_toplevel_binds:
                    try:
                        self._toplevel.unbind(seq)
                    except Exception:
                        pass
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        self.hub_header = header

        title_col = ctk.CTkFrame(header, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            title_col, text="Reports", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_col, text="Select a report to view",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        # "Open Advanced Report Module" -> the full report registry, i.e. this
        # hub itself.  The app has no separate advanced-report backend, so the
        # action focuses the search and returns focus to the report grid.
        self.advanced_btn = ctk.CTkButton(
            header, text="Open Advanced Report Module", width=220, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self._on_advanced_report,
        )
        self.advanced_btn.pack(side="right")

    def _build_search(self) -> None:
        self.search_bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS, border_width=1,
            border_color=config.COLOR_CARD_BORDER,
        )
        self.search_bar.pack(fill="x", pady=(0, config.SPACING_LG))
        self.search_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.search_bar, text="⌕", font=ctk.CTkFont(size=18),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=(config.SPACING_LG, config.SPACING_SM))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._refresh_cards)
        self.search_entry = ctk.CTkEntry(
            self.search_bar, textvariable=self.search_var, height=34,
            placeholder_text="Search reports...",
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", pady=config.SPACING_SM)

        self.search_hint = ctk.CTkLabel(
            self.search_bar, text="Ctrl+F  Search", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        )
        self.search_hint.grid(row=0, column=2, padx=config.SPACING_LG)

    def _build_body(self) -> None:
        """Hub content: report cards, recent reports, help panel.

        ``body_container`` is a plain frame packed into the hub so it can be
        reliably hidden with ``pack_forget`` while a report is open (a
        CTkScrollableFrame cannot be unhidden via pack_forget).  The
        scrollable region lives inside it.
        """
        self.body_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.body_container.pack(fill="both", expand=True)
        self.body_container.grid_columnconfigure(0, weight=1)
        self.body_container.grid_rowconfigure(0, weight=1)

        self.body_scroll = ctk.CTkScrollableFrame(
            self.body_container, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=config.COLOR_BG_TERTIARY,
        )
        self.body_scroll.grid(row=0, column=0, sticky="nsew")
        self.body_scroll.grid_columnconfigure(0, weight=1)

        self._build_cards()
        self._build_recent()
        self._build_help()

    def _build_cards(self) -> None:
        self.cards_frame = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        self.cards_frame.grid(row=0, column=0, sticky="nsew", pady=(0, config.SPACING_XL))
        self.cards_frame.grid_columnconfigure(0, weight=1)
        self.cards_frame.grid_columnconfigure(1, weight=1)

        self._cards_grid_inited = False
        self._last_card_columns: Optional[int] = None
        self._report_defs = [dict(item) for item in self.CARD_DEFINITIONS]
        self._refresh_cards()
        self._cards_grid_inited = True
        self._last_card_columns = self._card_columns()

    def _build_recent(self) -> None:
        self.recent_frame = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        self.recent_frame.grid(row=1, column=0, sticky="ew", pady=(0, config.SPACING_XL))

        header = ctk.CTkFrame(self.recent_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_SM))
        ctk.CTkLabel(
            header, text="Recently Opened Reports",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Reports opened in the current company",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_SM, 0))

        self.recent_panel = ctk.CTkFrame(
            self.recent_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS, border_width=1,
            border_color=config.COLOR_CARD_BORDER,
        )
        self.recent_panel.pack(fill="x")

        self._refresh_recent()

    def _build_help(self) -> None:
        self.help_frame = ctk.CTkFrame(self.body_scroll, fg_color="transparent")
        self.help_frame.grid(row=2, column=0, sticky="ew")

        ctk.CTkLabel(
            self.help_frame, text="How to use Reports",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", pady=(0, config.SPACING_SM))

        self.help_panel = ctk.CTkFrame(
            self.help_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS, border_width=1,
            border_color=config.COLOR_CARD_BORDER,
        )
        self.help_panel.pack(fill="x")

        self.help_panel.grid_columnconfigure(0, weight=1)
        self.help_panel.grid_columnconfigure(1, weight=1)

        steps = ctk.CTkFrame(self.help_panel, fg_color="transparent")
        steps.grid(row=0, column=0, sticky="nw", padx=config.SPACING_LG, pady=config.SPACING_LG)
        ctk.CTkLabel(
            steps, text="1. Single click any report to select it.", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            steps, text="2. Double click a report to open it.", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            steps, text="3. Press Enter or click Open to open the selected report.", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            steps, text="4. Set filters, generate, export or print inside the report.", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")

        tip = ctk.CTkFrame(self.help_panel, fg_color="transparent")
        tip.grid(row=0, column=1, sticky="nw", padx=config.SPACING_LG, pady=config.SPACING_LG)
        ctk.CTkLabel(
            tip, text="Tip", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            tip, text="You can also use shortcuts.", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            tip, text="↑ ↓  Move selection", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            tip, text="Enter  Open selected", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            tip, text="F5  Refresh", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            tip, text="Esc  Back", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")

    def _build_shortcut_bar(self) -> None:
        self.shortcut_bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS, border_width=1,
            border_color=config.COLOR_CARD_BORDER,
        )
        self.shortcut_bar.pack(fill="x", pady=(config.SPACING_LG, 0))

        ctk.CTkLabel(
            self.shortcut_bar, text="SHORTCUTS (THIS SCREEN)", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=config.SPACING_LG)

        self.shortcut_bar_body = ctk.CTkFrame(self.shortcut_bar, fg_color="transparent")
        self.shortcut_bar_body.pack(side="left", padx=config.SPACING_MD)

        self._shortcut_refresh_btn = ctk.CTkButton(
            self.shortcut_bar_body, text="F5  Refresh", width=110, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self.on_keyboard_refresh,
        )
        self._shortcut_refresh_btn.pack(side="left", padx=(0, config.SPACING_XS))
        self._shortcut_search_btn = ctk.CTkButton(
            self.shortcut_bar_body, text="Ctrl+F  Search", width=120, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self._focus_search_entry,
        )
        self._shortcut_search_btn.pack(side="left", padx=(0, config.SPACING_XS))
        self._shortcut_enter_btn = ctk.CTkButton(
            self.shortcut_bar_body, text="Enter  Open", width=110, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self._open_selected_report,
        )
        self._shortcut_enter_btn.pack(side="left", padx=(0, config.SPACING_XS))
        self._shortcut_back_btn = ctk.CTkButton(
            self.shortcut_bar_body, text="Esc  Back", width=100, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self._handle_back_shortcut,
        )
        self._shortcut_back_btn.pack(side="left")

        ctk.CTkLabel(
            self.shortcut_bar, text="Click / Enter  Open Report", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="right", padx=config.SPACING_LG)

    # ------------------------------------------------------------------ #
    # report opening
    # ------------------------------------------------------------------ #
    def _open_report(self, opener: Callable[[tk.Widget, int], tk.Widget], report_name: str) -> None:
        """Open the selected report module.

        The report's ``main_frame`` is packed into the hub's main frame so it
        is always visible; the hub body (cards/recent/help) stays hidden
        while a report is open and is restored on close.
        """
        self._destroy_current_report()
        self._select_report(report_name)
        # Hide ALL hub chrome (header, search, body, shortcut bar) while a
        # report is open; the report fills the whole hub area.
        for widget in (getattr(self, "hub_header", None),
                       getattr(self, "search_bar", None),
                       self.body_container,
                       getattr(self, "shortcut_bar", None)):
            if widget is not None:
                try:
                    widget.pack_forget()
                except Exception:
                    pass
        report_ui = opener(self.main_frame, self.company_id)
        self.current_report_ui = report_ui
        # The report packs its own main_frame into the given parent with the
        # standard XL padding (it fills the hub area the body used).
        self.current_frame = getattr(report_ui, "main_frame", report_ui)
        # Wire the report's own back-arrow header to close the report and
        # return to the hub.
        try:
            report_ui.on_keyboard_back = self.on_keyboard_back
        except Exception:
            pass
        record_report_open(self.company_id, report_name, self._current_user())
        # Reports now carry their own compact back-arrow header
        # (ReportBackHeader) wired to on_keyboard_back, so no extra injected
        # button is needed here.
        # Hand keyboard focus to the open report (its first focusable widget)
        # so keys like arrows / Enter act on the report, not on the now-hidden
        # hub cards.
        self._focus_open_report(report_ui)

    def _focus_open_report(self, report_ui: object) -> None:
        """Focus the open report's primary entry (search first, else the first
        CTkEntry in its filter bar).  Never steals focus from the app root."""
        try:
            entry = getattr(report_ui, "search_entry", None)
            if entry is not None and hasattr(entry, "focus_set"):
                entry.focus_set()
                return
            filters = getattr(report_ui, "filters", None) or getattr(report_ui, "filter_bar", None)
            if filters is not None and hasattr(filters, "body"):
                for child in filters.body.winfo_children():
                    if isinstance(child, ctk.CTkEntry):
                        child.focus_set()
                        return
        except Exception:
            pass

    def _current_user(self) -> str:
        try:
            row = self._db_fetch_user()
            return row or "Admin"
        except Exception:
            return "Admin"

    def _db_fetch_user(self) -> Optional[str]:
        from database.database import db
        row = db.fetch_one("SELECT value FROM settings WHERE key = 'user_name'")
        return str(row["value"]) if row else None

    def _destroy_current_report(self) -> None:
        if self.current_frame is not None:
            try:
                self.current_frame.destroy()
            except Exception:
                pass
            self.current_frame = None
        self.current_report_ui = None
        # Restore all hub chrome in the original pack order (header, search,
        # body, shortcut) so the hub is never blank after closing a report.
        try:
            if self.hub_header.winfo_manager() == "":
                self.hub_header.pack(fill="x")
        except Exception:
            pass
        try:
            if self.search_bar.winfo_manager() == "":
                self.search_bar.pack(fill="x")
        except Exception:
            pass
        try:
            if self.body_container.winfo_manager() == "":
                self.body_container.pack(fill="both", expand=True)
        except Exception:
            pass
        try:
            if self.shortcut_bar.winfo_manager() == "":
                self.shortcut_bar.pack(fill="x")
        except Exception:
            pass

    def _close_report(self) -> None:
        self._destroy_current_report()
        self._refresh_recent()
        self._focus_first_report()

    # ------------------------------------------------------------------ #
    # cards
    # ------------------------------------------------------------------ #
    def _clear_cards(self) -> None:
        for child in self.cards_frame.winfo_children():
            child.destroy()
        self._card_widgets = {}

    def _available_card_width(self) -> int:
        """Usable width for the card grid (inside padding / scrollbar)."""
        try:
            return max(self.cards_frame.winfo_width(), 0)
        except Exception:
            return 0

    def _card_columns(self) -> int:
        """Responsive column count: 2 columns when they fit, otherwise 1."""
        width = self._available_card_width()
        if width <= 0:
            return 2
        # Each card needs ~340px; two columns with 16px gutters need ~700px.
        return 2 if width >= 700 else 1

    def _refresh_cards(self, *args) -> None:
        self._clear_cards()
        search_term = self.search_var.get().strip().lower()
        filtered = [
            item for item in self._report_defs
            if search_term in item["title"].lower() or search_term in item["subtitle"].lower()
        ]

        columns = self._card_columns()
        for column in range(columns):
            self.cards_frame.grid_columnconfigure(column, weight=1)
        for column in range(columns, 3):
            self.cards_frame.grid_columnconfigure(column, weight=0)

        if not filtered:
            ctk.CTkLabel(
                self.cards_frame,
                text="No matching reports found.",
                font=ctk.CTkFont(size=14),
                text_color=config.COLOR_TEXT_MUTED,
            ).grid(row=0, column=0, columnspan=columns, sticky="ew", pady=config.SPACING_XL)
            return

        for index, item in enumerate(filtered):
            row = index // columns
            column = index % columns
            card = self._create_card(self.cards_frame, item)
            card.grid(row=row, column=column, sticky="ew", padx=config.SPACING_SM,
                      pady=config.SPACING_SM)
            self._card_widgets[item["title"]] = card
            self.cards_frame.grid_rowconfigure(row, weight=0)

        # Re-apply the keyboard-driven selection state.
        if self.selected_title in self._card_widgets:
            self._set_card_selected(self._card_widgets[self.selected_title], True)

    def _create_card(self, parent, item: Dict[str, object]) -> ctk.CTkFrame:
        title = str(item["title"])
        card = ctk.CTkFrame(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS, height=78,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        card.pack_propagate(False)
        card.grid_propagate(False)
        card.grid_columnconfigure(1, weight=1)

        icon = ctk.CTkLabel(
            card, text=str(item["icon"]), font=ctk.CTkFont(size=22),
            text_color=config.COLOR_PRIMARY, width=40,
        )
        icon.grid(row=0, column=0, rowspan=3, sticky="w",
                  padx=config.SPACING_LG, pady=config.SPACING_MD)

        text_col = ctk.CTkFrame(card, fg_color="transparent")
        text_col.grid(row=0, column=1, rowspan=3, sticky="ew", pady=config.SPACING_MD)
        text_col.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            text_col, text=title, font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            text_col, text=str(item["subtitle"]), font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        actions = self._actions_text(item)
        if actions:
            ctk.CTkLabel(
                text_col, text=actions, font=ctk.CTkFont(size=10),
                text_color=config.COLOR_TEXT_MUTED, anchor="w",
            ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Per-card action row: a real "Open" button (opens with one click) and
        # the Enter-key hint.  The Open button exists for every report and is
        # wired exactly like double-click / Enter — nothing fake.
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=0, column=2, rowspan=3, sticky="e", padx=config.SPACING_LG)
        open_btn = ctk.CTkButton(
            actions, text="Open", width=70, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=lambda t=title: self._on_open_button(t),
        )
        open_btn.pack(side="left")
        ctk.CTkLabel(
            actions, text="Enter", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_XS, 0))

        # The ENTIRE card is a click target: single click selects, double
        # click opens.  Every child (icon, text, action bar) forwards clicks
        # to the same handlers so no dead zone exists.
        card.bind("<Enter>", lambda _e, c=card: self._on_card_hover(c, True))
        card.bind("<Leave>", lambda _e, c=card: self._on_card_hover(c, False))
        card.bind("<Button-1>", lambda _e, t=title: self._on_card_click(t))
        card.bind("<Double-Button-1>", lambda _e, t=title: self._on_card_double_click(t))
        card.bind("<Return>", lambda _e, t=title: self._on_card_enter(t))
        card.bind("<KP_Enter>", lambda _e, t=title: self._on_card_enter(t))
        card.bind("<FocusIn>", lambda _e, c=card: self._on_card_focus_in(c))
        card.bind("<FocusOut>", lambda _e, c=card: self._on_card_focus_out(c))
        for child in (icon, text_col, title_label, actions):
            child.bind("<Button-1>", lambda _e, t=title: self._on_card_click(t), add="+")
            child.bind("<Double-Button-1>", lambda _e, t=title: self._on_card_double_click(t), add="+")
        card._report_title = title

        return card

    def _on_card_focus_in(self, card) -> None:
        """Keyboard focus reached the card — make the selection visible."""
        try:
            if not self._mouse_selected:
                self._keyboard_selected = True
            title = getattr(card, "_report_title", None)
            if title:
                self._select_report(title)
            card.configure(border_color=config.COLOR_PRIMARY, border_width=2)
        except Exception:
            pass

    def _on_card_focus_out(self, card) -> None:
        try:
            if card is not self._selected_card:
                card.configure(border_color=config.COLOR_CARD_BORDER, border_width=1)
        except Exception:
            pass

    def _bind_card_keyboard(self) -> None:
        # cards_frame arrow keys move the selection even when focus sits on
        # the container (after a mouse click on empty space).  The cards
        # themselves carry their own Enter bindings.
        self.cards_frame.bind("<Up>", self._on_card_arrow)
        self.cards_frame.bind("<Down>", self._on_card_arrow)
        self.cards_frame.bind("<Left>", self._on_card_arrow)
        self.cards_frame.bind("<Right>", self._on_card_arrow)
        # Responsive grid: re-flow the cards when the body width changes.
        self.cards_frame.bind("<Configure>", self._on_cards_resize)

    def _on_cards_resize(self, _event=None) -> None:
        """Re-flow the card grid when the available width crosses the
        single/two-column threshold (never clip the right column)."""
        if not getattr(self, "_cards_grid_inited", False):
            return
        old = getattr(self, "_last_card_columns", None)
        new = self._card_columns()
        if old is not None and new != old:
            self._last_card_columns = new
            self._refresh_cards()
        elif old is None:
            self._last_card_columns = new

    # ------------------------------------------------------------------ #
    # card interactions (single click selects, Enter/double click opens)
    # ------------------------------------------------------------------ #
    def _visible_titles(self) -> List[str]:
        return list(self._card_widgets.keys())

    def _on_card_hover(self, card, hovering: bool) -> None:
        if hovering and card is not self._selected_card:
            try:
                card.configure(border_color=config.COLOR_PRIMARY)
            except Exception:
                pass
        else:
            if card is not self._selected_card:
                try:
                    card.configure(border_color=config.COLOR_CARD_BORDER)
                except Exception:
                    pass

    def _set_card_selected(self, card, selected: bool) -> None:
        try:
            if selected:
                card.configure(border_color=config.COLOR_PRIMARY, border_width=2)
            else:
                card.configure(border_color=config.COLOR_CARD_BORDER, border_width=1)
        except Exception:
            pass

    def _select_report(self, title: str) -> None:
        self.selected_title = title
        if self._selected_card is not None and self._selected_card is not self._card_widgets.get(title):
            self._set_card_selected(self._selected_card, False)
        self._selected_card = self._card_widgets.get(title)
        if self._selected_card is not None:
            self._set_card_selected(self._selected_card, True)

    def _on_card_click(self, title: str) -> None:
        """Single click: select (and focus) the report card immediately."""
        self._mouse_selected = True
        self._keyboard_selected = False
        self._select_report(title)
        card = self._card_widgets.get(title)
        if card is not None:
            try:
                card.focus_set()
            except Exception:
                pass

    def _on_card_double_click(self, title: str) -> None:
        item = self._report_by_title(title)
        if item:
            item["open"](self)

    def _on_card_enter(self, title: str) -> None:
        self._select_report(title)
        item = self._report_by_title(title)
        if item:
            item["open"](self)

    def _on_open_button(self, title: str) -> None:
        """Visible 'Open' button on a card: opens the report in one click."""
        self._select_report(title)
        item = self._report_by_title(title)
        if item:
            item["open"](self)

    def _is_text_entry(self, widget) -> bool:
        """True when the widget is a text entry (CTkEntry or its inner
        tk.Entry, or a CTkComboBox's internal entry)."""
        if widget is None:
            return False
        if isinstance(widget, ctk.CTkEntry):
            return True
        return widget.__class__.__name__ == "Entry"

    def _on_hub_key(self, event) -> str:
        """Enter / arrows pressed anywhere on the hub (not inside the search
        entry): Enter opens the selected report, arrows move the selection."""
        if self.current_frame is not None:
            # A report is already open — the keys belong to it.
            return None
        if self._is_text_entry(self.focus_get()):
            return None
        if event.keysym in ("Return", "KP_Enter"):
            self._open_selected_report()
            return "break"
        return self._on_card_arrow(event)

    def _focus_first_report(self) -> None:
        """Give keyboard focus to the first visible report card so arrows /
        Enter work immediately after the hub opens (no click required)."""
        try:
            if self.current_frame is not None:
                return
            if not self._card_widgets:
                self._refresh_cards()
            if not self._card_widgets:
                return
            # If the user already started typing in search, leave focus there.
            if self._is_text_entry(self.focus_get()):
                return
            first = next(iter(self._card_widgets.values()))
            self._mouse_selected = False
            self._select_report(getattr(first, "_report_title", list(self._card_widgets.keys())[0]))
            try:
                first.focus_set()
            except Exception:
                pass
        except Exception:
            pass

    def _on_global_enter(self, _event=None) -> str:
        """Enter anywhere on the hub opens the selected report.

        With no selection, safely selects (and opens) the first visible
        report card.  Never crashes and never exits the application.
        """
        self._open_selected_report()
        return "break"

    def _open_selected_report(self) -> None:
        """Open the currently selected report; if none is selected, select
        the first visible card and open it (safe fallback)."""
        if self.current_frame is not None:
            # A report is already open — Enter does nothing (avoid double-open).
            return
        title = self.selected_title
        if title is None or title not in self._card_widgets:
            titles = self._visible_titles()
            if not titles:
                return
            title = titles[0]
            self._select_report(title)
        item = self._report_by_title(title)
        if item:
            item["open"](self)

    def _on_card_arrow(self, event) -> str:
        titles = self._visible_titles()
        if not titles:
            return "break"
        if self.selected_title in titles:
            index = titles.index(self.selected_title)
        else:
            index = -1
        columns = self._card_columns()
        if event.keysym == "Down":
            index += columns
        elif event.keysym == "Up":
            index -= columns
        elif event.keysym == "Right":
            index += 1
        elif event.keysym == "Left":
            index -= 1
        else:
            return "break"
        if index < 0 or index >= len(titles):
            return "break"
        self._mouse_selected = False
        self._keyboard_selected = True
        self._select_report(titles[index])
        card = self._card_widgets.get(titles[index])
        if card is not None:
            try:
                card.focus_set()
            except Exception:
                pass
        return "break"

    def _report_by_title(self, title: str) -> Optional[Dict[str, object]]:
        for item in self._report_defs:
            if item["title"] == title:
                return item
        return None

    def _actions_text(self, item: Dict[str, object]) -> str:
        """The report-specific action labels, shown on the card (no fake
        buttons — the actions come from the report's own implementation)."""
        actions = item.get("actions")
        if not actions:
            return ""
        return "Available: " + "  •  ".join(str(a) for a in actions)

    # ------------------------------------------------------------------ #
    # recently opened
    # ------------------------------------------------------------------ #
    def _refresh_recent(self) -> None:
        for child in self.recent_panel.winfo_children():
            child.destroy()

        entries = recent_reports(self.company_id)
        if not entries:
            ctk.CTkLabel(
                self.recent_panel, text="No reports opened yet in this company.",
                font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_MUTED,
                anchor="w",
            ).pack(anchor="w", padx=config.SPACING_LG, pady=config.SPACING_LG)
            return

        for entry in entries:
            row = ctk.CTkFrame(self.recent_panel, fg_color="transparent")
            row.pack(fill="x")
            self.recent_panel.grid_columnconfigure(0, weight=1)

            title = str(entry.get("report_name", ""))
            opened_at = str(entry.get("opened_at", ""))
            opened_by = str(entry.get("opened_by", "Admin"))
            try:
                opened_at = datetime.strptime(opened_at, config.DB_DATETIME_FORMAT).strftime(
                    config.DISPLAY_DATE_FORMAT + " " + config.TIME_DISPLAY_FORMAT)
            except Exception:
                opened_at = opened_at

            item = self._report_by_title(title)

            def _open_recent(t=title):
                entry_def = self._report_by_title(t)
                if entry_def:
                    entry_def["open"](self)

            ctk.CTkLabel(
                row, text=title, font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=config.SPACING_LG, pady=config.SPACING_MD)
            ctk.CTkLabel(
                row, text=opened_at, font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
            ).grid(row=0, column=1, sticky="e")
            ctk.CTkLabel(
                row, text=opened_by, font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
            ).grid(row=0, column=2, sticky="e", padx=config.SPACING_LG)
            ctk.CTkButton(
                row, text="Open", width=70, height=26,
                corner_radius=config.BUTTON_CORNER_RADIUS, command=_open_recent,
            ).grid(row=0, column=3, sticky="e", padx=config.SPACING_LG, pady=config.SPACING_SM)

            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=0)
            row.grid_columnconfigure(2, weight=0)
            row.grid_columnconfigure(3, weight=0)

    # ------------------------------------------------------------------ #
    # keyboard shortcuts
    # ------------------------------------------------------------------ #
    def _focus_search_entry(self) -> None:
        try:
            self.search_entry.focus_set()
        except Exception:
            pass

    def _on_advanced_report(self) -> None:
        """The app's report registry is this hub; focusing the search is the
        equivalent 'advanced' entry point (no fake backend is invented)."""
        self._focus_search_entry()
        self.search_entry.select_range(0, "end")

    def _on_ctrl_f(self, _event=None) -> str:
        self._focus_search_entry()
        return "break"

    def on_keyboard_back(self) -> None:
        """Esc: with a report open, close it and return to the hub; with no
        report open, return to the previous top-level screen (never quits)."""
        if self.current_frame is not None:
            self._close_report()
            return
        try:
            app = self.winfo_toplevel()
            if hasattr(app, "on_keyboard_back"):
                app.on_keyboard_back()
        except Exception:
            pass

    def _handle_back_shortcut(self) -> None:
        """The Esc / back button on this screen behaves exactly like Esc."""
        self.on_keyboard_back()

    def _forward(self, method_name: str):
        """Forward a shortcut to the currently open report UI if any."""
        ui = getattr(self, "current_report_ui", None)
        if ui is None:
            return None
        method = getattr(ui, method_name, None)
        if callable(method):
            return method
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
            self._refresh_recent()

    def on_keyboard_search(self) -> None:
        method = self._forward("on_keyboard_search")
        if method:
            method()
            return
        if self.current_report_ui is not None:
            self._focus_report_search()
            return
        self._focus_search_entry()

    def _focus_report_search(self) -> None:
        """Focus the open report's search field (most report screens expose
        ``search_entry``; fall back to the filter bar's first entry)."""
        ui = self.current_report_ui
        if ui is None:
            return
        entry = getattr(ui, "search_entry", None)
        if entry is not None and hasattr(entry, "focus_set"):
            try:
                entry.focus_set()
                entry.select_range(0, "end")
                return
            except Exception:
                pass
        # Fall back: find the filter bar body's first CTkEntry.
        try:
            filters = getattr(ui, "filters", None) or getattr(ui, "filter_bar", None)
            if filters is not None and hasattr(filters, "body"):
                for child in filters.body.winfo_children():
                    for sub in child.winfo_children():
                        if isinstance(sub, ctk.CTkEntry):
                            sub.focus_set()
                            return
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # global date control (Alt+F2 / F2)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _set_report_date(ui, attr: str, day) -> None:
        if hasattr(ui, attr) and hasattr(getattr(ui, attr), "set"):
            try:
                getattr(ui, attr).set(day.strftime(config.DISPLAY_DATE_FORMAT))
            except Exception:
                pass

    def on_global_date_period(self, from_date, to_date) -> None:
        """Forward the global period to the open report, then regenerate."""
        ui = self.current_report_ui
        if ui is None:
            return
        self._set_report_date(ui, "from_date_var", from_date)
        self._set_report_date(ui, "to_date_var", to_date)
        # As-on reports (outstanding/ageing/balance sheet/trial balance) use
        # the period's end date as their single As-On date.
        if hasattr(ui, "as_on_date_var") and not hasattr(ui, "from_date_var"):
            self._set_report_date(ui, "as_on_date_var", to_date)
        generate = getattr(ui, "_generate_report", None)
        if callable(generate):
            try:
                generate()
            except Exception:
                pass

    def on_global_single_date(self, day) -> None:
        """Forward the global single date to the open report, then regenerate."""
        ui = self.current_report_ui
        if ui is None:
            return
        self._set_report_date(ui, "from_date_var", day)
        self._set_report_date(ui, "to_date_var", day)
        if hasattr(ui, "as_on_date_var"):
            self._set_report_date(ui, "as_on_date_var", day)
        generate = getattr(ui, "_generate_report", None)
        if callable(generate):
            try:
                generate()
            except Exception:
                pass


def show_reports(parent: tk.Widget, company_id: int) -> ReportsHubUI:
    return ReportsHubUI(parent, company_id)
