"""
Expenzo — Company Management
Stateful multi-company master workflow:

    Masters Hub → Company → Company List
        Company List
            ├── + New Company (Ctrl+N) → Create Company (separate state)
            ├── Edit (Enter)           → Edit Company (same form state)
            ├── View                   → View Company (read-only state)
            ├── Delete (Del)           → Delete selected (last-company protected)
            └── Esc                    → Masters Hub
        Create / Edit form
            ├── Save / Update (Ctrl+S) → back to Company List (refreshed)
            ├── Clear                  → reset the form
            └── Cancel / Esc           → back to Company List

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
    {"id": "index", "heading": "#", "width": 34, "anchor": "center"},
    {"id": "name", "heading": "Company Name", "width": 150, "anchor": "w"},
    {"id": "code", "heading": "Code", "width": 80, "anchor": "w"},
    {"id": "email", "heading": "Email", "width": 160, "anchor": "w"},
    {"id": "phone", "heading": "Phone", "width": 110, "anchor": "w"},
    {"id": "status", "heading": "Status", "width": 80, "anchor": "center"},
]

_FORM_FIELDS: List[Dict[str, Any]] = [
    {"label": "Company Name *", "var": "name", "width": 320},
    {"label": "Company Code", "var": "code", "width": 160},
    {"label": "Email", "var": "email", "width": 300},
    {"label": "Phone", "var": "mobile", "width": 200},
    {"label": "Address", "var": "address", "width": 320},
    {"label": "State", "var": "state", "width": 200},
    {"label": "Country", "var": "country", "width": 200},
    {"label": "Pincode", "var": "pincode", "width": 160},
    {"label": "Financial Year Start (DD-MM)", "var": "fy_start", "width": 160},
    {"label": "Financial Year End (DD-MM)", "var": "fy_end", "width": 160},
    {"label": "Books Beginning From (YYYY-MM-DD)", "var": "books_begin", "width": 200},
]

_FIELD_DEFAULTS = {
    "fy_start": "01-04",
    "fy_end": "31-03",
}


def _company_code(company_id: int) -> str:
    """Deterministic display code derived from the record id."""
    return f"CMP-{int(company_id):03d}"


class _CompanyFormState:
    """Shared Create/Edit form built once and reused for both modes."""

    def __init__(self, owner: "CompanyManagementUI"):
        self.owner = owner
        self.main = ctk.CTkFrame(owner.main_frame, corner_radius=0, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.mode: Optional[str] = None  # "create" | "edit"
        self.company_id: Optional[int] = None
        self.vars: Dict[str, tk.StringVar] = {}
        self._build_header()
        self._build_form()

    # ------------------------------------------------------------------ #
    # header
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
    # form card
    # ------------------------------------------------------------------ #
    def _build_form(self) -> None:
        card = ctk.CTkFrame(
            self.main, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew", padx=config.SPACING_LG, pady=config.SPACING_LG)

        for field in _FORM_FIELDS:
            var = tk.StringVar(value=_FIELD_DEFAULTS.get(field["var"], ""))
            self.vars[field["var"]] = var
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=config.SPACING_XS)
            ctk.CTkLabel(
                row, text=field["label"], font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
                text_color=config.COLOR_TEXT_SECONDARY, width=280, anchor="w",
            ).pack(side="left")
            entry = ctk.CTkEntry(
                row, textvariable=var, width=field["width"],
                corner_radius=config.INPUT_CORNER_RADIUS,
            )
            entry.pack(side="left", fill="x", expand=True, padx=(config.SPACING_SM, 0))
            if field["var"] == "code":
                self.code_entry = entry
                entry.configure(state="readonly")

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=config.SPACING_LG,
                     pady=(config.SPACING_SM, config.SPACING_LG))
        self.btn_save = ctk.CTkButton(
            buttons, text="Save", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._save_company,
        )
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update = ctk.CTkButton(
            buttons, text="Update", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._update_company,
        )
        self.btn_update.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_clear = ctk.CTkButton(
            buttons, text="Clear", width=100, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._clear_form,
        )
        self.btn_clear.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_cancel = ctk.CTkButton(
            buttons, text="Cancel", width=100, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._go_list,
        )
        self.btn_cancel.pack(side="left")

        hint = ctk.CTkLabel(
            self.main,
            text="   ".join(f"{key} {label}" for key, label in [
                ("Ctrl+S", "Save / Update"), ("Esc", "Cancel / Back"),
            ]),
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED, anchor="w",
        )
        hint.grid(row=2, column=0, sticky="ew", pady=(config.SPACING_SM, 0))

    # ------------------------------------------------------------------ #
    # mode switching (shared component reused for create and edit)
    # ------------------------------------------------------------------ #
    def enter_create(self) -> None:
        self.mode = "create"
        self.company_id = None
        self.title_label.configure(text="Create Company")
        self.subtitle_label.configure(text="Create a new company")
        for var in self.vars.values():
            var.set("")
        self.vars["fy_start"].set("01-04")
        self.vars["fy_end"].set("31-03")
        self.btn_save.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_update.pack_forget()
        self.btn_save.configure(state="normal")
        self.btn_update.configure(state="disabled")

    def enter_edit(self, company: Any) -> None:
        self.mode = "edit"
        self.company_id = company.id
        self.title_label.configure(text="Edit Company")
        self.subtitle_label.configure(text="Update company details")
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
        self.btn_update.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_save.pack_forget()
        self.btn_save.configure(state="disabled")
        self.btn_update.configure(state="normal")

    def clear(self) -> None:
        self.enter_create()

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
        card.grid_columnconfigure(0, weight=1)

        self.value_labels: Dict[str, ctk.CTkLabel] = {}
        for index, field in enumerate(_FORM_FIELDS):
            label = ctk.CTkLabel(
                card, text=field["label"], font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_SECONDARY, width=280, anchor="w",
            )
            label.grid(row=index, column=0, sticky="w", padx=(config.SPACING_LG, config.SPACING_SM),
                       pady=(config.SPACING_XS, 0))
            value = ctk.CTkLabel(
                card, text="", font=ctk.CTkFont(size=13), anchor="w",
                justify="left", wraplength=480,
            )
            value.grid(row=index, column=1, sticky="ew", padx=(0, config.SPACING_LG),
                       pady=(config.SPACING_XS, 0))
            self.value_labels[field["var"]] = value
        card.grid_rowconfigure(len(_FORM_FIELDS), weight=1)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=len(_FORM_FIELDS) + 1, column=0, columnspan=2, sticky="ew",
                     padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_LG))
        ctk.CTkButton(
            buttons, text="Back", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._go_list,
        ).pack(side="left")

        hint = ctk.CTkLabel(
            self.main,
            text="Esc to return to Company List",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED, anchor="w",
        )
        hint.grid(row=2, column=0, sticky="ew", pady=(config.SPACING_SM, 0))

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
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", owner._apply_search)
        self.selected_id: Optional[int] = None

        self._build_header()
        self._build_list_card()
        self._build_info_bar()

    # ------------------------------------------------------------------ #
    # header (owned by the list state; hidden when a sub-state is open)
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, config.SPACING_LG))

        self.btn_back = ctk.CTkButton(
            header, text="←", width=36, height=32, corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self.owner._back_to_hub,
        )
        self.btn_back.pack(side="left")

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(side="left", padx=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            title_block, text="Company Management",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Create, view, edit and manage companies",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right")
        self.btn_refresh = ctk.CTkButton(
            actions, text="F5 Refresh", width=100, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner.refresh_companies,
        )
        self.btn_refresh.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_new = ctk.CTkButton(
            actions, text="+ New Company", width=130, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF", command=self.owner._go_create,
        )
        self.btn_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_header_search = ctk.CTkButton(
            actions, text="Search", width=90, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self.owner._focus_search,
        )
        self.btn_header_search.pack(side="left")

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
        card.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=config.SPACING_LG,
                 pady=(config.SPACING_MD, config.SPACING_SM))
        self.list_title = ctk.CTkLabel(
            top, text="Companies (0)", font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.list_title.pack(side="left")

        search_row = ctk.CTkFrame(card, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        self.search_entry = ctk.CTkEntry(
            search_row, textvariable=self.search_var, width=280,
            corner_radius=config.INPUT_CORNER_RADIUS,
            placeholder_text="Search companies…",
        )
        self.search_entry.pack(side="left", fill="x", expand=True)

        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_frame, columns=[c["id"] for c in _LIST_COLUMNS],
            show="headings", selectmode="browse",
        )
        for col in _LIST_COLUMNS:
            self.tree.heading(col["id"], text=col["heading"])
            self.tree.column(col["id"], width=col["width"], anchor=col["anchor"],
                             stretch=True, minwidth=30)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self.owner._on_select)
        self.tree.bind("<Return>", self.owner._on_enter_pressed)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=config.SPACING_LG,
                    pady=(0, config.SPACING_SM))
        self.page_label = ctk.CTkLabel(
            footer, text="Showing 0 to 0 of 0 companies",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
        )
        self.page_label.pack(side="left")

        self.action_row = ctk.CTkFrame(card, fg_color="transparent")
        self.action_row.grid(row=4, column=0, sticky="ew", padx=config.SPACING_LG,
                             pady=(0, config.SPACING_LG))
        self.btn_edit = ctk.CTkButton(
            self.action_row, text="Edit (Enter)", width=110, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.owner._edit_selected,
        )
        self.btn_edit.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_delete = ctk.CTkButton(
            self.action_row, text="Delete (Del)", width=110, height=32,
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

    # ------------------------------------------------------------------ #
    # compact info bar (never competes with the table for space)
    # ------------------------------------------------------------------ #
    def _build_info_bar(self) -> None:
        bar = ctk.CTkFrame(self.main, fg_color=config.COLOR_BG_SECONDARY,
                           corner_radius=config.CARD_CORNER_RADIUS,
                           border_width=1, border_color=config.COLOR_CARD_BORDER)
        bar.grid(row=2, column=0, sticky="ew", pady=(config.SPACING_MD, 0))

        ctk.CTkLabel(
            bar, text="Keyboard Shortcuts", font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=config.SPACING_LG)
        for key, label in [
            ("F5", "Refresh"),
            ("Ctrl+N", "New Company"),
            ("Ctrl+S", "Save"),
            ("Ctrl+F", "Search"),
            ("Del", "Delete"),
            ("Esc", "Back"),
        ]:
            ctk.CTkLabel(
                bar, text=key, font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLOR_PRIMARY,
            ).pack(side="left", padx=(config.SPACING_MD, 0))
            ctk.CTkLabel(
                bar, text=label, font=ctk.CTkFont(size=11),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(side="left", padx=(2, 0))
        # Note on its own line so it is never squeezed by the shortcut keys.
        ctk.CTkLabel(
            bar, text="Note: At least one company must always exist. "
                     "The last remaining company cannot be deleted.",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED,
            anchor="w", justify="left",
        ).pack(fill="x", padx=config.SPACING_LG, pady=(2, config.SPACING_SM))

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
        self._set_status(f"Loaded {len(self.companies)} companies")

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

    def _focus_search(self) -> None:
        try:
            self.list.search_entry.focus_set()
            self.list.search_entry.select_range(0, "end")
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        try:
            self.parent.update_idletasks()
        except Exception:
            pass
        self.status_text = text

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
        self.refresh_companies()

    def _clear_form(self) -> None:
        self.form.clear()
        self._set_status("Form cleared")

    def _save_company(self) -> None:
        data = self._form_data()
        try:
            company = self.service.create_company(
                data["name"], data["address"], data["mobile"], data["email"],
                data["fy_start"], data["fy_end"], data["books_begin"],
                data["state"], data["country"], data["pincode"],
            )
        except CompanyServiceError as exc:
            dialogs.error("Validation", exc.message, parent=self.parent)
            self._set_status(exc.message)
            return
        self._set_status(f"Company '{company.company_name}' saved")
        self._go_list()

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
            dialogs.error("Validation", exc.message, parent=self.parent)
            self._set_status(exc.message)
            return
        self._set_status(f"Company '{company.company_name}' updated")
        self._go_list()

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


def show_company_management(parent: tk.Widget, company_service: CompanyService,
                            current_company_id: Optional[int] = None,
                            on_company_switched=None) -> CompanyManagementUI:
    return CompanyManagementUI(parent, company_service, current_company_id, on_company_switched)
