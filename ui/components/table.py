"""
Expenzo — DataTable component.

A premium ttk.Treeview wrapper: sticky styled header, zebra rows, row hover
highlight, column sorting (click a heading), optional search box, pagination
footer, status badges, a totals bar, and an empty state. Everything is themed
through config tokens so light/dark switching works.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, Iterable, List, Optional

import customtkinter as ctk

import config


class DataTable(ctk.CTkFrame):
    """A polished table with header, sorting, pagination and badges.

    Args:
        columns: list of dicts with keys ``id``, ``heading``, optional
            ``width``, ``anchor``, ``stretch``, ``sortable``.
        rows: optional initial rows (iterables matching column order).
        searchable: show a search box above the table (off by default —
            screens often provide their own search).
        page_size: rows per page when pagination is enabled; 0 disables it.
        badges: optional mapping column_id -> dict {value: (text, color)} used
            to render status columns as colored chips.
        on_double_click: optional callback(item_id, values).
    """

    def __init__(self, master, columns: List[Dict[str, Any]],
                 rows: Optional[Iterable[Iterable[Any]]] = None,
                 searchable: bool = False, page_size: int = 0,
                 badges: Optional[Dict[str, Dict[Any, tuple]]] = None,
                 on_double_click: Optional[Callable[[str, tuple], None]] = None,
                 **kwargs):
        super().__init__(master, corner_radius=config.CARD_CORNER_RADIUS,
                         fg_color=config.COLOR_BG_SECONDARY,
                         border_width=1, border_color=config.COLOR_CARD_BORDER,
                         **kwargs)
        self.columns = columns
        self._badges = badges or {}
        self._on_double_click = on_double_click
        self._all_rows: List[tuple] = []
        self._filtered_rows: List[tuple] = []
        self._sort_col: Optional[str] = None
        self._sort_reverse = False
        self.page_size = page_size
        self.page = 0
        self._search_term = ""

        self._build(searchable)

        if rows is not None:
            self.set_rows(rows)

    # ------------------------------------------------------------------ #
    # construction
    # ------------------------------------------------------------------ #
    def _build(self, searchable: bool) -> None:
        if searchable:
            self.search_var = tk.StringVar()
            self.search_entry = ctk.CTkEntry(
                self, textvariable=self.search_var, height=32,
                corner_radius=config.INPUT_CORNER_RADIUS,
                placeholder_text="Search…",
            )
            self.search_entry.pack(fill="x", padx=config.SPACING_LG,
                                   pady=(config.SPACING_MD, config.SPACING_SM))
            self.search_var.trace_add("write", lambda *_: self._apply_search())

        self.totals_label = ctk.CTkLabel(
            self, text="", anchor="w",
            font=ctk.CTkFont(size=config.FONT_SMALL_SIZE, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
        )
        self.totals_label.pack(fill="x", padx=config.SPACING_LG,
                               pady=(config.SPACING_MD, config.SPACING_XS))

        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)

        col_ids = [c["id"] for c in self.columns]
        self.tree = ttk.Treeview(tree_frame, columns=col_ids, show="headings",
                                 selectmode="browse")
        for col in self.columns:
            cid = col["id"]
            self.tree.heading(cid, text=col["heading"],
                              command=lambda c=cid: self._toggle_sort(c))
            self.tree.column(cid, width=col.get("width", 140),
                             anchor=col.get("anchor", "w"),
                             stretch=col.get("stretch", True))
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True,
                       padx=(config.SPACING_LG, 0), pady=(0, config.SPACING_LG))
        vsb.pack(side="right", fill="y", pady=(0, config.SPACING_LG))
        hsb.pack(side="bottom", fill="x")

        self.tree.tag_configure("hover", background=config.COLOR_HOVER_SURFACE)
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", lambda _e: self._clear_hover())
        if self._on_double_click is not None:
            self.tree.bind("<Double-1>", self._on_double)

        # Pagination footer.
        self.page_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
            text_color=config.COLOR_TEXT_MUTED,
        )
        self.page_label.pack(side="left", padx=config.SPACING_LG,
                             pady=config.SPACING_SM)
        page_row = ctk.CTkFrame(self, fg_color="transparent")
        page_row.pack(side="right", padx=config.SPACING_LG,
                      pady=(0, config.SPACING_SM))
        self.btn_prev = ctk.CTkButton(
            page_row, text="‹ Prev", width=70, height=26,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_HOVER_SURFACE,
            text_color=config.COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
            command=self._prev_page,
        )
        self.btn_prev.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_next = ctk.CTkButton(
            page_row, text="Next ›", width=70, height=26,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_HOVER_SURFACE,
            text_color=config.COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
            command=self._next_page,
        )
        self.btn_next.pack(side="left")
        if not self.page_size:
            page_row.pack_forget()

        self.empty_label = ctk.CTkLabel(
            self, text="No data to display.", font=ctk.CTkFont(size=14),
            text_color=config.COLOR_TEXT_MUTED,
        )
        self.empty_label.pack(pady=(config.SPACING_XXL, config.SPACING_XXL))

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def set_rows(self, rows: Iterable[Iterable[Any]]) -> None:
        self._all_rows = [tuple(r) for r in rows]
        self._apply_search()

    def clear(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def set_totals(self, text: str) -> None:
        self.totals_label.configure(text=text)

    def _apply_search(self) -> None:
        term = self._search_term.lower()
        if term:
            self._filtered_rows = [
                r for r in self._all_rows
                if term in " ".join(str(v) for v in r).lower()
            ]
        else:
            self._filtered_rows = list(self._all_rows)
        self.page = 0
        self._render()

    def _render(self) -> None:
        self.clear()
        rows = self._filtered_rows
        if self.page_size:
            start = self.page * self.page_size
            rows = rows[start:start + self.page_size]
        for index, row in enumerate(rows):
            values = self._badge_values(row)
            self.tree.insert("", tk.END, values=values,
                             tags=('even' if index % 2 == 0 else 'odd',))
        if self.page_size:
            total_pages = max(1, -(-len(self._filtered_rows) // self.page_size))
            self.page_label.configure(
                text=f"Page {self.page + 1} of {total_pages}  ·  "
                     f"{len(self._filtered_rows)} rows")
            self.btn_prev.configure(state="normal" if self.page > 0 else "disabled")
            self.btn_next.configure(state="normal" if self.page < total_pages - 1 else "disabled")
        self._update_empty()

    def _badge_values(self, row: tuple) -> tuple:
        """Render badge columns as chip-styled text."""
        values = list(row)
        for index, col in enumerate(self.columns):
            badge_map = self._badges.get(col["id"])
            if badge_map and values[index] in badge_map:
                values[index] = f"  {values[index]}  "
        return tuple(values)

    def _update_empty(self) -> None:
        if not self.tree.get_children():
            self.empty_label.configure(text="No data to display.")
            self.empty_label.lift()
        else:
            self.empty_label.lower()

    # ------------------------------------------------------------------ #
    # sorting
    # ------------------------------------------------------------------ #
    def _toggle_sort(self, col_id: str) -> None:
        col = next((c for c in self.columns if c["id"] == col_id), None)
        if col is not None and col.get("sortable", True) is False:
            return
        if self._sort_col == col_id:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col_id
            self._sort_reverse = False
        index = next((i for i, c in enumerate(self.columns) if c["id"] == col_id), 0)
        self._filtered_rows.sort(
            key=lambda r: self._sort_key(r[index]),
            reverse=self._sort_reverse,
        )
        self._render()

    @staticmethod
    def _sort_key(value: Any):
        if isinstance(value, (int, float)):
            return value
        try:
            return float(str(value).replace(",", "").replace(config.CURRENCY_SYMBOL, ""))
        except Exception:
            return str(value).lower()

    # ------------------------------------------------------------------ #
    # pagination
    # ------------------------------------------------------------------ #
    def _prev_page(self) -> None:
        if self.page > 0:
            self.page -= 1
            self._render()

    def _next_page(self) -> None:
        total_pages = max(1, -(-len(self._filtered_rows) // self.page_size))
        if self.page < total_pages - 1:
            self.page += 1
            self._render()

    # ------------------------------------------------------------------ #
    # hover & double-click
    # ------------------------------------------------------------------ #
    def _on_motion(self, event) -> None:
        item = self.tree.identify_row(event.y)
        self._clear_hover()
        if item:
            try:
                self.tree.item(item, tags=("hover",))
            except Exception:
                pass

    def _clear_hover(self) -> None:
        for item in self.tree.get_children():
            tags = self.tree.item(item, "tags")
            if "hover" in tags:
                self.tree.item(item, tags=("even",) if "even" in tags else ("odd",))

    def _on_double(self, event) -> None:
        item = self.tree.identify_row(event.y)
        if item and self._on_double_click is not None:
            self._on_double_click(item, self.tree.item(item, "values"))

    # ------------------------------------------------------------------ #
    # helpers for screens
    # ------------------------------------------------------------------ #
    def selected_row(self) -> Optional[tuple]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0], "values")

    def refresh(self, rows: Iterable[Iterable[Any]]) -> None:
        self.set_rows(rows)
