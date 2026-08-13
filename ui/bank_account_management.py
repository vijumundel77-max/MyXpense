"""
Expenzo — Bank Account Management
Stateful bank account master workflow matching the finalized Company /
Ledger masters:

    Masters Hub → Bank Accounts → Bank Account List
        Bank Account List
            ├── + New Bank Account (Ctrl+N) → Create Bank Account (separate state)
            ├── Edit (Enter)               → Edit Bank Account (same form state)
            ├── Open / View                → View Bank Account (read-only state)
            ├── Delete (Del)               → Delete selected (referenced-account protected)
            ├── Search (Ctrl+F)            → filter the list in the header toolbar
            ├── Refresh (F5)               → reload the list
            └── Esc                        → Masters Hub
        Create / Edit form (full-window, separate state)
            ├── Save / Update (Ctrl+S)     → back to Bank Account List (refreshed)
            ├── Save & New                 → save, then blank Create form
            ├── Clear                      → reset the form
            └── Cancel / Esc               → back to Bank Account List
        View (read-only)
            └── Back / Esc                 → Bank Account List

Bank accounts are scoped to the currently selected company; the company id
is always the explicit id passed in (never silently defaulted).  The
existing BankAccountService and bank_accounts schema are reused unchanged.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.bank_account_service import bank_account_service
from utils import dialogs

ACCOUNT_TYPES = ["Savings", "Current"]
_DRCR_CHOICES = ["Debit", "Credit"]

# List columns: (id, heading, width)
_BANK_COLUMNS: List[Dict[str, Any]] = [
    {"id": "index", "heading": "#", "width": 40, "anchor": "center", "stretch": False},
    {"id": "bank", "heading": "Bank Name", "width": 170, "anchor": "w", "stretch": True},
    {"id": "account_name", "heading": "Account Name", "width": 170, "anchor": "w", "stretch": True},
    {"id": "number", "heading": "Account Number", "width": 130, "anchor": "w", "stretch": False},
    {"id": "type", "heading": "Account Type", "width": 100, "anchor": "center", "stretch": False},
    {"id": "opening", "heading": "Opening Balance", "width": 120, "anchor": "e", "stretch": False},
    {"id": "drcr", "heading": "Dr/Cr", "width": 70, "anchor": "center", "stretch": False},
    {"id": "status", "heading": "Status", "width": 80, "anchor": "center", "stretch": False},
]

# Create/Edit form field definitions organised into logical sections.
_FORM_SECTIONS: List[Dict[str, Any]] = [
    {
        "title": "Bank Account Information",
        "fields": [
            {"label": "Bank Name *", "var": "bank_name", "kind": "entry", "width": 320},
            {"label": "Account Name", "var": "account_name", "kind": "entry", "width": 320},
            {"label": "Account Number", "var": "account_number", "kind": "entry", "width": 260},
            {"label": "Account Type", "var": "account_type", "kind": "combo_type", "width": 180},
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
        "title": "Branch Details",
        "fields": [
            {"label": "IFSC Code", "var": "ifsc_code", "kind": "entry", "width": 180},
            {"label": "Branch", "var": "branch", "kind": "entry", "width": 240},
            {"label": "Notes / Remarks", "var": "notes", "kind": "entry", "width": 420},
        ],
    },
]

_FIELD_DEFAULTS = {
    "account_type": "Savings",
    "opening_balance": "0.00",
    "opening_balance_type": "Debit",
}


class _BankFormState:
    """Shared Create/Edit form built once and reused for both modes.

    Layout: fixed header on top, scrollable two-column form in the middle,
    fixed bottom action bar.  Only the form body scrolls.
    """

    def __init__(self, owner: "BankAccountManagementUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.mode: Optional[str] = None  # "create" | "edit"
        self.bank_account_id: Optional[int] = None
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
            title_block, text="Create Bank Account",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(
            title_block, text="Create a new bank account",
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

        for section in _FORM_SECTIONS:
            for field in section["fields"]:
                if field["var"] not in self.vars:
                    self.vars[field["var"]] = tk.StringVar(
                        value=_FIELD_DEFAULTS.get(field["var"], ""))

        self.section_frames: List[ctk.CTkFrame] = []
        row_index = 0
        for section in _FORM_SECTIONS:
            row_index = self._build_section(row_index, section)
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
            if kind == "combo_type":
                widget = ctk.CTkComboBox(
                    section_frame, variable=var, width=field["width"], height=28,
                    corner_radius=config.INPUT_CORNER_RADIUS, state="readonly",
                    values=ACCOUNT_TYPES,
                )
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

        self.message_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=12), anchor="w", justify="left",
            wraplength=1100, height=24,
        )
        self.message_label.grid(row=0, column=0, sticky="ew")

        buttons = ctk.CTkFrame(bar, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew")

        self.btn_save = ctk.CTkButton(
            buttons, text="Save", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_bank_account,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_save_new = ctk.CTkButton(
            buttons, text="Save & New", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_and_new,
        )
        self.btn_save_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._update_bank_account,
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
        self.bank_account_id = None
        self.title_label.configure(text="Create Bank Account")
        self.subtitle_label.configure(text="Create a new bank account")
        self._reset_fields()
        self._set_actions_for_mode("create")
        self._set_error("")
        self._set_success("")

    def enter_edit(self, item: Dict[str, Any]) -> None:
        self.mode = "edit"
        self.bank_account_id = item["id"]
        self.title_label.configure(text="Edit Bank Account")
        self.subtitle_label.configure(text=f"Edit Bank Account: {item.get('bank_name', '')}")
        self.vars["bank_name"].set(item.get("bank_name", ""))
        self.vars["account_name"].set(item.get("account_name", ""))
        self.vars["account_number"].set(item.get("account_number", ""))
        self.vars["account_type"].set(item.get("account_type", "Savings") or "Savings")
        self.vars["opening_balance"].set(
            f"{float(item.get('opening_balance', 0.0) or 0.0):.2f}")
        self.vars["opening_balance_type"].set(
            item.get("opening_balance_type", "Debit") or "Debit")
        self.vars["ifsc_code"].set(item.get("ifsc_code", ""))
        self.vars["branch"].set(item.get("branch", ""))
        self.vars["notes"].set(item.get("notes", ""))
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


class _BankViewState:
    """Read-only bank account details state."""

    def __init__(self, owner: "BankAccountManagementUI"):
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
            title_block, text="View Bank Account",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Bank account details (read-only)",
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

    def show(self, item: Dict[str, Any]) -> None:
        mapping = {
            "bank_name": item.get("bank_name", ""),
            "account_name": item.get("account_name", ""),
            "account_number": item.get("account_number", ""),
            "account_type": item.get("account_type", "Savings"),
            "opening_balance": f"{float(item.get('opening_balance', 0.0) or 0.0):,.2f}",
            "opening_balance_type": item.get("opening_balance_type", "Debit"),
            "ifsc_code": item.get("ifsc_code", ""),
            "branch": item.get("branch", ""),
            "notes": item.get("notes", ""),
        }
        for key, label in self.value_labels.items():
            label.configure(text=mapping.get(key, ""))

    def is_visible(self) -> bool:
        try:
            return bool(self.main.winfo_manager())
        except Exception:
            return False


class _BankListState:
    """Bank Account List: the primary management screen."""

    def __init__(self, owner: "BankAccountManagementUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", owner._apply_search)
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
            title_block, text="Bank Accounts",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Bank account master",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e")
        self.btn_new = ctk.CTkButton(
            actions, text="+ New Bank Account", width=160, height=32,
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
            command=self.owner._delete_bank_account,
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
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner.refresh_bank_accounts,
        )
        self.btn_refresh.pack(side="left")

        # Search sits directly in the header toolbar, visible.
        search_box = ctk.CTkFrame(header, fg_color="transparent")
        search_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(config.SPACING_SM, 0))
        search_box.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(
            search_box, textvariable=self.search_var, height=32,
            corner_radius=config.INPUT_CORNER_RADIUS,
            placeholder_text="Search bank accounts…",
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            search_box, text="Ctrl+F", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).grid(row=0, column=1, padx=(config.SPACING_SM, 0))

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
            top, text="Bank Accounts (0)", font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.list_title.pack(side="left")
        ctk.CTkLabel(
            top, text="Select a bank account to edit, view or delete",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=config.SPACING_LG,
                        pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame, columns=[c["id"] for c in _BANK_COLUMNS],
            show="headings", selectmode="browse",
        )
        for col in _BANK_COLUMNS:
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
            footer, text="Showing 0 to 0 of 0 bank accounts",
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
            command=self.owner._delete_bank_account,
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


class BankAccountManagementUI:
    """Stateful Bank Account Management container (List → Create/Edit/View)."""

    def __init__(self, parent: tk.Widget, company_id: Optional[int] = None):
        self.parent = parent
        self.company_id = company_id
        self.current_items: List[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # The three states are built once and reused — never duplicated.
        self.form = _BankFormState(self)
        self.view = _BankViewState(self)
        self.list = _BankListState(self)

        self._show_state(self.list)
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
        self.refresh_bank_accounts()
        self._show_state(self.list)

    def _go_create(self) -> None:
        self.form.enter_create()
        self._show_state(self.form)

    def _go_edit(self) -> None:
        item = bank_account_service.get_bank_account(self._selected_id())
        if item:
            self.form.enter_edit(item)
            self._show_state(self.form)

    def _go_view(self) -> None:
        item = bank_account_service.get_bank_account(self._selected_id())
        if item:
            self.view.show(item)
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
                self._update_bank_account()
            else:
                self._save_bank_account()

    def on_keyboard_new(self) -> None:
        if self.list.is_visible():
            self._go_create()

    def on_keyboard_refresh(self) -> None:
        if self.list.is_visible():
            self.refresh_bank_accounts()

    def on_keyboard_search(self) -> None:
        if self.list.is_visible():
            self._focus_search()

    def on_keyboard_delete(self) -> None:
        if self.list.is_visible() and self.list.tree.selection():
            self._delete_bank_account()

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
    def refresh_bank_accounts(self) -> None:
        self.current_items = bank_account_service.list_bank_accounts(
            self.list.search_var.get().strip(), company_id=self._current_company_id())
        self._render_rows()
        self.list.set_status(f"Loaded {len(self.current_items)} bank accounts")

    def _render_rows(self) -> None:
        total = len(self.current_items)
        self.list.list_title.configure(text=f"Bank Accounts ({total})")
        for item in self.list.tree.get_children():
            self.list.tree.delete(item)
        for index, item in enumerate(self.current_items):
            iid = item.get("id")
            opening = float(item.get("opening_balance", 0.0) or 0.0)
            self.list.tree.insert("", tk.END, iid=str(iid), values=(
                index + 1,
                item.get("bank_name", ""),
                item.get("account_name", ""),
                item.get("account_number", ""),
                item.get("account_type", ""),
                f"{opening:,.2f}",
                item.get("opening_balance_type", "Debit"),
                "Active",
            ), tags=('even' if index % 2 == 0 else 'odd',))
        self.list.page_label.configure(
            text=f"Showing {1 if total else 0} to {total} of {total} bank accounts")
        if self.list.selected_id is not None:
            try:
                self.list.tree.selection_set(str(self.list.selected_id))
            except Exception:
                pass

    def _apply_search(self, *args) -> None:
        self.refresh_bank_accounts()

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
            dialogs.warn("Edit", "Select a bank account to edit.", parent=self.parent)
            return
        self._go_edit()

    def _view_selected(self) -> None:
        if not self.list.tree.selection():
            dialogs.warn("View", "Select a bank account to view.", parent=self.parent)
            return
        self._go_view()

    def _delete_bank_account(self) -> None:
        bank_account_id = self._selected_id()
        if bank_account_id < 0:
            dialogs.warn("Delete", "Select a bank account to delete.", parent=self.parent)
            return
        item = bank_account_service.get_bank_account(bank_account_id)
        name = item.get("bank_name", "") if item else "bank account"
        if bank_account_service.is_bank_account_referenced(bank_account_id):
            dialogs.error("Delete Bank Account", "Cannot delete referenced bank account.", parent=self.parent)
            self.list.set_status("Delete blocked: bank account is referenced in transactions")
            return
        if not dialogs.confirm_destructive("Delete Bank Account", "bank account", name, parent=self.parent):
            return
        success, message = bank_account_service.delete_bank_account(bank_account_id)
        if not success:
            dialogs.error("Delete", message, parent=self.parent)
            self.list.set_status(message)
            return
        self.list.selected_id = None
        self.list.set_status(message)
        self.refresh_bank_accounts()

    def _clear_form(self) -> None:
        self.form.clear()
        self.form._set_success("Form cleared")

    # ------------------------------------------------------------------ #
    # form data + persistence
    # ------------------------------------------------------------------ #
    def _form_data(self) -> Dict[str, Any]:
        v = self.form.vars
        return {
            "bank_name": v["bank_name"].get().strip(),
            "account_name": v["account_name"].get().strip(),
            "account_number": v["account_number"].get().strip(),
            "account_type": v["account_type"].get().strip(),
            "opening_balance": v["opening_balance"].get().strip() or "0",
            "opening_balance_type": v["opening_balance_type"].get().strip() or "Debit",
            "ifsc_code": v["ifsc_code"].get().strip(),
            "branch": v["branch"].get().strip(),
            "notes": v["notes"].get().strip(),
        }

    def _validate(self) -> Optional[str]:
        if not self.form.vars["bank_name"].get().strip():
            return "Bank name is required"
        if not self.form.vars["account_type"].get().strip():
            return "Account type is required"
        try:
            float(self.form.vars["opening_balance"].get() or 0)
        except Exception:
            return "Opening balance must be numeric"
        return None

    def _save_bank_account(self) -> None:
        error = self._validate()
        if error:
            self.form._set_error(error)
            dialogs.warn("Save Bank Account", error, parent=self.parent)
            return
        data = self._form_data()
        data["current_balance"] = float(data["opening_balance"] or 0)
        data["opening_balance"] = float(data["opening_balance"] or 0)
        company_id = self._current_company_id()
        success, message = bank_account_service.create_bank_account(data, company_id=company_id)
        if not success:
            self.form._set_error(message)
            dialogs.error("Save Bank Account", message, parent=self.parent)
            return
        self.list.set_status(f"✓ {message}")
        self._go_list()

    def _save_and_new(self) -> None:
        error = self._validate()
        if error:
            self.form._set_error(error)
            dialogs.warn("Save Bank Account", error, parent=self.parent)
            return
        data = self._form_data()
        data["current_balance"] = float(data["opening_balance"] or 0)
        data["opening_balance"] = float(data["opening_balance"] or 0)
        company_id = self._current_company_id()
        success, message = bank_account_service.create_bank_account(data, company_id=company_id)
        if not success:
            self.form._set_error(message)
            dialogs.error("Save Bank Account", message, parent=self.parent)
            return
        self.refresh_bank_accounts()
        self.form.enter_create()
        self.form._set_success(f"✓ {message}")
        self.list.set_status(message)

    def _update_bank_account(self) -> None:
        bank_account_id = self.form.bank_account_id
        if bank_account_id is None:
            dialogs.warn("Update", "Select a bank account to update first.", parent=self.parent)
            return
        error = self._validate()
        if error:
            self.form._set_error(error)
            dialogs.warn("Update Bank Account", error, parent=self.parent)
            return
        data = self._form_data()
        data["current_balance"] = float(data["opening_balance"] or 0)
        data["opening_balance"] = float(data["opening_balance"] or 0)
        success, message = bank_account_service.update_bank_account(bank_account_id, data)
        if not success:
            self.form._set_error(message)
            dialogs.error("Update Bank Account", message, parent=self.parent)
            return
        self.list.set_status(f"✓ {message}")
        self._go_list()


def show_bank_account_management(parent: tk.Widget, company_id: Optional[int] = None) -> BankAccountManagementUI:
    return BankAccountManagementUI(parent, company_id)
