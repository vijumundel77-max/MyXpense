"""
Expenzo — Report Base
Shared building blocks for the Expenzo report screens: themed header,
filter row, Treeview table, totals bar, empty state, and status bar.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Iterable, List, Optional

import customtkinter as ctk

import config


class ReportHeader(ctk.CTkFrame):
    """Expenzo-styled report header with title + subtitle + optional actions."""

    def __init__(self, parent, title: str, subtitle: str = ""):
        super().__init__(parent, fg_color="transparent")
        self.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                self, text=subtitle, font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(side="left", padx=(config.SPACING_MD, 0))


class FilterBar(ctk.CTkFrame):
    """Card-style filter row container."""

    def __init__(self, parent):
        super().__init__(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        self.pack(fill="x", pady=(0, config.SPACING_LG))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_MD)

    def add(self, label: str, widget, padx: int = 0) -> None:
        holder = ctk.CTkFrame(self.body, fg_color="transparent")
        holder.pack(side="left", padx=(0, padx if padx else config.SPACING_LG))
        ctk.CTkLabel(
            holder, text=label, font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")
        widget.pack(anchor="w", pady=(2, 0))


class ReportTable(ctk.CTkFrame):
    """Themed Treeview table with totals bar and empty state."""

    def __init__(self, parent, columns: List[Dict[str, Any]]):
        super().__init__(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        self.pack(fill="both", expand=True)
        self.pack_propagate(False)
        self.columns = columns

        # Totals / summary bar (reused for the empty state too)
        self.totals_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY, anchor="w",
        )
        self.totals_label.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_MD, config.SPACING_SM))

        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)

        column_ids = [c["id"] for c in columns]
        self.tree = ttk.Treeview(tree_frame, columns=column_ids, show="headings", selectmode="browse")
        for col in columns:
            self.tree.heading(col["id"], text=col["heading"])
            self.tree.column(
                col["id"], width=col.get("width", 140),
                anchor=col.get("anchor", "w"),
            )
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True,
                       padx=(config.SPACING_LG, 0), pady=(0, config.SPACING_LG))
        vsb.pack(side="right", fill="y", pady=(0, config.SPACING_LG))
        hsb.pack(side="bottom", fill="x")

        self.empty_label = ctk.CTkLabel(
            self, text="No data to display.", font=ctk.CTkFont(size=14),
            text_color=config.COLOR_TEXT_MUTED,
        )
        self.empty_label.pack(pady=(config.SPACING_XXL, config.SPACING_XXL))

    def clear(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

    def set_rows(self, rows: Iterable[Iterable[Any]]) -> None:
        """Replace table contents with the given rows (zebra-striped)."""
        self.clear()
        for index, row in enumerate(rows):
            self.tree.insert("", tk.END, values=tuple(row),
                             tags=('even' if index % 2 == 0 else 'odd',))

    def show_empty(self, message: str = "No data to display.") -> None:
        self.clear()
        self.totals_label.configure(text="")
        self.empty_label.configure(text=message)
        self.empty_label.lift()

    def hide_empty(self) -> None:
        self.empty_label.lower()
        self.empty_label.configure(text="")

    def set_totals(self, text: str) -> None:
        self.totals_label.configure(text=text)


class ReportStatusBar(ctk.CTkFrame):
    """Bottom status label."""

    def __init__(self, parent, initial: str = "Ready"):
        super().__init__(parent, fg_color="transparent")
        self.pack(fill="x", pady=(config.SPACING_SM, 0))
        self.status_var = tk.StringVar(value=initial)
        ctk.CTkLabel(
            self, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x")

    def set(self, text: str) -> None:
        self.status_var.set(text)
        try:
            self.winfo_toplevel().update_idletasks()
        except Exception:
            pass


def make_date_entry(parent, var: tk.StringVar) -> ctk.CTkEntry:
    return ctk.CTkEntry(parent, textvariable=var, width=130,
                        corner_radius=config.INPUT_CORNER_RADIUS)


def make_readonly_combo(parent, values: List[str], var: tk.StringVar, width: int = 180) -> ctk.CTkComboBox:
    return ctk.CTkComboBox(
        parent, values=values, variable=var, width=width, state="readonly",
    )


def make_button(parent, text: str, command, width: int = 90, accent: bool = False) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, width=width, height=30,
        corner_radius=config.BUTTON_CORNER_RADIUS, command=command,
        fg_color=config.COLOR_PRIMARY if accent else None,
        hover_color=config.COLOR_PRIMARY_HOVER if accent else None,
        text_color="#FFFFFF" if accent else None,
    )
