"""
Expenzo — Accounting Voucher Entry (Redesigned Deep Dark Theme)
A keyboard-first, double-entry voucher entry screen with the six core
Tally-style voucher types:
    Contra (F4)  — Cash/Bank to Cash/Bank transfers only.
    Payment (F5) — Money outflow via Cash/Bank (expenses, debts, assets).
    Receipt (F6) — Money inflow via Cash/Bank (income, receivables, capital).
    Journal (F7) — Non-cash adjustment entries (no Cash/Bank ledgers).
    Sales (F8)   — Sales bill (Cash or Credit to Debtors).
    Purchase (F9)— Purchase / asset purchase (Cash or Credit from Creditors).

Theme: Deep Dark — #0B1329 screen, #10192E cards, #1B2848 borders, #3B82F6 accents.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.voucher_service import (
    voucher_service,
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    VOUCHER_CONTRA,
    VOUCHER_JOURNAL,
    VOUCHER_SALES,
    VOUCHER_PURCHASE,
    VOUCHER_TYPES,
    STATUS_CANCELLED,
)
from services.account_service import account_service
from services.group_service import group_service
from ui.ledger_picker import LedgerPicker, configure_picker_style
from utils import dialogs
from utils.keyboard import wire_entry_screen

# Party groups
PARTY_GROUPS = ["Sundry Debtors", "Sundry Creditors"]
BANK_GROUPS = ["Bank Accounts"]
CASH_GROUPS = ["Cash-in-Hand"]
CASH_BANK_GROUPS = CASH_GROUPS + BANK_GROUPS

# Grid column widths
_ROW_HEIGHT = 40
_HEADER_ROW_HEIGHT = 30
_NUM_COL_WIDTH = 40
_PARTICULARS_COL_WIDTH = 360
_AMOUNT_COL_WIDTH = 160

# Voucher type labels
VOUCHER_TYPE_LABELS = {
    VOUCHER_CONTRA: "Contra (F4)",
    VOUCHER_PAYMENT: "Payment (F5)",
    VOUCHER_RECEIPT: "Receipt (F6)",
    VOUCHER_JOURNAL: "Journal (F7)",
    VOUCHER_SALES: "Sales (F8)",
    VOUCHER_PURCHASE: "Purchase (F9)",
}

VOUCHER_TYPE_HOTKEYS = {
    "<F4>": VOUCHER_CONTRA,
    "<F5>": VOUCHER_PAYMENT,
    "<F6>": VOUCHER_RECEIPT,
    "<F7>": VOUCHER_JOURNAL,
    "<F8>": VOUCHER_SALES,
    "<F9>": VOUCHER_PURCHASE,
}

# Semantic colors
COLOR_DEBIT = "#EF4444"    # Red for Debit
COLOR_CREDIT = "#10B981"   # Green for Credit
COLOR_DIFF = "#F59E0B"     # Amber for Difference
COLOR_CANCEL = "#EF4444"   # Red for Cancel Voucher


def _fmt(amount: float) -> str:
    return f"{amount:,.2f}"


class VouchersFrame(ctk.CTkFrame):
    """Tally-style accounting voucher workspace — Deep Dark redesign."""

    def __init__(self, parent, company_id: Optional[int] = None):
        super().__init__(parent, fg_color=config.VOUCHER_BG_PRIMARY, corner_radius=0)
        self.parent = parent
        self.pack(fill="both", expand=True)

        self.company_id = company_id or 1
        self.current_voucher_id: Optional[int] = None
        self.current_voucher_number: Optional[str] = None

        self.rows: List[Dict[str, Any]] = []
        self._register_open = False
        self.register_window: Optional[ctk.CTkToplevel] = None
        self.register_tree = None
        self._saving = False
        self._pending_after: Optional[str] = None

        # Main container with compact padding
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_frame.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        self._build_header()
        self._build_voucher_meta_card()
        self._build_entry_grid_card()
        self._build_summary_card()
        self._build_narration_card()
        self._build_action_bar()
        self._build_status()

        wire_entry_screen(self, self.main_frame, [
            ("Ctrl+S", "Save"), ("Ctrl+A", "Accept"), ("Ctrl+N", "New"),
            ("Ctrl+F", "Search"), ("F5", "Refresh"), ("F4-F9", "Type"),
            ("Del", "Cancel selected"), ("Esc", "Back"),
        ])
        self.on_keyboard_back = self._on_keyboard_back_register_aware

        self._bind_voucher_hotkeys()
        self.bind("<Control-a>", self._on_hotkey_save, add="+")
        self.bind("<Control-A>", self._on_hotkey_save, add="+")
        self.main_frame.bind("<Control-a>", self._on_hotkey_save, add="+")
        self.main_frame.bind("<Control-A>", self._on_hotkey_save, add="+")

        self.refresh_vouchers()
        self._new_voucher()
        self._on_type_changed()  # Initialize flow and filters
        self._focus_first_field()

    # ------------------------------------------------------------------ #
    # Hotkeys
    # ------------------------------------------------------------------ #
    def _bind_voucher_hotkeys(self) -> None:
        self._hotkey_toplevel = self.winfo_toplevel()
        self._hotkey_binds: Dict[str, str] = {}
        for seq, vtype in VOUCHER_TYPE_HOTKEYS.items():
            try:
                self._hotkey_binds[seq] = self._hotkey_toplevel.bind(
                    seq, self._make_hotkey_handler(vtype))
            except Exception:
                pass
        self.bind("<Destroy>", self._on_hotkey_destroy, add="+")

    def _make_hotkey_handler(self, vtype: str):
        def _handler(_event=None) -> str:
            self._switch_voucher_type(vtype)
            return "break"
        return _handler

    def _on_hotkey_destroy(self, _event=None) -> None:
        try:
            if getattr(self, "_hotkey_binds", None):
                for seq in self._hotkey_binds:
                    try:
                        self._hotkey_toplevel.unbind(seq)
                    except Exception:
                        pass
        except Exception:
            pass

    def _switch_voucher_type(self, vtype: str) -> None:
        try:
            self.type_var.set(vtype)
            self.type_combo.set(VOUCHER_TYPE_LABELS[vtype])
        except Exception:
            pass
        self._on_type_changed()

    def _on_hotkey_save(self, _event=None) -> str:
        self._save_voucher()
        return "break"

    # ------------------------------------------------------------------ #
    # Top Header
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=36)
        header.pack(fill="x", pady=(4, 2))
        header.pack_propagate(False)

        # Left: Title + Breadcrumbs
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", fill="y")

        ctk.CTkLabel(
            left, text="Voucher Entry",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=config.VOUCHER_INPUT_TEXT,
        ).pack(side="left", anchor="w")

        ctk.CTkLabel(
            left, text="Contra · Payment · Receipt · Journal · Sales · Purchase",
            font=ctk.CTkFont(size=12),
            text_color="#64748B",
        ).pack(side="left", padx=(16, 0), anchor="w")

        # Right: + New Voucher button
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", fill="y")

        self.btn_new_voucher = ctk.CTkButton(
            right, text="+ New Voucher",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=config.COLOR_PRIMARY,
            hover_color=config.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF",
            corner_radius=8,
            height=34,
            command=self._new_voucher,
        )
        self.btn_new_voucher.pack(side="right", padx=(8, 0))

    # ------------------------------------------------------------------ #
    # Voucher Meta Header Card
    # ------------------------------------------------------------------ #
    def _build_voucher_meta_card(self) -> None:
        self.meta_card = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        self.meta_card.pack(fill="x", pady=(2, 4))
        self.meta_card.grid_columnconfigure(0, weight=1)
        self.meta_card.grid_columnconfigure(1, weight=1)
        self.meta_card.grid_columnconfigure(2, weight=1)
        self.meta_card.grid_columnconfigure(3, weight=1)

        pad_x = 10
        pad_y = 6

        # Voucher Type
        self._build_meta_field(0, "Voucher Type", self._build_type_combo_widget)

        # Date
        self._build_meta_field(1, "Date (DD-MM-YYYY)", self._build_date_entry_widget)

        # Voucher No.
        self._build_meta_field(2, "Voucher No.", self._build_number_label_widget)

        # Party A/C Name (right aligned) - stored for toggling visibility
        self.party_holder = ctk.CTkFrame(self.meta_card, fg_color="transparent")
        self.party_holder.grid(row=0, column=3, sticky="e", padx=(pad_x, pad_x), pady=pad_y)
        self.party_holder.grid_rowconfigure(0, weight=1)

        ctk.CTkLabel(
            self.party_holder, text="Party A/C Name",
            font=ctk.CTkFont(size=10),
            text_color="#64748B", anchor="w",
        ).pack(anchor="w")

        self.party_row = ctk.CTkFrame(self.party_holder, fg_color="transparent")
        self.party_row.pack(fill="x", pady=(1, 0))

        self.party_picker = LedgerPicker(
            self.party_row, self.company_id, width=180,
            groups=PARTY_GROUPS, on_selected=lambda _id: self._on_party_selected(),
            on_add_new=self._add_ledger_modal,
            placeholder="Select or type party name...",
        )
        self.party_picker.pack(side="left", fill="x", expand=True)

        # Flow hint (row 1, spans columns)
        self.flow_hint = ctk.CTkLabel(
            self.meta_card, text="",
            font=ctk.CTkFont(size=9),
            text_color="#64748B", anchor="w",
        )
        self.flow_hint.grid(row=1, column=0, columnspan=4, sticky="ew", padx=pad_x, pady=(0, pad_y))

    def _build_meta_field(self, column: int, label: str, builder) -> None:
        pad_x = 10
        pad_y = 6
        holder = ctk.CTkFrame(self.meta_card, fg_color="transparent")
        holder.grid(row=0, column=column, sticky="ew", padx=(pad_x, 0) if column == 0 else (pad_x, pad_x), pady=pad_y)
        holder.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            holder, text=label,
            font=ctk.CTkFont(size=10),
            text_color="#64748B", anchor="w",
        ).pack(anchor="w")
        widget = builder(holder)
        widget.pack(fill="x", pady=(1, 0))

    def _build_type_combo_widget(self, holder) -> ctk.CTkWidget:
        labels = [VOUCHER_TYPE_LABELS[t] for t in VOUCHER_TYPES]
        self.type_var = tk.StringVar(value=VOUCHER_PAYMENT)
        self.type_combo = ctk.CTkComboBox(
            holder, values=labels, width=180, height=36,
            corner_radius=8,
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
            dropdown_font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
            command=self._on_segmented_type,
            state="readonly",
            fg_color=config.VOUCHER_INPUT_BG,
            border_color=config.VOUCHER_INPUT_BORDER,
            button_color=config.VOUCHER_CARD_BORDER,
            button_hover_color=config.COLOR_PRIMARY,
            text_color=config.VOUCHER_INPUT_TEXT,
        )
        self.type_combo.set(labels[0])
        return self.type_combo

    def _on_segmented_type(self, label: str) -> None:
        for vtype, lbl in VOUCHER_TYPE_LABELS.items():
            if lbl == label:
                self.type_var.set(vtype)
                break
        self._on_type_changed()

    def _build_date_entry_widget(self, holder) -> ctk.CTkWidget:
        from ui.report_base import make_date_picker
        self.date_var = tk.StringVar(value=self._default_voucher_date())
        widget = make_date_picker(holder, self.date_var)
        self.date_entry = widget.search_entry
        self.date_entry.configure(
            width=140,
            fg_color=config.VOUCHER_INPUT_BG,
            border_color=config.VOUCHER_INPUT_BORDER,
            text_color=config.VOUCHER_INPUT_TEXT,
        )
        self.date_entry.bind("<Return>", lambda _e: self._focus_next_field())
        return widget

    def _build_number_label_widget(self, holder) -> ctk.CTkWidget:
        self.number_label = ctk.CTkLabel(
            holder, text="",
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="w",
        )
        return self.number_label

    def _on_type_changed(self) -> None:
        self._update_number_preview()
        self._sync_flow()
        self._toggle_party_field()
        self._update_balance()

    # ------------------------------------------------------------------ #
    # Entry Grid Card
    # ------------------------------------------------------------------ #
    def _build_entry_grid_card(self) -> None:
        self.grid_card = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        self.grid_card.pack(fill="x", pady=(2, 4))

        # Scrollable area - compact height for 2-3 rows
        self.grid_scroll = ctk.CTkScrollableFrame(
            self.grid_card,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=config.VOUCHER_CARD_BORDER,
            scrollbar_button_hover_color=config.COLOR_PRIMARY,
            height=120,
        )
        self.grid_scroll.pack(fill="x", padx=6, pady=4)
        self.grid_scroll.grid_columnconfigure(0, weight=1)

        self.grid_rows_frame = ctk.CTkFrame(self.grid_scroll, fg_color="transparent")
        self.grid_rows_frame.grid(row=0, column=0, sticky="ew")
        self.grid_rows_frame.grid_columnconfigure(0, weight=0, minsize=_NUM_COL_WIDTH)
        self.grid_rows_frame.grid_columnconfigure(1, weight=1, minsize=_PARTICULARS_COL_WIDTH)
        self.grid_rows_frame.grid_columnconfigure(2, weight=0, minsize=_AMOUNT_COL_WIDTH)
        self.grid_rows_frame.grid_columnconfigure(3, weight=0, minsize=_AMOUNT_COL_WIDTH)

        # Header row
        self._build_grid_header()

        # Initial rows
        self._first_focus: Optional[Any] = None
        self._add_row()  # Row 1 (debit side)
        self._add_row(to_line=True)  # Row 2 (credit/To line)

        # Row controls - compact
        self._build_row_controls()

    def _build_grid_header(self) -> None:
        header = ctk.CTkFrame(self.grid_rows_frame, fg_color="transparent", height=_HEADER_ROW_HEIGHT)
        header.pack(fill="x", padx=(8, 0))
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=0, minsize=_NUM_COL_WIDTH)
        header.grid_columnconfigure(1, weight=1, minsize=_PARTICULARS_COL_WIDTH)
        header.grid_columnconfigure(2, weight=0, minsize=_AMOUNT_COL_WIDTH)
        header.grid_columnconfigure(3, weight=0, minsize=_AMOUNT_COL_WIDTH)

        ctk.CTkLabel(
            header, text="#", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#64748B", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(12, 0), pady=4)
        ctk.CTkLabel(
            header, text="Particulars", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#64748B", anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=4)
        ctk.CTkLabel(
            header, text="Debit", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_DEBIT, anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(0, 24), pady=4)
        ctk.CTkLabel(
            header, text="Credit", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_CREDIT, anchor="e",
        ).grid(row=0, column=3, sticky="e", padx=(0, 24), pady=4)

    def _build_row_controls(self) -> None:
        controls = ctk.CTkFrame(self.grid_card, fg_color="transparent", height=30)
        controls.pack(fill="x", padx=8, pady=(3, 3))
        controls.pack_propagate(False)

        # Center aligned
        center = ctk.CTkFrame(controls, fg_color="transparent")
        center.pack(expand=True)

        self.btn_add_row = ctk.CTkButton(
            center, text="+ Add Row",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="transparent",
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
            text_color=config.VOUCHER_INPUT_TEXT,
            corner_radius=6,
            height=24,
            width=90,
            command=self._add_row_manual,
        )
        self.btn_add_row.pack(side="left", padx=(0, 4))

        self.btn_remove_row = ctk.CTkButton(
            center, text="🗑 Remove Row",
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
            text_color=config.VOUCHER_INPUT_TEXT,
            corner_radius=6,
            height=24,
            width=100,
            command=self._remove_last_row,
        )
        self.btn_remove_row.pack(side="left")

    def _add_row(self, account_id: Optional[int] = None, debit: str = "",
                 credit: str = "", to_line: bool = False) -> Dict[str, Any]:
        """Append one accounting line to the grid."""
        row: Dict[str, Any] = {"to_line": to_line}
        row_num = len(self.rows) + 1

        frame = ctk.CTkFrame(self.grid_rows_frame, fg_color="transparent", height=_ROW_HEIGHT)
        frame.pack(fill="x", pady=2)
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=0, minsize=_NUM_COL_WIDTH)
        frame.grid_columnconfigure(1, weight=1, minsize=_PARTICULARS_COL_WIDTH)
        frame.grid_columnconfigure(2, weight=0, minsize=_AMOUNT_COL_WIDTH)
        frame.grid_columnconfigure(3, weight=0, minsize=_AMOUNT_COL_WIDTH)
        row["frame"] = frame

        # Row number
        num_label = ctk.CTkLabel(
            frame, text=str(row_num),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#64748B", anchor="w",
            width=_NUM_COL_WIDTH,
        )
        num_label.grid(row=0, column=0, sticky="w", padx=(12, 0))
        row["num_label"] = num_label

        # Particulars container
        particulars = ctk.CTkFrame(
            frame,
            fg_color=config.VOUCHER_CARD_BORDER,
            corner_radius=8,
            border_width=0,
        )
        particulars.grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=6)
        particulars.grid_columnconfigure(0, weight=0)
        particulars.grid_columnconfigure(1, weight=1)
        row["particulars_frame"] = particulars

        # "To" prefix for credit lines
        to_label = ctk.CTkLabel(
            particulars, text="To ",
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE, weight="bold"),
            text_color="#64748B",
        )
        to_label.grid(row=0, column=0, sticky="w", padx=(12, 4))
        to_label.grid_remove()  # Hidden by default
        row["to_label"] = to_label

        # Ledger picker
        picker = LedgerPicker(
            particulars, self.company_id, width=0,
            on_selected=lambda _id, r=row: self._on_row_selected(r),
            on_add_new=self._add_ledger_modal,
            on_tab=lambda r=row: self._focus_after_particulars(r),
            placeholder="Enter Particulars" if not to_line else "Enter Ledger / Party",
            fg_color=config.VOUCHER_INPUT_BG,
            border_color=config.VOUCHER_INPUT_BORDER,
            text_color=config.VOUCHER_INPUT_TEXT,
        )
        picker.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=4)
        row["picker"] = picker

        # Debit / Credit amount entries
        debit_var = tk.StringVar(value="0.00")
        credit_var = tk.StringVar(value="0.00")
        debit_var.trace_add("write", lambda *_: self._update_balance())
        credit_var.trace_add("write", lambda *_: self._update_balance())

        entry_common = dict(
            width=0, justify="right",
            corner_radius=8,
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
            fg_color=config.VOUCHER_INPUT_BG,
            border_color=config.VOUCHER_INPUT_BORDER,
            text_color=config.VOUCHER_INPUT_TEXT,
        )

        debit_entry = ctk.CTkEntry(frame, textvariable=debit_var, **entry_common)
        debit_entry.grid(row=0, column=2, sticky="ew", padx=(0, 16), pady=6)

        credit_entry = ctk.CTkEntry(frame, textvariable=credit_var, **entry_common)
        credit_entry.grid(row=0, column=3, sticky="ew", padx=(0, 16), pady=6)

        row["debit_var"] = debit_var
        row["credit_var"] = credit_var
        row["debit_entry"] = debit_entry
        row["credit_entry"] = credit_entry

        # Bindings
        debit_entry.bind("<Return>", lambda _e, r=row: self._on_amount_return(r, "debit"))
        credit_entry.bind("<Return>", lambda _e, r=row: self._on_amount_return(r, "credit"))
        debit_entry.bind("<Tab>", lambda _e, r=row: self._on_amount_tab(r, "debit"))
        credit_entry.bind("<Tab>", lambda _e, r=row: self._on_amount_tab(r, "credit"))
        debit_entry.bind("<Shift-Tab>", lambda _e, r=row: self._on_amount_shift_tab(r, "debit"))
        credit_entry.bind("<Shift-Tab>", lambda _e, r=row: self._on_amount_shift_tab(r, "credit"))
        credit_entry.bind("<KeyRelease>", lambda _e, r=row: self._maybe_add_row(r))
        debit_entry.bind("<KeyRelease>", lambda _e, r=row: self._maybe_add_row(r))

        self.rows.append(row)
        self._renumber_rows()
        self._apply_row_presentation(row)
        if account_id is not None:
            picker.set_account(account_id)
        return row

    def _add_row_manual(self) -> None:
        self._add_row()
        self._focus_last_row_account()

    def _remove_last_row(self) -> None:
        if len(self.rows) <= 2:  # Keep at least 2 rows (1 debit + 1 credit)
            return
        # Remove last row
        row = self.rows.pop()
        try:
            row["frame"].destroy()
        except Exception:
            pass
        self._renumber_rows()
        self._update_balance()

    def _renumber_rows(self) -> None:
        for idx, row in enumerate(self.rows, 1):
            try:
                row["num_label"].configure(text=str(idx))
            except Exception:
                pass

    def _apply_row_presentation(self, row: Dict[str, Any]) -> None:
        # Always hide the "To" prefix; second row behaves like a normal particulars row
        row["to_label"].grid_remove()
        row["picker"].entry.configure(text_color=config.VOUCHER_INPUT_TEXT)
        row["picker"].entry.configure(placeholder_text="Enter Particulars")

    def _on_row_selected(self, row: Dict[str, Any]) -> None:
        if row.get("to_line"):
            row["credit_entry"].focus_set()
        else:
            row["debit_entry"].focus_set()

    def _on_amount_return(self, row: Dict[str, Any], side: str) -> None:
        if row.get("to_line"):
            self._on_enter_after_credit(row)
            return
        credit_row = self._ensure_credit_row()
        credit_row["picker"].focus_entry()

    def _on_amount_tab(self, row: Dict[str, Any], side: str) -> str:
        if side == "debit":
            credit_row = self._ensure_credit_row()
            credit_row["credit_entry"].focus_set()
            return "break"
        self._focus_after_credit(row)
        return "break"

    def _on_amount_shift_tab(self, row: Dict[str, Any], side: str) -> str:
        if side == "debit":
            row["picker"].focus_entry()
        else:
            debit_row = next((r for r in self.rows if not r.get("to_line")), None)
            if debit_row is not None:
                debit_row["debit_entry"].focus_set()
        return "break"

    def _focus_after_particulars(self, row: Dict[str, Any]) -> None:
        if row.get("to_line"):
            row["credit_entry"].focus_set()
        else:
            row["debit_entry"].focus_set()

    def _focus_after_credit(self, row: Dict[str, Any]) -> None:
        index = self.rows.index(row) if row in self.rows else -1
        next_row = None
        for candidate in self.rows[index + 1:]:
            next_row = candidate
            break
        if next_row is not None:
            next_row["picker"].focus_entry()
        else:
            self.narration_entry.focus_set()

    def _on_enter_after_credit(self, row: Dict[str, Any]) -> None:
        if self._has_incomplete_rows():
            self._add_row()
            self._focus_last_row_account()
        elif self._is_balanced():
            self._save_voucher()
        else:
            self._add_row()
            self._focus_last_row_account()

    def _on_narration_return(self, _event=None) -> str:
        self.btn_save.focus_set()
        self.btn_save.invoke()
        return "break"

    def _on_narration_tab(self, _event=None) -> str:
        self.btn_save.focus_set()
        return "break"

    def _maybe_add_row(self, row: Dict[str, Any]) -> None:
        try:
            amount = float(row["debit_var"].get() or row["credit_var"].get() or 0)
        except ValueError:
            amount = 0.0
        if amount and row["picker"].get_account() is not None and self.rows[-1] is row:
            self._add_row()

    def _any_credit_row(self) -> bool:
        return any(r.get("to_line") for r in self.rows)

    def _ensure_credit_row(self) -> Dict[str, Any]:
        for row in self.rows:
            if row.get("to_line"):
                return row
        return self._add_row(to_line=True)

    def _has_incomplete_rows(self) -> bool:
        for row in self.rows:
            if not row.get("to_line") and row["picker"].get_account() is None:
                return True
        return False

    def _focus_first_field(self) -> None:
        # Focus Party A/C Name only when it is visible (Sales / Purchase)
        if self.party_picker is not None and self.party_holder.winfo_ismapped():
            self.party_picker.focus_entry()
        elif self.rows:
            self.rows[0]["picker"].focus_entry()

    def _focus_last_row_account(self) -> None:
        if self.rows:
            self.rows[-1]["picker"].focus_entry()

    def _focus_next_field(self) -> None:
        if self.rows:
            self.rows[0]["picker"].focus_entry()

    def _remove_row(self, index: int) -> None:
        if index < 0 or index >= len(self.rows):
            return
        row = self.rows.pop(index)
        try:
            row["frame"].destroy()
        except Exception:
            pass
        self._renumber_rows()

    # ------------------------------------------------------------------ #
    # Add Ledger Modal
    # ------------------------------------------------------------------ #
    def _add_ledger_modal(self) -> None:
        try:
            existing = getattr(self, "_ledger_modal", None)
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        modal = ctk.CTkToplevel(self)
        modal.title("Add New Ledger")
        modal.geometry("420x360")
        modal.resizable(False, False)
        modal.configure(fg_color=config.VOUCHER_CARD_BG)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()
        self._ledger_modal = modal

        body = ctk.CTkFrame(modal, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=24)

        name_var = tk.StringVar()
        code_var = tk.StringVar()
        group_var = tk.StringVar()
        opening_var = tk.StringVar(value="0.00")
        opening_type_var = tk.StringVar(value="Debit")

        groups = []
        try:
            groups = [g["name"] for g in group_service.list_groups(
                self.company_id, include_inactive=True)]
        except Exception:
            groups = []
        if not groups:
            groups = ["Assets", "Liabilities", "Capital", "Income", "Expense"]

        def _field(label, widget) -> None:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(row, text=label, width=120,
                         font=ctk.CTkFont(size=12),
                         text_color="#64748B").pack(side="left")
            widget.pack(side="left", fill="x", expand=True)

        entry_style = dict(
            fg_color=config.VOUCHER_INPUT_BG,
            border_color=config.VOUCHER_INPUT_BORDER,
            text_color=config.VOUCHER_INPUT_TEXT,
            corner_radius=8,
        )
        combo_style = dict(
            fg_color=config.VOUCHER_INPUT_BG,
            border_color=config.VOUCHER_INPUT_BORDER,
            button_color=config.VOUCHER_CARD_BORDER,
            button_hover_color=config.COLOR_PRIMARY,
            text_color=config.VOUCHER_INPUT_TEXT,
            corner_radius=8,
            state="readonly",
        )

        _field("Name", ctk.CTkEntry(body, textvariable=name_var, **entry_style))
        _field("Code", ctk.CTkEntry(body, textvariable=code_var, **entry_style))
        _field("Group", ctk.CTkComboBox(body, values=groups, variable=group_var, **combo_style))
        _field("Opening Balance", ctk.CTkEntry(body, textvariable=opening_var, **entry_style))
        _field("Balance Type", ctk.CTkComboBox(
            body, values=["Debit", "Credit"], variable=opening_type_var, **combo_style))

        def _create() -> None:
            name = name_var.get().strip()
            if not name:
                dialogs.warn("Add Ledger", "Ledger name is required.", parent=modal)
                return
            group = group_var.get().strip() or "Assets"
            try:
                opening = float(opening_var.get() or 0)
            except ValueError:
                dialogs.warn("Add Ledger", "Opening balance must be numeric.", parent=modal)
                return
            try:
                account_id = account_service.create_account(
                    self.company_id, name, code_var.get().strip(), group,
                    opening, opening_type_var.get())
            except Exception as exc:
                dialogs.error("Add Ledger", f"Failed to create ledger: {exc}", parent=modal)
                return
            self._refresh_pickers()
            try:
                focused = self.focus_get()
                if focused is not None:
                    for row in self.rows:
                        if row["picker"].entry is focused:
                            row["picker"].set_account(account_id)
                            break
            except Exception:
                pass
            try:
                modal.destroy()
            except Exception:
                pass
            self._set_status(f"Ledger '{name}' created")

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(16, 0))
        ctk.CTkButton(buttons, text="Create", width=110, height=32,
                      corner_radius=8, fg_color=config.COLOR_PRIMARY,
                      hover_color=config.COLOR_PRIMARY_HOVER,
                      text_color="#FFFFFF", command=_create).pack(side="right")
        ctk.CTkButton(buttons, text="Cancel", width=90, height=32,
                      corner_radius=8,
                      fg_color="transparent", border_width=1,
                      border_color=config.VOUCHER_CARD_BORDER,
                      text_color=config.VOUCHER_INPUT_TEXT,
                      command=modal.destroy).pack(side="right", padx=(0, 8))
        modal.bind("<Return>", lambda _e: _create())
        modal.bind("<Escape>", lambda _e: modal.destroy())
        modal.after(60, lambda: (modal.lift(), modal.focus_force()))

    def _add_ledger_modal_for_row(self, row: Dict[str, Any]) -> None:
        """Open ledger modal and pre-select in the specific row's picker."""
        self._add_ledger_modal()
        # Store which row triggered it
        self._ledger_modal_target_row = row

    def _refresh_pickers(self) -> None:
        try:
            if self.party_picker is not None:
                self.party_picker.refresh()
            for row in self.rows:
                try:
                    row["picker"].refresh()
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Summary Card
    # ------------------------------------------------------------------ #
    def _build_summary_card(self) -> None:
        """Ultra-compact single-row summary strip (height 44px)."""
        self.summary_card = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=8,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        self.summary_card.pack(fill="x", padx=16, pady=(2, 4))

        summary_frame = ctk.CTkFrame(
            self.summary_card,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=8,
            height=44,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        summary_frame.pack(fill="x", padx=4, pady=2)
        summary_frame.pack_propagate(False)

        # 3 Equal Grid Columns
        summary_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Total Debit Column
        col1 = ctk.CTkFrame(summary_frame, fg_color="transparent")
        col1.grid(row=0, column=0, pady=6)
        ctk.CTkLabel(col1, text="↓", text_color=COLOR_DEBIT, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(col1, text="Total Debit:", font=ctk.CTkFont(size=11), text_color="#8DA4D0").pack(side="left", padx=(0, 4))
        self.total_debit_lbl = ctk.CTkLabel(col1, text="0.00", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_DEBIT)
        self.total_debit_lbl.pack(side="left")

        # Total Credit Column
        col2 = ctk.CTkFrame(summary_frame, fg_color="transparent")
        col2.grid(row=0, column=1, pady=6)
        ctk.CTkLabel(col2, text="↑", text_color=COLOR_CREDIT, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(col2, text="Total Credit:", font=ctk.CTkFont(size=11), text_color="#8DA4D0").pack(side="left", padx=(0, 4))
        self.total_credit_lbl = ctk.CTkLabel(col2, text="0.00", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_CREDIT)
        self.total_credit_lbl.pack(side="left")

        # Difference Column
        col3 = ctk.CTkFrame(summary_frame, fg_color="transparent")
        col3.grid(row=0, column=2, pady=6)
        ctk.CTkLabel(col3, text="⚖", text_color=COLOR_DIFF, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(col3, text="Difference:", font=ctk.CTkFont(size=11), text_color="#8DA4D0").pack(side="left", padx=(0, 4))
        self.diff_lbl = ctk.CTkLabel(col3, text="0.00", font=ctk.CTkFont(size=13, weight="bold"), text_color=COLOR_DIFF)
        self.diff_lbl.pack(side="left")

    # _tint_for_summary kept for compatibility if used elsewhere
    def _tint_for_summary(self, hex_color: str) -> str:
        """Tint toward card background for subtle badge."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        bg_r, bg_g, bg_b = 0x10, 0x19, 0x2E
        factor = 0.15
        r = int(r * factor + bg_r * (1 - factor))
        g = int(g * factor + bg_g * (1 - factor))
        b = int(b * factor + bg_b * (1 - factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    # ------------------------------------------------------------------ #
    # Narration Card
    # ------------------------------------------------------------------ #
    def _build_narration_card(self) -> None:
        """Narration box with proper focus/click handling."""
        narr_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        narr_container.pack(fill="x", padx=16, pady=(2, 6))

        ctk.CTkLabel(
            narr_container, text="Narration (optional)",
            font=ctk.CTkFont(size=11), text_color="#8DA4D0",
        ).pack(anchor="w", pady=(0, 2))

        self.narration_var = tk.StringVar()
        self.narration_entry = ctk.CTkEntry(
            narr_container,
            textvariable=self.narration_var,
            placeholder_text="Enter narration...",
            height=32,
            fg_color="#0B1329",
            border_color="#1B2848",
            border_width=1,
            text_color="#FFFFFF",
            placeholder_text_color="#64748B",
            font=ctk.CTkFont(size=12),
            state="normal",
        )
        self.narration_entry.pack(fill="x", expand=True)

        # Explicit click focus bind
        self.narration_entry.bind("<Button-1>", lambda e: self.narration_entry.focus_set())

        self.narration_entry.bind("<Return>", self._on_narration_return)
        self.narration_entry.bind("<Tab>", self._on_narration_tab)

    # ------------------------------------------------------------------ #
    # Action Bar
    # ------------------------------------------------------------------ #
    def _build_action_bar(self) -> None:
        self.action_bar = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=10,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        self.action_bar.pack(fill="x", pady=(4, 6))

        inner = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=4)

        # Single horizontal row with all buttons
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        # Save (F5) - Solid Blue
        self.btn_save = ctk.CTkButton(
            btn_row, text="💾 Save (F5)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=config.COLOR_PRIMARY,
            hover_color=config.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF",
            corner_radius=6,
            height=30,
            width=110,
            command=self._save_voucher,
        )
        self.btn_save.pack(side="left", padx=(0, 4))
        self.btn_save.bind("<Return>", lambda _e: self._save_voucher() or "break")
        self.btn_save.bind("<space>", lambda _e: self._save_voucher() or "break")

        # Save & New (Ctrl+N) - Deep Navy
        self.btn_save_new = ctk.CTkButton(
            btn_row, text="💾 Save & New (Ctrl+N)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#162A52",
            hover_color="#1E3A5F",
            border_width=1,
            border_color=config.COLOR_PRIMARY_HOVER,
            text_color="#BFDBFE",
            corner_radius=6,
            height=30,
            width=135,
            command=self._save_and_new,
        )
        self.btn_save_new.pack(side="left", padx=(0, 4))

        # Clear - Dark Navy
        self.btn_clear = ctk.CTkButton(
            btn_row, text="↻ Clear",
            font=ctk.CTkFont(size=11),
            fg_color="#16223E",
            hover_color="#1B2848",
            text_color="#94A3B8",
            corner_radius=6,
            height=30,
            width=80,
            command=self._clear_form,
        )
        self.btn_clear.pack(side="left", padx=(0, 4))

        # Cancel (Esc) - Dark Navy
        self.btn_cancel = ctk.CTkButton(
            btn_row, text="✕ Cancel (Esc)",
            font=ctk.CTkFont(size=11),
            fg_color="#16223E",
            hover_color="#1B2848",
            text_color="#94A3B8",
            corner_radius=6,
            height=30,
            width=100,
            command=self._cancel_form,
        )
        self.btn_cancel.pack(side="left", padx=(0, 4))

        # Voucher Register - Dark Navy
        self.btn_register = ctk.CTkButton(
            btn_row, text="📖 Voucher Register",
            font=ctk.CTkFont(size=11),
            fg_color="#16223E",
            hover_color="#1B2848",
            text_color="#94A3B8",
            corner_radius=6,
            height=30,
            width=130,
            command=self._open_register,
        )
        self.btn_register.pack(side="left", padx=(0, 4))

        # Cancel Voucher - Right aligned, Red border/accent
        self.btn_cancel_voucher = ctk.CTkButton(
            btn_row, text="🚫 Cancel Voucher",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3B1D28",
            hover_color="#4A1D28",
            border_width=1,
            border_color=COLOR_CANCEL,
            text_color=COLOR_CANCEL,
            corner_radius=6,
            height=30,
            width=130,
            command=self._cancel_selected_voucher,
        )
        self.btn_cancel_voucher.pack(side="right")

    # ------------------------------------------------------------------ #
    # Status Bar
    # ------------------------------------------------------------------ #
    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=11), text_color="#64748B",
        ).pack(fill="x")

    # ------------------------------------------------------------------ #
    # Voucher Type Behavior
    # ------------------------------------------------------------------ #
    def _sync_flow(self) -> None:
        vtype = self.type_var.get()
        self._apply_row_filters()
        if vtype == VOUCHER_PAYMENT:
            self._set_flow("Payment: Debit expense/party  →  To Bank/Cash A/c")
            self.party_side = "debit"
        elif vtype == VOUCHER_RECEIPT:
            self._set_flow("Receipt: Debit Cash/Bank  →  To Party A/c")
            self.party_side = "credit"
        elif vtype == VOUCHER_CONTRA:
            self._set_flow("Contra: Debit Cash/Bank  →  To Cash/Bank")
            self.party_side = "none"
        elif vtype == VOUCHER_JOURNAL:
            self._set_flow("Journal: Debit account  →  Credit account (no Cash/Bank)")
            self.party_side = "none"
        elif vtype == VOUCHER_SALES:
            self._set_flow("Sales: Debit Party  →  Credit Sales")
            self.party_side = "debit"
        elif vtype == VOUCHER_PURCHASE:
            self._set_flow("Purchase: Debit Purchase  →  Credit Party")
            self.party_side = "credit"
        self._update_balance()

    def _set_flow(self, text: str) -> None:
        self.flow_hint.configure(text=text)

    def _apply_row_filters(self) -> None:
        vtype = self.type_var.get()
        for row in self.rows:
            picker = row["picker"]
            if vtype in (VOUCHER_PAYMENT, VOUCHER_RECEIPT, VOUCHER_CONTRA):
                picker.set_group_filter(CASH_BANK_GROUPS if row.get("to_line") else PARTY_GROUPS + ["Expenses"])
            elif vtype == VOUCHER_JOURNAL:
                picker.set_group_filter(None)
            elif vtype == VOUCHER_SALES:
                picker.set_group_filter(PARTY_GROUPS + ["Sales"] if not row.get("to_line") else CASH_BANK_GROUPS)
            elif vtype == VOUCHER_PURCHASE:
                picker.set_group_filter(["Purchases", "Expenses"] if not row.get("to_line") else PARTY_GROUPS + CASH_BANK_GROUPS)

    def _toggle_party_field(self) -> None:
        """Show Party A/C Name only for Sales and Purchase vouchers."""
        vtype = self.type_var.get()
        if vtype in (VOUCHER_SALES, VOUCHER_PURCHASE):
            self.party_holder.grid()
            # ensure picker is packed inside its row
            try:
                self.party_picker.pack(side="left", fill="x", expand=True)
            except Exception:
                pass
        else:
            # hide picker completely so winfo_manager() returns ""
            try:
                self.party_picker.pack_forget()
            except Exception:
                pass
            self.party_holder.grid_remove()

    # ------------------------------------------------------------------ #
    # Voucher Operations
    # ------------------------------------------------------------------ #
    def _default_voucher_date(self) -> str:
        try:
            from services.date_control_service import date_control
            return date_control.today().strftime("%d-%m-%Y")
        except Exception:
            return date.today().strftime("%d-%m-%Y")

    def _update_number_preview(self) -> None:
        try:
            preview = voucher_service.preview_voucher_number(self.company_id, self.type_var.get())
            self.number_label.configure(text=preview)
        except Exception:
            self.number_label.configure(text="")

    def _update_balance(self, *args) -> None:
        debit, credit = self._totals()
        difference = round(debit - credit, 2)

        self.total_debit_lbl.configure(text=_fmt(debit))
        self.total_credit_lbl.configure(text=_fmt(credit))

        diff_lbl = getattr(self, "diff_lbl", None)
        if diff_lbl is not None:
            if difference == 0 and (debit or credit):
                diff_lbl.configure(text="0.00", text_color=COLOR_CREDIT)
            else:
                diff_lbl.configure(text=_fmt(difference), text_color=COLOR_DIFF if difference > 0 else COLOR_DEBIT)

    def _totals(self) -> tuple:
        debit = 0.0
        credit = 0.0
        for row in self.rows:
            try:
                debit += float(row["debit_var"].get() or 0)
            except ValueError:
                pass
            try:
                credit += float(row["credit_var"].get() or 0)
            except ValueError:
                pass
        return round(debit, 2), round(credit, 2)

    def _is_balanced(self) -> bool:
        debit, credit = self._totals()
        return round(debit, 2) == round(credit, 2) and debit > 0

    def _collect_details(self) -> List[Dict[str, Any]]:
        details = []
        for row in self.rows:
            account_id = row["picker"].get_account()
            if account_id is None:
                continue
            try:
                dr = float(row["debit_var"].get() or 0)
            except ValueError:
                dr = 0.0
            try:
                cr = float(row["credit_var"].get() or 0)
            except ValueError:
                cr = 0.0
            if dr == 0 and cr == 0:
                continue
            details.append({
                "account_id": account_id,
                "debit_amount": dr,
                "credit_amount": cr,
            })
        return details

    def _save_voucher(self) -> None:
        if self._saving:
            return
        if not self._is_balanced():
            dialogs.error("Save Voucher", "Voucher is not balanced. Debit must equal Credit.", parent=self)
            return
        details = self._collect_details()
        if not details:
            dialogs.error("Save Voucher", "No valid entries found.", parent=self)
            return
        self._saving = True
        try:
            narration = self.narration_var.get().strip()
            voucher_date = self._parse_date(self.date_var.get())
            if voucher_date is None:
                dialogs.error("Save Voucher", "Invalid date format. Use DD-MM-YYYY.", parent=self)
                return
            voucher_service.save_voucher(
                company_id=self.company_id,
                voucher_type=self.type_var.get(),
                voucher_date=voucher_date,
                entries=details,
                narration=narration,
                reference_number="",
            )
            self._set_status("Voucher saved successfully")
            self._new_voucher()
        except Exception as exc:
            dialogs.error("Save Voucher", f"Failed to save: {exc}", parent=self)
        finally:
            self._saving = False

    def _save_and_new(self) -> None:
        self._save_voucher()
        if not self._saving:
            self._new_voucher()

    def _new_voucher(self) -> None:
        self.current_voucher_id = None
        self.current_voucher_number = None
        self.narration_var.set("")
        self.date_var.set(self._default_voucher_date())
        if self.party_picker:
            self.party_picker.clear()
        # Clear rows but keep 2 default rows
        for row in self.rows[:]:
            try:
                row["frame"].destroy()
            except Exception:
                pass
        self.rows.clear()
        self._add_row()
        self._add_row(to_line=True)
        self._update_number_preview()
        self._update_balance()
        self._focus_first_field()

    def _clear_form(self) -> None:
        self._new_voucher()

    def _cancel_form(self) -> None:
        self._new_voucher()

    def _cancel_selected_voucher(self) -> None:
        if self.current_voucher_id is None:
            dialogs.warn("Cancel Voucher", "No voucher selected to cancel.", parent=self)
            return
        if dialogs.confirm("Cancel Voucher",
                           f"Cancel voucher {self.current_voucher_number}? This action cannot be undone.",
                           parent=self):
            try:
                voucher_service.cancel_voucher(self.current_voucher_id)
                self._set_status(f"Voucher {self.current_voucher_number} cancelled")
                self._new_voucher()
                self.refresh_vouchers()
            except Exception as exc:
                dialogs.error("Cancel Voucher", f"Failed to cancel: {exc}", parent=self)

    def _parse_date(self, date_str: str) -> Optional[date]:
        try:
            return datetime.strptime(date_str.strip(), "%d-%m-%Y").date()
        except Exception:
            return None

    def _open_register(self) -> None:
        if self._register_open and self.register_window and self.register_window.winfo_exists():
            self.register_window.lift()
            return
        self._register_open = True
        self.register_window = ctk.CTkToplevel(self)
        self.register_window.title("Voucher Register")
        self.register_window.geometry("900x600")
        self.register_window.configure(fg_color=config.VOUCHER_BG_PRIMARY)
        self.register_window.transient(self.winfo_toplevel())
        self.register_window.protocol("WM_DELETE_WINDOW", self._on_register_close)

        # Toolbar
        toolbar = ctk.CTkFrame(self.register_window, fg_color=config.VOUCHER_CARD_BG,
                               corner_radius=10, border_width=1,
                               border_color=config.VOUCHER_CARD_BORDER)
        toolbar.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(toolbar, text="Voucher Register",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=config.VOUCHER_INPUT_TEXT).pack(side="left", padx=16, pady=12)

        # Treeview
        from tkinter import ttk
        tree_frame = ctk.CTkFrame(self.register_window, fg_color=config.VOUCHER_CARD_BG,
                                   corner_radius=10, border_width=1,
                                   border_color=config.VOUCHER_CARD_BORDER)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        cols = ("number", "type", "date", "particulars", "amount")
        self.register_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=20)
        for col_id, col_text, width in [
            ("number", "Voucher No.", 120),
            ("type", "Type", 100),
            ("date", "Date", 100),
            ("particulars", "Particulars", 300),
            ("amount", "Amount", 150),
        ]:
            self.register_tree.heading(col_id, text=col_text)
            self.register_tree.column(col_id, width=width, anchor="w" if col_id != "amount" else "e")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.register_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.register_tree.xview)
        self.register_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.register_tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        vsb.pack(side="right", fill="y", pady=8)
        hsb.pack(side="bottom", fill="x", padx=8)

        # Style
        configure_picker_style(self.register_window)
        self.register_tree.tag_configure("cancelled", foreground=COLOR_DEBIT)

        self._load_register()
        self.register_tree.bind("<Double-1>", self._on_register_double_click)
        self.register_tree.bind("<Return>", lambda _e: self._on_register_double_click())

    def _on_register_close(self) -> None:
        self._register_open = False
        try:
            self.register_window.destroy()
        except Exception:
            pass

    def _load_register(self) -> None:
        if not self.register_tree:
            return
        for item in self.register_tree.get_children():
            self.register_tree.delete(item)
        try:
            vouchers = voucher_service.list_vouchers(
                self.company_id,
                from_date=None, to_date=None,
                include_cancelled=True,
            )
            for v in vouchers:
                particulars = self._register_particulars(v.get("details", []), v)
                amount = v.get("total_amount", 0)
                tag = "cancelled" if v.get("status") == STATUS_CANCELLED else ""
                self.register_tree.insert("", "end", values=(
                    v.get("voucher_number", ""),
                    v.get("voucher_type", ""),
                    v.get("voucher_date", ""),
                    particulars,
                    _fmt(amount),
                ), tags=(tag,))
        except Exception:
            pass

    def _register_particulars(self, details: List[Dict], voucher: Dict) -> str:
        parts = []
        for d in details:
            name = d.get("account_name", "")
            dr = d.get("debit_amount", 0)
            cr = d.get("credit_amount", 0)
            if dr:
                parts.append(f"Dr {name} {_fmt(dr)}")
            elif cr:
                parts.append(f"Cr {name} {_fmt(cr)}")
        return "; ".join(parts)

    def _on_register_double_click(self, _event=None) -> None:
        selection = self.register_tree.selection()
        if not selection:
            return
        item = self.register_tree.item(selection[0])
        voucher_number = item["values"][0]
        try:
            voucher = voucher_service.get_voucher_by_number(self.company_id, voucher_number)
            if voucher:
                self._load_voucher_for_edit(voucher)
        except Exception:
            pass

    def _load_voucher_for_edit(self, voucher: Dict) -> None:
        self.current_voucher_id = voucher.get("id")
        self.current_voucher_number = voucher.get("voucher_number")
        self.type_var.set(voucher.get("voucher_type", VOUCHER_PAYMENT))
        self.type_combo.set(VOUCHER_TYPE_LABELS.get(voucher.get("voucher_type", VOUCHER_PAYMENT), ""))
        self.date_var.set(voucher.get("voucher_date", self._default_voucher_date()))
        self.narration_var.set(voucher.get("narration", ""))

        # Party
        party_id = voucher.get("party_id")
        if party_id and self.party_picker:
            self.party_picker.set_account(party_id)

        # Clear existing rows
        for row in self.rows[:]:
            try:
                row["frame"].destroy()
            except Exception:
                pass
        self.rows.clear()

        # Add rows from voucher details
        details = voucher.get("details", [])
        for idx, d in enumerate(details):
            is_credit = d.get("credit_amount", 0) > 0
            self._add_row(
                account_id=d.get("account_id"),
                debit=_fmt(d.get("debit_amount", 0)) if not is_credit else "",
                credit=_fmt(d.get("credit_amount", 0)) if is_credit else "",
                to_line=is_credit and idx > 0,
            )

        self._update_balance()
        self._set_status(f"Loaded voucher {self.current_voucher_number} for editing")

    def _on_keyboard_back_register_aware(self) -> str:
        if self._register_open and self.register_window and self.register_window.winfo_exists():
            self._on_register_close()
            return "break"
        self._go_back()
        return "break"

    def _go_back(self) -> None:
        try:
            self.parent.show_hub()
        except Exception:
            pass

    def refresh_vouchers(self) -> None:
        if self.register_tree and self.register_window and self.register_window.winfo_exists():
            self._load_register()

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)