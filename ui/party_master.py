"""
Expenzo — Party Master
Stateful party master workflow matching the finalized Company / Ledger
masters:

    Masters Hub → Parties → Party List
        Party List
            ├── + New Party (Ctrl+N)  → Create Party (separate state)
            ├── Edit (Enter)          → Edit Party (same form state)
            ├── Open / View           → View Party (read-only state)
            ├── Delete (Del)          → Delete selected (referenced-party protected)
            ├── Search (Ctrl+F)       → filter the list in the header toolbar
            ├── Refresh (F5)          → reload the list
            └── Esc                   → Masters Hub
        Create / Edit form (full-window, separate state)
            ├── Save / Update (Ctrl+S) → back to Party List (refreshed)
            ├── Save & New             → save, then blank Create form
            ├── Clear                  → reset the form
            └── Cancel / Esc           → back to Party List
        View (read-only)
            └── Back / Esc             → Party List

Parties are ledgers under the Sundry Debtors / Sundry Creditors groups in
the Chart of Accounts.  Creating a party here creates an Expenzo ledger so
party reports read the same accounting data.  The existing AccountService /
GroupService and the accounts schema are reused unchanged; no new columns
are invented.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

import config
from services.account_service import account_service
from services.group_service import group_service
from utils import dialogs

DEBTOR_GROUP = "Sundry Debtors"
CREDITOR_GROUP = "Sundry Creditors"

_PARTY_TYPES = ["Sundry Debtors", "Sundry Creditors"]
_DRCR_CHOICES = ["Debit", "Credit"]

# List columns: (id, heading, width)
_PARTY_COLUMNS: List[Dict[str, Any]] = [
    {"id": "index", "heading": "#", "width": 40, "anchor": "center", "stretch": False},
    {"id": "name", "heading": "Party Name", "width": 180, "anchor": "w", "stretch": True},
    {"id": "under", "heading": "Under", "width": 130, "anchor": "w", "stretch": False},
    {"id": "mobile", "heading": "Mobile", "width": 110, "anchor": "w", "stretch": False},
    {"id": "email", "heading": "Email", "width": 170, "anchor": "w", "stretch": True},
    {"id": "opening", "heading": "Opening Balance", "width": 120, "anchor": "e", "stretch": False},
    {"id": "drcr", "heading": "Dr/Cr", "width": 70, "anchor": "center", "stretch": False},
    {"id": "credit_days", "heading": "Credit Days", "width": 90, "anchor": "center", "stretch": False},
    {"id": "status", "heading": "Status", "width": 80, "anchor": "center", "stretch": False},
]

# Create/Edit form field definitions organised into logical sections.
_FORM_SECTIONS: List[Dict[str, Any]] = [
    {
        "title": "Primary Information",
        "fields": [
            {"label": "Party Name *", "var": "name", "kind": "entry", "width": 320},
            {"label": "Under", "var": "party_type", "kind": "combo_party", "width": 260},
            {"label": "Alias", "var": "alias", "kind": "entry", "width": 220},
        ],
    },
    {
        "title": "Contact Details",
        "fields": [
            {"label": "Contact Person", "var": "contact_person", "kind": "entry", "width": 240},
            {"label": "Mobile", "var": "mobile", "kind": "entry", "width": 180},
            {"label": "Email", "var": "email", "kind": "entry", "width": 300},
        ],
    },
    {
        "title": "Address",
        "fields": [
            {"label": "Address", "var": "address", "kind": "entry", "width": 420},
            {"label": "State", "var": "state", "kind": "entry", "width": 180},
            {"label": "Country", "var": "country", "kind": "entry", "width": 180},
            {"label": "Pincode", "var": "pincode", "kind": "entry", "width": 150},
        ],
    },
    {
        "title": "Opening Balance",
        "columns": 2,
        "fields": [
            {"label": "Opening Balance", "var": "opening_balance", "kind": "entry", "width": 150},
            {"label": "Dr / Cr", "var": "opening_balance_type", "kind": "combo_drcr", "width": 130},
        ],
    },
    {
        "title": "Credit / Payment Terms",
        "columns": 2,
        "fields": [
            {"label": "Credit Limit", "var": "credit_limit", "kind": "entry", "width": 150},
            {"label": "Credit Days", "var": "credit_days", "kind": "entry", "width": 130},
        ],
    },
]

_FIELD_DEFAULTS = {
    "party_type": "Sundry Debtors",
    "opening_balance": "0.00",
    "opening_balance_type": "Debit",
    "credit_limit": "0.00",
    "credit_days": "0",
}


class _PartyFormState:
    """Shared Create/Edit form built once and reused for both modes.

    Layout: fixed header on top, scrollable two-column form in the middle,
    fixed bottom action bar.  Only the form body scrolls; the header and the
    action bar always stay visible.
    """

    def __init__(self, owner: "PartyMasterUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.mode: Optional[str] = None  # "create" | "edit"
        self.party_id: Optional[int] = None
        self.vars: Dict[str, tk.StringVar] = {}
        self.entries: Dict[str, ctk.CTkEntry] = {}
        self._build_header()
        self._build_form()
        self._build_actions()

    # ------------------------------------------------------------------ #
    # header (fixed)
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, config.SPACING_LG))

        self.btn_back = ctk.CTkButton(
            header, text="←", width=36, height=32, corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self.owner._go_list,
        )
        self.btn_back.pack(side="left")

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(side="left", padx=(config.SPACING_MD, 0))
        self.title_label = ctk.CTkLabel(
            title_block, text="Create Party",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(
            title_block, text="Create a new debtor or creditor",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        )
        self.subtitle_label.pack(anchor="w")

    # ------------------------------------------------------------------ #
    # form body (scrollable, two-column)
    # ------------------------------------------------------------------ #
    def _build_form(self) -> None:
        body = ctk.CTkFrame(
            self.main, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.scroll = ctk.CTkScrollableFrame(
            body, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=config.COLOR_BG_TERTIARY,
        )
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=config.SPACING_LG,
                         pady=(config.SPACING_LG, config.SPACING_SM))
        self.scroll.grid_columnconfigure(0, weight=1)

        # Create the StringVars first so _form_data / enter_* can read them.
        for section in _FORM_SECTIONS:
            for field in section["fields"]:
                if field["var"] not in self.vars:
                    self.vars[field["var"]] = tk.StringVar(
                        value=_FIELD_DEFAULTS.get(field["var"], ""))

        self.section_frames: List[ctk.CTkFrame] = []
        row_index = 0
        for section in _FORM_SECTIONS:
            row_index = self._build_section(row_index, section)
        # A trailing spacer row so the last section is never glued to the
        # bottom of the scroll viewport when extra space is available.
        self.scroll.grid_rowconfigure(row_index, weight=1, minsize=config.SPACING_SM)

    def _build_section(self, row_index: int, section: Dict[str, Any]) -> int:
        section_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        section_frame.grid(row=row_index, column=0, columnspan=4, sticky="ew",
                           pady=(config.SPACING_SM, 0))
        self.section_frames.append(section_frame)

        columns = section.get("columns", 2)  # fields per row
        grid_columns = columns * 2
        for gc in range(grid_columns):
            section_frame.grid_columnconfigure(gc, weight=0 if gc % 2 == 0 else 1)
        section_frame.grid_columnconfigure(grid_columns, weight=0)

        ctk.CTkLabel(
            section_frame, text=section["title"],
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_PRIMARY,
        ).grid(row=0, column=0, columnspan=grid_columns + 1, sticky="w",
               pady=(0, config.SPACING_SM))

        fields = section["fields"]
        rows_used = (len(fields) + columns - 1) // columns
        for index, field in enumerate(fields):
            row = index // columns + 1
            gc = (index % columns) * 2
            label = ctk.CTkLabel(
                section_frame, text=field["label"],
                font=ctk.CTkFont(size=13),
                text_color=config.COLOR_TEXT_SECONDARY, anchor="w", width=150,
                height=28,
            )
            label.grid(row=row, column=gc, sticky="w", padx=(0, config.SPACING_SM),
                       pady=(config.SPACING_XS, config.SPACING_XS))
            var = self.vars[field["var"]]
            kind = field["kind"]
            if kind == "combo_party":
                widget = ctk.CTkComboBox(
                    section_frame, variable=var, width=field["width"], height=28,
                    corner_radius=config.INPUT_CORNER_RADIUS, state="readonly",
                    values=_PARTY_TYPES, command=self.owner._sync_opening_type,
                )
                self.party_type_combo = widget
            elif kind == "combo_drcr":
                widget = ctk.CTkComboBox(
                    section_frame, variable=var, width=field["width"], height=28,
                    corner_radius=config.INPUT_CORNER_RADIUS, state="readonly",
                    values=_DRCR_CHOICES,
                )
            else:
                widget = ctk.CTkEntry(
                    section_frame, textvariable=var, width=field["width"],
                    height=28, corner_radius=config.INPUT_CORNER_RADIUS,
                )
            widget.grid(row=row, column=gc + 1, sticky="w", padx=(0, config.SPACING_LG),
                        pady=(config.SPACING_XS, config.SPACING_XS))
            self.entries[field["var"]] = widget

        return row_index + rows_used + 1

    # ------------------------------------------------------------------ #
    # bottom action bar (fixed)
    # ------------------------------------------------------------------ #
    def _build_actions(self) -> None:
        bar = ctk.CTkFrame(self.main, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(config.SPACING_SM, 0))
        bar.grid_columnconfigure(0, weight=1)

        # Feedback message shown above the action buttons (hidden when empty).
        self.message_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=12), anchor="w", justify="left",
            wraplength=1100, height=24,
        )
        self.message_label.grid(row=0, column=0, sticky="ew")

        buttons = ctk.CTkFrame(bar, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew")

        self.btn_save = ctk.CTkButton(
            buttons, text="Save", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_party,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_save_new = ctk.CTkButton(
            buttons, text="Save & New", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_and_new,
        )
        self.btn_save_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._update_party,
        )
        self.btn_clear = ctk.CTkButton(
            buttons, text="Clear", width=100, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._clear_form,
        )
        self.btn_clear.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_cancel = ctk.CTkButton(
            buttons, text="Cancel", width=100, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._go_list,
        )
        self.btn_cancel.pack(side="left")

        hint = ctk.CTkLabel(
            buttons, text="   ".join(f"{key} {label}" for key, label in [
                ("Ctrl+S", "Save / Update"), ("Esc", "Cancel / Back"),
            ]),
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED, anchor="e",
        )
        hint.pack(side="right")

    # ------------------------------------------------------------------ #
    # mode switching (shared component reused for create and edit)
    # ------------------------------------------------------------------ #
    def _set_actions_for_mode(self, mode: str) -> None:
        self.mode = mode
        if mode == "edit":
            self.btn_update.pack(side="left", padx=(0, config.SPACING_SM))
            self.btn_save.pack_forget()
            self.btn_save_new.pack_forget()
        else:
            self.btn_update.pack_forget()
            self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
            self.btn_save_new.pack(side="left", padx=(0, config.SPACING_SM))

    def enter_create(self) -> None:
        self.mode = "create"
        self.party_id = None
        self.title_label.configure(text="Create Party")
        self.subtitle_label.configure(text="Create a new debtor or creditor")
        self._reset_fields()
        self._set_actions_for_mode("create")
        self._set_error("")
        self._set_success("")

    def enter_edit(self, party: Dict[str, Any]) -> None:
        self.mode = "edit"
        self.party_id = party["id"]
        self.title_label.configure(text="Edit Party")
        self.subtitle_label.configure(text=f"Edit Party: {party.get('name', '')}")
        self.vars["name"].set(party.get("name", ""))
        self.vars["party_type"].set(self.owner._party_type_for_group(
            party.get("account_group", "")))
        self.vars["alias"].set(party.get("alias", ""))
        self.vars["address"].set(party.get("address", ""))
        self.vars["state"].set(party.get("state", ""))
        self.vars["country"].set(party.get("country", ""))
        self.vars["pincode"].set(party.get("pincode", ""))
        self.vars["contact_person"].set(party.get("contact_person", ""))
        self.vars["mobile"].set(party.get("mobile", ""))
        self.vars["email"].set(party.get("email", ""))
        self.vars["opening_balance"].set(
            f"{float(party.get('opening_balance', 0.0) or 0.0):.2f}")
        self.vars["opening_balance_type"].set(
            party.get("opening_balance_type", "Debit") or "Debit")
        self.vars["credit_limit"].set(
            f"{float(party.get('credit_limit', 0.0) or 0.0):.2f}")
        self.vars["credit_days"].set(str(int(party.get("credit_days", 0) or 0)))
        # Legacy party table fallback for phone/email.
        legacy = self.owner._find_legacy_party(party.get("name", ""))
        if legacy:
            if not self.vars["mobile"].get():
                self.vars["mobile"].set(legacy.get("phone", ""))
            if not self.vars["email"].get():
                self.vars["email"].set(legacy.get("email", ""))
        self._set_actions_for_mode("edit")
        self._set_error("")
        self._set_success("")

    def clear(self) -> None:
        self.enter_create()

    def _reset_fields(self) -> None:
        for var_name, var in self.vars.items():
            var.set(_FIELD_DEFAULTS.get(var_name, ""))

    def _set_error(self, message: str) -> None:
        self.message_label.configure(text=message, text_color=config.COLOR_EXPENSE)

    def _set_success(self, message: str) -> None:
        self.message_label.configure(text=message, text_color=config.COLOR_INCOME)

    def is_visible(self) -> bool:
        try:
            return bool(self.main.winfo_manager())
        except Exception:
            return False


class _PartyViewState:
    """Read-only party details state."""

    def __init__(self, owner: "PartyMasterUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_card()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, config.SPACING_LG))
        self.btn_back = ctk.CTkButton(
            header, text="←", width=36, height=32, corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self.owner._go_list,
        )
        self.btn_back.pack(side="left")
        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(side="left", padx=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            title_block, text="View Party",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Party details (read-only)",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

    def _build_card(self) -> None:
        card = ctk.CTkFrame(
            self.main, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew", padx=config.SPACING_LG,
                    pady=config.SPACING_LG)

        self.value_labels: Dict[str, ctk.CTkLabel] = {}
        row_index = 0
        for section in _FORM_SECTIONS:
            columns = section.get("columns", 2)
            grid_columns = columns * 2
            ctk.CTkLabel(
                scroll, text=section["title"], font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLOR_PRIMARY,
            ).grid(row=row_index, column=0, columnspan=grid_columns + 1, sticky="w",
                   pady=(config.SPACING_MD, config.SPACING_XS))
            row_index += 1
            for field in section["fields"]:
                gc = (row_index % 2) * 2
                ctk.CTkLabel(
                    scroll, text=field["label"], font=ctk.CTkFont(size=12),
                    text_color=config.COLOR_TEXT_SECONDARY, width=160, anchor="w",
                ).grid(row=row_index // 2 + 1, column=gc, sticky="w",
                       padx=(0, config.SPACING_SM), pady=config.SPACING_XS)
                value = ctk.CTkLabel(
                    scroll, text="", font=ctk.CTkFont(size=13), anchor="w",
                    justify="left", wraplength=380,
                )
                value.grid(row=row_index // 2 + 1, column=gc + 1, sticky="ew",
                           padx=(0, config.SPACING_LG), pady=config.SPACING_XS)
                self.value_labels[field["var"]] = value
                row_index += 1

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=config.SPACING_LG,
                     pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_back_full = ctk.CTkButton(
            buttons, text="Back", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._go_list,
        )
        self.btn_back_full.pack(side="left")

    def show(self, party: Dict[str, Any]) -> None:
        mapping = {
            "name": party.get("name", ""),
            "party_type": self.owner._party_type_for_group(party.get("account_group", "")),
            "alias": party.get("alias", ""),
            "contact_person": party.get("contact_person", ""),
            "mobile": party.get("mobile", ""),
            "email": party.get("email", ""),
            "address": party.get("address", ""),
            "state": party.get("state", ""),
            "country": party.get("country", ""),
            "pincode": party.get("pincode", ""),
            "opening_balance": f"{float(party.get('opening_balance', 0.0) or 0.0):,.2f}",
            "opening_balance_type": party.get("opening_balance_type", "Debit"),
            "credit_limit": f"{float(party.get('credit_limit', 0.0) or 0.0):,.2f}",
            "credit_days": str(int(party.get("credit_days", 0) or 0)),
        }
        for key, label in self.value_labels.items():
            label.configure(text=mapping.get(key, ""))

    def is_visible(self) -> bool:
        try:
            return bool(self.main.winfo_manager())
        except Exception:
            return False


class _PartyListState:
    """Party List: the primary management screen."""

    def __init__(self, owner: "PartyMasterUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", owner._apply_search)
        self.show_inactive_var = tk.BooleanVar(value=False)
        self.selected_id: Optional[int] = None

        self._build_header()
        self._build_list_card()
        self._build_status_line()

    # ------------------------------------------------------------------ #
    # header (fixed): title + toolbar with every important action visible
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, config.SPACING_LG))
        header.grid_columnconfigure(1, weight=1)

        self.btn_back = ctk.CTkButton(
            header, text="←", width=36, height=32, corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self.owner._back_to_hub,
        )
        self.btn_back.grid(row=0, column=0, sticky="w")

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=1, sticky="w", padx=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            title_block, text="Party Master",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Debtors & Creditors",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e")
        self.btn_new = ctk.CTkButton(
            actions, text="+ New Party", width=120, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF", command=self.owner._go_create,
        )
        self.btn_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_edit_toolbar = ctk.CTkButton(
            actions, text="Edit", width=70, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._edit_selected,
        )
        self.btn_edit_toolbar.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_delete_toolbar = ctk.CTkButton(
            actions, text="Delete", width=80, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_EXPENSE, hover_color=config.COLOR_EXPENSE_HOVER,
            command=self.owner._delete_party,
        )
        self.btn_delete_toolbar.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_view_toolbar = ctk.CTkButton(
            actions, text="Open / View", width=100, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._view_selected,
        )
        self.btn_view_toolbar.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_refresh = ctk.CTkButton(
            actions, text="Refresh", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner.refresh_parties,
        )
        self.btn_refresh.pack(side="left")

        # Search + Inactive filter sit directly in the header toolbar, visible.
        search_box = ctk.CTkFrame(header, fg_color="transparent")
        search_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(config.SPACING_SM, 0))
        search_box.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(
            search_box, textvariable=self.search_var, height=32,
            corner_radius=config.INPUT_CORNER_RADIUS,
            placeholder_text="Search parties…",
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            search_box, text="Ctrl+F", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).grid(row=0, column=1, padx=(config.SPACING_SM, 0))
        ctk.CTkCheckBox(
            search_box, text="Inactive", variable=self.show_inactive_var,
            command=self.owner.refresh_parties, font=ctk.CTkFont(size=12),
        ).grid(row=0, column=2, padx=(config.SPACING_MD, 0))

    # ------------------------------------------------------------------ #
    # list card — the primary content, given full space
    # ------------------------------------------------------------------ #
    def _build_list_card(self) -> None:
        card = ctk.CTkFrame(
            self.main, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=config.SPACING_LG,
                 pady=(config.SPACING_MD, config.SPACING_SM))
        self.list_title = ctk.CTkLabel(
            top, text="Parties (0)", font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.list_title.pack(side="left")
        ctk.CTkLabel(
            top, text="Select a party to edit, view or delete",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=config.SPACING_LG,
                        pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame, columns=[c["id"] for c in _PARTY_COLUMNS],
            show="headings", selectmode="browse",
        )
        for col in _PARTY_COLUMNS:
            self.tree.heading(col["id"], text=col["heading"])
            self.tree.column(col["id"], width=col["width"], anchor=col["anchor"],
                             stretch=col.get("stretch", True), minwidth=40)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.owner._on_select)
        self.tree.bind("<Return>", self.owner._on_enter_pressed)
        self.tree.bind("<Double-1>", self.owner._on_double_click)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=config.SPACING_LG,
                    pady=(0, config.SPACING_SM))
        self.page_label = ctk.CTkLabel(
            footer, text="Showing 0 to 0 of 0 parties",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        )
        self.page_label.pack(side="left")

        self.action_row = ctk.CTkFrame(card, fg_color="transparent")
        self.action_row.grid(row=3, column=0, sticky="ew", padx=config.SPACING_LG,
                             pady=(0, config.SPACING_LG))
        self.btn_edit = ctk.CTkButton(
            self.action_row, text="Edit (Enter)", width=120, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._edit_selected,
        )
        self.btn_edit.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_delete = ctk.CTkButton(
            self.action_row, text="Delete (Del)", width=120, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_EXPENSE, hover_color=config.COLOR_EXPENSE_HOVER,
            command=self.owner._delete_party,
        )
        self.btn_delete.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_view = ctk.CTkButton(
            self.action_row, text="View", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._view_selected,
        )
        self.btn_view.pack(side="left")
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_delete.configure(state=state)
        self.btn_view.configure(state=state)
        self.btn_edit_toolbar.configure(state=state)
        self.btn_delete_toolbar.configure(state=state)
        self.btn_view_toolbar.configure(state=state)

    # ------------------------------------------------------------------ #
    # compact status line (never competes with the table for space)
    # ------------------------------------------------------------------ #
    def _build_status_line(self) -> None:
        bar = ctk.CTkFrame(self.main, fg_color=config.COLOR_BG_SECONDARY,
                           corner_radius=config.CARD_CORNER_RADIUS,
                           border_width=1, border_color=config.COLOR_CARD_BORDER)
        bar.grid(row=2, column=0, sticky="ew", pady=(config.SPACING_MD, 0))
        self.status_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w", justify="left",
        )
        self.status_label.pack(side="left", padx=config.SPACING_LG, pady=config.SPACING_SM,
                               fill="x", expand=True)

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def is_visible(self) -> bool:
        try:
            return bool(self.main.winfo_manager())
        except Exception:
            return False


class PartyMasterUI:
    """Stateful Party Management container (List → Create/Edit/View)."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = int(company_id)
        self.parties: List[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # The three states are built once and reused — never duplicated.
        self.form = _PartyFormState(self)
        self.view = _PartyViewState(self)
        self.list = _PartyListState(self)

        self._show_state(self.list)
        self.refresh_parties()

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _party_group(self, party_type: str) -> str:
        return DEBTOR_GROUP if party_type == "Sundry Debtors" else CREDITOR_GROUP

    def _party_type_for_group(self, group: str) -> str:
        return "Sundry Debtors" if group == DEBTOR_GROUP else "Sundry Creditors"

    def _sync_opening_type(self, *args) -> None:
        # Debtors default to Debit opening; creditors to Credit opening.
        if self.form.vars["party_type"].get() == "Sundry Debtors":
            self.form.vars["opening_balance_type"].set("Debit")
        else:
            self.form.vars["opening_balance_type"].set("Credit")

    # ------------------------------------------------------------------ #
    # state switching (swap in place, no duplicate widgets)
    # ------------------------------------------------------------------ #
    def _show_state(self, state) -> None:
        for candidate in (self.list, self.form, self.view):
            if candidate.is_visible():
                candidate.main.grid_forget()
        state.main.grid(row=1, column=0, sticky="nsew")
        state.main.lift()

    # ------------------------------------------------------------------ #
    # navigation
    # ------------------------------------------------------------------ #
    def _go_list(self) -> None:
        self.refresh_parties()
        self._show_state(self.list)

    def _go_create(self) -> None:
        self.form.enter_create()
        self._show_state(self.form)

    def _go_edit(self) -> None:
        party = account_service.get_account(self._selected_id())
        if party:
            self.form.enter_edit(party)
            self._show_state(self.form)

    def _go_view(self) -> None:
        party = account_service.get_account(self._selected_id())
        if party:
            self.view.show(party)
            self._show_state(self.view)

    def _back_to_hub(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _selected_id(self) -> int:
        selection = self.list.tree.selection()
        if not selection:
            return -1
        return int(selection[0])

    # ------------------------------------------------------------------ #
    # keyboard hooks (dispatched per active state by the global manager)
    # ------------------------------------------------------------------ #
    def on_keyboard_save(self) -> None:
        if self.form.is_visible():
            if self.form.mode == "edit":
                self._update_party()
            else:
                self._save_party()

    def on_keyboard_new(self) -> None:
        if self.list.is_visible():
            self._go_create()

    def on_keyboard_refresh(self) -> None:
        if self.list.is_visible():
            self.refresh_parties()

    def on_keyboard_search(self) -> None:
        if self.list.is_visible():
            self._focus_search()

    def on_keyboard_delete(self) -> None:
        if self.list.is_visible() and self.list.tree.selection():
            self._delete_party()

    def on_keyboard_back(self) -> None:
        """Esc routing: form/view → list; list → hub (never exits the app)."""
        if self.form.is_visible():
            self._go_list()
        elif self.view.is_visible():
            self._go_list()
        elif self.list.is_visible():
            self._back_to_hub()

    def handle_escape(self) -> bool:
        """Called by the Masters hub's Esc handler.

        Returns True when this screen consumed the Esc internally (form or
        view returns to the list).  Returns False in the List state so the
        hub closes this screen and shows the Masters Hub.
        """
        if self.form.is_visible() or self.view.is_visible():
            self._go_list()
            return True
        return False

    # ------------------------------------------------------------------ #
    # list data
    # ------------------------------------------------------------------ #
    def refresh_parties(self) -> None:
        groups = {DEBTOR_GROUP, CREDITOR_GROUP}
        self.parties = [
            p for p in account_service.search_accounts(
                self.company_id, self.list.search_var.get().strip(),
                include_inactive=self.list.show_inactive_var.get())
            if p.get('account_group') in groups
        ]
        self._render_rows()
        self.list.set_status(f"Loaded {len(self.parties)} parties")

    def _render_rows(self) -> None:
        total = len(self.parties)
        self.list.list_title.configure(text=f"Parties ({total})")
        for item in self.list.tree.get_children():
            self.list.tree.delete(item)
        for index, party in enumerate(self.parties):
            pid = party.get("id")
            opening = float(party.get("opening_balance", 0.0) or 0.0)
            status = "Active" if party.get("is_active", True) else "Inactive"
            self.list.tree.insert("", tk.END, iid=str(pid), values=(
                index + 1,
                party.get("name", ""),
                self._party_type_for_group(party.get("account_group", "")),
                party.get("mobile", ""),
                party.get("email", ""),
                f"{opening:,.2f}",
                party.get("opening_balance_type", "Debit"),
                str(int(party.get("credit_days", 0) or 0)),
                status,
            ), tags=('even' if index % 2 == 0 else 'odd',))
        self.list.page_label.configure(
            text=f"Showing {1 if total else 0} to {total} of {total} parties")
        if self.list.selected_id is not None:
            try:
                self.list.tree.selection_set(str(self.list.selected_id))
            except Exception:
                pass

    def _apply_search(self, *args) -> None:
        self.refresh_parties()

    def _on_select(self, event=None) -> None:
        selection = self.list.tree.selection()
        if not selection:
            self.list._set_actions_enabled(False)
            self.list.selected_id = None
            return
        self.list.selected_id = int(selection[0])
        self.list._set_actions_enabled(True)

    def _on_enter_pressed(self, event=None) -> None:
        if self.list.tree.selection():
            self._edit_selected()

    def _on_double_click(self, event=None) -> None:
        if self.list.tree.selection():
            self._view_selected()

    def _focus_search(self) -> None:
        try:
            self.list.search_entry.focus_set()
            self.list.search_entry.select_range(0, "end")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def _edit_selected(self) -> None:
        if not self.list.tree.selection():
            dialogs.warn("Edit", "Select a party to edit.", parent=self.parent)
            return
        self._go_edit()

    def _view_selected(self) -> None:
        if not self.list.tree.selection():
            dialogs.warn("View", "Select a party to view.", parent=self.parent)
            return
        self._go_view()

    def _delete_party(self) -> None:
        party_id = self._selected_id()
        if party_id < 0:
            dialogs.warn("Delete", "Select a party to delete.", parent=self.parent)
            return
        party = account_service.get_account(party_id)
        if not party:
            return
        if account_service.is_account_referenced(party_id):
            dialogs.error(
                "Delete Party",
                "Cannot delete this party because it is used in vouchers.",
                parent=self.parent,
            )
            self.list.set_status("Delete blocked: party is referenced in vouchers")
            return
        if not dialogs.confirm_destructive("Delete Party", "party", party.get("name", ""), parent=self.parent):
            return
        account_service.delete_account(party_id)
        self.list.selected_id = None
        self.list.set_status(f"Party '{party.get('name', '')}' deleted successfully")
        self.refresh_parties()

    def _clear_form(self) -> None:
        self.form.clear()
        self.form._set_success("Form cleared")

    # ------------------------------------------------------------------ #
    # legacy party table sync (unchanged behaviour)
    # ------------------------------------------------------------------ #
    def _find_legacy_party(self, name: str) -> Optional[Dict[str, Any]]:
        try:
            return self._db_fetch_party(name)
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

    def _ensure_group(self, party_type: str) -> bool:
        group_name = self._party_group(party_type)
        groups = group_service.list_groups(self.company_id, include_inactive=False)
        return any(g['name'] == group_name for g in groups)

    # ------------------------------------------------------------------ #
    # form data + persistence
    # ------------------------------------------------------------------ #
    def _form_data(self) -> Dict[str, Any]:
        v = self.form.vars
        return {
            "name": v["name"].get().strip(),
            "party_type": v["party_type"].get().strip(),
            "alias": v["alias"].get().strip(),
            "address": v["address"].get().strip(),
            "state": v["state"].get().strip(),
            "country": v["country"].get().strip(),
            "pincode": v["pincode"].get().strip(),
            "contact": v["contact_person"].get().strip(),
            "phone": v["mobile"].get().strip(),
            "email": v["email"].get().strip(),
            "opening_balance": v["opening_balance"].get().strip() or "0",
            "opening_balance_type": v["opening_balance_type"].get().strip() or "Debit",
            "credit_limit": v["credit_limit"].get().strip() or "0",
            "credit_days": v["credit_days"].get().strip() or "0",
        }

    def _parse_opening(self, raw: str) -> Optional[float]:
        try:
            return float(raw or 0)
        except Exception:
            return None

    def _validate_party(self, data: Dict[str, Any]) -> Optional[str]:
        if not data["name"]:
            return "Party name is required."
        if self._parse_opening(data["opening_balance"]) is None:
            return "Opening balance must be numeric."
        if self._parse_opening(data["credit_limit"]) is None:
            return "Credit limit must be numeric."
        return None

    def _save_party(self) -> None:
        data = self._form_data()
        error = self._validate_party(data)
        if error:
            self.form._set_error(error)
            dialogs.warn("Save Party", error, parent=self.parent)
            return
        if not self._ensure_group(data["party_type"]):
            message = (f"Group '{self._party_group(data['party_type'])}' does not exist. "
                       "Create it under Groups first.")
            self.form._set_error(message)
            dialogs.error("Save Party", message, parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"]) or 0.0
        try:
            credit_limit = self._parse_opening(data["credit_limit"]) or 0.0
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
                credit_limit=credit_limit, credit_days=credit_days,
            )
            self._upsert_legacy_party(data["name"], data["phone"], data["email"])
        except Exception as exc:
            self.form._set_error(f"Failed to save party: {exc}")
            dialogs.error("Save Party", f"Failed to save party: {exc}", parent=self.parent)
            return
        self.list.set_status(f"✓ Party '{data['name']}' created successfully.")
        self._go_list()

    def _save_and_new(self) -> None:
        data = self._form_data()
        error = self._validate_party(data)
        if error:
            self.form._set_error(error)
            dialogs.warn("Save Party", error, parent=self.parent)
            return
        if not self._ensure_group(data["party_type"]):
            message = (f"Group '{self._party_group(data['party_type'])}' does not exist. "
                       "Create it under Groups first.")
            self.form._set_error(message)
            dialogs.error("Save Party", message, parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"]) or 0.0
        try:
            credit_limit = self._parse_opening(data["credit_limit"]) or 0.0
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
                credit_limit=credit_limit, credit_days=credit_days,
            )
            self._upsert_legacy_party(data["name"], data["phone"], data["email"])
        except Exception as exc:
            self.form._set_error(f"Failed to save party: {exc}")
            dialogs.error("Save Party", f"Failed to save party: {exc}", parent=self.parent)
            return
        self.form.enter_create()
        self.form._set_success(f"✓ Party '{data['name']}' created successfully.")
        self.list.set_status(f"Party '{data['name']}' created successfully.")

    def _update_party(self) -> None:
        party_id = self.form.party_id
        if party_id is None:
            dialogs.warn("Update", "Select a party to update first.", parent=self.parent)
            return
        data = self._form_data()
        error = self._validate_party(data)
        if error:
            self.form._set_error(error)
            dialogs.warn("Update Party", error, parent=self.parent)
            return
        if not self._ensure_group(data["party_type"]):
            message = (f"Group '{self._party_group(data['party_type'])}' does not exist. "
                       "Create it under Groups first.")
            self.form._set_error(message)
            dialogs.error("Update Party", message, parent=self.parent)
            return
        opening = self._parse_opening(data["opening_balance"]) or 0.0
        try:
            credit_limit = self._parse_opening(data["credit_limit"]) or 0.0
            try:
                credit_days = int(data["credit_days"] or 0)
            except ValueError:
                credit_days = 0
            ok = account_service.update_account(
                party_id,
                name=data["name"],
                account_group=self._party_group(data["party_type"]),
                opening_balance=opening,
                opening_balance_type=data["opening_balance_type"],
                is_active=True,
                alias=data["alias"], address=data["address"], state=data["state"],
                country=data["country"], pincode=data["pincode"],
                contact_person=data["contact"], mobile=data["phone"], email=data["email"],
                credit_limit=credit_limit, credit_days=credit_days,
            )
        except Exception as exc:
            self.form._set_error(f"Failed to update party: {exc}")
            dialogs.error("Update Party", f"Failed to update party: {exc}", parent=self.parent)
            return
        if not ok:
            self.form._set_error("Party not found.")
            dialogs.error("Update Party", "Party not found.", parent=self.parent)
            return
        self._upsert_legacy_party(data["name"], data["phone"], data["email"])
        self.list.set_status(f"✓ Party '{data['name']}' updated successfully.")
        self._go_list()


def show_party_master(parent: tk.Widget, company_id: int) -> PartyMasterUI:
    return PartyMasterUI(parent, company_id)
