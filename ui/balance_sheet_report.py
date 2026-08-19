"""
Expenzo — Balance Sheet Report (Tally Prime-style, with drill-down)
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk

import config
from database.database import db
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

# Treeview tag names
TAG_HEADER = "bs_header"
TAG_SUBTOTAL = "bs_subtotal"
TAG_TOTAL = "bs_total"
TAG_EVEN = "bs_even"
TAG_ODD = "bs_odd"
TAG_GROUP = "bs_group"
TAG_SUBGROUP = "bs_subgroup"

ROW_HEIGHT = 24

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


def _format_indian(amount: float) -> str:
    try:
        val = round(float(amount or 0.0), 2)
        sign = "-" if val < 0 else ""
        val = abs(val)
        integer_part = int(val)
        decimal_part = round(val - integer_part, 2)
        s = str(integer_part)
        if len(s) <= 3:
            formatted_int = s
        else:
            last3 = s[-3:]
            rest = s[:-3]
            parts = []
            while len(rest) > 2:
                parts.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                parts.append(rest)
            formatted_int = ",".join(reversed(parts)) + "," + last3
        if decimal_part > 0:
            return f"{sign}{formatted_int}.{int(round(decimal_part * 100)):02d}"
        return f"{sign}{formatted_int}.00"
    except Exception:
        return f"{amount:,.2f}"


class _SidePanel(ctk.CTkFrame):
    def __init__(self, parent, title: str):
        super().__init__(parent, fg_color="transparent")
        self.title = title
        self.rows: List[Dict[str, Any]] = []
        self._group_children = {}
        self._group_subtotal = {}
        self._expanded = set()

        if "Liabilities" in title:
            self.total_label = ctk.CTkLabel(self, text="Total Liabilities & Capital")
        else:
            self.total_label = ctk.CTkLabel(self, text="Total Assets")

        self.tree = ttk.Treeview(
            self, columns=("account", "amount"), show="headings",
            selectmode="browse", style="Treeview",
        )
        self.tree.heading("account", text="", anchor="w")
        self.tree.heading("amount", text="", anchor="e")
        self.tree.column("account", width=280, anchor="w", stretch=True)
        self.tree.column("amount", width=160, anchor="e", stretch=False)
        self.tree.pack(fill="both", expand=True, padx=0, pady=0)

        try:
            style = ttk.Style(self.tree)
            style.configure("Treeview", rowheight=ROW_HEIGHT)
        except Exception:
            pass

        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self.tree.bind("<<TreeviewClose>>", self._on_close)
        self._scrollbar_shown = False

    def clear(self) -> None:
        self.rows.clear()
        self._group_children.clear()
        self._group_subtotal.clear()
        self._expanded.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _make_iid(self, prefix: str) -> str:
        return f"{self.title.replace(' ', '_')}-{prefix}-{len(self.rows)}"

    def _insert_node(self, parent_iid: str, kind: str, tags: str, name: str,
                     amount_text: str, account_id: Optional[int],
                     entry: Optional[Dict[str, Any]], level: int = 0) -> str:
        display_name = ("    " * level) + name
        iid = self._make_iid(kind)
        self.tree.insert(parent_iid, "end", iid=iid,
                         values=(display_name, amount_text), tags=(tags,))
        self.rows.append({
            'kind': kind, 'name': name, 'amount_text': amount_text,
            'account_id': account_id, 'entry': entry, 'children': [],
            'level': level, 'iid': iid,
        })
        return iid

    def add_group_heading(self, name: str, total_amount: float, children: List[Dict[str, Any]]) -> str:
        amount_text = _format_indian(total_amount)
        iid = self._insert_node("", "heading", TAG_GROUP, name, amount_text, None, None, level=0)
        self._group_children[iid] = children
        self.tree.item(iid, open=False)
        return iid

    def add_account(self, entry: Dict[str, Any], parent_iid: Optional[str] = None) -> None:
        amount = float(entry.get('net_balance', 0) or 0)
        tag = TAG_EVEN if len(self.rows) % 2 == 0 else TAG_ODD
        level = 1 if parent_iid else 0
        self._insert_node(parent_iid or "", "account", tag,
                          str(entry.get('account_name', '')),
                          _format_indian(amount), entry.get('account_id'), entry, level)

    def add_subtotal(self, name: str, amount: float, parent_iid: Optional[str] = None) -> None:
        self._insert_node(parent_iid or "", "subtotal", TAG_SUBTOTAL,
                          name, _format_indian(amount), None, None, level=1)

    def add_total(self, name: str, amount: float) -> None:
        self._insert_node("", "total", TAG_TOTAL, name,
                          _format_indian(amount), None, None, level=0)

    def _on_open(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self._group_children and iid not in self._expanded:
            self._expanded.add(iid)
            children = self._group_children.get(iid, [])
            for entry in children:
                self.add_account(entry, parent_iid=iid)

    def _on_close(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self._expanded:
            for child in self.tree.get_children(iid):
                self.tree.delete(child)
            self._expanded.discard(iid)

    def selected_row(self) -> Optional[Dict[str, Any]]:
        selection = self.tree.selection()
        if not selection:
            return None
        iid = selection[0]
        for row in self.rows:
            if row.get('iid') == iid:
                return row
        try:
            idx = self.tree.index(iid)
            return self.rows[idx]
        except Exception:
            return None

    def select_index(self, index: int) -> None:
        children = self.tree.get_children("")
        if 0 <= index < len(children):
            item = children[index]
            self.tree.selection_set(item)
            self.tree.see(item)


class _DrillDownDialog(ctk.CTkToplevel):
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
        container.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=config.SPACING_LG)
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
        ctk.CTkLabel(title_block, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(title_block, text=subtitle, font=ctk.CTkFont(size=12),
                      text_color=config.COLOR_TEXT_SECONDARY).pack(anchor="w")

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
                    _format_indian(float(row.get('debit_amount', 0) or 0)),
                    _format_indian(float(row.get('credit_amount', 0) or 0)),
                    _format_indian(float(row.get('running_balance', 0) or 0)),
                    row.get('balance_type', ''),
                )
                tags = ('bs_even' if index % 2 == 0 else 'bs_odd',)
            elif row.get('kind') == 'heading':
                values = (row.get('name', ''), "")
                tags = ('bs_header',)
            elif row.get('kind') == 'total':
                values = (row.get('name', ''),
                          _format_indian(float(row.get('amount', 0) or 0)))
                tags = ('bs_total',)
            else:
                values = (row.get('name', ''),
                          _format_indian(float(row.get('amount', 0) or 0)))
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
            parts.append(f"Opening: {_format_indian(opening)}")
        if debit is not None:
            parts.append(f"Debit: {_format_indian(debit)}")
        if credit is not None:
            parts.append(f"Credit: {_format_indian(credit)}")
        if closing is not None:
            parts.append(f"Closing: {_format_indian(closing)}")
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
    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None
        self._drill: Optional[_DrillDownDialog] = None
        self._focused_side: str = "left"
        self._saved_selection: Dict[int, int] = {0: 0, 1: 0}

        # MAIN CONTAINER
        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self.main_frame.grid_rowconfigure(0, weight=0)   # Top Bar
        self.main_frame.grid_rowconfigure(1, weight=0)   # Column Header
        self.main_frame.grid_rowconfigure(2, weight=1)   # Main Body (Tables stretch)
        self.main_frame.grid_rowconfigure(3, weight=0)   # Summary Bar
        self.main_frame.grid_rowconfigure(4, weight=0)   # Status Bar
        self.main_frame.grid_columnconfigure(0, weight=1)

        # 1. TOP BAR (Height: 32px)
        top_bar = ctk.CTkFrame(self.main_frame, fg_color=config.COLOR_BG_TERTIARY, height=32, corner_radius=0)
        top_bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        top_bar.pack_propagate(False)
        top_bar.grid_columnconfigure(0, weight=1)
        top_bar.grid_columnconfigure(1, weight=0)
        top_bar.grid_columnconfigure(2, weight=0)

        left_top = ctk.CTkFrame(top_bar, fg_color="transparent")
        left_top.grid(row=0, column=0, sticky="w", padx=8, pady=2)
        ctk.CTkButton(left_top, text="←", width=26, height=22,
                      corner_radius=4, fg_color="transparent",
                      text_color=config.COLOR_TEXT_PRIMARY,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._back).pack(side="left")
        ctk.CTkLabel(left_top, text="Balance Sheet",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=config.COLOR_TEXT_PRIMARY).pack(side="left", padx=(6, 0))

        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        filter_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        filter_frame.grid(row=0, column=1, sticky="ew", padx=8)
        ctk.CTkLabel(filter_frame, text="As on", font=ctk.CTkFont(size=11),
                     text_color=config.COLOR_TEXT_SECONDARY).pack(side="left", padx=(0, 4))
        make_date_picker(filter_frame, self.as_on_date_var).pack(side="left", padx=(0, 8))
        make_button(filter_frame, "Generate", self._generate_report, width=80, accent=True).pack(side="left", padx=2)
        make_button(filter_frame, "Clear", self._clear_filters, width=60).pack(side="left", padx=2)

        right_top = ctk.CTkFrame(top_bar, fg_color="transparent")
        right_top.grid(row=0, column=2, sticky="e", padx=8, pady=2)
        make_button(right_top, "CSV", self._export_to_csv, width=50).pack(side="left", padx=1)
        make_button(right_top, "JSON", self._export_to_json, width=50).pack(side="left", padx=1)
        make_button(right_top, "PNG", self._export_to_png, width=50).pack(side="left", padx=1)

        # 2. COLUMN HEADERS (Height: 34px)
        self.company_header = ctk.CTkFrame(self.main_frame, fg_color=config.COLOR_BG_SECONDARY, height=34, corner_radius=0)
        self.company_header.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        self.company_header.pack_propagate(False)
        self.company_header.grid_columnconfigure(0, weight=1)
        self.company_header.grid_columnconfigure(1, weight=1)

        left_header = ctk.CTkFrame(self.company_header, fg_color="transparent")
        left_header.grid(row=0, column=0, sticky="nsew", padx=(12, 6))
        left_header.grid_columnconfigure(0, weight=1)
        left_header.grid_columnconfigure(1, weight=0)
        self.left_header_label = ctk.CTkLabel(
            left_header, text="Liabilities",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        )
        self.left_header_label.grid(row=0, column=0, sticky="ew")
        self.left_sub_label = ctk.CTkLabel(
            left_header, text="", font=ctk.CTkFont(size=10),
            text_color=config.COLOR_TEXT_MUTED, anchor="e",
        )
        self.left_sub_label.grid(row=0, column=1, sticky="e")

        right_header = ctk.CTkFrame(self.company_header, fg_color="transparent")
        right_header.grid(row=0, column=1, sticky="nsew", padx=(6, 12))
        right_header.grid_columnconfigure(0, weight=1)
        right_header.grid_columnconfigure(1, weight=0)
        self.right_header_label = ctk.CTkLabel(
            right_header, text="Assets",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        )
        self.right_header_label.grid(row=0, column=0, sticky="ew")
        self.right_sub_label = ctk.CTkLabel(
            right_header, text="", font=ctk.CTkFont(size=10),
            text_color=config.COLOR_TEXT_MUTED, anchor="e",
        )
        self.right_sub_label.grid(row=0, column=1, sticky="e")

        # 3. BODY (Takes remaining screen height)
        self.body = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1, uniform="side")
        self.body.grid_columnconfigure(1, weight=1, uniform="side")

        self.left_panel = _SidePanel(self.body, "Liabilities")
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=4)

        self.right_panel = _SidePanel(self.body, "Assets")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=4)

        # 4. SUMMARY BAR (Clear height of 52px so values show properly)
        self.summary_bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=6, height=52,
        )
        self.summary_bar.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 2))
        self.summary_bar.pack_propagate(False)
        self._build_summary_bar()

        # 5. STATUS BAR
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var,
            font=ctk.CTkFont(size=10), text_color=config.COLOR_TEXT_SECONDARY,
            anchor="w", height=18,
        )
        self.status_label.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 4))

        self.status = type('Status', (object,), {'status_var': self.status_var})()

        wire_report_keyboard(self)
        self._configure_tree_tags()
        self._wire_keyboard()

    def _build_summary_bar(self) -> None:
        cells_frame = ctk.CTkFrame(self.summary_bar, fg_color="transparent")
        cells_frame.pack(fill="both", expand=True, padx=12, pady=2)
        for i in range(4):
            cells_frame.grid_columnconfigure(i, weight=1)
        cells_frame.grid_columnconfigure(4, weight=0)

        def _cell(col, label_text):
            cell = ctk.CTkFrame(cells_frame, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="w", pady=1)
            ctk.CTkLabel(
                cell, text=label_text, font=ctk.CTkFont(size=9),
                text_color=config.COLOR_TEXT_MUTED, anchor="w",
            ).pack(anchor="w")
            value = ctk.CTkLabel(
                cell, text="-", font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY, anchor="w",
            )
            value.pack(anchor="w")
            return value

        self._summary_values: Dict[str, ctk.CTkLabel] = {}
        self._summary_values['date'] = _cell(0, "Balance Sheet as of")
        self._summary_values['liab_capital'] = _cell(1, "Total Liabilities & Capital")
        self._summary_values['assets'] = _cell(2, "Total Assets")
        self._summary_values['difference'] = _cell(3, "Difference")

        self.status_chip = ctk.CTkLabel(
            cells_frame, text="BALANCED ✓", font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLOR_INCOME, corner_radius=4,
            padx=12, pady=4, text_color="#FFFFFF",
        )
        self.status_chip.grid(row=0, column=4, sticky="e", padx=(10, 0), pady=4)

    def _configure_tree_tags(self) -> None:
        style = ttk.Style(self.left_panel.tree)
        for tag, fg, bg, bold in [
            (TAG_GROUP, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_PRIMARY, True),
            (TAG_SUBGROUP, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_PRIMARY, True),
            (TAG_HEADER, config.COLOR_TEXT_SECONDARY, config.COLOR_BG_MUTED, True),
            (TAG_SUBTOTAL, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_TERTIARY, True),
            (TAG_TOTAL, config.COLOR_PRIMARY, config.COLOR_BG_TERTIARY, True),
            (TAG_EVEN, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_PRIMARY, False),
            (TAG_ODD, config.COLOR_TEXT_PRIMARY, config.COLOR_BG_SECONDARY, False),
        ]:
            try:
                style.configure(tag, foreground=fg, background=bg,
                                font=(config.FONT_FAMILY, 11, "bold" if bold else "normal"))
            except Exception:
                pass

    def _wire_keyboard(self) -> None:
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
            self.main_frame.winfo_toplevel().bind("<Escape>", lambda _e: self._handle_escape(), add="+")
        except Exception:
            pass
        self.main_frame.bind("<Destroy>", self._on_destroy, add="+")

    def _handle_escape(self, _event=None) -> str:
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
        if row['kind'] in ("group", "heading"):
            self._open_group_detail(panel, row)
        elif row['kind'] == "account":
            self._open_account_ledger(row['entry'])

    def _drill_filters(self) -> Dict[str, Any]:
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
        self._drill.summary_label.configure(text=f"Ledger: {name}   |   {subtitle}")

    def _open_group_detail(self, panel: _SidePanel, row: Dict[str, Any]) -> None:
        iid = row.get('iid')
        children = panel._group_children.get(iid, [])
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
        try:
            app = self.main_frame.winfo_toplevel()
            if hasattr(app, "show_vouchers"):
                app.show_vouchers()
            view = getattr(app, "current_view", None)
            if view is not None and hasattr(view, "_load_voucher"):
                view._load_voucher(voucher)
        except Exception:
            pass

    def _back(self) -> None:
        self._handle_escape()

    def _clear_filters(self) -> None:
        self.as_on_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.status_var.set("Filters cleared")

    def _generate_report(self) -> None:
        as_on = _parse_date(self.as_on_date_var.get())
        if not as_on:
            dialogs.warn("Balance Sheet", "Invalid date. Use DD-MM-YYYY format.", parent=self.parent)
            return
        report = balance_sheet_service.generate_balance_sheet(self.company_id, as_on)
        if not report.get('success'):
            dialogs.error("Balance Sheet", report.get('error', 'Failed to generate report'), parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        sections = report.get('sections', {})
        totals = report.get('totals', {})
        as_on = _parse_date(str(report.get('as_on_date', '')))

        company_name = "Company"
        try:
            row = db.fetch_one("SELECT name FROM companies WHERE id = ?", (self.company_id,))
            if row:
                company_name = row["name"]
        except Exception:
            pass

        self.left_header_label.configure(text="Liabilities")
        self.left_sub_label.configure(text=f"{company_name}  as at {_format_date(as_on)}")
        self.right_header_label.configure(text="Assets")
        self.right_sub_label.configure(text=f"{company_name}  as at {_format_date(as_on)}")

        # ---- LEFT: Liabilities & Capital ----
        left = self.left_panel
        left.clear()
        liab_entries = sections.get(TYPE_LIABILITIES, [])
        capital_entries = sections.get(TYPE_CAPITAL, [])

        if liab_entries:
            liab_hierarchy = self._build_group_hierarchy(liab_entries)
            for group_name, group_data in sorted(liab_hierarchy.items()):
                group_total = sum(float(e.get('net_balance', 0) or 0) for e in group_data["entries"])
                heading_iid = left.add_group_heading(group_name, group_total, group_data["entries"])
                left._group_subtotal[heading_iid] = {'name': f"Subtotal — {group_name}", 'amount': group_total}
            left.add_subtotal("Subtotal — Liabilities", totals.get('total_liabilities', 0))

        if capital_entries:
            cap_hierarchy = self._build_group_hierarchy(capital_entries)
            for group_name, group_data in sorted(cap_hierarchy.items()):
                group_total = sum(float(e.get('net_balance', 0) or 0) for e in group_data["entries"])
                heading_iid = left.add_group_heading(group_name, group_total, group_data["entries"])
                left._group_subtotal[heading_iid] = {'name': f"Subtotal — {group_name}", 'amount': group_total}
            left.add_subtotal("Subtotal — Capital & Equity", totals.get('total_capital', 0))

        left.add_total("Total Liabilities & Capital", totals.get('total_liabilities_capital', 0))

        # ---- RIGHT: Assets ----
        right = self.right_panel
        right.clear()
        asset_entries = sections.get(TYPE_ASSETS, [])

        if asset_entries:
            asset_hierarchy = self._build_group_hierarchy(asset_entries)
            for group_name, group_data in sorted(asset_hierarchy.items()):
                group_total = sum(float(e.get('net_balance', 0) or 0) for e in group_data["entries"])
                heading_iid = right.add_group_heading(group_name, group_total, group_data["entries"])
                right._group_subtotal[heading_iid] = {'name': f"Subtotal — {group_name}", 'amount': group_total}
            right.add_subtotal("Subtotal — Assets", totals.get('total_assets', 0))

        right.add_total("Total Assets", totals.get('total_assets', 0))

        # Re-focus
        for panel in (left, right):
            index = self._saved_selection.get(self._side_index(panel), 0)
            if panel.rows:
                panel.select_index(min(index, len(panel.rows) - 1))
        self._current_panel().tree.focus_set()

        # ---- BOTTOM SUMMARY ----
        total_assets = totals.get('total_assets', 0)
        total_liab_capital = totals.get('total_liabilities_capital', 0)
        difference = round(float(total_assets) - float(total_liab_capital), 2)
        balanced = report.get('is_balanced', False) and abs(difference) < 0.01

        self._summary_values['date'].configure(text=_format_date(as_on))
        self._summary_values['liab_capital'].configure(text=f"₹ {_format_indian(total_liab_capital)}")
        self._summary_values['assets'].configure(text=f"₹ {_format_indian(total_assets)}")
        self._summary_values['difference'].configure(text=f"₹ {_format_indian(difference)}")
        
        status_text = "BALANCED ✓" if balanced else "NOT BALANCED ✗"
        if not balanced:
            status_text += f"  (Diff: ₹ {_format_indian(abs(difference))})"
        self.status_chip.configure(
            text=status_text,
            text_color="#FFFFFF",
            fg_color=config.COLOR_INCOME if balanced else config.COLOR_EXPENSE)

        self.status_var.set(
            f"Balance Sheet as of {_format_date(as_on)} — "
            f"Assets {_format_indian(total_assets)} = "
            f"Liab+Capital {_format_indian(total_liab_capital)} — "
            f"{'Balanced' if balanced else 'NOT balanced'}")

    def _build_group_hierarchy(self, entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        hierarchy = {}
        for entry in entries:
            group = entry.get('account_group', '').strip()
            if not group:
                group = "Other"
            if group not in hierarchy:
                hierarchy[group] = {"entries": []}
            hierarchy[group]["entries"].append(entry)
        return hierarchy

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