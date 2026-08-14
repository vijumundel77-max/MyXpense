"""
Expenzo — Report Base
Shared building blocks for the Expenzo report screens: themed header,
compact grid filter bar, calendar date picker, Treeview table, totals bar,
fixed action bar, and status bar.

Layout contract (every report follows it):

    header (fixed)
    filter bar (compact, wraps to 2 rows at most)
    table (flexible, takes the majority of the window)
    totals (fixed)
    action bar (fixed)

Only the table's rows scroll; the header, filter bar, totals and action bar
stay visible.
"""
from __future__ import annotations

import calendar as _cal
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk
from typing import Any, Callable, Dict, Iterable, List, Optional

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
    """Compact responsive filter bar.

    Fields are laid out in a wrapping grid (up to 4 per row) instead of one
    long horizontal strip, so the filter card stays short and the table gets
    the majority of the window.  Related controls share rows; ``add_actions``
    places the Generate/Clear buttons on the last row.
    """

    _PER_ROW = 4  # max field slots per row

    def __init__(self, parent):
        super().__init__(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        self.pack(fill="x", pady=(0, config.SPACING_LG))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_SM)
        for col in range(self._PER_ROW * 2):
            self.body.grid_columnconfigure(col, weight=0)
        self._slots: List[tk.Widget] = []
        self._actions_row_created = False

    def add(self, label: str, widget) -> None:
        """Add a labelled field.  Fields fill the current row left-to-right
        and wrap to the next row after ``_PER_ROW`` fields.

        ``widget`` must be a child of ``self.body`` (created with
        ``filters.body`` as parent); it is grid-placed directly so no
        pack/grid geometry conflict occurs.
        """
        index = len(self._slots)
        row = index // self._PER_ROW
        col = (index % self._PER_ROW) * 2
        ctk.CTkLabel(
            self.body, text=label, font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).grid(row=row, column=col, sticky="w", padx=(0, config.SPACING_SM),
               pady=(config.SPACING_XS, 0))
        widget.grid(row=row, column=col + 1, sticky="w",
                    padx=(0, config.SPACING_LG), pady=(0, config.SPACING_XS))
        self.body.grid_columnconfigure(col + 1, weight=1)
        self._slots.append(widget)

    def add_actions(self, *buttons: ctk.CTkButton) -> None:
        """Place Generate/Clear buttons on their own row below the fields.

        Buttons are children of ``self.body``; they are grid-placed so no
        pack/grid conflict occurs.  The action row always starts on a fresh
        grid row so the filter card stays readable.
        """
        row = (len(self._slots) + self._PER_ROW - 1) // self._PER_ROW
        self._action_row = row
        for offset, button in enumerate(buttons):
            button.grid(row=row, column=offset, sticky="w",
                        padx=(0, config.SPACING_SM), pady=(config.SPACING_SM, 0))
        self._slots.extend(buttons)
        self._actions_row_created = True

    def add_modify_filters(self) -> None:
        """Add a 'Modify Filters' action on the action row.

        The filter bar is always visible and its fields stay editable; this
        action makes sure the user lands on the first filter field (and shows
        the filter card again if a report ever hid it to give the table the
        full window).
        """
        if getattr(self, "_modify_filters_btn", None) is not None:
            return
        # The action row is where Generate/Clear live (recorded by
        # ``add_actions``).  Modify Filters sits right after them on the same
        # row so the filter card stays compact (fields row + action row).
        action_row = getattr(self, "_action_row", 0)
        action_cols = 0
        for child in self.body.winfo_children():
            info = child.grid_info()
            if info and int(info.get("row", -1)) == action_row:
                action_cols = max(action_cols, int(info.get("column", 0)) + 1)
        button = make_button(self.body, "Modify Filters", self._focus_filters,
                             width=130)
        button.grid(row=action_row, column=action_cols, sticky="w",
                    padx=(0, config.SPACING_SM), pady=(config.SPACING_SM, 0))
        self._slots.append(button)
        self._modify_filters_btn = button

    def _focus_filters(self) -> None:
        """Reveal the filter card if hidden, then focus its first entry."""
        try:
            if self.winfo_manager() == "":
                self.pack(fill="x", pady=(0, config.SPACING_LG))
        except Exception:
            pass
        for child in self.body.winfo_children():
            if isinstance(child, ctk.CTkEntry):
                try:
                    child.focus_set()
                    return
                except Exception:
                    continue
            for sub in child.winfo_children():
                if isinstance(sub, ctk.CTkEntry):
                    try:
                        sub.focus_set()
                        return
                    except Exception:
                        continue


class DatePicker:
    """Calendar popup for date entry.

    Clicking a date entry opens a themed calendar Toplevel; picking a day
    writes the value back to the StringVar in ``DD-MM-YYYY`` display format
    (database storage format is untouched).  Keyboard entry into the entry
    still works, and the report's existing validation remains intact.
    """

    def __init__(self, parent: tk.Widget, var: tk.StringVar,
                 on_change: Optional[Callable[[], None]] = None):
        self.parent = parent
        self.var = var
        self.on_change = on_change
        self._popup: Optional[tk.Toplevel] = None

    def _parse(self, raw: str) -> date:
        try:
            return datetime.strptime(raw.strip(), config.DISPLAY_DATE_FORMAT).date()
        except ValueError:
            return date.today()

    def _format(self, day: date) -> str:
        return day.strftime(config.DISPLAY_DATE_FORMAT)

    def open(self) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            try:
                self._popup.lift()
                self._popup.focus_set()
                return
            except Exception:
                pass
        try:
            self.parent.winfo_toplevel().withdraw()
        except Exception:
            pass
        popup = ctk.CTkToplevel(self.parent)
        popup.title("Select Date")
        popup.geometry("340x380")
        popup.resizable(False, False)
        popup.configure(fg_color=config.COLOR_BG_SECONDARY)
        popup.transient(self.parent.winfo_toplevel())
        popup.grab_set()
        self._popup = popup

        now = self._parse(self.var.get())
        view_year, view_month = now.year, now.month

        header = ctk.CTkFrame(popup, fg_color="transparent")
        header.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_MD, config.SPACING_SM))
        month_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=15, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY, width=160,
        )
        month_label.pack(side="left")

        def _prev() -> None:
            nonlocal view_year, view_month
            view_month -= 1
            if view_month < 1:
                view_month = 12
                view_year -= 1
            _draw(view_year, view_month)

        def _next() -> None:
            nonlocal view_year, view_month
            view_month += 1
            if view_month > 12:
                view_month = 1
                view_year += 1
            _draw(view_year, view_month)

        ctk.CTkButton(
            header, text="▶", width=30, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=_next,
        ).pack(side="right")
        ctk.CTkButton(
            header, text="◀", width=30, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=_prev,
        ).pack(side="right", padx=(0, config.SPACING_XS))

        grid = ctk.CTkFrame(popup, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(0, config.SPACING_SM))
        for col in range(7):
            grid.grid_columnconfigure(col, weight=1)
        for row in range(7):
            grid.grid_rowconfigure(row, weight=1)

        day_names = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for col, name in enumerate(day_names):
            ctk.CTkLabel(
                grid, text=name, font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLOR_TEXT_MUTED,
            ).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)

        def _draw(year: int, month: int) -> None:
            month_label.configure(text=f"{_cal.month_name[month]} {year}")
            for child in grid.winfo_children():
                if int(child.grid_info().get("row", 0)) > 0:
                    child.destroy()
            first_weekday, days_in_month = _cal.monthrange(year, month)
            # Monday-first offset.
            offset = (first_weekday - 0) % 7
            for day in range(1, days_in_month + 1):
                grid_row = (offset + day - 1) // 7 + 1
                grid_col = (offset + day - 1) % 7

                def _pick(day=day):
                    try:
                        chosen = date(year, month, day)
                        self.var.set(self._format(chosen))
                        if self.on_change:
                            try:
                                self.on_change()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    finally:
                        try:
                            popup.destroy()
                        except Exception:
                            pass
                    self._popup = None

                selected = (year, month, day) == (now.year, now.month, now.day)
                ctk.CTkButton(
                    grid, text=str(day), width=36, height=30,
                    corner_radius=config.BUTTON_CORNER_RADIUS,
                    fg_color=config.COLOR_PRIMARY if selected else "transparent",
                    hover_color=config.COLOR_PRIMARY_HOVER if selected else config.COLOR_BG_TERTIARY,
                    text_color="#FFFFFF" if selected else config.COLOR_TEXT_PRIMARY,
                    command=_pick,
                ).grid(row=grid_row, column=grid_col, sticky="nsew", padx=1, pady=1)

        footer = ctk.CTkFrame(popup, fg_color="transparent")
        footer.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_MD))
        ctk.CTkButton(
            footer, text="Today", width=80, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=lambda: (self.var.set(self._format(date.today())),
                             self.on_change() if self.on_change else None,
                             popup.destroy()),
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="Cancel", width=80, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1,
            command=popup.destroy,
        ).pack(side="right")

        popup.bind("<Escape>", lambda _e: popup.destroy())
        _draw(view_year, view_month)
        popup.after(50, lambda: (popup.lift(), popup.focus_set()))


def make_date_picker(parent, var: tk.StringVar,
                     on_change: Optional[Callable[[], None]] = None) -> ctk.CTkFrame:
    """Entry + calendar button that opens the DatePicker calendar."""
    holder = ctk.CTkFrame(parent, fg_color="transparent")
    entry = ctk.CTkEntry(holder, textvariable=var, width=110,
                         corner_radius=config.INPUT_CORNER_RADIUS, height=30)
    entry.pack(side="left")
    picker = DatePicker(holder, var, on_change)
    ctk.CTkButton(
        holder, text="📅", width=30, height=30,
        corner_radius=config.INPUT_CORNER_RADIUS,
        fg_color=config.COLOR_BG_TERTIARY, command=picker.open,
    ).pack(side="left", padx=(4, 0))
    holder.search_entry = entry
    return holder


def make_date_entry(parent, var: tk.StringVar) -> ctk.CTkEntry:
    return ctk.CTkEntry(parent, textvariable=var, width=130,
                        corner_radius=config.INPUT_CORNER_RADIUS)


class ReportTable(ctk.CTkFrame):
    """Themed Treeview table with totals bar and empty state.

    Packed with ``fill=both, expand=True`` so it takes the majority of the
    window; only the tree's rows scroll.  The totals bar stays fixed on top.
    """

    def __init__(self, parent, columns: List[Dict[str, Any]]):
        super().__init__(
            parent, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        self.pack(fill="both", expand=True)
        self.pack_propagate(False)
        self.columns = columns

        # Totals / summary bar (fixed above the table rows)
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


class ReportActionBar(ctk.CTkFrame):
    """Fixed bottom action bar: Refresh / Export(s) / Clear / Back.

    Only buttons that are actually implemented are shown — the report passes
    a ``refresh`` callable and a list of ``export`` (label, command) pairs;
    ``clear`` and ``back`` are optional.
    """

    def __init__(self, parent, refresh: Optional[Callable[[], Any]] = None,
                 exports: Optional[List[tuple]] = None,
                 clear: Optional[Callable[[], Any]] = None,
                 back: Optional[Callable[[], Any]] = None):
        super().__init__(parent, fg_color=config.COLOR_BG_SECONDARY,
                         corner_radius=config.CARD_CORNER_RADIUS,
                         border_width=1, border_color=config.COLOR_CARD_BORDER)
        self.pack(fill="x", pady=(config.SPACING_MD, 0))
        # Fixed compact height: the action bar must never stretch vertically.
        self.pack_propagate(False)
        self.configure(height=46)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", padx=config.SPACING_LG, pady=config.SPACING_SM)

        if refresh is not None:
            make_button(self.body, "Refresh", refresh).pack(
                side="left", padx=(0, config.SPACING_SM))
        for label, command in (exports or []):
            make_button(self.body, label, command).pack(
                side="left", padx=(0, config.SPACING_SM))
        if clear is not None:
            make_button(self.body, "Clear", clear).pack(
                side="left", padx=(0, config.SPACING_SM))
        spacer = ctk.CTkFrame(self.body, fg_color="transparent")
        spacer.pack(side="left", fill="x", expand=True)
        if back is not None:
            make_button(self.body, "← Back", back, width=110).pack(side="left")


class ReportBackHeader(ctk.CTkFrame):
    """Compact report header with a back arrow (returns to the Reports hub)."""

    def __init__(self, parent, title: str, subtitle: str = "",
                 on_back: Optional[Callable[[], Any]] = None):
        super().__init__(parent, fg_color="transparent")
        self.pack(fill="x", pady=(0, config.SPACING_LG))
        if on_back is not None:
            ctk.CTkButton(
                self, text="←", width=36, height=32,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                command=on_back,
            ).pack(side="left")
        title_block = ctk.CTkFrame(self, fg_color="transparent")
        title_block.pack(side="left", padx=(config.SPACING_MD if on_back else 0, 0))
        ctk.CTkLabel(
            title_block, text=title, font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(
                title_block, text=subtitle, font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(anchor="w")


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


def wire_report_keyboard(view) -> None:
    """Give a report screen the conventional ``on_keyboard_*`` hooks.

    The Reports hub forwards F5 / Ctrl+F / Esc to the open report UI via
    these methods, so every report behaves consistently:

    - F5 regenerates the report (falls back to ``_generate_report``).
    - Ctrl+F focuses the report's search entry (falls back to the first
      filter entry).
    - Ctrl+S regenerates the report too (reports are read-only).
    - Esc is handled by the hub (which closes the report and returns to the
      Reports hub), never by the report itself.
    """
    if getattr(view, "on_keyboard_refresh", None) is None:
        view.on_keyboard_refresh = lambda: getattr(
            view, "_generate_report", lambda: None)()
    if getattr(view, "on_keyboard_search", None) is None:
        def _focus_search() -> None:
            entry = getattr(view, "search_entry", None)
            if entry is not None and hasattr(entry, "focus_set"):
                try:
                    entry.focus_set()
                    entry.select_range(0, "end")
                    return
                except Exception:
                    pass
            filters = getattr(view, "filters", None) or getattr(view, "filter_bar", None)
            if filters is not None and hasattr(filters, "body"):
                for child in filters.body.winfo_children():
                    for sub in child.winfo_children():
                        if isinstance(sub, ctk.CTkEntry):
                            try:
                                sub.focus_set()
                                return
                            except Exception:
                                pass
        view.on_keyboard_search = _focus_search
    if getattr(view, "on_keyboard_save", None) is None:
        view.on_keyboard_save = lambda: getattr(
            view, "_generate_report", lambda: None)()
    if getattr(view, "on_keyboard_new", None) is None:
        view.on_keyboard_new = lambda: None
