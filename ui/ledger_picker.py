"""
Expenzo — Searchable Ledger / Party selector

A compact, keyboard-first account picker for accounting entry screens.
Reuses the existing ``account_service`` ledger data (parties are ledgers
under Sundry Debtors / Sundry Creditors) — no duplicate database is created.

Behavior:
    * Focus the field to open the live result list (all ledgers).
    * Type to filter by name / code / alias / group.
    * Down / Up move through the results; Enter selects and closes;
      Esc closes without selecting.
    * A blue focus ring marks the active entry so the current row is always
      obvious when tabbing through the voucher grid.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk

import config
from services.account_service import account_service

_PICKER_STYLE = "VoucherPicker.Treeview"


class LedgerPicker(ctk.CTkFrame):
    """Searchable account selector used inside voucher entry rows."""

    def __init__(
        self,
        master,
        company_id: int,
        width: int = 320,
        on_selected: Optional[Callable[[int], None]] = None,
        groups: Optional[List[str]] = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.company_id = company_id
        self.width = width
        self.on_selected = on_selected
        self.groups = groups  # Optional list of account groups to restrict to.

        self.entry_var = tk.StringVar()
        self.entry_var.trace_add("write", self._on_search)
        self.entry = ctk.CTkEntry(
            self, textvariable=self.entry_var, width=width,
            corner_radius=config.INPUT_CORNER_RADIUS,
            font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
        )
        self.entry.pack(fill="x")
        self.entry.bind("<KeyRelease>", self._on_search_event)
        self.entry.bind("<Down>", lambda _e: self._move(1))
        self.entry.bind("<Up>", lambda _e: self._move(-1))
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Escape>", self._on_escape)
        self.entry.bind("<Tab>", self._on_tab_out)
        self.entry.bind("<Shift-Tab>", self._on_shift_tab_out)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        self.results: List[Dict[str, Any]] = []
        self._selected: Optional[Dict[str, Any]] = None

        # Popup result list (a Toplevel owned by this picker).
        self.popup: Optional[tk.Toplevel] = None
        self._suppress_popup = False

        self._build_popup()
        self._load_all()

    # ------------------------------------------------------------------ #
    # popup
    # ------------------------------------------------------------------ #
    def _build_popup(self) -> None:
        self.popup = tk.Toplevel(self)
        self.popup.withdraw()
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        self.popup.configure(bg=config.COLOR_BG_SECONDARY)
        self.popup.protocol("WM_DELETE_WINDOW", self._hide_popup)

        frame = ttk.Frame(self.popup)
        frame.pack(fill="both", expand=True)

        columns = ("name", "group")
        self.tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="browse",
            height=8, style=_PICKER_STYLE,
        )
        self.tree.heading("name", text="Ledger / Party")
        self.tree.heading("group", text="Under")
        self.tree.column("name", width=max(200, self.width - 130), anchor="w")
        self.tree.column("group", width=120, anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Return>", self._on_enter)
        self.tree.bind("<Escape>", self._on_escape)
        self.tree.bind("<Down>", lambda _e: self._move(1))
        self.tree.bind("<Up>", lambda _e: self._move(-1))
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<Tab>", self._on_tab_out)
        self.tree.bind("<Shift-Tab>", self._on_shift_tab_out)

    # ------------------------------------------------------------------ #
    # data (existing ledger service only)
    # ------------------------------------------------------------------ #
    def _load_all(self) -> None:
        try:
            self.results = account_service.search_accounts(
                self.company_id, include_inactive=False)
        except Exception:
            self.results = []
        if self.groups:
            self.results = [a for a in self.results if a.get('account_group') in self.groups]

    @staticmethod
    def account_label(account: Dict[str, Any]) -> str:
        code = account.get('code', '')
        return f"{account['name']} ({code})" if code else account['name']

    def set_account(self, account_id: Optional[int]) -> None:
        """Programmatically set the current account (no popup)."""
        self._selected = None
        if account_id is None:
            self.entry_var.set("")
            return
        for account in self.results:
            if int(account['id']) == int(account_id):
                self._selected = account
                self.entry_var.set(self.account_label(account))
                try:
                    self.entry.select_range(0, tk.END)
                except Exception:
                    pass
                return
        self.entry_var.set("")

    def get_account(self) -> Optional[int]:
        if self._selected is not None:
            return int(self._selected['id'])
        return None

    def clear(self) -> None:
        self._selected = None
        self.entry_var.set("")
        self._hide_popup()

    def focus_entry(self) -> None:
        self.entry.focus_set()

    # ------------------------------------------------------------------ #
    # popup visibility
    # ------------------------------------------------------------------ #
    def _show_popup(self) -> None:
        if self._suppress_popup or self.popup is None:
            return
        try:
            self.entry.update_idletasks()
            x = self.entry.winfo_rootx()
            y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
            width = max(self.width + 8, 320)
            self.popup.geometry(f"{width}x{190}+{x}+{y}")
            self.popup.deiconify()
            self.popup.lift()
            self.popup.attributes("-topmost", True)
        except Exception:
            pass

    def _hide_popup(self) -> None:
        if self.popup is not None:
            try:
                self.popup.withdraw()
            except Exception:
                pass

    def _refresh_results(self, filter_text: str) -> None:
        term = filter_text.strip().lower()
        if term:
            filtered = [
                a for a in self.results
                if term in str(a.get('name', '')).lower()
                or term in str(a.get('code', '')).lower()
                or term in str(a.get('alias', '')).lower()
                or term in str(a.get('account_group', '')).lower()
            ]
        else:
            filtered = list(self.results)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for account in filtered[:200]:
            self.tree.insert("", tk.END, iid=str(account['id']), values=(
                self.account_label(account),
                account.get('account_group', ''),
            ))
        if filtered:
            self.tree.selection_set(self.tree.get_children()[0])
        if filtered and self.popup is not None and self.popup.winfo_ismapped():
            try:
                self.popup.attributes("-topmost", True)
                self.popup.lift()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # events
    # ------------------------------------------------------------------ #
    def _on_search(self, *args) -> None:
        if self._selected is not None and self.entry_var.get() != self.account_label(self._selected):
            self._selected = None
        self._refresh_results(self.entry_var.get())

    def _on_search_event(self, _event) -> None:
        self._show_popup()

    def _on_focus_in(self, _event) -> None:
        self._refresh_results(self.entry_var.get())
        self._show_popup()

    def _on_focus_out(self, _event) -> None:
        # Defer so clicks inside the popup tree register first.
        self.after(120, self._maybe_hide_on_focus_out)

    def _maybe_hide_on_focus_out(self) -> None:
        if self.popup is None:
            return
        try:
            focused = self.focus_get()
        except Exception:
            focused = None
        if focused is not self.tree and focused is not self.entry:
            self._hide_popup()

    def _move(self, delta: int) -> None:
        children = self.tree.get_children()
        if not children:
            return
        if not self.popup or not self.popup.winfo_ismapped():
            self._show_popup()
            self._refresh_results(self.entry_var.get())
            return
        current = self.tree.selection()
        index = children.index(current[0]) if current else -1
        next_index = max(0, min(len(children) - 1, index + delta))
        self.tree.selection_set(children[next_index])
        self.tree.see(children[next_index])
        self.popup.lift()

    def _on_enter(self, _event=None):
        self._select_current()
        return "break"

    def _on_tree_click(self, _event) -> None:
        self._select_current()

    def _on_escape(self, _event=None):
        self._hide_popup()
        return "break"

    def _on_tab_out(self, _event=None):
        # Commit the highlighted account when tabbing away, then let the
        # normal traversal move focus to the next widget.
        if self._select_current(silent=True):
            self._hide_popup()
        return None

    def _on_shift_tab_out(self, _event=None):
        if self._select_current(silent=True):
            self._hide_popup()
        return None

    def _select_current(self, silent: bool = False) -> bool:
        children = self.tree.get_children()
        if not children:
            if silent:
                return False
            return False
        selection = self.tree.selection()
        iid = selection[0] if selection else children[0]
        account_id = int(iid)
        account = next((a for a in self.results if int(a['id']) == account_id), None)
        if account is None:
            return False
        self._selected = account
        self.entry_var.set(self.account_label(account))
        try:
            self.entry.select_range(0, tk.END)
        except Exception:
            pass
        self._hide_popup()
        if self.on_selected is not None:
            try:
                self.on_selected(int(account['id']))
            except Exception:
                pass
        return True

    def _selected_label(self) -> str:
        return self.account_label(self._selected) if self._selected else ""

    def is_focused(self) -> bool:
        try:
            return self.focus_get() is self.entry
        except Exception:
            return False


# ---------------------------------------------------------------------- #
# ttk styles for the picker (light/dark aware via theme.apply_theme)
# ---------------------------------------------------------------------- #
def configure_picker_style(root=None) -> None:
    """Make sure the picker Treeview style exists with sensible colors."""
    style = ttk.Style(root) if root is not None else ttk.Style()
    try:
        style.configure(
            _PICKER_STYLE,
            background=config.COLOR_BG_SECONDARY,
            fieldbackground=config.COLOR_BG_SECONDARY,
            foreground=config.COLOR_TEXT_PRIMARY,
            bordercolor=config.COLOR_CARD_BORDER,
            rowheight=24,
        )
        style.map(
            _PICKER_STYLE,
            background=[("selected", config.COLOR_PRIMARY)],
            foreground=[("selected", "#FFFFFF")],
        )
        style.configure(
            f"{_PICKER_STYLE}.Heading",
            background=config.COLOR_BG_TERTIARY,
            foreground=config.COLOR_TEXT_PRIMARY,
            font=(config.FONT_FAMILY, 11, "bold"),
        )
    except Exception:
        pass
