"""
Expenzo — Parties Master
Parties are ledgers under the Sundry Debtors / Sundry Creditors groups in
the Chart of Accounts. Creating a party here creates an Expenzo ledger so
party reports read the same accounting data.
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

DEBTOR_GROUP = "Sundry Debtors"
CREDITOR_GROUP = "Sundry Creditors"


class PartyMasterUI:
    """Parties (debtors/creditors) master screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_edit_id: Optional[int] = None
        self.parties: List[Dict[str, Any]] = []

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
        self.refresh_parties()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Parties", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Debtors & creditors",
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
        ctk.CTkLabel(top, text="Party List", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
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
            search_row, textvariable=self.search_var, width=150,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.search_entry.pack(side="left", padx=(config.SPACING_SM, 0))
        self.type_filter_var = tk.StringVar(value="All")
        ctk.CTkComboBox(
            search_row, values=["All", "Debtor", "Creditor"], variable=self.type_filter_var,
            width=110, state="readonly", command=lambda _: self.refresh_parties(),
        ).pack(side="left", padx=(config.SPACING_SM, 0))

        tree_frame = ctk.CTkFrame(pane, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("name", "type", "opening")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("name", "Party Name", 150),
            ("type", "Type", 80),
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
            command=self._delete_party,
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
            pane, text="Create Party", font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        fields = ctk.CTkFrame(pane, fg_color="transparent")
        fields.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        self.name_var = tk.StringVar()
        self.party_type_var = tk.StringVar(value="Sundry Debtors")
        self.alias_var = tk.StringVar()
        self.address_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.country_var = tk.StringVar()
        self.pincode_var = tk.StringVar()
        self.contact_var = tk.StringVar()
        self.mobile_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.opening_var = tk.StringVar(value="0.00")
        self.opening_type_var = tk.StringVar(value="Debit")
        self.credit_limit_var = tk.StringVar(value="0.00")
        self.credit_days_var = tk.StringVar(value="0")
        self.active_var = tk.BooleanVar(value=True)

        self._label(fields, 0, "Party Name *")
        ctk.CTkEntry(fields, textvariable=self.name_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=0, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 1, "Under")
        self.type_combo = ctk.CTkComboBox(
            fields, values=["Sundry Debtors", "Sundry Creditors"], variable=self.party_type_var,
            width=200, state="readonly", command=lambda _: self._sync_opening_type(),
        )
        self.type_combo.grid(row=1, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 2, "Alias")
        ctk.CTkEntry(fields, textvariable=self.alias_var, width=180,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=2, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 3, "Address")
        ctk.CTkEntry(fields, textvariable=self.address_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=3, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 4, "State")
        ctk.CTkEntry(fields, textvariable=self.state_var, width=140,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=4, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 5, "Country")
        ctk.CTkEntry(fields, textvariable=self.country_var, width=140,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=5, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 6, "Pincode")
        ctk.CTkEntry(fields, textvariable=self.pincode_var, width=110,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=6, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 7, "Contact Person")
        ctk.CTkEntry(fields, textvariable=self.contact_var, width=180,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=7, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 8, "Mobile")
        ctk.CTkEntry(fields, textvariable=self.mobile_var, width=160,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=8, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 9, "Email")
        ctk.CTkEntry(fields, textvariable=self.email_var, width=220,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=9, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 10, "Opening Balance")
        ctk.CTkEntry(fields, textvariable=self.opening_var, width=130,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=10, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 11, "Dr / Cr")
        self.opening_type_combo = ctk.CTkComboBox(
            fields, values=["Debit", "Credit"], variable=self.opening_type_var,
            width=100, state="readonly")
        self.opening_type_combo.grid(row=11, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 12, "Credit Limit")
        ctk.CTkEntry(fields, textvariable=self.credit_limit_var, width=130,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=12, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 13, "Payment / Credit Days")
        ctk.CTkEntry(fields, textvariable=self.credit_days_var, width=100,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=13, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 14, "Active")
        ctk.CTkCheckBox(fields, text="", variable=self.active_var, width=20).grid(
            row=14, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        buttons = ctk.CTkFrame(pane, fg_color="transparent")
        buttons.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_save = ctk.CTkButton(
            buttons, text="Save / Accept", width=120, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_party,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._update_party,
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
            text_color=config.COLOR_TEXT_SECONDARY, width=180, anchor="w",
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
        self._set_status("Creating a new party")

    def _edit_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            dialogs.warn("Edit", "Select a party to edit.", parent=self.parent)
            return
        self._on_select()

    def _cancel_form(self) -> None:
        self._clear_form()
        self._set_status("Cancelled")

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _party_group(self, party_type: str) -> str:
        return DEBTOR_GROUP if party_type == "Sundry Debtors" else CREDITOR_GROUP

    def _party_type_for_group(self, group: str) -> str:
        return "Sundry Debtors" if group == DEBTOR_GROUP else "Sundry Creditors"

    def _sync_opening_type(self) -> None:
        # Debtors default to Debit opening; creditors to Credit opening.
        if self.party_type_var.get() == "Sundry Debtors":
            self.opening_type_var.set("Debit")
        else:
            self.opening_type_var.set("Credit")

    def refresh_parties(self) -> None:
        groups = {DEBTOR_GROUP, CREDITOR_GROUP}
        self.parties = [
            p for p in account_service.search_accounts(
                self.company_id, self.search_var.get().strip(), include_inactive=True)
            if p.get('account_group') in groups
        ]
        filter_type = self.type_filter_var.get()
        if filter_type != "All":
            target = self._party_group(filter_type)
            self.parties = [p for p in self.parties if p.get('account_group') == target]
        self._render_rows()
        self._set_status(f"Loaded {len(self.parties)} parties")

    def _render_rows(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, party in enumerate(self.parties):
            self.tree.insert("", tk.END, iid=str(party['id']), values=(
                party.get('name', ''),
                "Debtor" if party.get('account_group') == DEBTOR_GROUP else "Creditor",
                f"{party.get('opening_balance', 0):,.2f}",
            ), tags=('even' if index % 2 == 0 else 'odd',))

    def _apply_search(self, *args) -> None:
        self.refresh_parties()

    def _on_select(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self._set_actions_enabled(False)
            return
        self._set_actions_enabled(True)
        party = account_service.get_account(int(selection[0]))
        if not party:
            return
        self.current_edit_id = party['id']
        self.name_var.set(party.get('name', ''))
        self.party_type_var.set(self._party_type_for_group(party.get('account_group', '')))
        self.alias_var.set(party.get('alias', ''))
        self.address_var.set(party.get('address', ''))
        self.state_var.set(party.get('state', ''))
        self.country_var.set(party.get('country', ''))
        self.pincode_var.set(party.get('pincode', ''))
        self.contact_var.set(party.get('contact_person', ''))
        self.mobile_var.set(party.get('mobile', ''))
        self.email_var.set(party.get('email', ''))
        self.opening_var.set(str(party.get('opening_balance', 0.0)))
        self.opening_type_var.set(party.get('opening_balance_type', 'Debit'))
        self.credit_limit_var.set(str(party.get('credit_limit', 0.0)))
        self.credit_days_var.set(str(party.get('credit_days', 0)))
        self.active_var.set(bool(party.get('is_active', True)))
        # Legacy party table fallback for phone/email
        legacy = self._find_legacy_party(party.get('name', ''))
        if legacy:
            if not self.mobile_var.get():
                self.mobile_var.set(legacy.get('phone', ''))
            if not self.email_var.get():
                self.email_var.set(legacy.get('email', ''))
        self._set_status(f"Editing party: {party['name']}")

    def _find_legacy_party(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            row = self._db_fetch_party(name)
            return row
        except Exception:
            return None

    def _db_fetch_party(self, name: str) -> Optional[Dict[str, Any]]:
        from database.database import db
        row = db.fetch_one("SELECT id, name, phone, email FROM parties WHERE LOWER(name) = LOWER(?)",
                           (name,))
        if not row:
            return None
        return {"id": row["id"], "name": row["name"], "phone": row["phone"] or "",
                "email": row["email"] or ""}

    def _form_data(self) -> Dict[str, Any]:
        return {
            "name": self.name_var.get().strip(),
            "party_type": self.party_type_var.get().strip(),
            "alias": self.alias_var.get().strip(),
            "address": self.address_var.get().strip(),
            "state": self.state_var.get().strip(),
            "country": self.country_var.get().strip(),
            "pincode": self.pincode_var.get().strip(),
            "contact": self.contact_var.get().strip(),
            "phone": self.mobile_var.get().strip(),
            "email": self.email_var.get().strip(),
            "opening_balance": self.opening_var.get().strip(),
            "opening_balance_type": self.opening_type_var.get().strip(),
            "credit_limit": self.credit_limit_var.get().strip(),
            "credit_days": self.credit_days_var.get().strip(),
            "is_active": self.active_var.get(),
        }

    def _parse_opening(self, raw: str) -> Optional[float]:
        try:
            return float(raw or 0)
        except Exception:
            return None

    def _clear_form(self) -> None:
        self.current_edit_id = None
        for var in (self.name_var, self.alias_var, self.address_var, self.state_var,
                    self.country_var, self.pincode_var, self.contact_var, self.mobile_var,
                    self.email_var):
            var.set("")
        self.party_type_var.set("Sundry Debtors")
        self.opening_var.set("0.00")
        self.opening_type_var.set("Debit")
        self.credit_limit_var.set("0.00")
        self.credit_days_var.set("0")
        self.active_var.set(True)
        self.tree.selection_remove(self.tree.selection())
        self._set_actions_enabled(False)
        self._set_status("Form cleared")

    def _save_party(self) -> None:
        data = self._form_data()
        if not data["name"]:
            dialogs.warn("Save Party", "Party name is required.", parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"])
        if opening is None:
            dialogs.warn("Save Party", "Opening balance must be numeric.", parent=self.parent)
            return
        if not self._ensure_group(data["party_type"]):
            dialogs.error("Save Party",
                          f"Group '{self._party_group(data['party_type'])}' does not exist. "
                          "Create it under Groups first.", parent=self.parent)
            return
        try:
            credit_limit = self._parse_opening(data["credit_limit"])
            try:
                credit_days = int(data["credit_days"] or 0)
            except ValueError:
                credit_days = 0
            account_service.create_account(
                self.company_id, data["name"], "", self._party_group(data["party_type"]),
                opening, data["opening_balance_type"],
                alias=data["alias"], address=data["address"], state=data["state"],
                country=data["country"], pincode=data["pincode"],
                contact_person=data["contact"], mobile=data["phone"], email=data["email"],
                credit_limit=credit_limit or 0.0, credit_days=credit_days,
            )
            self._upsert_legacy_party(data["name"], data["phone"], data["email"])
        except Exception as exc:
            dialogs.error("Save Party", f"Failed to save party: {exc}", parent=self.parent)
            return
        self._set_status("Party saved successfully")
        self._clear_form()
        self.refresh_parties()

    def _update_party(self) -> None:
        if self.current_edit_id is None:
            dialogs.warn("Update", "Select a party to update first.", parent=self.parent)
            return
        data = self._form_data()
        if not data["name"]:
            dialogs.warn("Update Party", "Party name is required.", parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"])
        if opening is None:
            dialogs.warn("Update Party", "Opening balance must be numeric.", parent=self.parent)
            return
        if not self._ensure_group(data["party_type"]):
            dialogs.error("Update Party",
                          f"Group '{self._party_group(data['party_type'])}' does not exist. "
                          "Create it under Groups first.", parent=self.parent)
            return
        credit_limit = self._parse_opening(data["credit_limit"])
        try:
            credit_days = int(data["credit_days"] or 0)
        except ValueError:
            credit_days = 0
        ok = account_service.update_account(
            self.current_edit_id,
            name=data["name"],
            account_group=self._party_group(data["party_type"]),
            opening_balance=opening,
            opening_balance_type=data["opening_balance_type"],
            is_active=data["is_active"],
            alias=data["alias"], address=data["address"], state=data["state"],
            country=data["country"], pincode=data["pincode"],
            contact_person=data["contact"], mobile=data["phone"], email=data["email"],
            credit_limit=credit_limit or 0.0, credit_days=credit_days,
        )
        if not ok:
            dialogs.error("Update Party", "Party not found.", parent=self.parent)
            return
        self._upsert_legacy_party(data["name"], data["phone"], data["email"])
        self._set_status("Party updated successfully")
        self._clear_form()
        self.refresh_parties()

    def _delete_party(self) -> None:
        if self.current_edit_id is None:
            dialogs.warn("Delete", "Select a party to delete.", parent=self.parent)
            return
        party = account_service.get_account(self.current_edit_id)
        if not party:
            return
        if account_service.is_account_referenced(self.current_edit_id):
            dialogs.error(
                "Delete Party",
                "Cannot delete this party because it is used in vouchers.",
                parent=self.parent,
            )
            self._set_status("Delete blocked: party is referenced in vouchers")
            return
        if not dialogs.confirm_destructive("Delete Party", "party", party['name'], parent=self.parent):
            return
        account_service.delete_account(self.current_edit_id)
        self._clear_form()
        self.refresh_parties()
        self._set_status("Party deleted successfully")

    def _ensure_group(self, party_type: str) -> bool:
        group_name = self._party_group(party_type)
        groups = group_service.list_groups(self.company_id, include_inactive=False)
        return any(g['name'] == group_name for g in groups)

    def _upsert_legacy_party(self, name: str, phone: str, email: str) -> None:
        """Keep the legacy personal ``parties`` table in sync for fallback
        report paths. Never fails the save."""
        try:
            from database.database import db
            row = db.fetch_one("SELECT id FROM parties WHERE LOWER(name) = LOWER(?)", (name,))
            if row:
                db.execute(
                    "UPDATE parties SET phone = ?, email = ? WHERE id = ?",
                    (phone, email, row["id"]),
                )
            else:
                db.execute(
                    "INSERT INTO parties (name, phone, email, opening_balance, current_balance) "
                    "VALUES (?, ?, ?, 0.0, 0.0)",
                    (name, phone, email),
                )
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.parent.update_idletasks()
        except Exception:
            pass


def show_party_master(parent: tk.Widget, company_id: int) -> PartyMasterUI:
    return PartyMasterUI(parent, company_id)
