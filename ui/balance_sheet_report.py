"""
Expenzo — Balance Sheet Report (Tally-style, with drill-down)

Redesigned as a flat, full-height report — no card-style scroll regions:

  * LEFT  = Liabilities & Capital
  * RIGHT = Assets
  * Both columns are equal width and equal height, and each side is a plain
    Treeview that fills the whole available vertical space with compact rows.
  * Internal scrollbars are hidden whenever every row fits; they appear only
    when accounts overflow the window.
  * Each side's TOTAL sits on a fixed bottom bar, both on the same horizontal
    line, with a summary strip below: date, Total Liabilities & Capital,
    Total Assets, Difference, and BALANCED / NOT BALANCED status.

Accounting: the equation Assets = Liabilities + Capital is enforced by the
existing balance_sheet_service (which reuses the trial-balance ledger
calculation).  A computed Opening Balance Adjustment covers opening balances
that were entered without a balancing capital entry, so the report reconciles
without touching the data.

Drill-down (unchanged from the previous design):

  * Account row   -> Ledger / Account History dialog (Date | Voucher No. |
                     Type | Particulars | Debit | Credit | Running Balance |
                     Dr/Cr).  Enter on a voucher row opens the original
                     voucher in the Vouchers screen.
  * Group heading -> list of the ledgers inside that group.
  * Keyboard: Up/Down move rows, Left/Right switch side, Enter opens,
    Esc closes drill-down / backs out.
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
from services.balance_sheet_service import (
    balance_sheet_service,
    TYPE_ASSETS,
    TYPE_LIABILITIES,
    TYPE_CAPITAL,
)
from services.voucher_service import voucher_service
from ui.report_base import (
    ReportBackHeader,
    FilterBar,
    ReportStatusBar,
    ReportActionBar,
    make_date_picker,
    make_button,
    wire_report_keyboard,
)
from utils import dialogs

# Treeview tag names used across the two side tables.
TAG_HEADER = "bs_header"
TAG_SUBTOTAL = "bs_subtotal"
TAG_TOTAL = "bs_total"
TAG_EVEN = "bs_even"
TAG_ODD = "bs_odd"

# Compact row height: normal data fits the window without internal scrolling.
ROW_HEIGHT = 24

# Ledger dialog columns (same order as the Ledger report screen).
LEDGER_COLUMNS = [
    ("date", "Date", 90),
    ("number", "Voucher No.", 95),
    ("type", "Type", 85),
    ("particulars", "Particulars", 240),
    ("debit", "Debit", 100),
    ("credit", "Credit", 100),
    ("balance", "Balance", 105),
    ("dr_cr", "Dr/Cr", 55),
]


def _parse_date(raw: Any) -> Optional[date]:
    """Parse a date from display (DD-MM-YYYY) or ISO (YYYY-MM-DD) format."""
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    for fmt in (config.DISPLAY_DATE_FORMAT, config.DB_DATE_FORMAT):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _format_date(raw: Any) -> str:
    d = _parse_date(raw)
    return d.strftime(config.DISPLAY_DATE_FORMAT) if d else str(raw)


class _SidePanel(ctk.CTkFrame):
    """One side of the balance sheet (Liabilities & Capital | Assets).

    A flat, full-height Treeview with a fixed bottom total bar.  The
    scrollbar is hidden whenever every row fits; it only appears when the
    account list overflows the available height.

    ``rows`` is a list of dicts: ``kind`` (account/heading/subtotal/total),
    ``name``, ``amount_text``, ``account_id``, ``entry`` (service entry for
    drill-down) and ``children`` (ledger list for group headings).
    """

    def __init__(self, parent, title: str):
        super().__init__(
            parent, fg_color="transparent",
        )
        self.title = title
        self.rows: List[Dict[str, Any]] = []

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_XS))
        ctk.CTkLabel(
            header, text=title, font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")
        self.count_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        )
        self.count_label.pack(side="left", padx=(config.SPACING_SM, 0))

        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame, columns=("account", "amount"), show="headings",
            selectmode="browse", style="Treeview",
        )
        self.tree.heading("account", text="Account", anchor="w")
        self.tree.heading("amount", text="Amount", anchor="e")
        self.tree.column("account", width=220, anchor="w", stretch=True)
        self.tree.column("amount", width=140, anchor="e", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Thin scrollbar; only packed when the rows overflow.
        self.vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                                 command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.vsb.set)
        self._scrollbar_shown = False

        try:
            style = ttk.Style(self.tree)
            style.configure("Treeview", rowheight=ROW_HEIGHT)
        except Exception:
            pass

        # Fixed bottom total bar — same horizontal line on both sides.
        total_bar = ctk.CTkFrame(
            self, fg_color=config.COLOR_BG_TERTIARY, corner_radius=8,
            height=34,
        )
        total_bar.pack(fill="x", pady=(config.SPACING_SM, 0))
        total_bar.pack_propagate(False)
        self.total_label = ctk.CTkLabel(
            total_bar, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="w",
        )
        self.total_label.pack(fill="both", padx=config.SPACING_MD,
                              pady=config.SPACING_XS)

        # Re-evaluate whether the scrollbar is needed on resize/render.
        self.tree.bind("<Configure>", lambda _e: self._refresh_scrollbar())

    # ------------------------------------------------------------------ #
    def _refresh_scrollbar(self) -> None:
        """Hide the scrollbar when every row fits, show it only on overflow."""
        try:
            if self.tree.winfo_height() <= 1 or not self.tree.get_children():
                return
            content_height = len(self.tree.get_children()) * ROW_HEIGHT
            needs = content_height > self.tree.winfo_height()
            if needs and not self._scrollbar_shown:
                self.vsb.grid(row=0, column=1, sticky="ns")
                self._scrollbar_shown = True
            elif not needs and self._scrollbar_shown:
                self.vsb.grid_forget()
                self._scrollbar_shown = False
        except Exception:
            pass

    def clear(self) -> None:
        self.rows.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._refresh_scrollbar()

    def _insert(self, kind: str, tags: str, name: str, amount_text: str,
                account_id: Optional[int], entry: Optional[Dict[str, Any]],
                children: Optional[List[Dict[str, Any]]] = None) -> None:
        iid = f"{self.title.replace(' ', '_')}-{len(self.rows)}"
        self.tree.insert("", tk.END, iid=iid, values=(name, amount_text),
                         tags=(tags,))
        self.rows.append({
            'kind': kind, 'name': name, 'amount_text': amount_text,
            'account_id': account_id, 'entry': entry, 'children': children or [],
        })

    def add_heading(self, name: str, children: List[Dict[str, Any]]) -> None:
        self._insert("heading", TAG_HEADER, name, "", None, None, children)

    def add_account(self, entry: Dict[str, Any]) -> None:
        amount = float(entry.get('net_balance', 0) or 0)
        tag = TAG_EVEN if len(self.rows) % 2 == 0 else TAG_ODD
        self._insert("account", tag, str(entry.get('account_name', '')),
                     f"{amount:,.2f}", entry.get('account_id'), entry)

    def add_subtotal(self, name: str, amount: float) -> None:
        self._insert("subtotal", TAG_SUBTOTAL, name, f"{amount:,.2f}", None, None)

    def add_total(self, name: str, amount: float) -> None:
        self._insert("total", TAG_TOTAL, name, f"{amount:,.2f}", None, None)

    def set_total_text(self, text: str) -> None:
        self.total_label.configure(text=text)

    def set_count(self, count: int) -> None:
        self.count_label.configure(text=f"{count} ledgers")

    def selected_row(self) -> Optional[Dict[str, Any]]:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return self.rows[int(selection[0].rsplit("-", 1)[1])]
        except (ValueError, IndexError):
            return None

    def select_index(self, index: int) -> None:
        if not (0 <= index < len(self.rows)):
            return
        item = self.tree.get_children()[index]
        self.tree.selection_set(item)
        self.tree.see(item)


class _DrillDownDialog(ctk.CTkToplevel):
    """Modal drill-down dialog: ledger history or group ledger list.

    ``rows`` is a list of dicts.  Ledger view rows carry ``kind``
    'opening'/'ledger_row'/'closing'; group view rows carry 'account'/'total'.
    ``on_open`` is called with the selected entry when Enter/double-click.
    """

    def __init__(self, parent, title: str, subtitle: str,
                 rows: List[Dict[str, Any]],
                 on_open: Optional[Any] = None,
                 account_id: Optional[int] = None):
        super().__init__(parent)
        self.title(title)
        self.geometry("980x560")
        self.minsize(760, 420)
        self.configure(fg_color=config.COLOR_BG_PRIMARY)
        self.transient(parent)
        self.on_open = on_open
        self.account_id = account_id
        self.rows = rows
        self._opened = False

        container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=config.SPACING_LG,
                       pady=config.SPACING_LG)
        container.grid_rowconfigure(2, weight=1)
        container.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(container, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, config.SPACING_SM))
        ctk.CTkButton(
            head, text="←", width=34, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._close,
        ).pack(side="left")
        title_block = ctk.CTkFrame(head, fg_color="transparent")
        title_block.pack(side="left", padx=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            title_block, text=title, font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text=subtitle, font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        self.summary_label = ctk.CTkLabel(
            container, text="", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_PRIMARY, anchor="w",
        )
        self.summary_label.grid(row=1, column=0, sticky="ew",
                                padx=config.SPACING_SM, pady=(0, config.SPACING_SM))

        tree_frame = ctk.CTkFrame(container, fg_color=config.COLOR_BG_SECONDARY,
                                  corner_radius=config.CARD_CORNER_RADIUS,
                                  border_width=1, border_color=config.COLOR_CARD_BORDER)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        is_ledger_view = any(row.get('kind') == 'ledger_row' for row in rows)
        if is_ledger_view:
            columns = LEDGER_COLUMNS
        else:
            columns = [("account", "Account", 320), ("amount", "Amount", 140)]
        col_ids = [c[0] for c in columns]
        self.tree = ttk.Treeview(tree_frame, columns=col_ids, show="headings",
                                 selectmode="browse", style="Treeview")
        for cid, heading, width in columns:
            self.tree.heading(cid, text=heading,
                              anchor="w" if cid in ("account", "particulars") else "e")
            self.tree.column(cid, width=width,
                             anchor="w" if cid in ("account", "particulars") else "e")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew",
                       padx=(config.SPACING_SM, 0), pady=config.SPACING_SM)
        vsb.grid(row=0, column=1, sticky="ns", pady=config.SPACING_SM)

        hint = ctk.CTkLabel(
            container,
            text="↑ ↓ move   |   Enter open   |   Esc close",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        )
        hint.grid(row=3, column=0, sticky="ew", pady=(config.SPACING_SM, 0))

        self._render(rows)
        self.tree.bind("<Double-Button-1>", lambda _e: self._open_selected())
        self.tree.bind("<Return>", lambda _e: self._open_selected())
        self.tree.bind("<KP_Enter>", lambda _e: self._open_selected())
        self.tree.bind("<Escape>", lambda _e: self._close())
        self.bind("<Escape>", lambda _e: self._close())

        self._set_summary(rows)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(60, lambda: (self.lift(), self.tree.focus_set()))
        self.grab_set()

    # ------------------------------------------------------------------ #
    def _render(self, rows: List[Dict[str, Any]]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._row_index: Dict[str, Dict[str, Any]] = {}
        for index, row in enumerate(rows):
            if row.get('kind') == 'ledger_row':
                values = (
                    _format_date(row.get('voucher_date', '')),
                    row.get('voucher_number', ''),
                    row.get('voucher_type', ''),
                    row.get('particulars', ''),
                    f"{float(row.get('debit_amount', 0) or 0):,.2f}",
                    f"{float(row.get('credit_amount', 0) or 0):,.2f}",
                    f"{float(row.get('running_balance', 0) or 0):,.2f}",
                    row.get('balance_type', ''),
                )
                tags = ('bs_even' if index % 2 == 0 else 'bs_odd',)
            elif row.get('kind') == 'heading':
                values = (row.get('name', ''), "")
                tags = ('bs_header',)
            elif row.get('kind') == 'total':
                values = (row.get('name', ''),
                          f"{float(row.get('amount', 0) or 0):,.2f}")
                tags = ('bs_total',)
            else:
                values = (row.get('name', ''),
                          f"{float(row.get('amount', 0) or 0):,.2f}")
                tags = ('bs_even' if index % 2 == 0 else 'bs_odd',)
            iid = f"r{index}"
            self.tree.insert("", tk.END, iid=iid, values=values, tags=tags)
            self._row_index[iid] = row
        if rows:
            self.tree.selection_set(self.tree.get_children()[0])

    def _set_summary(self, rows: List[Dict[str, Any]]) -> None:
        opening = closing = debit = credit = None
        for row in rows:
            if row.get('kind') == 'opening':
                opening = row.get('amount')
            elif row.get('kind') == 'closing':
                closing = row.get('amount')
            if row.get('kind') == 'ledger_row':
                debit = (debit or 0.0) + float(row.get('debit_amount', 0) or 0)
                credit = (credit or 0.0) + float(row.get('credit_amount', 0) or 0)
        parts = []
        if opening is not None:
            parts.append(f"Opening: {opening:,.2f}")
        if debit is not None:
            parts.append(f"Debit: {debit:,.2f}")
        if credit is not None:
            parts.append(f"Credit: {credit:,.2f}")
        if closing is not None:
            parts.append(f"Closing: {closing:,.2f}")
        if parts:
            self.summary_label.configure(text="   |   ".join(parts))

    def _selected_row(self) -> Optional[Dict[str, Any]]:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._row_index.get(selection[0])

    def _open_selected(self) -> None:
        row = self._selected_row()
        if row is None or self._opened:
            return
        if row.get('kind') in ('opening', 'closing', 'total'):
            return
        if self.on_open is not None:
            self._opened = True
            self.on_open(row)

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class BalanceSheetReportUI:
    """Tally-style, drillable Balance Sheet report screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None
        self._drill: Optional[_DrillDownDialog] = None
        self._focused_side: str = "left"
        self._saved_selection: Dict[int, int] = {0: 0, 1: 0}

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL,
                             pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Balance Sheet",
                         "Assets = Liabilities + Capital", on_back=self._back)

        filters = FilterBar(self.main_frame)
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        filters.add("As On Date", make_date_picker(filters.body, self.as_on_date_var))
        filters.add_actions(
            make_button(filters.body, "Generate", self._generate_report, accent=True),
            make_button(filters.body, "Clear", self._clear_filters),
        )
        filters.add_modify_filters()

        # Flat report body: equal-width, equal-height side tables.
        self.body = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.body.pack(fill="both", expand=True, pady=(config.SPACING_SM, 0))
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1, uniform="side")
        self.body.grid_columnconfigure(1, weight=1, uniform="side")

        self.left_panel = _SidePanel(self.body, "Liabilities & Capital")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, config.SPACING_MD))

        self.right_panel = _SidePanel(self.body, "Assets")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(config.SPACING_MD, 0))

        # Summary strip below both totals: date | totals | difference | status.
        self.summary_bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
            height=44,
        )
        self.summary_bar.pack(fill="x", pady=(config.SPACING_SM, 0))
        self.summary_bar.pack_propagate(False)
        self._build_summary_bar()

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
        self._configure_tree_tags()
        self._wire_keyboard()

    # ------------------------------------------------------------------ #
    # summary bar
    # ------------------------------------------------------------------ #
    def _build_summary_bar(self) -> None:
        for col in range(4):
            self.summary_bar.grid_columnconfigure(col, weight=1)
        self._summary_values: Dict[str, ctk.CTkLabel] = {}

        def _cell(col, label_text):
            cell = ctk.CTkFrame(self.summary_bar, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="nsew", padx=config.SPACING_MD)
            ctk.CTkLabel(
                cell, text=label_text, font=ctk.CTkFont(size=10),
                text_color=config.COLOR_TEXT_MUTED, anchor="w",
            ).pack(anchor="w")
            value = ctk.CTkLabel(
                cell, text="", font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY, anchor="w",
            )
            value.pack(anchor="w")
            return value

        self._summary_values['date'] = _cell(0, "Balance Sheet as of")
        self._summary_values['liab_capital'] = _cell(1, "Total Liabilities & Capital")
        self._summary_values['assets'] = _cell(2, "Total Assets")
        self._summary_values['difference'] = _cell(3, "Difference")

        # Status chip on the right edge of the summary strip.
        self.status_chip = ctk.CTkLabel(
            self.summary_bar, text="", font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLOR_BG_TERTIARY, corner_radius=8,
            padx=14, pady=6, text_color=config.COLOR_TEXT_PRIMARY,
        )
        self.status_chip.grid(row=0, column=4, sticky="e", padx=config.SPACING_LG)

    # ------------------------------------------------------------------ #
    # construction helpers
    # ------------------------------------------------------------------ #
    def _configure_tree_tags(self) -> None:
        style = ttk.Style(self.left_panel.tree)
        for tag, fg, bg, bold in [
            (TAG_HEADER, config.COLOR_TEXT_SECONDARY, config.COLOR_BG_MUTED, True),
            (TAG_SUBTOTAL, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_TERTIARY, True),
            (TAG_TOTAL, config.COLOR_PRIMARY, config.COLOR_BG_TERTIARY, True),
            (TAG_EVEN, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_MUTED, False),
            (TAG_ODD, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_SECONDARY, False),
        ]:
            try:
                style.configure(tag, foreground=fg, background=bg,
                                font=(config.FONT_FAMILY, 12, "bold" if bold else "normal"))
            except Exception:
                pass
        try:
            style.map(TAG_TOTAL, background=[("selected", config.COLOR_PRIMARY)],
                      foreground=[("selected", "#FFFFFF")])
            style.map(TAG_HEADER, background=[("selected", config.COLOR_BG_TERTIARY)],
                      foreground=[("selected", config.COLOR_TEXT_PRIMARY)])
        except Exception:
            pass

    def _wire_keyboard(self) -> None:
        """Row navigation on both trees: Up/Down within a side, Left/Right
        switch side, Enter opens, Esc closes drill-down / backs out."""
        for panel in (self.left_panel, self.right_panel):
            tree = panel.tree
            tree.bind("<Up>", lambda _e, p=panel: self._move_selection(p, -1))
            tree.bind("<Down>", lambda _e, p=panel: self._move_selection(p, 1))
            tree.bind("<Left>", lambda _e: self._switch_side("left"))
            tree.bind("<Right>", lambda _e: self._switch_side("right"))
            tree.bind("<Return>", lambda _e, p=panel: self._open_selected(p))
            tree.bind("<KP_Enter>", lambda _e, p=panel: self._open_selected(p))
            tree.bind("<Double-Button-1>", lambda _e, p=panel: self._open_selected(p))
            tree.bind("<Escape>", lambda _e: self._handle_escape())

        self.main_frame.bind("<Escape>", lambda _e: self._handle_escape())
        try:
            self.main_frame.winfo_toplevel().bind(
                "<Escape>", lambda _e: self._handle_escape(), add="+")
        except Exception:
            pass
        self.main_frame.bind("<Destroy>", self._on_destroy, add="+")

    def _handle_escape(self, _event=None) -> str:
        """Esc: close the drill-down first (never both at once), otherwise
        delegate to the report's back handler.  Always returns 'break' so the
        app-wide Esc binding does not also fire."""
        if self._drill is not None:
            try:
                self._drill._close()
            except Exception:
                pass
            self._drill = None
            return "break"
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()
        return "break"

    def _on_destroy(self, _event=None) -> None:
        try:
            self.main_frame.winfo_toplevel().unbind("<Escape>")
        except Exception:
            pass
        if self._drill is not None:
            try:
                self._drill.destroy()
            except Exception:
                pass
            self._drill = None

    # ------------------------------------------------------------------ #
    # navigation
    # ------------------------------------------------------------------ #
    def _side_index(self, panel) -> int:
        return 0 if panel is self.left_panel else 1

    def _current_panel(self) -> _SidePanel:
        return self.left_panel if self._focused_side == "left" else self.right_panel

    def _move_selection(self, panel: _SidePanel, delta: int) -> str:
        self._focused_side = "left" if panel is self.left_panel else "right"
        current = panel.tree.selection()
        index = -1
        if current:
            try:
                index = panel.tree.index(current[0])
            except Exception:
                index = -1
        new_index = max(0, min(len(panel.rows) - 1, index + delta)) if panel.rows else 0
        if panel.rows:
            panel.select_index(new_index)
            self._saved_selection[self._side_index(panel)] = new_index
        return "break"

    def _switch_side(self, side: str) -> str:
        self._focused_side = side
        panel = self._current_panel()
        index = self._saved_selection.get(self._side_index(panel), 0)
        if panel.rows:
            panel.select_index(min(index, len(panel.rows) - 1))
        else:
            panel.tree.focus_set()
        return "break"

    def _open_selected(self, panel: _SidePanel) -> None:
        self._focused_side = "left" if panel is self.left_panel else "right"
        row = panel.selected_row()
        if row is None:
            return
        index = panel.tree.index(panel.tree.selection()[0])
        self._saved_selection[self._side_index(panel)] = index
        if row['kind'] == "heading":
            self._open_group_detail(row)
        elif row['kind'] == "account":
            self._open_account_ledger(row['entry'])

    # ------------------------------------------------------------------ #
    # drill-down
    # ------------------------------------------------------------------ #
    def _drill_filters(self) -> Dict[str, Any]:
        """The current as-on date (the ledger dialog shows the full history
        from the start of the books to the as-on date)."""
        as_on = _parse_date(self.as_on_date_var.get())
        if as_on is None:
            as_on = date.today()
        return {'as_on': as_on}

    def _open_account_ledger(self, entry: Optional[Dict[str, Any]]) -> None:
        if not entry or entry.get('account_id') is None:
            return
        account_id = int(entry['account_id'])
        as_on = self._drill_filters()['as_on']

        account = None
        try:
            account = account_service.get_account(account_id)
        except Exception:
            account = None
        name = str(entry.get('account_name', ''))
        if account:
            name = str(account.get('name', name))
            code = str(account.get('code', ''))
            name = f"{name} ({code})" if code else name

        report = account_book_service.generate_account_book(
            self.company_id, account_id, date(1900, 1, 1), as_on)
        rows: List[Dict[str, Any]] = []
        if report.get('success'):
            opening = report.get('opening_balance', {})
            rows.append({'kind': 'opening', 'label': 'Opening',
                         'amount': float(opening.get('amount', 0) or 0)})
            for txn in report.get('transactions', []):
                rows.append({
                    'kind': 'ledger_row',
                    'voucher_date': txn.get('voucher_date', ''),
                    'voucher_number': txn.get('voucher_number', ''),
                    'voucher_type': txn.get('voucher_type', ''),
                    'particulars': self._txn_particulars(txn),
                    'debit_amount': txn.get('debit_amount', 0),
                    'credit_amount': txn.get('credit_amount', 0),
                    'running_balance': txn.get('running_balance', 0),
                    'balance_type': txn.get('balance_type', ''),
                    'voucher_id': txn.get('voucher_id'),
                })
            closing = report.get('closing_balance', {})
            rows.append({'kind': 'closing', 'label': 'Closing',
                         'amount': float(closing.get('amount', 0) or 0)})

        subtitle = f"As on {as_on.strftime(config.DISPLAY_DATE_FORMAT)}"
        self._drill = _DrillDownDialog(
            self.main_frame, "Account Ledger", name, rows,
            on_open=self._open_voucher_from_row, account_id=account_id)
        self._drill.summary_label.configure(
            text=f"Ledger: {name}   |   {subtitle}")

    def _open_group_detail(self, row: Dict[str, Any]) -> None:
        children = row.get('children', [])
        if not children:
            return
        rows: List[Dict[str, Any]] = []
        for child in children:
            amount = float(child.get('net_balance', 0) or 0)
            rows.append({'kind': 'account', 'name': child.get('account_name', ''),
                         'amount': amount, 'entry': child})
        rows.append({'kind': 'total', 'name': 'Total',
                     'amount': sum(float(c.get('net_balance', 0) or 0) for c in children)})
        self._drill = _DrillDownDialog(
            self.main_frame, "Group Ledgers", str(row.get('name', '')), rows,
            on_open=self._open_account_from_group)
        self._drill.summary_label.configure(
            text=f"{len(children)} ledgers   |   {row.get('name', '')}")

    def _open_account_from_group(self, row: Dict[str, Any]) -> None:
        self._drill = None
        self._open_account_ledger(row.get('entry'))

    def _txn_particulars(self, txn: Dict[str, Any]) -> str:
        narration = str(txn.get('narration', '') or '')
        if narration:
            return narration
        return str(txn.get('reference_number', '') or '')

    def _open_voucher_from_row(self, row: Dict[str, Any]) -> None:
        voucher_id = row.get('voucher_id')
        if not voucher_id:
            return
        try:
            voucher = voucher_service.get_voucher_with_details(int(voucher_id))
        except Exception:
            voucher = None
        if not voucher:
            dialogs.warn("Balance Sheet", "Voucher not found.", parent=self.parent)
            return
        self._route_to_vouchers(voucher)

    def _route_to_vouchers(self, voucher: Dict[str, Any]) -> None:
        """Leave the reports hub, open the Vouchers screen and load the
        voucher — same route the Ledger report uses."""
        try:
            app = self.main_frame.winfo_toplevel()
            if hasattr(app, "show_vouchers"):
                app.show_vouchers()
            view = getattr(app, "current_view", None)
            if view is not None and hasattr(view, "_load_voucher"):
                view._load_voucher(voucher)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # report generation / rendering
    # ------------------------------------------------------------------ #
    def _back(self) -> None:
        self._handle_escape()

    def _clear_filters(self) -> None:
        self.as_on_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.status.set("Filters cleared")

    def _generate_report(self) -> None:
        as_on = _parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Balance Sheet", "Invalid date. Use DD-MM-YYYY format.",
                         parent=self.parent)
            return
        report = balance_sheet_service.generate_balance_sheet(self.company_id, as_on)
        if not report.get('success'):
            dialogs.error("Balance Sheet",
                          report.get('error', 'Failed to generate report'),
                          parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        sections = report.get('sections', {})
        totals = report.get('totals', {})
        as_on = _parse_date(str(report.get('as_on_date', '')))

        # ---- LEFT: Liabilities & Capital ----
        left = self.left_panel
        left.clear()
        liab_entries = sections.get(TYPE_LIABILITIES, [])
        capital_entries = sections.get(TYPE_CAPITAL, [])
        if liab_entries:
            left.add_heading("Liabilities", liab_entries)
            for entry in liab_entries:
                left.add_account(entry)
            left.add_subtotal("Subtotal — Liabilities",
                              totals.get('total_liabilities', 0))
        if capital_entries:
            left.add_heading("Capital & Equity", capital_entries)
            for entry in capital_entries:
                left.add_account(entry)
            left.add_subtotal("Subtotal — Capital & Equity",
                              totals.get('total_capital', 0))
        left.add_total("Total Liabilities & Capital",
                       totals.get('total_liabilities_capital', 0))
        left.set_total_text(
            f"Total Liabilities & Capital: ₹ "
            f"{totals.get('total_liabilities_capital', 0):,.2f}")
        left.set_count(len(liab_entries) + len(capital_entries))

        # ---- RIGHT: Assets ----
        right = self.right_panel
        right.clear()
        asset_entries = sections.get(TYPE_ASSETS, [])
        if asset_entries:
            right.add_heading("Assets", asset_entries)
            for entry in asset_entries:
                right.add_account(entry)
            right.add_subtotal("Subtotal — Assets", totals.get('total_assets', 0))
        right.add_total("Total Assets", totals.get('total_assets', 0))
        right.set_total_text(f"Total Assets: ₹ {totals.get('total_assets', 0):,.2f}")
        right.set_count(len(asset_entries))

        # Restore saved selections (drill-down return keeps the same state).
        for panel in (left, right):
            index = self._saved_selection.get(self._side_index(panel), 0)
            if panel.rows:
                panel.select_index(min(index, len(panel.rows) - 1))
        self._current_panel().tree.focus_set()

        # ---- Summary strip + status ----
        total_assets = totals.get('total_assets', 0)
        total_liab_capital = totals.get('total_liabilities_capital', 0)
        difference = round(float(total_assets) - float(total_liab_capital), 2)
        balanced = report.get('is_balanced', False) and abs(difference) < 0.01

        self._summary_values['date'].configure(
            text=_format_date(as_on))
        self._summary_values['liab_capital'].configure(
            text=f"₹ {total_liab_capital:,.2f}")
        self._summary_values['assets'].configure(
            text=f"₹ {total_assets:,.2f}")
        self._summary_values['difference'].configure(
            text=f"₹ {difference:,.2f}")
        self.status_chip.configure(
            text="BALANCED ✓" if balanced else "NOT BALANCED ✗",
            text_color="#FFFFFF",
            fg_color=config.COLOR_INCOME if balanced else config.COLOR_EXPENSE)

        self.status.set(
            f"Balance Sheet as of {_format_date(as_on)} — "
            f"Assets {total_assets:,.2f} = "
            f"Liab+Capital {total_liab_capital:,.2f} — "
            f"{'Balanced' if balanced else 'NOT balanced'}")

    # ------------------------------------------------------------------ #
    # export
    # ------------------------------------------------------------------ #
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
