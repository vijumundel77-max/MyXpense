"""
Expenzo — Ledgers (Chart of Accounts)
Tally-style ledger master: create/edit/delete ledgers with name, alias,
under-group, opening balance + Dr/Cr nature, mailing details and an opening
balance summary.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.account_service import account_service
from services.group_service import group_service
from utils import dialogs


class LedgerMasterUI:
    """Chart of Accounts (ledgers) master screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_edit_id: Optional[int] = None
        self.ledgers: List[Dict[str, Any]] = []

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
        self.refresh_ledgers()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Ledgers", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Chart of Accounts ledgers",
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
        ctk.CTkLabel(top, text="Ledger List", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
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
        self.show_inactive_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            search_row, text="Inactive", variable=self.show_inactive_var,
            command=self.refresh_ledgers, font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(config.SPACING_SM, 0))

        tree_frame = ctk.CTkFrame(pane, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("name", "group", "opening")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("name", "Ledger Name", 160),
            ("group", "Under", 130),
            ("opening", "Opening", 90),
        ]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w" if col != "opening" else "e")
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
            command=self._delete_ledger,
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
            pane, text="Create Ledger", font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        fields = ctk.CTkFrame(pane, fg_color="transparent")
        fields.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        self.name_var = tk.StringVar()
        self.alias_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.group_var = tk.StringVar()
        self.opening_var = tk.StringVar(value="0.00")
        self.opening_type_var = tk.StringVar(value="Debit")
        self.address_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.country_var = tk.StringVar()
        self.pincode_var = tk.StringVar()
        self.active_var = tk.BooleanVar(value=True)

        self._label(fields, 0, "Name *")
        ctk.CTkEntry(fields, textvariable=self.name_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=0, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 1, "Alias")
        ctk.CTkEntry(fields, textvariable=self.alias_var, width=180,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=1, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 2, "Under")
        self.group_combo = ctk.CTkComboBox(
            fields, values=[], variable=self.group_var, width=240, state="readonly")
        self.group_combo.grid(row=2, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 3, "Opening Balance")
        ctk.CTkEntry(fields, textvariable=self.opening_var, width=130,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=3, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 4, "Dr / Cr")
        ctk.CTkComboBox(
            fields, values=["Debit", "Credit"], variable=self.opening_type_var,
            width=110, state="readonly").grid(
            row=4, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        # Mailing Details
        ctk.CTkLabel(
            fields, text="Mailing Details", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).grid(row=5, column=0, columnspan=2, padx=(0, config.SPACING_MD),
               pady=(config.SPACING_MD, 0), sticky="w")

        self._label(fields, 6, "Address")
        ctk.CTkEntry(fields, textvariable=self.address_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=6, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 7, "State")
        ctk.CTkEntry(fields, textvariable=self.state_var, width=140,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=7, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 8, "Country")
        ctk.CTkEntry(fields, textvariable=self.country_var, width=140,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=8, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 9, "Pincode")
        ctk.CTkEntry(fields, textvariable=self.pincode_var, width=110,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=9, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 10, "Active")
        ctk.CTkCheckBox(fields, text="", variable=self.active_var, width=20).grid(
            row=10, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        # Opening balance summary
        self.summary_label = ctk.CTkLabel(
            pane, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_PRIMARY, anchor="w",
        )
        self.summary_label.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        self.opening_var.trace_add("write", self._update_summary)
        self.opening_type_var.trace_add("write", self._update_summary)

        buttons = ctk.CTkFrame(pane, fg_color="transparent")
        buttons.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_save = ctk.CTkButton(
            buttons, text="Save / Accept", width=120, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_ledger,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._update_ledger,
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
            text_color=config.COLOR_TEXT_SECONDARY, width=200, anchor="w",
        ).grid(row=row, column=0, padx=(0, config.SPACING_MD), pady=config.SPACING_XS, sticky="w")

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self.main_frame, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x", pady=(config.SPACING_SM, 0))

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)

    def _new_form(self) -> None:
        self._clear_form()
        self._set_status("Creating a new ledger")

    def _edit_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            dialogs.warn("Edit", "Select a ledger to edit.", parent=self.parent)
            return
        self._on_select()

    def _cancel_form(self) -> None:
        self._clear_form()
        self._set_status("Cancelled")

    def _update_summary(self, *args) -> None:
        try:
            opening = float(self.opening_var.get() or 0)
        except ValueError:
            opening = 0.0
        nature = self.opening_type_var.get().strip() or "Debit"
        if opening != 0:
            self.summary_label.configure(text=f"Opening Balance: {opening:,.2f} {nature}")
        else:
            self.summary_label.configure(text="")

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def refresh_ledgers(self) -> None:
        self.ledgers = account_service.search_accounts(
            self.company_id, self.search_var.get().strip(),
            include_inactive=self.show_inactive_var.get())
        self._update_group_combo()
        self._render_rows()
        self._set_status(f"Loaded {len(self.ledgers)} ledgers")

    def _update_group_combo(self) -> None:
        groups = group_service.list_groups(self.company_id, include_inactive=False)
        self.group_combo.configure(values=[g['name'] for g in groups])

    def _render_rows(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, ledger in enumerate(self.ledgers):
            self.tree.insert("", tk.END, iid=str(ledger['id']), values=(
                ledger.get('name', ''),
                ledger.get('account_group', ''),
                f"{ledger.get('opening_balance', 0):,.2f}",
            ), tags=('even' if index % 2 == 0 else 'odd',))

    def _apply_search(self, *args) -> None:
        self.refresh_ledgers()

    def _on_select(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self._set_actions_enabled(False)
            return
        self._set_actions_enabled(True)
        ledger = account_service.get_account(int(selection[0]))
        if not ledger:
            return
        self.current_edit_id = ledger['id']
        self.name_var.set(ledger.get('name', ''))
        self.alias_var.set(ledger.get('alias', ''))
        self.code_var.set(ledger.get('code', ''))
        self.group_var.set(ledger.get('account_group', ''))
        self.opening_var.set(str(ledger.get('opening_balance', 0.0)))
        self.opening_type_var.set(ledger.get('opening_balance_type', 'Debit'))
        self.address_var.set(ledger.get('address', ''))
        self.state_var.set(ledger.get('state', ''))
        self.country_var.set(ledger.get('country', ''))
        self.pincode_var.set(ledger.get('pincode', ''))
        self.active_var.set(bool(ledger.get('is_active', True)))
        self._update_summary()
        self._set_status(f"Editing ledger: {ledger['name']}")

    def _form_data(self) -> Dict[str, Any]:
        return {
            "name": self.name_var.get().strip(),
            "alias": self.alias_var.get().strip(),
            "code": self.code_var.get().strip(),
            "account_group": self.group_var.get().strip(),
            "opening_balance": self.opening_var.get().strip(),
            "opening_balance_type": self.opening_type_var.get().strip(),
            "address": self.address_var.get().strip(),
            "state": self.state_var.get().strip(),
            "country": self.country_var.get().strip(),
            "pincode": self.pincode_var.get().strip(),
            "is_active": self.active_var.get(),
        }

    def _clear_form(self) -> None:
        self.current_edit_id = None
        for var in (self.name_var, self.alias_var, self.code_var, self.group_var,
                    self.address_var, self.state_var, self.country_var, self.pincode_var):
            var.set("")
        self.opening_var.set("0.00")
        self.opening_type_var.set("Debit")
        self.active_var.set(True)
        self._update_summary()
        self.tree.selection_remove(self.tree.selection())
        self._set_actions_enabled(False)
        self._set_status("Form cleared")

    def _parse_opening(self, raw: str) -> Optional[float]:
        try:
            return float(raw or 0)
        except Exception:
            return None

    def _save_ledger(self) -> None:
        data = self._form_data()
        if not data["name"]:
            dialogs.warn("Save Ledger", "Ledger name is required.", parent=self.parent)
            return
        if not data["account_group"]:
            dialogs.warn("Save Ledger", "Select an account group (Under).", parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"])
        if opening is None:
            dialogs.warn("Save Ledger", "Opening balance must be numeric.", parent=self.parent)
            return
        try:
            account_service.create_account(
                self.company_id, data["name"], data["code"], data["account_group"],
                opening, data["opening_balance_type"],
                alias=data["alias"], address=data["address"], state=data["state"],
                country=data["country"], pincode=data["pincode"],
            )
        except Exception as exc:
            dialogs.error("Save Ledger", f"Failed to save ledger: {exc}", parent=self.parent)
            return
        self._set_status("Ledger saved successfully")
        self._clear_form()
        self.refresh_ledgers()

    def _update_ledger(self) -> None:
        if self.current_edit_id is None:
            dialogs.warn("Update", "Select a ledger to update first.", parent=self.parent)
            return
        data = self._form_data()
        if not data["name"]:
            dialogs.warn("Update Ledger", "Ledger name is required.", parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"])
        if opening is None:
            dialogs.warn("Update Ledger", "Opening balance must be numeric.", parent=self.parent)
            return
        ok = account_service.update_account(
            self.current_edit_id, name=data["name"], code=data["code"],
            account_group=data["account_group"], opening_balance=opening,
            opening_balance_type=data["opening_balance_type"],
            is_active=data["is_active"],
            alias=data["alias"], address=data["address"], state=data["state"],
            country=data["country"], pincode=data["pincode"],
        )
        if not ok:
            dialogs.error("Update Ledger", "Ledger not found.", parent=self.parent)
            return
        self._set_status("Ledger updated successfully")
        self._clear_form()
        self.refresh_ledgers()

    def _delete_ledger(self) -> None:
        if self.current_edit_id is None:
            dialogs.warn("Delete", "Select a ledger to delete.", parent=self.parent)
            return
        ledger = account_service.get_account(self.current_edit_id)
        if not ledger:
            return
        if account_service.is_account_referenced(self.current_edit_id):
            dialogs.error(
                "Delete Ledger",
                "Cannot delete this ledger because it is used in vouchers.",
                parent=self.parent,
            )
            self._set_status("Delete blocked: ledger is referenced in vouchers")
            return
        if not dialogs.confirm_destructive("Delete Ledger", "ledger", ledger['name'], parent=self.parent):
            return
        account_service.delete_account(self.current_edit_id)
        self._clear_form()
        self.refresh_ledgers()
        self._set_status("Ledger deleted successfully")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.parent.update_idletasks()
        except Exception:
            pass


def show_ledger_master(parent: tk.Widget, company_id: int) -> LedgerMasterUI:
    return LedgerMasterUI(parent, company_id)
