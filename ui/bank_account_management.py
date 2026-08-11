"""
Expenzo — Bank Account Management
Bank account master screen in the Expenzo design system with company
isolation: bank accounts are scoped to the currently selected company.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.bank_account_service import bank_account_service
from utils import dialogs

ACCOUNT_TYPES = ["Savings", "Current"]


class BankAccountManagementUI:
    """UI for bank account management."""

    def __init__(self, parent: tk.Widget, company_id: Optional[int] = None):
        self.parent = parent
        self.company_id = company_id
        self.current_bank_account_id: Optional[int] = None
        self.current_items: list[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        self._build_header()
        self._build_body()
        self._build_status()
        from utils.keyboard import wire_entry_screen
        wire_entry_screen(self, self.main_frame, [
            ("Ctrl+S", "Save"), ("Ctrl+N", "New"), ("Ctrl+F", "Search"),
            ("F5", "Refresh"), ("Del", "Delete selected"), ("Esc", "Back"),
        ])
        self.refresh_bank_accounts()

    def _current_company_id(self) -> int:
        """Return the explicit company id passed in, else discover from the
        top-level window (legacy path), else fail safely."""
        if self.company_id:
            return int(self.company_id)
        try:
            app = self.parent.winfo_toplevel()
            return int(getattr(app, "current_company_id", 0))
        except Exception:
            return 0

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Bank Accounts",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Bank account master",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

    def _build_body(self) -> None:
        self.body = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)
        self._build_list_pane()
        self._build_form_pane()

    def _build_list_pane(self) -> None:
        pane = ctk.CTkFrame(
            self.body, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        pane.grid(row=0, column=0, sticky="nsew", padx=(0, config.SPACING_MD))
        pane.grid_rowconfigure(2, weight=1)
        pane.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(pane, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=config.SPACING_LG,
                 pady=(config.SPACING_MD, config.SPACING_SM))
        ctk.CTkLabel(top, text="Bank Account List", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(
            top, text="+ Create", width=90, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._new_form,
        ).pack(side="right")

        search_row = ctk.CTkFrame(pane, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        ctk.CTkLabel(search_row, text="Search", font=ctk.CTkFont(size=12)).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._apply_search)
        self.search_entry = ctk.CTkEntry(
            search_row, textvariable=self.search_var, width=170,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.search_entry.pack(side="left", padx=(config.SPACING_SM, 0))

        tree_frame = ctk.CTkFrame(pane, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("bank", "number", "type")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("bank", "Bank Name", 150),
            ("number", "Account No.", 120),
            ("type", "Type", 70),
        ]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.action_row = ctk.CTkFrame(pane, fg_color="transparent")
        self.action_row.grid(row=3, column=0, sticky="ew", padx=config.SPACING_LG,
                             pady=(0, config.SPACING_LG))
        self.btn_edit = ctk.CTkButton(
            self.action_row, text="Edit", width=80, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._edit_selected,
        )
        self.btn_edit.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_delete = ctk.CTkButton(
            self.action_row, text="Delete", width=80, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_EXPENSE, hover_color=config.COLOR_EXPENSE_HOVER,
            command=self._delete_bank_account,
        )
        self.btn_delete.pack(side="left")
        self._set_actions_enabled(False)

    def _build_form_pane(self) -> None:
        pane = ctk.CTkFrame(
            self.body, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        pane.grid(row=0, column=1, sticky="nsew", padx=(config.SPACING_MD, 0))

        ctk.CTkLabel(
            pane, text="Create Bank Account", font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        fields = ctk.CTkFrame(pane, fg_color="transparent")
        fields.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        self.bank_name_var = tk.StringVar()
        self.account_name_var = tk.StringVar()
        self.account_number_var = tk.StringVar()
        self.account_type_var = tk.StringVar(value="Savings")
        self.opening_balance_var = tk.StringVar(value="0.00")
        self.opening_balance_type_var = tk.StringVar(value="Debit")
        self.ifsc_var = tk.StringVar()
        self.branch_var = tk.StringVar()
        self.notes_var = tk.StringVar()

        self._label(fields, 0, "Bank Name *")
        ctk.CTkEntry(fields, textvariable=self.bank_name_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=0, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 1, "Account Name")
        ctk.CTkEntry(fields, textvariable=self.account_name_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=1, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 2, "Account Number")
        ctk.CTkEntry(fields, textvariable=self.account_number_var, width=200,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=2, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 3, "Account Type")
        ctk.CTkComboBox(
            fields, values=ACCOUNT_TYPES, variable=self.account_type_var,
            width=140, state="readonly").grid(
            row=3, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 4, "Opening Balance")
        ctk.CTkEntry(fields, textvariable=self.opening_balance_var, width=130,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=4, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 5, "Dr / Cr")
        ctk.CTkComboBox(
            fields, values=["Debit", "Credit"], variable=self.opening_balance_type_var,
            width=100, state="readonly").grid(
            row=5, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 6, "IFSC Code")
        ctk.CTkEntry(fields, textvariable=self.ifsc_var, width=150,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=6, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 7, "Branch")
        ctk.CTkEntry(fields, textvariable=self.branch_var, width=180,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=7, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 8, "Notes / Remarks")
        ctk.CTkEntry(fields, textvariable=self.notes_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=8, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        buttons = ctk.CTkFrame(pane, fg_color="transparent")
        buttons.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_save = ctk.CTkButton(
            buttons, text="Save / Accept", width=120, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_bank_account,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._update_bank_account,
        )
        self.btn_update.pack(side="left", padx=(0, config.SPACING_SM))
        ctk.CTkButton(
            buttons, text="Clear", width=80, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._clear_form,
        ).pack(side="left", padx=(0, config.SPACING_SM))
        ctk.CTkButton(
            buttons, text="Cancel", width=80, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._cancel_form,
        ).pack(side="left")

    def _label(self, parent, row: int, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text, font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
            text_color=config.COLOR_TEXT_SECONDARY, width=160, anchor="w",
        ).grid(row=row, column=0, padx=(0, config.SPACING_MD), pady=config.SPACING_XS, sticky="w")

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x", pady=(config.SPACING_SM, 0))

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.parent.update_idletasks()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # keyboard hooks (invoked by the global shortcut manager)
    # ------------------------------------------------------------------ #
    def on_keyboard_save(self) -> None:
        if self.current_bank_account_id is None:
            self._save_bank_account()
        else:
            self._update_bank_account()

    def on_keyboard_new(self) -> None:
        self._clear_form()

    def on_keyboard_refresh(self) -> None:
        self.refresh_bank_accounts()

    def on_keyboard_search(self) -> None:
        from utils.keyboard import _focus_search
        _focus_search(self)

    def on_keyboard_delete(self) -> None:
        if self.tree.selection():
            self._delete_bank_account()

    def on_keyboard_back(self) -> None:
        app = self.parent.winfo_toplevel()
        if hasattr(app, "on_keyboard_back"):
            app.on_keyboard_back()

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)

    def _new_form(self) -> None:
        self._clear_form()
        self._set_status("Creating a new bank account")

    def _edit_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            dialogs.warn("Edit", "Select a bank account to edit.", parent=self.parent)
            return
        self._on_select()

    def _cancel_form(self) -> None:
        self._clear_form()
        self._set_status("Cancelled")

    def _clear_form(self) -> None:
        self.current_bank_account_id = None
        self.bank_name_var.set("")
        self.account_name_var.set("")
        self.account_number_var.set("")
        self.account_type_var.set("Savings")
        self.opening_balance_var.set("0.00")
        self.opening_balance_type_var.set("Debit")
        self.ifsc_var.set("")
        self.branch_var.set("")
        self.notes_var.set("")
        self.tree.selection_remove(self.tree.selection())
        self._set_actions_enabled(False)
        self._set_status("Form cleared")

    def _validate(self) -> Optional[str]:
        if not self.bank_name_var.get().strip():
            return "Bank name is required"
        if not self.account_type_var.get().strip():
            return "Account type is required"
        try:
            float(self.opening_balance_var.get() or 0)
        except Exception:
            return "Opening balance must be numeric"
        return None

    def _form_data(self) -> Dict[str, Any]:
        return {
            "bank_name": self.bank_name_var.get().strip(),
            "account_name": self.account_name_var.get().strip(),
            "account_number": self.account_number_var.get().strip(),
            "account_type": self.account_type_var.get().strip(),
            "opening_balance": float(self.opening_balance_var.get() or 0),
            "opening_balance_type": self.opening_balance_type_var.get().strip() or "Debit",
            "current_balance": float(self.opening_balance_var.get() or 0),
            "ifsc_code": self.ifsc_var.get().strip(),
            "branch": self.branch_var.get().strip(),
            "notes": self.notes_var.get().strip(),
        }

    def _save_bank_account(self) -> None:
        error = self._validate()
        if error:
            dialogs.warn("Validation", error, parent=self.parent)
            self._set_status(error)
            return
        data = self._form_data()
        company_id = self._current_company_id()
        success, message = bank_account_service.create_bank_account(data, company_id=company_id)
        if success:
            self._set_status(message)
            self.refresh_bank_accounts()
            self._clear_form()
        else:
            dialogs.error("Error", message, parent=self.parent)
            self._set_status(message)

    def _update_bank_account(self) -> None:
        if self.current_bank_account_id is None:
            dialogs.warn("Update", "Select a bank account to update first.", parent=self.parent)
            return
        error = self._validate()
        if error:
            dialogs.warn("Validation", error, parent=self.parent)
            self._set_status(error)
            return
        data = self._form_data()
        success, message = bank_account_service.update_bank_account(self.current_bank_account_id, data)
        if success:
            self._set_status(message)
            self.refresh_bank_accounts()
            self._clear_form()
        else:
            dialogs.error("Error", message, parent=self.parent)
            self._set_status(message)

    def _delete_bank_account(self) -> None:
        if self.current_bank_account_id is None:
            dialogs.warn("Delete", "Select a bank account to delete", parent=self.parent)
            return
        item = bank_account_service.get_bank_account(self.current_bank_account_id)
        name = item.get("bank_name", "") if item else "bank account"
        if bank_account_service.is_bank_account_referenced(self.current_bank_account_id):
            dialogs.error("Delete", "Cannot delete referenced bank account", parent=self.parent)
            return
        if not dialogs.confirm_destructive("Delete", "bank account", name, parent=self.parent):
            return
        success, message = bank_account_service.delete_bank_account(self.current_bank_account_id)
        if success:
            self._set_status(message)
            self.refresh_bank_accounts()
            self._clear_form()
        else:
            dialogs.error("Error", message, parent=self.parent)
            self._set_status(message)

    def refresh_bank_accounts(self) -> None:
        self.current_items = bank_account_service.list_bank_accounts(
            self.search_var.get().strip(), company_id=self._current_company_id())
        self._render_rows()
        self._set_status(f"Loaded {len(self.current_items)} bank accounts")

    def _apply_search(self, *args) -> None:
        self.refresh_bank_accounts()

    def _render_rows(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, item in enumerate(self.current_items):
            self.tree.insert("", tk.END, iid=str(item["id"]), values=(
                item.get("bank_name", ""),
                item.get("account_number", ""),
                item.get("account_type", ""),
            ), tags=('even' if index % 2 == 0 else 'odd',))

    def _on_select(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self._set_actions_enabled(False)
            return
        self._set_actions_enabled(True)
        item = bank_account_service.get_bank_account(int(selection[0]))
        if not item:
            return
        self.current_bank_account_id = item["id"]
        self.bank_name_var.set(item.get("bank_name", ""))
        self.account_name_var.set(item.get("account_name", ""))
        self.account_number_var.set(item.get("account_number", ""))
        self.account_type_var.set(item.get("account_type", "Savings"))
        self.opening_balance_var.set(str(item.get("opening_balance", 0.0)))
        self.opening_balance_type_var.set(item.get("opening_balance_type", "Debit"))
        self.ifsc_var.set(item.get("ifsc_code", ""))
        self.branch_var.set(item.get("branch", ""))
        self.notes_var.set(item.get("notes", ""))
        self._set_status(f"Editing bank account #{item['id']}")


def show_bank_account_management(parent: tk.Widget, company_id: Optional[int] = None) -> BankAccountManagementUI:
    return BankAccountManagementUI(parent, company_id)
