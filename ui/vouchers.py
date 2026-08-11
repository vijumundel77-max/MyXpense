"""
Expenzo — Vouchers Workspace
Double-entry voucher entry (Payment / Receipt / Contra / Journal) with a
voucher register (list, search, filter, edit, cancel).
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
from utils import dialogs


class VouchersFrame(ctk.CTkFrame):
    """Accounting voucher workspace."""

    def __init__(self, parent, company_id: Optional[int] = None):
        super().__init__(parent)
        self.parent = parent
        self.pack(fill="both", expand=True)

        self.company_id = company_id or 1
        self.current_voucher_id: Optional[int] = None
        self.accounts: List[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        self._build_header()
        self._build_entry_form()
        self._build_register()
        self._build_status()
        self.refresh_vouchers()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Vouchers", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Payment · Receipt · Contra · Journal",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

        # Keyboard shortcut hints (learnable, non-intrusive).
        from utils.keyboard import add_shortcut_bar
        add_shortcut_bar(self.main_frame, [
            ("Ctrl+S", "Save"), ("Ctrl+N", "New"), ("Ctrl+F", "Search"),
            ("F5", "Refresh"), ("Del", "Cancel selected"), ("Esc", "Back"),
        ])

    def _build_entry_form(self) -> None:
        form = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        form.pack(fill="x", pady=(0, config.SPACING_LG))

        form_header = ctk.CTkFrame(form, fg_color="transparent")
        form_header.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))
        ctk.CTkLabel(
            form_header, text="Voucher Entry", font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        # Balance indicator as a prominent chip on the right of the card header.
        self.balance_label = ctk.CTkLabel(
            form_header, text="Difference: 0.00", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_INCOME, fg_color=config.COLOR_BG_TERTIARY,
            corner_radius=6, padx=10, pady=3,
        )
        self.balance_label.pack(side="right")

        # Row 1: type, date, number, reference
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        self.type_var = tk.StringVar(value=VOUCHER_PAYMENT)
        self.date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.number_var = tk.StringVar()
        self.reference_var = tk.StringVar()

        self._field(row1, 0, "Voucher Type", lambda m: ctk.CTkComboBox(
            m, values=list(VOUCHER_TYPES), variable=self.type_var, width=140, state="readonly",
            command=lambda _: self._on_type_changed(),
        ))
        self._field(row1, 1, "Date (DD-MM-YYYY)", lambda m: ctk.CTkEntry(
            m, textvariable=self.date_var, width=140,
            corner_radius=config.INPUT_CORNER_RADIUS,
        ))
        self._field(row1, 2, "Voucher No.", lambda m: ctk.CTkEntry(
            m, textvariable=self.number_var, width=130,
            corner_radius=config.INPUT_CORNER_RADIUS, state="disabled",
        ))
        self._field(row1, 3, "Reference / Cheque", lambda m: ctk.CTkEntry(
            m, textvariable=self.reference_var, width=180,
            corner_radius=config.INPUT_CORNER_RADIUS,
        ))

        # Row 2: narration
        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        self.narration_var = tk.StringVar()
        ctk.CTkLabel(
            row2, text="Narration", font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
            text_color=config.COLOR_TEXT_SECONDARY, width=110, anchor="w",
        ).pack(side="left")
        ctk.CTkEntry(row2, textvariable=self.narration_var, width=560,
                     corner_radius=config.INPUT_CORNER_RADIUS).pack(side="left")

        # Row 3: entry lines (debit / credit)
        lines = ctk.CTkFrame(form, fg_color="transparent")
        lines.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        ctk.CTkLabel(
            lines, text="Debit", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_EXPENSE, width=300, anchor="w",
        ).grid(row=0, column=0, padx=(0, config.SPACING_MD), pady=2, sticky="w")
        ctk.CTkLabel(
            lines, text="Amount", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY, width=140, anchor="w",
        ).grid(row=0, column=1, padx=(0, config.SPACING_XL), pady=2, sticky="w")
        ctk.CTkLabel(
            lines, text="Credit", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_INCOME, width=300, anchor="w",
        ).grid(row=0, column=2, padx=(0, config.SPACING_MD), pady=2, sticky="w")
        ctk.CTkLabel(
            lines, text="Amount", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY, width=140, anchor="w",
        ).grid(row=0, column=3, padx=(0, config.SPACING_XL), pady=2, sticky="w")

        self.debit_account_var = tk.StringVar()
        self.debit_amount_var = tk.StringVar()
        self.credit_account_var = tk.StringVar()
        self.credit_amount_var = tk.StringVar()

        self.debit_combo = ctk.CTkComboBox(
            lines, values=[], variable=self.debit_account_var, width=300, state="readonly")
        self.debit_combo.grid(row=1, column=0, padx=(0, config.SPACING_MD), pady=2, sticky="w")
        self.debit_amount_entry = ctk.CTkEntry(
            lines, textvariable=self.debit_amount_var, width=140,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.debit_amount_entry.grid(row=1, column=1, padx=(0, config.SPACING_XL), pady=2, sticky="w")

        self.credit_combo = ctk.CTkComboBox(
            lines, values=[], variable=self.credit_account_var, width=300, state="readonly")
        self.credit_combo.grid(row=1, column=2, padx=(0, config.SPACING_MD), pady=2, sticky="w")
        self.credit_amount_entry = ctk.CTkEntry(
            lines, textvariable=self.credit_amount_var, width=140,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.credit_amount_entry.grid(row=1, column=3, padx=(0, config.SPACING_XL), pady=2, sticky="w")

        for var in (self.debit_amount_var, self.credit_amount_var):
            var.trace_add("write", self._update_balance)

        # Row 4: actions
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_save = ctk.CTkButton(
            actions, text="Save Voucher", width=130, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_voucher,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            actions, text="Update", width=100, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._update_voucher,
        )
        self.btn_update.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_cancel = ctk.CTkButton(
            actions, text="Cancel Voucher", width=120, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_EXPENSE, hover_color=config.COLOR_EXPENSE_HOVER,
            command=self._cancel_voucher,
        )
        self.btn_cancel.pack(side="left", padx=(0, config.SPACING_SM))
        ctk.CTkButton(
            actions, text="New", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._clear_form,
        ).pack(side="left")

    def _field(self, parent, column: int, label: str, builder) -> None:
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(row=0, column=column, padx=(0, config.SPACING_LG), sticky="w")
        ctk.CTkLabel(
            holder, text=label, font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")
        builder(holder).pack(anchor="w", pady=(2, 0))

    def _build_register(self) -> None:
        register = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        register.pack(fill="both", expand=True)
        register.pack_propagate(False)

        header = ctk.CTkFrame(register, fg_color="transparent")
        header.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_MD, config.SPACING_SM))
        ctk.CTkLabel(
            header, text="Voucher Register", font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        filters = ctk.CTkFrame(register, fg_color="transparent")
        filters.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._apply_filters)
        ctk.CTkLabel(filters, text="Search", font=ctk.CTkFont(size=12)).pack(side="left")
        self.search_entry = ctk.CTkEntry(filters, textvariable=self.search_var, width=200,
                                         corner_radius=config.INPUT_CORNER_RADIUS)
        self.search_entry.pack(side="left", padx=(config.SPACING_SM, config.SPACING_MD))

        self.type_filter_var = tk.StringVar(value="All Types")
        ctk.CTkComboBox(
            filters, values=["All Types"] + list(VOUCHER_TYPES), variable=self.type_filter_var,
            width=140, state="readonly", command=lambda _: self.refresh_vouchers(),
        ).pack(side="left", padx=(0, config.SPACING_MD))

        self.show_cancelled_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            filters, text="Show cancelled", variable=self.show_cancelled_var,
            command=self.refresh_vouchers, font=ctk.CTkFont(size=12),
        ).pack(side="left")
        ctk.CTkButton(
            filters, text="↻ Refresh", width=96, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.refresh_vouchers,
        ).pack(side="right")

        columns = ("number", "type", "date", "reference", "narration", "debit", "credit", "status")
        self.tree = ttk.Treeview(register, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("number", "Voucher No.", 120),
            ("type", "Type", 100),
            ("date", "Date", 110),
            ("reference", "Reference", 140),
            ("narration", "Narration", 240),
            ("debit", "Debit", 110),
            ("credit", "Credit", 110),
            ("status", "Status", 90),
        ]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w" if col not in {"debit", "credit"} else "e")
        vsb = ttk.Scrollbar(register, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(register, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(config.SPACING_LG, 0),
                       pady=(0, config.SPACING_LG))
        vsb.pack(side="right", fill="y", pady=(0, config.SPACING_LG))
        hsb.pack(side="bottom", fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x", pady=(config.SPACING_SM, 0))

    # ------------------------------------------------------------------ #
    # keyboard hooks (invoked by the global shortcut manager)
    # ------------------------------------------------------------------ #
    def on_keyboard_save(self) -> None:
        self._save_voucher()

    def on_keyboard_new(self) -> None:
        self._clear_form()

    def on_keyboard_refresh(self) -> None:
        self.refresh_vouchers()

    def on_keyboard_search(self) -> None:
        from utils.keyboard import _focus_search
        _focus_search(self)

    def on_keyboard_delete(self) -> None:
        if self.tree.selection():
            self._cancel_voucher()

    def on_keyboard_back(self) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, "on_keyboard_back"):
            app.on_keyboard_back()

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def refresh_vouchers(self) -> None:
        self._load_accounts()
        self.vouchers = voucher_service.list_vouchers(
            self.company_id,
            search_term=self.search_var.get().strip(),
            voucher_type="" if self.type_filter_var.get() == "All Types" else self.type_filter_var.get(),
            include_cancelled=self.show_cancelled_var.get(),
        )
        self.vouchers = voucher_service.enrich_vouchers_with_totals(self.vouchers)
        self._render_rows()
        self._set_status(f"Loaded {len(self.vouchers)} vouchers")

    def _load_accounts(self) -> None:
        self.accounts = account_service.search_accounts(self.company_id, include_inactive=False)
        self.account_map = {self._account_label(a): a['id'] for a in self.accounts}
        values = list(self.account_map.keys())
        self.debit_combo.configure(values=values)
        self.credit_combo.configure(values=values)

    @staticmethod
    def _account_label(account: Dict[str, Any]) -> str:
        code = account.get('code', '')
        return f"{account['name']} ({code})" if code else account['name']

    def _render_rows(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, voucher in enumerate(self.vouchers):
            cancelled = voucher.get('status') == STATUS_CANCELLED
            tags = ('cancelled',) if cancelled else ('even' if index % 2 == 0 else 'odd',)
            self.tree.insert("", tk.END, iid=str(voucher['id']), values=(
                voucher.get('voucher_number', ''),
                voucher.get('voucher_type', ''),
                voucher.get('voucher_date', ''),
                voucher.get('reference_number', ''),
                voucher.get('narration', ''),
                f"{voucher.get('total_debit', 0):,.2f}",
                f"{voucher.get('total_credit', 0):,.2f}",
                voucher.get('status', ''),
            ), tags=tags)

    def _apply_filters(self, *args) -> None:
        self.refresh_vouchers()

    def _on_type_changed(self) -> None:
        self._update_number_preview()

    def _update_number_preview(self) -> None:
        voucher_type = self.type_var.get()
        if self.current_voucher_id is None:
            self.number_var.set(voucher_service.next_voucher_number(self.company_id, voucher_type))

    def _parse_date(self, raw: str) -> Optional[date]:
        for fmt in (config.DISPLAY_DATE_FORMAT, "%Y-%m-%d"):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _update_balance(self, *args) -> None:
        try:
            debit = float(self.debit_amount_var.get() or 0)
        except ValueError:
            debit = 0.0
        try:
            credit = float(self.credit_amount_var.get() or 0)
        except ValueError:
            credit = 0.0
        difference = round(debit - credit, 2)
        color = config.COLOR_INCOME if difference == 0 else config.COLOR_WARNING
        self.balance_label.configure(
            text=f"Difference: {difference:,.2f}",
            text_color=color,
        )

    def _form_entries(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        debit_account = self.debit_account_var.get().strip()
        debit_amount = self.debit_amount_var.get().strip()
        credit_account = self.credit_account_var.get().strip()
        credit_amount = self.credit_amount_var.get().strip()

        if debit_account and debit_amount:
            entries.append({
                'account_id': self.account_map.get(debit_account),
                'debit_amount': debit_amount,
                'credit_amount': 0.0,
                'narration': self.narration_var.get().strip(),
            })
        if credit_account and credit_amount:
            entries.append({
                'account_id': self.account_map.get(credit_account),
                'debit_amount': 0.0,
                'credit_amount': credit_amount,
                'narration': self.narration_var.get().strip(),
            })
        return entries

    def _clear_form(self) -> None:
        self.current_voucher_id = None
        self.type_var.set(VOUCHER_PAYMENT)
        self.date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.reference_var.set("")
        self.narration_var.set("")
        self.debit_account_var.set("")
        self.credit_account_var.set("")
        self.debit_amount_var.set("")
        self.credit_amount_var.set("")
        self._update_number_preview()
        self.tree.selection_remove(self.tree.selection())
        self._set_status("New voucher")

    def _validate_form(self) -> Optional[str]:
        if self._parse_date(self.date_var.get()) is None:
            return "Invalid date. Use DD-MM-YYYY format."
        debit_account = self.debit_account_var.get().strip()
        credit_account = self.credit_account_var.get().strip()
        debit_amount = self.debit_amount_var.get().strip()
        credit_amount = self.credit_amount_var.get().strip()
        if not debit_account or not credit_account:
            return "Select both a debit and a credit account."
        if not debit_amount or not credit_amount:
            return "Enter amounts for both debit and credit."
        try:
            debit = float(debit_amount)
            credit = float(credit_amount)
        except ValueError:
            return "Amounts must be numeric."
        if debit <= 0 or credit <= 0:
            return "Amounts must be greater than zero."
        if round(debit, 2) != round(credit, 2):
            return "Debit and credit amounts must balance."
        return None

    def _save_voucher(self) -> None:
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
            reference_number=self.reference_var.get().strip(),
            narration=self.narration_var.get().strip(),
        )
        if not ok:
            dialogs.error("Save Voucher", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._clear_form()
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
            reference_number=self.reference_var.get().strip(),
            narration=self.narration_var.get().strip(),
        )
        if not ok:
            dialogs.error("Update Voucher", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._clear_form()
        self.refresh_vouchers()

    def _cancel_voucher(self) -> None:
        if self.current_voucher_id is None:
            dialogs.warn("Cancel", "Select a voucher to cancel.", parent=self.parent)
            return
        voucher = voucher_service.get_voucher(self.current_voucher_id)
        if not voucher:
            return
        if voucher['status'] == STATUS_CANCELLED:
            dialogs.warn("Cancel", "This voucher is already cancelled.", parent=self.parent)
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
        self._clear_form()
        self.refresh_vouchers()

    def _on_select(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        voucher = voucher_service.get_voucher_with_details(int(selection[0]))
        if not voucher:
            return
        self.current_voucher_id = voucher['id']
        self.type_var.set(voucher.get('voucher_type', VOUCHER_PAYMENT))
        self.date_var.set(voucher.get('voucher_date', ''))
        self.reference_var.set(voucher.get('reference_number', ''))
        self.narration_var.set(voucher.get('narration', ''))
        self.number_var.set(voucher.get('voucher_number', ''))
        # Pre-fill debit/credit from details (first debit + first credit).
        details = voucher.get('details', [])
        self.debit_account_var.set("")
        self.credit_account_var.set("")
        self.debit_amount_var.set("")
        self.credit_amount_var.set("")
        for detail in details:
            name = detail.get('account_name', '')
            code = detail.get('account_code', '')
            label = f"{name} ({code})" if code else name
            if float(detail.get('debit_amount', 0) or 0) > 0:
                self.debit_account_var.set(label)
                self.debit_amount_var.set(str(detail.get('debit_amount', 0)))
            if float(detail.get('credit_amount', 0) or 0) > 0:
                self.credit_account_var.set(label)
                self.credit_amount_var.set(str(detail.get('credit_amount', 0)))
        self._set_status(f"Editing voucher {voucher['voucher_number']}")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.parent.update_idletasks()
        except Exception:
            pass
