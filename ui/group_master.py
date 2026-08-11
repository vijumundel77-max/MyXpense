"""
Expenzo — Group Master
Chart of Accounts group management: create/edit/delete groups with a
parent hierarchy (Under), Tally-style flags, and the 30 default groups
seeded idempotently for the current company.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.group_service import group_service, GroupService
from utils import dialogs

ALLOCATION_METHODS = [
    "Proportional to Quantity",
    "Proportional to Value",
    "Equal Distribution",
    "First-in-First-out",
    "Last-in-First-out",
]


class GroupMasterUI:
    """Groups master screen."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_edit_id: Optional[int] = None
        self.groups: List[Dict[str, Any]] = []

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
        self.refresh_groups()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            header, text="Groups", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="Chart of Accounts groups",
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
        ctk.CTkLabel(top, text="Group List", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
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
            command=self.refresh_groups, font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(config.SPACING_SM, 0))
        ctk.CTkLabel(
            search_row, text="Ctrl+F to search", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_SM, 0))

        tree_frame = ctk.CTkFrame(pane, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("name", "under")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("name", "Group Name", 180),
            ("under", "Under", 140),
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
            command=self._delete_group,
        )
        self.btn_delete.pack(side="left")
        self._set_actions_enabled(False)

    def _build_form_pane(self) -> None:
        pane = ctk.CTkFrame(
            self.body, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        pane.grid(row=0, column=1, sticky="nsew", padx=(config.SPACING_MD, 0))

        self.form_title = ctk.CTkLabel(
            pane, text="Create Group", font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.form_title.pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))

        fields = ctk.CTkFrame(pane, fg_color="transparent")
        fields.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        self.name_var = tk.StringVar()
        self.parent_var = tk.StringVar(value="(None)")
        self.sub_ledger_var = tk.BooleanVar(value=False)
        self.net_balance_var = tk.BooleanVar(value=False)
        self.used_for_calc_var = tk.BooleanVar(value=False)
        self.allocation_var = tk.StringVar(value=ALLOCATION_METHODS[0])

        self._label(fields, 0, "Name *")
        ctk.CTkEntry(fields, textvariable=self.name_var, width=240,
                     corner_radius=config.INPUT_CORNER_RADIUS).grid(
            row=0, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 1, "Under")
        self.parent_combo = ctk.CTkComboBox(
            fields, values=[], variable=self.parent_var, width=240, state="readonly")
        self.parent_combo.grid(row=1, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 2, "Group behaves like a sub-ledger")
        ctk.CTkCheckBox(fields, text="Yes", variable=self.sub_ledger_var,
                        font=ctk.CTkFont(size=12)).grid(
            row=2, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 3, "Nett Debit/Credit Balances for Reporting")
        ctk.CTkCheckBox(fields, text="Yes", variable=self.net_balance_var,
                        font=ctk.CTkFont(size=12)).grid(
            row=3, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 4, "Used for calculation (e.g. taxes, discounts)")
        ctk.CTkCheckBox(fields, text="Yes", variable=self.used_for_calc_var,
                        font=ctk.CTkFont(size=12)).grid(
            row=4, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        self._label(fields, 5, "Method to allocate when used in purchase invoice")
        ctk.CTkComboBox(
            fields, values=ALLOCATION_METHODS, variable=self.allocation_var,
            width=220, state="readonly").grid(
            row=5, column=1, padx=config.SPACING_XS, pady=config.SPACING_XS, sticky="w")

        buttons = ctk.CTkFrame(pane, fg_color="transparent")
        buttons.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_save = ctk.CTkButton(
            buttons, text="Save / Accept", width=120, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._save_group,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=90, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._update_group,
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
        self._set_status("Creating a new group")

    def _edit_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            dialogs.warn("Edit", "Select a group to edit.", parent=self.parent)
            return
        self._on_select()

    def _cancel_form(self) -> None:
        self._clear_form()
        self._set_status("Cancelled")

    # ------------------------------------------------------------------ #
    # keyboard hooks (invoked by the global shortcut manager via the hub)
    # ------------------------------------------------------------------ #
    def on_keyboard_save(self) -> None:
        if self.current_edit_id is None:
            self._save_group()
        else:
            self._update_group()

    def on_keyboard_new(self) -> None:
        self._clear_form()

    def on_keyboard_refresh(self) -> None:
        self.refresh_groups()

    def on_keyboard_search(self) -> None:
        from utils.keyboard import _focus_search
        _focus_search(self)

    def on_keyboard_delete(self) -> None:
        if self.tree.selection():
            self._delete_group()

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def refresh_groups(self) -> None:
        # Ensure the 30 default groups exist for this company (idempotent).
        group_service.seed_default_groups(self.company_id)
        self.groups = group_service.group_tree(
            self.company_id, self.search_var.get().strip(),
            include_inactive=self.show_inactive_var.get())
        self._render_rows()
        self._update_parent_combo()
        self._set_status(f"Loaded {len(self.groups)} groups")

    def _update_parent_combo(self) -> None:
        values = ["(None)"] + [f"{g['display_name']}  (ID {g['id']})" for g in self.groups]
        self.parent_combo.configure(values=values)

    def _render_rows(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, group in enumerate(self.groups):
            parent_id = group.get('parent_id')
            parent_name = next(
                (g['name'] for g in self.groups if g['id'] == parent_id), "")
            self.tree.insert("", tk.END, iid=str(group['id']), values=(
                group.get('display_name', group.get('name', '')),
                parent_name,
            ), tags=('even' if index % 2 == 0 else 'odd',))

    def _apply_search(self, *args) -> None:
        self.refresh_groups()

    def _on_select(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self._set_actions_enabled(False)
            return
        self._set_actions_enabled(True)
        group = group_service.get_group(int(selection[0]))
        if not group:
            return
        self.current_edit_id = group['id']
        self.form_title.configure(text="Edit Group")
        self.name_var.set(group.get('name', ''))
        self.sub_ledger_var.set(bool(group.get('behaves_like_sub_ledger', False)))
        self.net_balance_var.set(bool(group.get('net_balance_for_reporting', False)))
        self.used_for_calc_var.set(bool(group.get('used_for_calculation', False)))
        self.allocation_var.set(group.get('allocation_method', '') or ALLOCATION_METHODS[0])
        parent_id = group.get('parent_id')
        if parent_id:
            parent = group_service.get_group(parent_id)
            self.parent_var.set(f"{parent['name']}  (ID {parent['id']})" if parent else "(None)")
        else:
            self.parent_var.set("(None)")
        self._set_status(f"Editing group: {group['name']}")

    def _form_data(self) -> Dict[str, Any]:
        parent_text = self.parent_var.get().strip()
        parent_id = None
        if parent_text != "(None)":
            try:
                parent_id = int(parent_text.rsplit("ID ", 1)[1].rstrip(")"))
            except Exception:
                parent_id = None
        return {
            "name": self.name_var.get().strip(),
            "parent_id": parent_id,
            "behaves_like_sub_ledger": self.sub_ledger_var.get(),
            "net_balance_for_reporting": self.net_balance_var.get(),
            "used_for_calculation": self.used_for_calc_var.get(),
            "allocation_method": self.allocation_var.get().strip(),
        }

    def _clear_form(self) -> None:
        self.current_edit_id = None
        self.form_title.configure(text="Create Group")
        self.name_var.set("")
        self.parent_var.set("(None)")
        self.sub_ledger_var.set(False)
        self.net_balance_var.set(False)
        self.used_for_calc_var.set(False)
        self.allocation_var.set(ALLOCATION_METHODS[0])
        self.tree.selection_remove(self.tree.selection())
        self._set_actions_enabled(False)
        self._set_status("Form cleared")

    def _save_group(self) -> None:
        data = self._form_data()
        group_type = "Assets"
        parent = group_service.get_group(data["parent_id"]) if data["parent_id"] else None
        if parent:
            group_type = parent.get("group_type", "Assets")
        ok, message, _ = group_service.create_group(
            self.company_id, data["name"], group_type, data["parent_id"], True,
            data["behaves_like_sub_ledger"], data["net_balance_for_reporting"],
            data["used_for_calculation"], data["allocation_method"],
        )
        if not ok:
            dialogs.error("Save Group", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._clear_form()
        self.refresh_groups()

    def _update_group(self) -> None:
        if self.current_edit_id is None:
            dialogs.warn("Update", "Select a group to update first.", parent=self.parent)
            return
        data = self._form_data()
        group_type = "Assets"
        parent = group_service.get_group(data["parent_id"]) if data["parent_id"] else None
        if parent:
            group_type = parent.get("group_type", "Assets")
        else:
            existing = group_service.get_group(self.current_edit_id)
            group_type = existing.get("group_type", "Assets") if existing else "Assets"
        existing = group_service.get_group(self.current_edit_id)
        is_active = bool(existing.get("is_active", True)) if existing else True
        ok, message = group_service.update_group(
            self.current_edit_id, data["name"], group_type, data["parent_id"], is_active,
            data["behaves_like_sub_ledger"], data["net_balance_for_reporting"],
            data["used_for_calculation"], data["allocation_method"],
        )
        if not ok:
            dialogs.error("Update Group", message, parent=self.parent)
            self._set_status(message)
            return
        self._set_status(message)
        self._clear_form()
        self.refresh_groups()

    def _delete_group(self) -> None:
        if self.current_edit_id is None:
            dialogs.warn("Delete", "Select a group to delete.", parent=self.parent)
            return
        group = group_service.get_group(self.current_edit_id)
        if not group:
            return
        if not dialogs.confirm_destructive("Delete Group", "group", group['name'], parent=self.parent):
            return
        ok, message = group_service.delete_group(self.current_edit_id)
        if not ok:
            dialogs.error("Delete Group", message, parent=self.parent)
            self._set_status(message)
            return
        self._clear_form()
        self.refresh_groups()
        self._set_status(message)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.parent.update_idletasks()
        except Exception:
            pass


def show_group_master(parent: tk.Widget, company_id: int) -> GroupMasterUI:
    return GroupMasterUI(parent, company_id)
