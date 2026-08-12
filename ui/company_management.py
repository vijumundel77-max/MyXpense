"""
Expenzo — Company Management
Stateful multi-company master workflow:

    Masters Hub → Company → Company List
        Company List
            ├── + New Company (Ctrl+N) → Create Company (separate state)
            ├── Edit (Enter)           → Edit Company (same form state)
            ├── View / Open            → View Company (read-only state)
            ├── Delete (Del)           → Delete selected (last-company protected)
            ├── Search (Ctrl+F)        → filter the list in the header toolbar
            ├── Refresh (F5)           → reload the list
            └── Esc                    → Masters Hub
        Create / Edit form (full-window, separate state)
            ├── Save / Update (Ctrl+S) → back to Company List (refreshed)
            ├── Save & New             → save, then blank Create form
            ├── Clear                  → reset the form
            └── Cancel / Esc           → back to Company List
        View (read-only)
            └── Back / Esc             → Company List

The Company List and the Create/Edit form are SEPARATE UI states — the form is
never cramped into the list screen.  Company switching stays in Settings; this
screen never switches the active company.  Existing company fields/schema and
the existing CompanyService are reused unchanged; the Status column reflects
the current data model (every company is Active) and the Code column is
derived deterministically from the record id for display only — no schema
changes.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

import config
from services.company_service import CompanyService, CompanyServiceError
from utils import dialogs

# List columns: (id, heading, width)
_LIST_COLUMNS: List[Dict[str, Any]] = [
    {"id": "index", "heading": "#", "width": 40, "anchor": "center", "stretch": False},
    {"id": "name", "heading": "Company Name", "width": 200, "anchor": "w", "stretch": True},
    {"id": "code", "heading": "Code", "width": 90, "anchor": "w", "stretch": False},
    {"id": "email", "heading": "Email", "width": 200, "anchor": "w", "stretch": True},
    {"id": "phone", "heading": "Phone", "width": 120, "anchor": "w", "stretch": False},
    {"id": "status", "heading": "Status", "width": 90, "anchor": "center", "stretch": False},
]

# Create/Edit form field definitions organised into logical sections.
# Only the existing finalized Company fields/schema are used — no invented
# accounting fields (GSTIN/PAN/etc.).
_FORM_SECTIONS: List[Dict[str, Any]] = [
    {
        "title": "Company Information",
        "fields": [
            {"label": "Company Name *", "var": "name", "kind": "entry", "width": 320},
            {"label": "Company Code", "var": "code", "kind": "readonly", "width": 160},
            {"label": "Phone", "var": "mobile", "kind": "entry", "width": 200},
            {"label": "Email", "var": "email", "kind": "entry", "width": 280},
        ],
    },
    {
        "title": "Address",
        "fields": [
            {"label": "Address", "var": "address", "kind": "entry", "width": 420},
            {"label": "State", "var": "state", "kind": "entry", "width": 200},
            {"label": "Country", "var": "country", "kind": "entry", "width": 200},
            {"label": "Pincode", "var": "pincode", "kind": "entry", "width": 160},
        ],
    },
    {
        "title": "Financial Year",
        "columns": 3,
        "fields": [
            {"label": "FY Start (DD-MM)", "var": "fy_start", "kind": "entry", "width": 120},
            {"label": "FY End (DD-MM)", "var": "fy_end", "kind": "entry", "width": 120},
            {"label": "Books Beginning From", "var": "books_begin", "kind": "entry", "width": 180},
        ],
    },
]

_FIELD_DEFAULTS = {
    "fy_start": "01-04",
    "fy_end": "31-03",
}


def _company_code(company_id: int) -> str:
    """Deterministic display code derived from the record id."""
    return f"CMP-{int(company_id):03d}"


class _CompanyFormState:
    """Shared Create/Edit form built once and reused for both modes.

    Layout: fixed header on top, scrollable two-column form in the middle,
    fixed bottom action bar.  Only the form body scrolls; the header and the
    action bar always stay visible.
    """

    def __init__(self, owner: "CompanyManagementUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.mode: Optional[str] = None  # "create" | "edit"
        self.company_id: Optional[int] = None
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
            title_block, text="Create Company",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        )
        self.title_label.pack(anchor="w")
        self.subtitle_label = ctk.CTkLabel(
            title_block, text="Create a new company",
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
        # Each field pair occupies two grid columns (label, entry).
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
        # Place fields N-per-row using a label/entry pair per grid slot.
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
            if field["kind"] == "readonly":
                entry = ctk.CTkEntry(
                    section_frame, textvariable=var, width=field["width"],
                    height=28, corner_radius=config.INPUT_CORNER_RADIUS,
                    state="readonly",
                )
            else:
                entry = ctk.CTkEntry(
                    section_frame, textvariable=var, width=field["width"],
                    height=28, corner_radius=config.INPUT_CORNER_RADIUS,
                )
            entry.grid(row=row, column=gc + 1, sticky="w", padx=(0, config.SPACING_LG),
                       pady=(config.SPACING_XS, config.SPACING_XS))
            self.entries[field["var"]] = entry

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
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_company,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_save_new = ctk.CTkButton(
            buttons, text="Save & New", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_and_new,
        )
        self.btn_save_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=120, height=36,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._update_company,
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
        self.company_id = None
        self.title_label.configure(text="Create Company")
        self.subtitle_label.configure(text="Create a new company")
        self._reset_fields()
        self._set_actions_for_mode("create")
        self._set_error("")
        self._set_success("")

    def enter_edit(self, company: Any) -> None:
        self.mode = "edit"
        self.company_id = company.id
        self.title_label.configure(text="Edit Company")
        self.subtitle_label.configure(text=f"Edit Company: {company.company_name}")
        self.vars["name"].set(company.company_name)
        self.vars["address"].set(company.address)
        self.vars["state"].set(company.state)
        self.vars["country"].set(company.country)
        self.vars["pincode"].set(company.pincode)
        self.vars["mobile"].set(company.mobile)
        self.vars["email"].set(company.email)
        self.vars["fy_start"].set(company.financial_year_start)
        self.vars["fy_end"].set(company.financial_year_end)
        self.vars["books_begin"].set(company.books_begin_date)
        self.vars["code"].set(_company_code(company.id))
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


class _CompanyViewState:
    """Read-only company details state."""

    def __init__(self, owner: "CompanyManagementUI"):
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
            title_block, text="View Company",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Company details (read-only)",
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
            seen = set()
            for field in section["fields"]:
                if field["var"] in seen:
                    continue
                seen.add(field["var"])
                slot = len(seen) - 1
                gc = (slot % columns) * 2
                if slot % columns == 0:
                    row = row_index
                    row_index += 1
                ctk.CTkLabel(
                    scroll, text=field["label"], font=ctk.CTkFont(size=12),
                    text_color=config.COLOR_TEXT_SECONDARY, width=160, anchor="w",
                ).grid(row=row, column=gc, sticky="w",
                       padx=(0, config.SPACING_SM), pady=config.SPACING_XS)
                value = ctk.CTkLabel(
                    scroll, text="", font=ctk.CTkFont(size=13), anchor="w",
                    justify="left", wraplength=380,
                )
                value.grid(row=row, column=gc + 1, sticky="ew",
                           padx=(0, config.SPACING_LG), pady=config.SPACING_XS)
                self.value_labels[field["var"]] = value

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=config.SPACING_LG,
                     pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_back_full = ctk.CTkButton(
            buttons, text="Back", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._go_list,
        )
        self.btn_back_full.pack(side="left")

    def show(self, company: Any) -> None:
        mapping = {
            "name": company.company_name,
            "code": _company_code(company.id),
            "email": company.email,
            "mobile": company.mobile,
            "address": company.address,
            "state": company.state,
            "country": company.country,
            "pincode": company.pincode,
            "fy_start": company.financial_year_start,
            "fy_end": company.financial_year_end,
            "books_begin": company.books_begin_date,
        }
        for key, label in self.value_labels.items():
            label.configure(text=mapping.get(key, ""))

    def is_visible(self) -> bool:
        try:
            return bool(self.main.winfo_manager())
        except Exception:
            return False


class _CompanyListState:
    """Company List: the primary management screen."""

    def __init__(self, owner: "CompanyManagementUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        # Row 1 (the list card) absorbs all extra vertical space.
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
            title_block, text="Company Management",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Create, view, edit and manage companies",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        # Toolbar: every workflow action is a visible button.
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e")
        self.btn_new = ctk.CTkButton(
            actions, text="+ New Company", width=140, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF", command=self.owner._go_create,
        )
        self.btn_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_edit_toolbar = ctk.CTkButton(
            actions, text="Edit", width=80, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._edit_selected,
        )
        self.btn_edit_toolbar.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_delete_toolbar = ctk.CTkButton(
            actions, text="Delete", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_EXPENSE, hover_color=config.COLOR_EXPENSE_HOVER,
            command=self.owner._delete_company,
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
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner.refresh_companies,
        )
        self.btn_refresh.pack(side="left")

        # Search sits directly in the header toolbar, visible.
        search_box = ctk.CTkFrame(header, fg_color="transparent")
        search_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(config.SPACING_SM, 0))
        search_box.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(
            search_box, textvariable=self.search_var, height=32,
            corner_radius=config.INPUT_CORNER_RADIUS,
            placeholder_text="Search companies by name, email or phone…",
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
            top, text="Companies (0)", font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.list_title.pack(side="left")
        ctk.CTkLabel(
            top, text="Select a company to edit, view or delete",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_MD, 0))

        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=config.SPACING_LG,
                        pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame, columns=[c["id"] for c in _LIST_COLUMNS],
            show="headings", selectmode="browse",
        )
        for col in _LIST_COLUMNS:
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
            footer, text="Showing 0 to 0 of 0 companies",
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
            command=self.owner._delete_company,
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


class CompanyManagementUI:
    """Stateful Company Management container (List → Create/Edit/View)."""

    def __init__(self, parent: tk.Widget, company_service: CompanyService,
                 current_company_id: Optional[int] = None,
                 on_company_switched=None):
        self.parent = parent
        self.service = company_service
        self.current_company_id = current_company_id
        self.on_company_switched = on_company_switched
        self.companies: List[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # The three states are built once and reused — never duplicated.
        self.form = _CompanyFormState(self)
        self.view = _CompanyViewState(self)
        self.list = _CompanyListState(self)

        self._show_state(self.list)
        self.refresh_companies()

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
        self.refresh_companies()
        self._show_state(self.list)

    def _go_create(self) -> None:
        self.form.enter_create()
        self._show_state(self.form)

    def _go_edit(self) -> None:
        company = self.service.get_company(self._selected_id())
        if company:
            self.form.enter_edit(company)
            self._show_state(self.form)

    def _go_view(self) -> None:
        company = self.service.get_company(self._selected_id())
        if company:
            self.view.show(company)
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
                self._update_company()
            else:
                self._save_company()

    def on_keyboard_new(self) -> None:
        if self.list.is_visible():
            self._go_create()

    def on_keyboard_refresh(self) -> None:
        if self.list.is_visible():
            self.refresh_companies()

    def on_keyboard_search(self) -> None:
        if self.list.is_visible():
            self._focus_search()

    def on_keyboard_delete(self) -> None:
        if self.list.is_visible() and self.list.tree.selection():
            self._delete_company()

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
    def refresh_companies(self) -> None:
        self.companies = self.service.list_companies(self.list.search_var.get().strip())
        self._render_rows()
        self.list.set_status(f"Loaded {len(self.companies)} companies")

    def _render_rows(self) -> None:
        total = len(self.companies)
        self.list.list_title.configure(text=f"Companies ({total})")
        for item in self.list.tree.get_children():
            self.list.tree.delete(item)
        for index, company in enumerate(self.companies):
            cid = company.get("id")
            self.list.tree.insert("", tk.END, iid=str(cid), values=(
                index + 1,
                company.get("name", ""),
                _company_code(cid),
                company.get("email", ""),
                company.get("mobile", ""),
                "Active",
            ), tags=('even' if index % 2 == 0 else 'odd',))
        self.list.page_label.configure(
            text=f"Showing {1 if total else 0} to {total} of {total} companies")
        if self.list.selected_id is not None:
            try:
                self.list.tree.selection_set(str(self.list.selected_id))
            except Exception:
                pass

    def _apply_search(self, *args) -> None:
        self.refresh_companies()

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
            dialogs.warn("Edit", "Select a company to edit.", parent=self.parent)
            return
        self._go_edit()

    def _view_selected(self) -> None:
        if not self.list.tree.selection():
            dialogs.warn("View", "Select a company to view.", parent=self.parent)
            return
        self._go_view()

    def _delete_company(self) -> None:
        company_id = self._selected_id()
        if company_id < 0:
            dialogs.warn("Delete", "Select a company to delete.", parent=self.parent)
            return
        company = self.service.get_company(company_id)
        if not company:
            return
        remaining = len(self.service.list_companies())
        if remaining <= 1:
            dialogs.error(
                "Delete", "The last remaining company cannot be deleted.\n\n"
                "At least one company must always exist.",
                parent=self.parent,
            )
            return
        if not dialogs.confirm_destructive("Delete Company", "company", company.company_name, parent=self.parent):
            return
        try:
            self.service.delete_company(company_id)
        except CompanyServiceError as exc:
            dialogs.error("Delete", exc.message, parent=self.parent)
            return
        self.list.selected_id = None
        self.list.set_status(f"Company '{company.company_name}' deleted")
        self.refresh_companies()

    def _clear_form(self) -> None:
        self.form.clear()
        self.form._set_success("Form cleared")

    def _form_data(self) -> dict:
        v = self.form.vars
        return {
            "name": v["name"].get().strip(),
            "address": v["address"].get().strip(),
            "state": v["state"].get().strip(),
            "country": v["country"].get().strip(),
            "pincode": v["pincode"].get().strip(),
            "mobile": v["mobile"].get().strip(),
            "email": v["email"].get().strip(),
            "fy_start": v["fy_start"].get().strip() or "01-04",
            "fy_end": v["fy_end"].get().strip() or "31-03",
            "books_begin": v["books_begin"].get().strip(),
        }

    def _save_company(self) -> None:
        data = self._form_data()
        try:
            company = self.service.create_company(
                data["name"], data["address"], data["mobile"], data["email"],
                data["fy_start"], data["fy_end"], data["books_begin"],
                data["state"], data["country"], data["pincode"],
            )
        except CompanyServiceError as exc:
            self.form._set_error(exc.message)
            dialogs.error("Validation", exc.message, parent=self.parent)
            return
        self.list.set_status(f"✓ Company '{company.company_name}' created successfully.")
        self._go_list()

    def _save_and_new(self) -> None:
        data = self._form_data()
        try:
            company = self.service.create_company(
                data["name"], data["address"], data["mobile"], data["email"],
                data["fy_start"], data["fy_end"], data["books_begin"],
                data["state"], data["country"], data["pincode"],
            )
        except CompanyServiceError as exc:
            self.form._set_error(exc.message)
            dialogs.error("Validation", exc.message, parent=self.parent)
            return
        self.form.enter_create()
        self.form._set_success(f"✓ Company '{company.company_name}' created successfully.")
        self.list.set_status(f"Company '{company.company_name}' created successfully.")

    def _update_company(self) -> None:
        company_id = self.form.company_id
        if company_id is None:
            dialogs.warn("Update", "Select a company to update first.", parent=self.parent)
            return
        data = self._form_data()
        try:
            company = self.service.update_company(
                company_id, data["name"], data["address"], data["mobile"],
                data["email"], data["fy_start"], data["fy_end"], data["books_begin"],
                data["state"], data["country"], data["pincode"],
            )
        except CompanyServiceError as exc:
            self.form._set_error(exc.message)
            dialogs.error("Validation", exc.message, parent=self.parent)
            return
        self.list.set_status(f"✓ Company '{company.company_name}' updated successfully.")
        self._go_list()


def show_company_management(parent: tk.Widget, company_service: CompanyService,
                            current_company_id: Optional[int] = None,
                            on_company_switched=None) -> CompanyManagementUI:
    return CompanyManagementUI(parent, company_service, current_company_id, on_company_switched)
