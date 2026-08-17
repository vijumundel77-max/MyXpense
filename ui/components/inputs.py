"""
Expenzo — Input components.

Premium form building blocks: two-column responsive form grid, section cards,
labeled fields, money entry, date entry with calendar popup, search box,
combobox field, and toggle switch. All theme-aware.
"""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from typing import Callable, List, Optional

import customtkinter as ctk

import config


class FormGrid(ctk.CTkFrame):
    """A responsive grid of (label, widget) rows.

    ``columns`` controls the number of label/widget pairs per row (2 = typical
    desktop form layout). Pairs are laid out left-to-right, top-to-bottom.
    """

    def __init__(self, master, columns: int = 2, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.columns = columns
        self._cells: List[tuple] = []  # (label_text, widget, row, col)
        self._next_row = 0
        self._next_col = 0
        for c in range(columns):
            self.grid_columnconfigure(c * 2 + 1, weight=1)
            self.grid_columnconfigure(c * 2, weight=0, minsize=140)

    def add_field(self, label: str, widget, span: int = 1) -> None:
        """Add a labeled widget. ``span`` can merge columns (max: columns)."""
        row = self._next_row
        col = self._next_col
        if span > 1:
            self._next_col += span
        else:
            self._next_col += 1
        if self._next_col >= self.columns:
            self._next_row += 1
            self._next_col = 0

        ctk.CTkLabel(
            self, text=label, anchor="w",
            font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).grid(row=row, column=col * 2, sticky="e", padx=(0, config.SPACING_SM),
               pady=config.SPACING_XS)
        widget.grid(row=row, column=col * 2 + 1, sticky="ew",
                    padx=(0, config.SPACING_XL), pady=config.SPACING_XS)
        self._cells.append((label, widget, row, col))


class FormSection(ctk.CTkFrame):
    """A titled section card for grouping form fields."""

    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, corner_radius=config.CARD_CORNER_RADIUS,
                         fg_color=config.COLOR_BG_SECONDARY,
                         border_width=1, border_color=config.COLOR_CARD_BORDER,
                         **kwargs)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))
        ctk.CTkLabel(
            header, text=title, anchor="w",
            font=ctk.CTkFont(size=config.FONT_SUBTITLE_SIZE, weight="bold"),
        ).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                header, text=subtitle, anchor="w",
                font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(side="left", padx=(config.SPACING_SM, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True,
                       padx=config.SPACING_LG, pady=(0, config.SPACING_LG))


class MoneyEntry(ctk.CTkEntry):
    """A numeric entry pre-formatted as money."""

    def __init__(self, master, **kwargs):
        super().__init__(master, width=140, corner_radius=config.INPUT_CORNER_RADIUS, **kwargs)
        self.bind("<FocusOut>", self._format)
        self.bind("<Return>", lambda _e: self._format())

    def _format(self, _event=None) -> None:
        try:
            value = float(self.get() or 0)
            self.delete(0, tk.END)
            self.insert(0, f"{value:,.2f}")
        except ValueError:
            pass

    def get_value(self) -> float:
        try:
            return float(str(self.get()).replace(",", "").strip() or 0)
        except ValueError:
            return 0.0


class SearchBox(ctk.CTkEntry):
    """A search input that calls a callback on change."""

    def __init__(self, master, on_change: Callable[[str], None], **kwargs):
        super().__init__(master, corner_radius=config.INPUT_CORNER_RADIUS,
                         placeholder_text="Search…", height=32, **kwargs)
        self._on_change = on_change
        self.bind("<KeyRelease>", self._changed)

    def _changed(self, _event) -> None:
        try:
            self._on_change(self.get())
        except Exception:
            pass


class ComboField(ctk.CTkFrame):
    """A labeled readonly combobox."""

    def __init__(self, master, label: str, values: List[str], var: tk.StringVar,
                 width: int = 200, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        ctk.CTkLabel(
            self, text=label, anchor="w",
            font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x")
        self.combo = ctk.CTkComboBox(
            self, values=values, variable=var, width=width, state="readonly",
        )
        self.combo.pack(fill="x", pady=(config.SPACING_XS, 0))


class ToggleSwitch(ctk.CTkSwitch):
    """A themed toggle with a label."""

    def __init__(self, master, text: str, var: tk.BooleanVar, **kwargs):
        super().__init__(master, text=text, variable=var,
                         font=ctk.CTkFont(size=config.FONT_SMALL_SIZE), **kwargs)


class DateEntry(ctk.CTkEntry):
    """A date entry with a small calendar popup."""

    def __init__(self, master, var: Optional[tk.StringVar] = None, width: int = 130,
                 **kwargs):
        super().__init__(master, textvariable=var, width=width,
                         corner_radius=config.INPUT_CORNER_RADIUS, **kwargs)
        self._picker: Optional[tk.Toplevel] = None

    def open_calendar(self) -> None:
        """Open the calendar popup beneath the entry."""
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.lift()
            return
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except Exception:
            pass
        popup.configure(bg=config.COLOR_BG_SECONDARY)
        self._picker = popup

        today = date.today()
        view_year, view_month = today.year, today.month
        selected: Optional[date] = None

        header = ctk.CTkFrame(popup, fg_color=config.COLOR_BG_SECONDARY)
        header.pack(fill="x")

        def _redraw() -> None:
            for child in grid.winfo_children():
                child.destroy()
            ctk.CTkLabel(grid, text=f"{calendar.month_name[view_month]} {view_year}",
                         font=ctk.CTkFont(size=config.FONT_SMALL_SIZE, weight="bold"),
                         fg_color="transparent").grid(row=0, column=0, columnspan=7, pady=4)
            for day, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
                ctk.CTkLabel(grid, text=name, font=ctk.CTkFont(size=9),
                             text_color=config.COLOR_TEXT_MUTED).grid(row=1, column=day, padx=2)
            first = date(view_year, view_month, 1)
            start_col = first.weekday()
            days = calendar.monthrange(view_year, view_month)[1]
            for d in range(1, days + 1):
                col = (start_col + d - 1) % 7
                row = 2 + (start_col + d - 1) // 7
                is_today = (d == today.day and view_month == today.month
                            and view_year == today.year)
                ctk.CTkButton(
                    grid, text=str(d), width=28, height=24,
                    corner_radius=config.CHIP_RADIUS,
                    fg_color=config.COLOR_PRIMARY if is_today else "transparent",
                    hover_color=config.COLOR_HOVER_SURFACE,
                    text_color=config.COLOR_TEXT_PRIMARY,
                    font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
                    command=lambda dd=d: _pick(dd),
                ).grid(row=row, column=col, padx=1, pady=1)

        def _pick(day: int) -> None:
            picked = date(view_year, view_month, day)
            self.delete(0, tk.END)
            self.insert(0, picked.strftime(config.DISPLAY_DATE_FORMAT))
            popup.destroy()

        def _prev() -> None:
            nonlocal view_month, view_year
            if view_month == 1:
                view_month = 12
                view_year -= 1
            else:
                view_month -= 1
            _redraw()

        def _next() -> None:
            nonlocal view_month, view_year
            if view_month == 12:
                view_month = 1
                view_year += 1
            else:
                view_month += 1
            _redraw()

        ctk.CTkButton(header, text="‹", width=30, height=26, corner_radius=config.CHIP_RADIUS,
                      fg_color="transparent", text_color=config.COLOR_TEXT_SECONDARY,
                      command=_prev).pack(side="left", padx=4, pady=4)
        ctk.CTkButton(header, text="›", width=30, height=26, corner_radius=config.CHIP_RADIUS,
                      fg_color="transparent", text_color=config.COLOR_TEXT_SECONDARY,
                      command=_next).pack(side="right", padx=4, pady=4)

        grid = ctk.CTkFrame(popup, fg_color=config.COLOR_BG_SECONDARY)
        grid.pack(padx=8, pady=8)
        _redraw()

        try:
            self.update_idletasks()
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height() + 4
            popup.geometry(f"+{x}+{y}")
        except Exception:
            pass
        popup.bind("<Escape>", lambda _e: popup.destroy())
