"""
Expenzo — Ledger (Tally-style Account Ledger Statement)

A keyboard-first, Tally-inspired ledger screen replacing the old
"Party Ledger" report.  It opens into a ledger selection/search view:
type a ledger name, pick it with Enter, and the full statement opens.

    Select Ledger  ->  [Date | Voucher No. | Type | Particulars |
                         Debit | Credit | Balance | Dr/Cr]
                       Opening Balance -> transactions -> Closing Balance

The statement reads from the existing ``account_book_service`` (which
reuses the voucher schema unchanged — no database or accounting logic is
touched), and shows every voucher type: Payment, Receipt, Contra, Sales,
Purchase, Journal.

Keyboard workflow: type-to-search + Enter to select a ledger; Tab/Enter
move From Date -> To Date -> table; Enter on a transaction row opens the
original voucher for editing (same route as the Day Book); F2 sets a
single date and Alt+F2 a date period via the global date control; Esc
returns to the Reports hub.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.account_book_service import account_book_service
from services.account_service import account_service
from services.voucher_service import voucher_service
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


class LedgerReportUI:
    """Tally-style ledger statement screen (any chart-of-accounts ledger)."""

    _COLUMNS = [
        {"id": "date", "heading": "Date", "width": 100},
        {"id": "number", "heading": "Voucher No.", "width": 110},
        {"id": "type", "heading": "Type", "width": 100},
        {"id": "particulars", "heading": "Particulars", "width": 240},
        {"id": "debit", "heading": "Debit", "width": 110, "anchor": "e"},
        {"id": "credit", "heading": "Credit", "width": 110, "anchor": "e"},
        {"id": "balance", "heading": "Balance", "width": 120, "anchor": "e"},
        {"id": "dr_cr", "heading": "Dr/Cr", "width": 60, "anchor": "center"},
    ]

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None
        self.current_account: Optional[Dict[str, Any]] = None
        self.all_accounts: List[Dict[str, Any]] = []
        self._filtered_accounts: List[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL,
                             pady=config.SPACING_XL)

        # Vars must exist before the builders bind to them.
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_search_results())

        self._build_header()
        self._build_selection_stage()
        self._build_statement_stage()
        self._build_action_bar()
        self.status = ReportStatusBar(self.main_frame)

        self._load_accounts()
        self._show_selection_stage()
        wire_report_keyboard(self)

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        self.header = header

        ctk.CTkButton(
            header, text="←", width=36, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._back,
        ).pack(side="left")

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(side="left", padx=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            title_block, text="Ledger", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Account ledger statement",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        # Current ledger + active period badge (clearly visible, updates on
        # generate / F2 / Alt+F2).
        badge_block = ctk.CTkFrame(header, fg_color="transparent")
        badge_block.pack(side="right")
        self.ledger_badge = ctk.CTkLabel(
            badge_block, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="e",
        )
        self.ledger_badge.pack(anchor="e")
        self.period_badge = ctk.CTkLabel(
            badge_block, text="", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="e",
        )
        self.period_badge.pack(anchor="e")

    def _build_selection_stage(self) -> None:
        """Ledger selection / search view (shown before a ledger is picked)."""
        stage = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        stage.pack(fill="both", expand=True)
        self.selection_stage = stage
        stage.grid_rowconfigure(2, weight=1)
        stage.grid_columnconfigure(0, weight=1)

        prompt = ctk.CTkFrame(stage, fg_color="transparent")
        prompt.grid(row=0, column=0, sticky="ew",
                    padx=config.SPACING_LG, pady=(config.SPACING_LG, 0))
        ctk.CTkLabel(
            prompt, text="Select Ledger", font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            prompt, text="Type a ledger name to search, then press Enter to open its statement.",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", pady=(2, 0))

        search_row = ctk.CTkFrame(stage, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew",
                        padx=config.SPACING_LG, pady=(config.SPACING_MD, 0))
        search_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            search_row, text="⌕", font=ctk.CTkFont(size=18),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).grid(row=0, column=0, padx=(0, config.SPACING_SM))
        self.search_entry = ctk.CTkEntry(
            search_row, textvariable=self.search_var, height=34,
            placeholder_text="Type ledger name / code / group...",
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.search_entry.grid(row=0, column=1, sticky="ew")
        self.search_entry.bind("<Return>", self._on_search_enter)
        self.search_entry.bind("<KP_Enter>", self._on_search_enter)
        self.search_entry.bind("<Down>", lambda _e: self._focus_search_tree())
        self.search_entry.bind("<Escape>", lambda _e: self._clear_search())

        # Results list: Name | Code | Group.
        tree_frame = ctk.CTkFrame(stage, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew",
                        padx=config.SPACING_LG, pady=config.SPACING_MD)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.search_tree = ttk.Treeview(
            tree_frame, columns=("name", "code", "group"), show="headings",
            selectmode="browse",
        )
        for col, heading, width in [("name", "Ledger Name", 320),
                                    ("code", "Code", 120),
                                    ("group", "Under", 200)]:
            self.search_tree.heading(col, text=heading)
            self.search_tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.search_tree.yview)
        self.search_tree.configure(yscrollcommand=vsb.set)
        self.search_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.search_tree.bind("<Return>", self._on_search_enter)
        self.search_tree.bind("<KP_Enter>", self._on_search_enter)
        self.search_tree.bind("<Double-Button-1>", lambda _e: self._on_search_enter())
        self.search_tree.bind("<Up>", self._on_tree_up)
        self.search_tree.bind("<Escape>", lambda _e: self.search_entry.focus_set())

        self.search_hint = ctk.CTkLabel(
            stage, text="↑ ↓  move   |   Enter  open ledger   |   Type to search",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED, anchor="w",
        )
        self.search_hint.grid(row=3, column=0, sticky="ew",
                              padx=config.SPACING_LG, pady=(0, config.SPACING_MD))

    def _build_statement_stage(self) -> None:
        """Ledger statement view (filters + table), hidden until selection."""
        stage = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        stage.pack(fill="both", expand=True)
        self.statement_stage = stage

        filters = FilterBar(stage)
        self.filters = filters
        filters.add("From Date", make_date_picker(filters.body, self.from_date_var))
        filters.add("To Date", make_date_picker(filters.body, self.to_date_var))
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        self.table = ReportTable(stage, [dict(c) for c in self._COLUMNS])
        self.table.show_empty("No ledger selected yet.")
        try:
            self.table.tree.tag_configure("odd", background=config.COLOR_BG_MUTED)
        except Exception:
            pass

        # Enter on a transaction row opens the original voucher.
        self.table.tree.bind("<Return>", lambda _e: self._open_selected_voucher())
        self.table.tree.bind("<KP_Enter>", lambda _e: self._open_selected_voucher())
        self.table.tree.bind("<Double-Button-1>", lambda _e: self._open_selected_voucher())
        self.table.tree.bind("<ButtonRelease-1>", self._on_row_selected)

    def _build_action_bar(self) -> None:
        ReportActionBar(
            self.main_frame,
            refresh=self._generate_report,
            exports=[("Export CSV", self._export_to_csv),
                     ("Export JSON", self._export_to_json),
                     ("Export PNG", self._export_to_png)],
            clear=self._clear_filters,
            back=self._back,
        )

    # ------------------------------------------------------------------ #
    # stage switching
    # ------------------------------------------------------------------ #
    def _show_selection_stage(self) -> None:
        self.statement_stage.pack_forget()
        self.selection_stage.pack(fill="both", expand=True)
        self.search_entry.focus_set()

    def _show_statement_stage(self) -> None:
        self.selection_stage.pack_forget()
        self.statement_stage.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # ledger search / selection
    # ------------------------------------------------------------------ #
    def _load_accounts(self) -> None:
        try:
            self.all_accounts = account_service.search_accounts(
                self.company_id, include_inactive=False)
        except Exception:
            self.all_accounts = []
        self._refresh_search_results()

    def _refresh_search_results(self) -> None:
        term = self.search_var.get().strip().lower()
        if term:
            self._filtered_accounts = [
                a for a in self.all_accounts
                if term in str(a.get('name', '')).lower()
                or term in str(a.get('code', '')).lower()
                or term in str(a.get('account_group', '')).lower()
            ]
        else:
            self._filtered_accounts = list(self.all_accounts)
        self._filtered_accounts = self._filtered_accounts[:200]
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        for account in self._filtered_accounts:
            self.search_tree.insert("", tk.END, iid=str(account['id']), values=(
                account.get('name', ''),
                account.get('code', ''),
                account.get('account_group', ''),
            ))
        if self._filtered_accounts:
            self.search_tree.selection_set(self.search_tree.get_children()[0])

    def _focus_search_tree(self) -> None:
        if self._filtered_accounts:
            self.search_tree.focus_set()

    def _on_tree_up(self, _event=None) -> str:
        # From the tree, Up on the first row returns to the search box.
        if self.search_tree.get_children():
            if self.search_tree.selection() == (self.search_tree.get_children()[0],):
                self.search_entry.focus_set()
                return "break"
        return None

    def _on_search_enter(self, _event=None) -> str:
        selection = self.search_tree.selection()
        if not selection:
            selection = self.search_tree.get_children()
        if not selection:
            return "break"
        account_id = int(selection[0])
        self._select_account(account_id)
        return "break"

    def _clear_search(self) -> None:
        self.search_var.set("")
        self.search_entry.focus_set()

    def _select_account(self, account_id: int) -> None:
        account = next((a for a in self.all_accounts if int(a['id']) == int(account_id)), None)
        if account is None:
            try:
                account = account_service.get_account(account_id)
            except Exception:
                account = None
        if account is None:
            dialogs.warn("Ledger", "Ledger not found.", parent=self.parent)
            return
        self.current_account = account
        self.ledger_badge.configure(
            text=f"{account.get('name', '')} ({account.get('code', '')})")
        self._show_statement_stage()
        self._generate_report()

    # ------------------------------------------------------------------ #
    # statement generation
    # ------------------------------------------------------------------ #
    def _parse_date(self, raw: str) -> Optional[date]:
        for fmt in (config.DISPLAY_DATE_FORMAT, config.DB_DATE_FORMAT):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _format_date(self, raw: Any) -> str:
        d = self._parse_date(str(raw))
        if d is None:
            return str(raw)
        return d.strftime(config.DISPLAY_DATE_FORMAT)

    def _clear_filters(self) -> None:
        self.from_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self._update_period_badge()
        if self.current_account is not None:
            self._generate_report()
        else:
            self.table.show_empty("No ledger selected yet.")
            self.status.set("Filters cleared")

    def _generate_report(self) -> None:
        if self.current_account is None:
            self.table.show_empty("Select a ledger first.")
            self._update_period_badge()
            return
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Ledger", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Ledger", "From Date cannot be after To Date.", parent=self.parent)
            return

        report = account_book_service.generate_account_book(
            self.company_id, self.current_account['id'], from_date, to_date)
        if not report.get('success'):
            dialogs.error("Ledger", report.get('error', 'Failed to generate report'),
                          parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)
        self._update_period_badge()

    def _render(self, report: Dict[str, Any]) -> None:
        self.table.hide_empty()
        self.table.clear()
        opening = report.get('opening_balance', {})
        self.table.tree.insert("", tk.END, values=(
            self._format_date(report.get('from_date', '')),
            "Opening", "", "Balance brought forward",
            "", "",
            f"{opening.get('amount', 0):,.2f}",
            opening.get('type', ''),
        ))
        for index, txn in enumerate(report.get('transactions', [])):
            # Transaction rows are keyed by voucher id so Enter / double-click
            # can reopen the original voucher.
            iid = str(txn.get('voucher_id', 0))
            self.table.tree.insert("", tk.END, iid=iid, values=(
                self._format_date(txn.get('voucher_date', '')),
                txn.get('voucher_number', ''),
                txn.get('voucher_type', ''),
                self._txn_particulars(txn),
                f"{txn.get('debit_amount', 0):,.2f}",
                f"{txn.get('credit_amount', 0):,.2f}",
                f"{txn.get('running_balance', 0):,.2f}",
                txn.get('balance_type', ''),
            ), tags=('even' if index % 2 == 0 else 'odd',))
        closing = report.get('closing_balance', {})
        self.table.tree.insert("", tk.END, values=(
            self._format_date(report.get('to_date', '')),
            "Closing", "", "Balance carried down",
            "", "",
            f"{closing.get('amount', 0):,.2f}",
            closing.get('type', ''),
        ))

        account = self.current_account or {}
        totals = {
            'debit': sum(float(t.get('debit_amount', 0) or 0)
                         for t in report.get('transactions', [])),
            'credit': sum(float(t.get('credit_amount', 0) or 0)
                          for t in report.get('transactions', [])),
        }
        self.table.set_totals(
            f"Ledger: {account.get('name', '')} ({account.get('code', '')})   |   "
            f"Opening: {opening.get('amount', 0):,.2f} {opening.get('type', '')}   |   "
            f"Debit: {totals['debit']:,.2f}   Credit: {totals['credit']:,.2f}   |   "
            f"Closing: {closing.get('amount', 0):,.2f} {closing.get('type', '')}"
        )
        count = report.get('transaction_count', 0)
        self.status.set(
            f"Ledger generated: {count} transactions "
            f"({self._format_date(report.get('from_date', ''))} to "
            f"{self._format_date(report.get('to_date', ''))})"
        )

    def _txn_particulars(self, txn: Dict[str, Any]) -> str:
        """The contra/other-side account if known, else the voucher narration."""
        narration = str(txn.get('narration', '') or '')
        if narration:
            return narration
        return str(txn.get('reference_number', '') or '')

    def _update_period_badge(self) -> None:
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if from_date and to_date:
            if from_date == to_date:
                self.period_badge.configure(
                    text=f"As on: {from_date.strftime(config.DISPLAY_DATE_FORMAT)}")
            else:
                self.period_badge.configure(
                    text=f"Period: {from_date.strftime(config.DISPLAY_DATE_FORMAT)}  to  "
                         f"{to_date.strftime(config.DISPLAY_DATE_FORMAT)}")
        else:
            self.period_badge.configure(text="")

    # ------------------------------------------------------------------ #
    # open the original voucher
    # ------------------------------------------------------------------ #
    def _on_row_selected(self, _event=None) -> None:
        return None

    def _selected_voucher(self) -> Optional[Dict[str, Any]]:
        selection = self.table.tree.selection()
        if not selection:
            return None
        # Rows are keyed by voucher id; opening/closing rows have no id and
        # are skipped.
        iid = selection[0]
        try:
            voucher_id = int(iid)
        except (ValueError, TypeError):
            return None
        if voucher_id <= 0:
            return None
        return voucher_service.get_voucher_with_details(voucher_id)

    def _open_selected_voucher(self) -> None:
        voucher = self._selected_voucher()
        if voucher is None:
            dialogs.warn("Ledger", "Select a transaction to open.", parent=self.parent)
            return
        self._open_voucher_in_editor(voucher)

    def _open_voucher_in_editor(self, voucher: Dict[str, Any],
                                read_only: bool = False) -> None:
        """Open the existing Voucher Entry screen and load the voucher."""
        self._route_to_vouchers()
        try:
            app = self.winfo_toplevel()
            view = getattr(app, "current_view", None)
            if view is not None and hasattr(view, "_load_voucher"):
                view._load_voucher(voucher)
                if read_only:
                    view._set_read_only(True)
        except Exception:
            pass

    def _route_to_vouchers(self) -> None:
        try:
            app = self.winfo_toplevel()
            if hasattr(app, "show_vouchers"):
                app.show_vouchers()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # export
    # ------------------------------------------------------------------ #
    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the ledger first.", parent=self.parent)
            return
        success, path = account_book_service.export_account_book_to_csv(
            self.current_report_data, "ledger")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the ledger first.", parent=self.parent)
            return
        success, path = account_book_service.export_to_json(
            self.current_report_data, "ledger")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the ledger first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table, "ledger")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    # ------------------------------------------------------------------ #
    # navigation / keyboard hooks
    # ------------------------------------------------------------------ #
    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def on_global_date_period(self, from_date, to_date) -> None:
        try:
            self.from_date_var.set(from_date.strftime(config.DISPLAY_DATE_FORMAT))
            self.to_date_var.set(to_date.strftime(config.DISPLAY_DATE_FORMAT))
        except Exception:
            pass
        self._update_period_badge()
        if self.current_account is not None:
            self._generate_report()

    def on_global_single_date(self, day) -> None:
        try:
            self.from_date_var.set(day.strftime(config.DISPLAY_DATE_FORMAT))
            self.to_date_var.set(day.strftime(config.DISPLAY_DATE_FORMAT))
        except Exception:
            pass
        self._update_period_badge()
        if self.current_account is not None:
            self._generate_report()


def show_ledger_report(parent: tk.Widget, company_id: int) -> LedgerReportUI:
    return LedgerReportUI(parent, company_id)
