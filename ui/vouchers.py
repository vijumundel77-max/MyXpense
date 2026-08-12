"""
Expenzo — Accounting Voucher Entry (Tally-inspired workflow)

A keyboard-first, double-entry voucher entry screen. The UI is presented in
the traditional accounting format:

    Voucher Type | Date | Voucher No.
    Party A/C Name (where the voucher type involves a party)
    Particulars                    Debit          Credit
        <Dr-side account>           25,000.00
        To <Cr-side account>                       25,000.00
    Narration
    [Save] [Save & New] [Clear] [Cancel]

The underlying accounting engine is unchanged: every voucher is a balanced set
of ``voucher_details`` rows saved through ``voucher_service.save_voucher`` /
``update_voucher``. The "To" line is pure presentation of the credit side;
Debit / Credit columns map 1:1 to ``debit_amount`` / ``credit_amount``.

Voucher types (existing Expenzo types, unchanged):
    Payment  — Party/expense Dr  →  To Bank/Cash A/c
    Receipt  — Cash/Bank Dr      →  To Party A/c
    Contra   — Bank A/c Dr       →  To Cash A/c (or reverse)
    Journal  — Expense/Asset Dr  →  To Liability/Income A/c

Keyboard workflow (uses the existing global shortcut architecture in
``utils.keyboard``): Ctrl+N new, Ctrl+S save, Ctrl+F search, F5 refresh,
Esc back, Enter/Tab to move through the grid, arrows to navigate rows.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
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
    VOUCHER_TYPES,
    STATUS_CANCELLED,
)
from services.account_service import account_service
from ui.ledger_picker import LedgerPicker, configure_picker_style
from utils import dialogs
from utils.keyboard import wire_entry_screen

# Party groups (existing Expenzo model: parties are ledgers under these
# groups — see ui/party_master.py).
PARTY_GROUPS = ["Sundry Debtors", "Sundry Creditors"]
BANK_GROUPS = ["Bank Accounts"]
CASH_GROUPS = ["Cash-in-Hand"]

# Columns for the entry grid.
_GRID_HEADINGS = ["Particulars", "Debit", "Credit"]

# How much height each new row adds (kept explicit for clipping checks).
_ROW_HEIGHT = 40
_HEADER_ROW_HEIGHT = 30


def _fmt(amount: float) -> str:
    return f"{amount:,.2f}"


class VouchersFrame(ctk.CTkFrame):
    """Tally-style accounting voucher workspace."""

    def __init__(self, parent, company_id: Optional[int] = None):
        super().__init__(parent)
        self.parent = parent
        self.pack(fill="both", expand=True)

        self.company_id = company_id or 1
        self.current_voucher_id: Optional[int] = None
        self.current_voucher_number: Optional[str] = None

        self.rows: List[Dict[str, Any]] = []
        self._register_open = False
        self.register_window: Optional[ctk.CTkToplevel] = None
        self.register_tree = None

        # A short keep-alive hook so the test suite (and tools) can wait for
        # pending popup-hide callbacks without flapping.
        self._pending_after: Optional[str] = None

        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL,
                             pady=(config.SPACING_LG, config.SPACING_LG))

        self._build_header()
        self._build_voucher_bar()
        self._build_entry_area()
        self._build_totals()
        self._build_narration()
        self._build_action_bar()
        self._build_status()

        wire_entry_screen(self, self.main_frame, [
            ("Ctrl+S", "Save"), ("Ctrl+N", "New"), ("Ctrl+F", "Search"),
            ("F5", "Refresh"), ("Del", "Cancel selected"), ("Esc", "Back"),
        ])

        self.refresh_vouchers()
        self._new_voucher()
        self._focus_first_field()

    # ------------------------------------------------------------------ #
    # layout — fixed header + voucher bar (never scrolls)
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Voucher Entry",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Payment · Receipt · Contra · Journal",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

        self.mode_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_PRIMARY,
            fg_color=config.COLOR_BG_TERTIARY, corner_radius=6, padx=10, pady=3,
        )
        self.mode_label.pack(side="right")

    def _build_voucher_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, config.SPACING_LG))
        bar.grid_columnconfigure(3, weight=1)

        self.type_var = tk.StringVar(value=VOUCHER_PAYMENT)
        self.date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.number_var = tk.StringVar()

        self._bar_field(bar, 0, "Voucher Type", self._build_type_combo)
        self._bar_field(bar, 1, "Date (DD-MM-YYYY)", self._build_date_entry)
        self._bar_field(bar, 2, "Voucher No.", self._build_number_label)

        self.party_picker: Optional[LedgerPicker] = None
        party_holder = ctk.CTkFrame(bar, fg_color="transparent")
        party_holder.grid(row=0, column=4, sticky="w", padx=(0, config.SPACING_LG))
        ctk.CTkLabel(
            party_holder, text="Party A/C Name", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")
        self.party_picker = LedgerPicker(
            party_holder, self.company_id, width=260,
            groups=PARTY_GROUPS, on_selected=lambda _id: self._on_party_selected(),
        )
        self.party_picker.pack(anchor="w", pady=(2, 0))

        # Hint line under the party field, describing the current voucher's
        # accounting flow (pure presentation of the existing rules).
        self.flow_hint = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED, anchor="w",
        )
        self.flow_hint.grid(row=1, column=4, sticky="w", padx=(0, config.SPACING_LG),
                            pady=(2, config.SPACING_SM))

    def _bar_field(self, parent, column: int, label: str, builder) -> None:
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(row=0, column=column, sticky="w", padx=(config.SPACING_LG, 0))
        ctk.CTkLabel(
            holder, text=label, font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")
        widget = builder(holder)
        widget.pack(anchor="w", pady=(2, config.SPACING_SM))

    def _build_type_combo(self, holder) -> ctk.CTkComboBox:
        self.type_combo = ctk.CTkComboBox(
            holder, values=list(VOUCHER_TYPES), variable=self.type_var, width=140,
            state="readonly", command=lambda _: self._on_type_changed(),
        )
        return self.type_combo

    def _build_date_entry(self, holder) -> ctk.CTkEntry:
        self.date_entry = ctk.CTkEntry(
            holder, textvariable=self.date_var, width=140,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.date_entry.bind("<Return>", lambda _e: self._focus_next_field())
        return self.date_entry

    def _build_number_label(self, holder) -> ctk.CTkLabel:
        self.number_label = ctk.CTkLabel(
            holder, text="", font=ctk.CTkFont(size=config.FONT_BODY_SIZE, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="w", width=110,
        )
        return self.number_label

    def _on_type_changed(self) -> None:
        self._update_number_preview()
        self._sync_flow()
        self._update_balance()

    # ------------------------------------------------------------------ #
    # layout — accounting entry grid (scrolls; header row stays visible)
    # ------------------------------------------------------------------ #
    def _build_entry_area(self) -> None:
        area = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        area.pack(fill="both", expand=True, pady=(0, config.SPACING_LG))
        area.grid_rowconfigure(1, weight=1)
        area.grid_columnconfigure(0, weight=1)

        # Column headers (fixed).
        headers = ctk.CTkFrame(area, fg_color="transparent", height=_HEADER_ROW_HEIGHT)
        headers.grid(row=0, column=0, sticky="ew")
        headers.grid_propagate(False)
        headers.grid_columnconfigure(0, weight=1)
        headers.grid_columnconfigure(1, weight=0)
        headers.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(
            headers, text="Particulars", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=config.SPACING_LG, pady=4)
        ctk.CTkLabel(
            headers, text="Debit", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_EXPENSE, anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(0, config.SPACING_XL), pady=4)
        ctk.CTkLabel(
            headers, text="Credit", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_INCOME, anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(0, config.SPACING_XL), pady=4)

        # Scrollable grid body.
        body = ctk.CTkScrollableFrame(
            area, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=config.COLOR_BG_TERTIARY,
            scrollbar_button_hover_color=config.COLOR_PRIMARY_HOVER,
        )
        body.grid(row=1, column=0, sticky="nsew")
        self.grid_body = body
        # The frame itself holds the scrollable rows; we manage them via pack.
        self.grid_rows_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.grid_rows_frame.pack(fill="x")
        self.grid_rows_frame.grid_columnconfigure(0, weight=1)

        self._first_focus: Optional[Any] = None

    def _add_row(self, account_id: Optional[int] = None, debit: str = "",
                 credit: str = "", to_line: bool = False) -> Dict[str, Any]:
        """Append one accounting line to the grid."""
        row: Dict[str, Any] = {"to_line": to_line}
        frame = ctk.CTkFrame(self.grid_rows_frame, fg_color="transparent", height=_ROW_HEIGHT)
        frame.pack(fill="x")
        frame.grid_propagate(False)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=0)
        frame.grid_columnconfigure(2, weight=0)
        row["frame"] = frame

        # Particulars: a "To " prefix for credit-side lines, then the picker.
        label = ctk.CTkLabel(
            frame, text="To ", font=ctk.CTkFont(size=config.FONT_BODY_SIZE, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
        )
        label.grid(row=0, column=0, sticky="w", padx=(config.SPACING_MD, 0), pady=6)
        row["to_label"] = label

        picker = LedgerPicker(
            frame, self.company_id, width=0,
            on_selected=lambda _id, r=row: self._on_row_selected(r),
        )
        picker.grid(row=0, column=0, sticky="ew", padx=(config.SPACING_LG, config.SPACING_SM),
                    pady=6)
        row["picker"] = picker

        # Debit / Credit amount cells (right-aligned).
        debit_var = tk.StringVar(value=debit)
        credit_var = tk.StringVar(value=credit)
        debit_var.trace_add("write", lambda *_: self._update_balance())
        credit_var.trace_add("write", lambda *_: self._update_balance())

        debit_entry = ctk.CTkEntry(
            frame, textvariable=debit_var, width=150, justify="right",
            corner_radius=config.INPUT_CORNER_RADIUS,
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
        )
        debit_entry.grid(row=0, column=1, sticky="e", padx=(0, config.SPACING_SM), pady=6)
        credit_entry = ctk.CTkEntry(
            frame, textvariable=credit_var, width=150, justify="right",
            corner_radius=config.INPUT_CORNER_RADIUS,
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
        )
        credit_entry.grid(row=0, column=2, sticky="e", padx=(0, config.SPACING_XL), pady=6)

        row["debit_var"] = debit_var
        row["credit_var"] = credit_var
        row["debit_entry"] = debit_entry
        row["credit_entry"] = credit_entry

        debit_entry.bind("<Return>", lambda _e, r=row: self._on_amount_return(r, "debit"))
        credit_entry.bind("<Return>", lambda _e, r=row: self._on_amount_return(r, "credit"))
        credit_entry.bind("<KeyRelease>", lambda _e, r=row: self._maybe_add_row(r))
        debit_entry.bind("<KeyRelease>", lambda _e, r=row: self._maybe_add_row(r))

        self.rows.append(row)
        self._apply_row_presentation(row)
        if account_id is not None:
            picker.set_account(account_id)
        return row

    def _apply_row_presentation(self, row: Dict[str, Any]) -> None:
        to_line = bool(row.get("to_line"))
        if to_line:
            row["to_label"].grid()
            row["picker"].entry.configure(text_color=config.COLOR_PRIMARY)
        else:
            row["to_label"].grid_remove()
            row["picker"].entry.configure(text_color=config.COLOR_TEXT_PRIMARY)

    def _on_row_selected(self, row: Dict[str, Any]) -> None:
        # After picking an account, move to the debit amount cell of that row
        # (the natural next entry point).
        if row.get("to_line"):
            row["credit_entry"].focus_set()
        else:
            row["debit_entry"].focus_set()

    def _on_amount_return(self, row: Dict[str, Any], side: str) -> None:
        if row.get("to_line"):
            self._on_enter_after_credit(row)
            return
        # A debit-side amount: pressing Enter moves to the credit side (the
        # existing "To" line), or adds the first credit line if none exists.
        credit_row = self._ensure_credit_row()
        credit_row["picker"].focus_entry()

    def _on_enter_after_credit(self, row: Dict[str, Any]) -> None:
        # Finished the credit side: add a fresh debit line (continues the
        # entry flow), or save when the voucher is complete and balanced.
        if self._has_incomplete_rows():
            self._add_row()
            self._focus_last_row_account()
        elif self._is_balanced():
            self._save_voucher()
        else:
            self._add_row()
            self._focus_last_row_account()

    def _maybe_add_row(self, row: Dict[str, Any]) -> None:
        # When a row already carries an account + amount and the user keeps
        # typing, insert the next blank line automatically.
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
        if self.party_picker is not None:
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

    # ------------------------------------------------------------------ #
    # totals
    # ------------------------------------------------------------------ #
    def _build_totals(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, config.SPACING_LG))
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="e", padx=config.SPACING_XL, pady=config.SPACING_SM)

        self.total_debit_label = ctk.CTkLabel(
            inner, text="Total Debit: 0.00", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY, anchor="e", width=160,
        )
        self.total_debit_label.grid(row=0, column=0, sticky="e", padx=(0, config.SPACING_XL))
        self.total_credit_label = ctk.CTkLabel(
            inner, text="Total Credit: 0.00", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY, anchor="e", width=160,
        )
        self.total_credit_label.grid(row=0, column=1, sticky="e", padx=(0, config.SPACING_XL))
        self.difference_label = ctk.CTkLabel(
            inner, text="Difference: 0.00", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_INCOME, anchor="e", width=180,
        )
        self.difference_label.grid(row=0, column=2, sticky="e")

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

    def _update_balance(self, *args) -> None:
        debit, credit = self._totals()
        difference = round(debit - credit, 2)
        self.total_debit_label.configure(text=f"Total Debit: {_fmt(debit)}")
        self.total_credit_label.configure(text=f"Total Credit: {_fmt(credit)}")
        if difference == 0 and (debit or credit):
            self.difference_label.configure(
                text="Difference: 0.00", text_color=config.COLOR_INCOME)
        else:
            self.difference_label.configure(
                text=f"Difference: {_fmt(difference)}", text_color=config.COLOR_WARNING)

    def _is_balanced(self) -> bool:
        debit, credit = self._totals()
        return round(debit, 2) == round(credit, 2) and debit > 0

    # ------------------------------------------------------------------ #
    # narration + actions + status
    # ------------------------------------------------------------------ #
    def _build_narration(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, config.SPACING_LG))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_SM)
        ctk.CTkLabel(
            inner, text="Narration:", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(side="left")
        self.narration_var = tk.StringVar()
        self.narration_entry = ctk.CTkEntry(
            inner, textvariable=self.narration_var,
            corner_radius=config.INPUT_CORNER_RADIUS,
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
        )
        self.narration_entry.pack(side="left", fill="x", expand=True, padx=(config.SPACING_SM, 0))

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, config.SPACING_LG))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_SM)

        self.btn_save = ctk.CTkButton(
            inner, text="Save", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_voucher,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_save_new = ctk.CTkButton(
            inner, text="Save & New", width=120, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_and_new,
        )
        self.btn_save_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_clear = ctk.CTkButton(
            inner, text="Clear", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._clear_form,
        )
        self.btn_clear.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_cancel = ctk.CTkButton(
            inner, text="Cancel", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._cancel_form,
        )
        self.btn_cancel.pack(side="left", padx=(0, config.SPACING_SM))

        # Secondary actions (existing voucher workflow).
        self.btn_register = ctk.CTkButton(
            inner, text="Voucher Register", width=130, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._open_register,
        )
        self.btn_register.pack(side="left", padx=(config.SPACING_XL, 0))
        self.btn_cancel_voucher = ctk.CTkButton(
            inner, text="Cancel Voucher", width=130, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._cancel_selected_voucher,
        )
        self.btn_cancel_voucher.pack(side="left", padx=(config.SPACING_SM, 0))

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x")

    # ------------------------------------------------------------------ #
    # voucher-type behavior (presentation of the existing rules)
    # ------------------------------------------------------------------ #
    def _sync_flow(self) -> None:
        """Adapt the entry grid to the selected voucher type.

        The debit/credit direction follows the existing Expenzo voucher rules
        (see voucher_service tests); the UI only chooses which side the
        party line lands on and pre-fills the flow hint.
        """
        vtype = self.type_var.get()
        if vtype == VOUCHER_PAYMENT:
            # Payment: Dr expense/party  →  To Bank/Cash
            self._set_flow("Payment: Debit expense/party  →  To Bank/Cash A/c")
            self.party_side = "debit"
        elif vtype == VOUCHER_RECEIPT:
            # Receipt: Dr Cash/Bank  →  To party
            self._set_flow("Receipt: Debit Cash/Bank  →  To Party A/c")
            self.party_side = "credit"
        elif vtype == VOUCHER_CONTRA:
            # Contra: Dr Bank/Cash  →  To Cash/Bank
            self._set_flow("Contra: Debit Bank/Cash A/c  →  To Cash/Bank A/c")
            self.party_side = None
        else:
            # Journal: Dr account  →  To account
            self._set_flow("Journal: Debit A/c  →  To Credit A/c")
            self.party_side = None

        # Party field is only relevant when the voucher type involves one.
        if self.party_picker is not None:
            if vtype in (VOUCHER_PAYMENT, VOUCHER_RECEIPT):
                if self.party_picker.winfo_manager() == "":
                    self.party_picker.pack(anchor="w", pady=(2, 0))
            else:
                self.party_picker.pack_forget()

    def _set_flow(self, text: str) -> None:
        try:
            self.flow_hint.configure(text=text)
        except Exception:
            pass

    def _on_party_selected(self) -> None:
        # Party goes on the appropriate side (Dr for payment, Cr for receipt).
        vtype = self.type_var.get()
        if vtype not in (VOUCHER_PAYMENT, VOUCHER_RECEIPT):
            return
        party_id = self.party_picker.get_account()
        if party_id is None:
            return
        if vtype == VOUCHER_PAYMENT:
            row = self._ensure_debit_row()
            row["picker"].set_account(party_id)
            row["debit_entry"].focus_set()
        else:
            row = self._ensure_credit_row()
            row["picker"].set_account(party_id)
            row["credit_entry"].focus_set()

    def _ensure_debit_row(self) -> Dict[str, Any]:
        for row in self.rows:
            if not row.get("to_line") and row["picker"].get_account() is None:
                return row
        return self._add_row()

    def _ensure_credit_row(self) -> Dict[str, Any]:
        for row in self.rows:
            if row.get("to_line"):
                return row
        return self._add_row(to_line=True)

    # ------------------------------------------------------------------ #
    # number / date
    # ------------------------------------------------------------------ #
    def _update_number_preview(self) -> None:
        voucher_type = self.type_var.get()
        if self.current_voucher_id is None:
            self.number_var.set(voucher_service.next_voucher_number(self.company_id, voucher_type))
        self.number_label.configure(text=self.number_var.get())

    def _parse_date(self, raw: str) -> Optional[date]:
        for fmt in (config.DISPLAY_DATE_FORMAT, "%Y-%m-%d"):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------ #
    # form data -> existing voucher_service API
    # ------------------------------------------------------------------ #
    def _form_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for row in self.rows:
            account_id = row["picker"].get_account()
            if account_id is None:
                continue
            try:
                debit = float(row["debit_var"].get() or 0)
            except ValueError:
                debit = 0.0
            try:
                credit = float(row["credit_var"].get() or 0)
            except ValueError:
                credit = 0.0
            if debit <= 0 and credit <= 0:
                continue
            entries.append({
                'account_id': account_id,
                'debit_amount': debit,
                'credit_amount': credit,
                'narration': self.narration_var.get().strip(),
            })
        return entries

    def _validate_form(self) -> Optional[str]:
        if self._parse_date(self.date_var.get()) is None:
            return "Invalid date. Use DD-MM-YYYY format."
        entries = self._form_entries()
        if not entries:
            return "Enter at least one debit and one credit entry."
        has_debit = any(float(e['debit_amount'] or 0) > 0 for e in entries)
        has_credit = any(float(e['credit_amount'] or 0) > 0 for e in entries)
        if not has_debit or not has_credit:
            return "Enter both a debit and a credit amount."
        debit_total = round(sum(float(e['debit_amount'] or 0) for e in entries), 2)
        credit_total = round(sum(float(e['credit_amount'] or 0) for e in entries), 2)
        if debit_total <= 0 or credit_total <= 0:
            return "Amounts must be greater than zero."
        if debit_total != credit_total:
            return "Debit and credit amounts must balance."
        return None

    # ------------------------------------------------------------------ #
    # save / update / cancel
    # ------------------------------------------------------------------ #
    def _save_voucher(self) -> None:
        if self.current_voucher_id is not None:
            self._update_voucher()
            return
        error = self._validate_form()
        if error:
            dialogs.warn("Save Voucher", error, parent=self.parent)
            self._set_status(error)
            return
        voucher_date = self._parse_date(self.date_var.get())
        entries = self._form_entries()
        ok, message, voucher_id = voucher_service.save_voucher(
            self.company_id,
            self.type_var.get(),
            voucher_date,
            entries,
            narration=self.narration_var.get().strip(),
        )
        if not ok:
            dialogs.error("Save Voucher", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._new_voucher()
        self.refresh_vouchers()

    def _update_voucher(self) -> None:
        if self.current_voucher_id is None:
            dialogs.warn("Update", "Select a voucher to update first.", parent=self.parent)
            return
        error = self._validate_form()
        if error:
            dialogs.warn("Update Voucher", error, parent=self.parent)
            self._set_status(error)
            return
        voucher_date = self._parse_date(self.date_var.get())
        entries = self._form_entries()
        ok, message = voucher_service.update_voucher(
            self.current_voucher_id,
            self.company_id,
            self.type_var.get(),
            voucher_date,
            entries,
            narration=self.narration_var.get().strip(),
        )
        if not ok:
            dialogs.error("Update Voucher", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._new_voucher()
        self.refresh_vouchers()

    def _save_and_new(self) -> None:
        if self.current_voucher_id is not None:
            self._update_voucher()
            return
        if self._validate_form() is None:
            self._save_voucher()
        else:
            dialogs.warn("Save & New", "Fix the voucher first — Save & New keeps a "
                         "balanced entry only.", parent=self.parent)

    def _cancel_form(self) -> None:
        self._new_voucher()
        self._set_status("Cancelled")

    def _cancel_selected_voucher(self) -> None:
        if self.current_voucher_id is None:
            dialogs.warn("Cancel Voucher", "Select a voucher to cancel.", parent=self.parent)
            return
        voucher = voucher_service.get_voucher(self.current_voucher_id)
        if not voucher:
            return
        if voucher['status'] == STATUS_CANCELLED:
            dialogs.warn("Cancel Voucher", "This voucher is already cancelled.", parent=self.parent)
            return
        if not dialogs.confirm_destructive(
                "Cancel Voucher", "voucher", voucher['voucher_number'], parent=self.parent):
            return
        ok, message = voucher_service.cancel_voucher(self.current_voucher_id, self.company_id)
        if not ok:
            dialogs.error("Cancel Voucher", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._new_voucher()
        self.refresh_vouchers()

    # ------------------------------------------------------------------ #
    # new / load / clear
    # ------------------------------------------------------------------ #
    def _new_voucher(self) -> None:
        self.current_voucher_id = None
        self.current_voucher_number = None
        self.type_var.set(VOUCHER_PAYMENT)
        self.date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.narration_var.set("")
        for row in self.rows:
            try:
                row["frame"].destroy()
            except Exception:
                pass
        self.rows.clear()
        if self.party_picker is not None:
            self.party_picker.clear()
        self._add_row()
        self._add_row(to_line=True)
        self._update_number_preview()
        self._sync_flow()
        self._update_balance()
        self.mode_label.configure(text="New Voucher")
        self.btn_save.configure(text="Save")
        self.btn_save_new.configure(text="Save & New")
        self._set_status("New voucher")

    def _clear_form(self) -> None:
        self._new_voucher()

    def _load_voucher(self, voucher: Dict[str, Any]) -> None:
        self.current_voucher_id = voucher['id']
        self.current_voucher_number = voucher.get('voucher_number', '')
        self.type_var.set(voucher.get('voucher_type', VOUCHER_PAYMENT))
        self.date_var.set(voucher.get('voucher_date', ''))
        self.narration_var.set(voucher.get('narration', ''))
        self.number_var.set(voucher.get('voucher_number', ''))
        self.number_label.configure(text=voucher.get('voucher_number', ''))

        for row in self.rows:
            try:
                row["frame"].destroy()
            except Exception:
                pass
        self.rows.clear()
        if self.party_picker is not None:
            self.party_picker.clear()

        details = voucher.get('details', [])
        for detail in details:
            debit = float(detail.get('debit_amount', 0) or 0)
            credit = float(detail.get('credit_amount', 0) or 0)
            if debit > 0:
                row = self._add_row(account_id=detail.get('account_id'),
                                    debit=str(debit))
            else:
                row = self._add_row(account_id=detail.get('account_id'),
                                    credit=str(credit), to_line=True)
            # Keep the DB narration only on the voucher header (the grid is
            # per-line; the header narration is set above).
        if not self.rows:
            self._add_row()
            self._add_row(to_line=True)

        # Restore the party field when the type involves one.
        self._sync_flow()
        if self.type_var.get() in (VOUCHER_PAYMENT, VOUCHER_RECEIPT):
            party_id = self._party_id_from_details(details)
            if party_id is not None:
                self.party_picker.set_account(party_id)

        self._update_balance()
        self.mode_label.configure(text=f"Editing {self.current_voucher_number}")
        self.btn_save.configure(text="Update")
        self.btn_save_new.configure(text="Update")
        self._set_status(f"Editing voucher {self.current_voucher_number}")

    def _party_id_from_details(self, details: List[Dict[str, Any]]) -> Optional[int]:
        # The party line is the detail whose account belongs to a party group
        # and sits on the party side of the voucher type.
        vtype = self.type_var.get()
        party_groups = set(PARTY_GROUPS)
        for detail in details:
            group = detail.get('account_group', '')
            if group in party_groups:
                debit = float(detail.get('debit_amount', 0) or 0)
                credit = float(detail.get('credit_amount', 0) or 0)
                if vtype == VOUCHER_PAYMENT and debit > 0:
                    return detail.get('account_id')
                if vtype == VOUCHER_RECEIPT and credit > 0:
                    return detail.get('account_id')
        return None

    # ------------------------------------------------------------------ #
    # register (voucher list / history — existing feature, preserved)
    # ------------------------------------------------------------------ #
    def refresh_vouchers(self) -> None:
        self.vouchers = voucher_service.list_vouchers(
            self.company_id,
            search_term="",
            voucher_type="",
            include_cancelled=False,
        )
        self.vouchers = voucher_service.enrich_vouchers_with_totals(self.vouchers)
        if not hasattr(self, "_register_open") or not self._register_open:
            return
        if self.register_tree is not None:
            self._render_register()

    def _open_register(self) -> None:
        self._register_open = True
        if self.register_window is not None and self.register_window.winfo_exists():
            self.register_window.deiconify()
            self.register_window.lift()
            self.refresh_vouchers()
            return
        self.register_window = ctk.CTkToplevel(self)
        self.register_window.title("Voucher Register — " + self._company_name())
        self.register_window.geometry("980x520")
        self.register_window.minsize(720, 400)
        self.register_window.configure(fg_color=config.COLOR_BG_PRIMARY)

        container = ctk.CTkFrame(self.register_window, corner_radius=0, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=config.SPACING_LG)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, config.SPACING_SM))
        ctk.CTkLabel(
            top, text="Voucher Register", font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")
        self.register_search_var = tk.StringVar()
        self.register_search_var.trace_add("write", lambda *_: self.refresh_vouchers())
        self.register_search_entry = ctk.CTkEntry(
            top, textvariable=self.register_search_var, width=200,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.register_search_entry.pack(side="left", padx=(config.SPACING_LG, config.SPACING_SM))
        ctk.CTkButton(
            top, text="↻ Refresh", width=90, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.refresh_vouchers,
        ).pack(side="right")

        tree_frame = ctk.CTkFrame(container, fg_color=config.COLOR_BG_SECONDARY)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("number", "type", "date", "narration", "debit", "credit")
        self.register_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("number", "Voucher No.", 110),
            ("type", "Type", 90),
            ("date", "Date", 100),
            ("narration", "Narration", 260),
            ("debit", "Debit", 110),
            ("credit", "Credit", 110),
        ]:
            self.register_tree.heading(col, text=heading)
            self.register_tree.column(col, width=width,
                                      anchor="w" if col not in {"debit", "credit"} else "e")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.register_tree.yview)
        self.register_tree.configure(yscrollcommand=vsb.set)
        self.register_tree.grid(row=0, column=0, sticky="nsew", padx=(config.SPACING_SM, 0),
                                pady=config.SPACING_SM)
        vsb.grid(row=0, column=1, sticky="ns", pady=config.SPACING_SM)
        self.register_tree.bind("<Double-Button-1>", lambda _e: self._register_load_selected())
        self.register_tree.bind("<Return>", lambda _e: self._register_load_selected())

        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", pady=(config.SPACING_SM, 0))
        self.btn_register_load = ctk.CTkButton(
            actions, text="Open / Edit", width=110, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._register_load_selected,
        )
        self.btn_register_load.pack(side="left")
        ctk.CTkButton(
            actions, text="View", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1,
            command=lambda: self._register_load_selected(read_only=True),
        ).pack(side="left", padx=(config.SPACING_SM, 0))
        self.btn_register_close = ctk.CTkButton(
            actions, text="Close", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1,
            command=self._close_register,
        )
        self.btn_register_close.pack(side="right")

        self._render_register()

    def _render_register(self) -> None:
        if self.register_tree is None:
            return
        for item in self.register_tree.get_children():
            self.register_tree.delete(item)
        term = getattr(self, "register_search_var", None)
        search = term.get().strip().lower() if term is not None else ""
        for index, voucher in enumerate(self.vouchers):
            if search:
                haystack = " ".join([
                    str(voucher.get('voucher_number', '')),
                    str(voucher.get('voucher_type', '')),
                    str(voucher.get('narration', '')),
                ]).lower()
                if search not in haystack:
                    continue
            self.register_tree.insert("", tk.END, iid=str(voucher['id']), values=(
                voucher.get('voucher_number', ''),
                voucher.get('voucher_type', ''),
                voucher.get('voucher_date', ''),
                voucher.get('narration', ''),
                f"{voucher.get('total_debit', 0):,.2f}",
                f"{voucher.get('total_credit', 0):,.2f}",
            ), tags=('even' if index % 2 == 0 else 'odd',))

    def _register_load_selected(self, read_only: bool = False) -> None:
        selection = self.register_tree.selection()
        if not selection:
            dialogs.warn("Voucher Register", "Select a voucher to open.", parent=self.parent)
            return
        voucher = voucher_service.get_voucher_with_details(int(selection[0]))
        if not voucher:
            return
        self._close_register()
        self._load_voucher(voucher)
        if read_only:
            self._set_read_only(True)

    def _set_read_only(self, enabled: bool) -> None:
        state = "disabled" if enabled else "normal"
        for widget in (self.date_entry, self.narration_entry):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        self.type_combo.configure(state="disabled" if enabled else "readonly")
        for row in self.rows:
            row["picker"].entry.configure(state=state)
            row["debit_entry"].configure(state=state)
            row["credit_entry"].configure(state=state)
        if self.party_picker is not None:
            self.party_picker.entry.configure(state=state)
        if enabled:
            self.mode_label.configure(text=f"Viewing {self.current_voucher_number}")

    def _close_register(self) -> None:
        self._register_open = False
        try:
            self.register_window.withdraw()
        except Exception:
            pass

    def _company_name(self) -> str:
        try:
            row = db.fetch_one("SELECT name FROM companies WHERE id = ?",
                               (self.company_id,))
            return row["name"] if row else "Company"
        except Exception:
            return "Company"

    # ------------------------------------------------------------------ #
    # keyboard hooks (called by the global shortcut manager)
    # ------------------------------------------------------------------ #
    def on_keyboard_save(self) -> None:
        self._save_voucher()

    def on_keyboard_new(self) -> None:
        self._new_voucher()
        self._focus_first_field()

    def on_keyboard_refresh(self) -> None:
        self.refresh_vouchers()

    def on_keyboard_search(self) -> None:
        self._open_register()
        try:
            self.register_search_entry.focus_set()
        except Exception:
            pass

    def on_keyboard_delete(self) -> None:
        if self.current_voucher_id is not None:
            self._cancel_selected_voucher()

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.parent.update_idletasks()
        except Exception:
            pass


# Local import so we can read company names in the register title.
from database.database import db  # noqa: E402
