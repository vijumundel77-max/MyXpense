"""
Expenzo — Global Date Control dialogs (Alt+F2 period, F2 single date).

Two truly-modal, non-movable date windows:

    DatePeriodDialog  — From Date / To Date, Apply (Enter) / Cancel (Esc)
    DateDialog        — single date, Apply (Enter) / Cancel (Esc)

Both reuse the existing ``report_base.DatePicker`` calendar so the calendar
behavior is identical to every other screen.  The window grabs all input
(``grab_set``) — the underlying screen cannot be interacted with while the
window is open, clicking outside does not close it, and it cannot be moved.
The user must press Enter (Apply) or Esc (Cancel).
"""
from __future__ import annotations

import tkinter as tk
from datetime import date
from typing import Any, Callable, Optional

import customtkinter as ctk

import config
from services.date_control_service import date_control
from ui.report_base import DatePicker, make_date_picker


def _today_str() -> str:
    return date.today().strftime(config.DISPLAY_DATE_FORMAT)


class _BaseDateDialog(ctk.CTkToplevel):
    """Shared modal shell: grab, non-movable, Enter/Esc handling.

    ``focus_date_entry`` (True for the global F2/Alt+F2 shortcuts) puts
    keyboard focus directly on the dialog's date entry (current value
    selected), so the user can type a date immediately — no mouse click.
    """

    def __init__(self, parent: tk.Widget, title: str,
                 focus_date_entry: bool = False):
        super().__init__(parent)
        self.parent = parent
        self.result: Any = None
        self._applied = False
        self._focus_date_entry = focus_date_entry
        self._date_entry: Optional[tk.Widget] = None

        self.title(title)
        self.transient(parent)
        # Block the underlying window completely.
        self.grab_set()
        self.configure(fg_color=config.COLOR_BG_SECONDARY)

        # Non-movable: override the WM hints so the window manager will not
        # let the user drag it (programmatic centering still works).
        try:
            self.overrideredirect(True)
        except Exception:
            pass

        # Center over the parent.
        self.update_idletasks()
        try:
            w = int(self.winfo_reqwidth())
            h = int(self.winfo_reqheight())
            x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._apply())
        self.bind("<KP_Enter>", lambda _e: self._apply())
        # Alt+F2 / F2 re-press while open must not spawn another dialog.
        self.bind("<Alt-F2>", lambda _e: "break")
        self.bind("<F2>", lambda _e: "break")

        self._build_body()

        self.update_idletasks()
        self.focus_force()
        self._focus_first()

    # -- overridable -------------------------------------------------- #
    def _build_body(self) -> None:
        raise NotImplementedError

    def _focus_first(self) -> None:
        # Put keyboard focus on the date entry (with its current value
        # selected) so the user can type a date immediately — no mouse click.
        entry = self._date_entry
        if entry is not None and hasattr(entry, "focus_set"):
            try:
                entry.focus_set()
                entry.select_range(0, "end")
                entry.icursor("end")
                return
            except Exception:
                pass
        try:
            self.focus_set()
        except Exception:
            pass

    # -- actions ------------------------------------------------------ #
    def _apply(self) -> None:
        self._applied = True
        self._on_apply()
        self._restore_focus()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _cancel(self) -> None:
        self._applied = False
        self._restore_focus()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _restore_focus(self) -> None:
        """Return focus to the underlying window so global shortcuts
        (F2 / Alt+F2) keep working immediately after closing."""
        try:
            self.parent.focus_force()
            self.parent.lift()
        except Exception:
            pass

    def _on_apply(self) -> None:
        raise NotImplementedError


class DatePeriodDialog(_BaseDateDialog):
    """Alt+F2: choose a From/To date period.  Enter applies, Esc cancels."""

    def __init__(self, parent: tk.Widget, on_apply: Optional[Callable[[date, date], None]] = None,
                 focus_date_entry: bool = False):
        self.on_apply_cb = on_apply
        company_id = _resolve_company_id(parent)
        fy_start, fy_end = date_control.company_financial_year(company_id)
        # Defaults: existing/current app behavior (today..today), but always
        # inside the company's Financial Year when today is out of range.
        today = date.today()
        default_from = max(fy_start, today) if today < fy_start else today
        default_to = min(fy_end, today) if today > fy_end else today
        self._min_date, self._max_date = fy_start, fy_end
        self.from_date = default_from
        self.to_date = default_to
        super().__init__(parent, "Date Period — Alt+F2",
                         focus_date_entry=focus_date_entry)

    def _build_body(self) -> None:
        ctk.CTkLabel(
            self, text="Date Period", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=config.SPACING_XL, pady=(config.SPACING_LG, config.SPACING_XS))
        ctk.CTkLabel(
            self, text=f"Financial Year: {self._min_date.strftime('%d-%m-%Y')} — "
                       f"{self._max_date.strftime('%d-%m-%Y')}",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_MUTED,
        ).pack(padx=config.SPACING_XL, pady=(0, config.SPACING_MD))

        self.from_var = tk.StringVar(value=self.from_date.strftime(config.DISPLAY_DATE_FORMAT))
        self.to_var = tk.StringVar(value=self.to_date.strftime(config.DISPLAY_DATE_FORMAT))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=config.SPACING_XL, pady=config.SPACING_SM)
        ctk.CTkLabel(form, text="From Date", font=ctk.CTkFont(size=12),
                     text_color=config.COLOR_TEXT_SECONDARY).grid(
            row=0, column=0, sticky="w")
        from_widget = make_date_picker(form, self.from_var)
        from_widget.grid(row=1, column=0, sticky="w")
        self.from_entry = from_widget.search_entry
        ctk.CTkLabel(form, text="To Date", font=ctk.CTkFont(size=12),
                     text_color=config.COLOR_TEXT_SECONDARY).grid(
            row=0, column=1, sticky="w", padx=(config.SPACING_LG, 0))
        to_widget = make_date_picker(form, self.to_var)
        to_widget.grid(
            row=1, column=1, sticky="w", padx=(config.SPACING_LG, 0))
        self.to_entry = to_widget.search_entry

        # The global Alt+F2 shortcut lands on the From Date entry; Tab moves
        # to To Date.  The calendar button next to each entry still works.
        if self._focus_date_entry:
            self._date_entry = self.from_entry
            self.from_entry.bind("<Tab>", lambda _e: self._focus_to_entry())
            self.to_entry.bind("<Shift-Tab>", lambda _e: self._focus_from_entry())

        # Buttons.
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=config.SPACING_XL, pady=(config.SPACING_MD, config.SPACING_LG))
        ctk.CTkButton(btn_row, text="Apply", width=110, height=34,
                      corner_radius=config.BUTTON_CORNER_RADIUS, command=self._apply,
                      fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
                      text_color="#FFFFFF").pack(side="left", padx=(0, config.SPACING_SM))
        ctk.CTkButton(btn_row, text="Cancel", width=110, height=34,
                      corner_radius=config.BUTTON_CORNER_RADIUS, command=self._cancel,
                      fg_color="transparent", border_width=1,
                      border_color=config.COLOR_CARD_BORDER).pack(side="left")
        ctk.CTkLabel(btn_row, text="Enter Apply  •  Esc Cancel",
                     font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED
                     ).pack(side="left", padx=(config.SPACING_MD, 0))

    def _focus_from_entry(self) -> None:
        try:
            self.from_entry.focus_set()
        except Exception:
            pass

    def _focus_to_entry(self) -> None:
        try:
            self.to_entry.focus_set()
            self.to_entry.select_range(0, "end")
            self.to_entry.icursor("end")
        except Exception:
            pass

    def _on_apply(self) -> None:
        from_date = _parse_dmy(self.from_var.get(), self.from_date)
        to_date = _parse_dmy(self.to_var.get(), self.to_date)
        if to_date < from_date:
            from_date, to_date = to_date, from_date
        date_control.set_period(from_date, to_date)
        if self.on_apply_cb:
            try:
                self.on_apply_cb(from_date, to_date)
            except Exception:
                pass


class DateDialog(_BaseDateDialog):
    """F2: choose a single date.  Enter applies, Esc cancels."""

    def __init__(self, parent: tk.Widget, on_apply: Optional[Callable[[date], None]] = None,
                 focus_date_entry: bool = False):
        self.on_apply_cb = on_apply
        company_id = _resolve_company_id(parent)
        fy_start, fy_end = date_control.company_financial_year(company_id)
        self._min_date, self._max_date = fy_start, fy_end
        self.selected = date.today()
        super().__init__(parent, "Select Date — F2",
                         focus_date_entry=focus_date_entry)

    def _build_body(self) -> None:
        ctk.CTkLabel(
            self, text="Select Date", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=config.SPACING_XL, pady=(config.SPACING_LG, config.SPACING_XS))
        ctk.CTkLabel(
            self, text=f"Financial Year: {self._min_date.strftime('%d-%m-%Y')} — "
                       f"{self._max_date.strftime('%d-%m-%Y')}",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_MUTED,
        ).pack(padx=config.SPACING_XL, pady=(0, config.SPACING_MD))

        self.date_var = tk.StringVar(value=self.selected.strftime(config.DISPLAY_DATE_FORMAT))
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=config.SPACING_XL, pady=config.SPACING_SM)
        ctk.CTkLabel(form, text="Date", font=ctk.CTkFont(size=12),
                     text_color=config.COLOR_TEXT_SECONDARY).pack(anchor="w")
        date_widget = make_date_picker(form, self.date_var)
        date_widget.pack(anchor="w")
        self.date_entry = date_widget.search_entry
        if self._focus_date_entry:
            self._date_entry = self.date_entry

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=config.SPACING_XL, pady=(config.SPACING_MD, config.SPACING_LG))
        ctk.CTkButton(btn_row, text="Apply", width=110, height=34,
                      corner_radius=config.BUTTON_CORNER_RADIUS, command=self._apply,
                      fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
                      text_color="#FFFFFF").pack(side="left", padx=(0, config.SPACING_SM))
        ctk.CTkButton(btn_row, text="Cancel", width=110, height=34,
                      corner_radius=config.BUTTON_CORNER_RADIUS, command=self._cancel,
                      fg_color="transparent", border_width=1,
                      border_color=config.COLOR_CARD_BORDER).pack(side="left")
        ctk.CTkLabel(btn_row, text="Enter Apply  •  Esc Cancel",
                     font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_MUTED
                     ).pack(side="left", padx=(config.SPACING_MD, 0))

    def _on_apply(self) -> None:
        day = _parse_dmy(self.date_var.get(), self.selected)
        date_control.set_single_date(day)
        if self.on_apply_cb:
            try:
                self.on_apply_cb(day)
            except Exception:
                pass


def _parse_dmy(raw: str, fallback: date) -> date:
    try:
        return date_control._parse_dmy(raw) or fallback
    except Exception:
        return fallback


def _resolve_company_id(parent: tk.Widget) -> int:
    try:
        top = parent.winfo_toplevel()
        company_id = getattr(top, "current_company_id", None)
        if company_id is not None:
            return int(company_id)
    except Exception:
        pass
    try:
        from database.database import db
        row = db.fetch_one("SELECT id FROM companies ORDER BY id LIMIT 1")
        return int(row["id"]) if row else 1
    except Exception:
        return 1


def show_date_period_dialog(parent: tk.Widget,
                            on_apply: Optional[Callable[[date, date], None]] = None,
                            focus_date_entry: bool = False) -> DatePeriodDialog:
    """Open the modal Date Period window (Alt+F2).

    ``focus_date_entry`` (set by the Alt+F2 shortcut) focuses the From Date
    entry so no mouse click is needed.
    """
    return DatePeriodDialog(parent, on_apply,
                            focus_date_entry=focus_date_entry)


def show_date_dialog(parent: tk.Widget,
                     on_apply: Optional[Callable[[date], None]] = None,
                     focus_date_entry: bool = False) -> DateDialog:
    """Open the modal single-date window (F2).

    ``focus_date_entry`` (set by the F2 shortcut) focuses the date entry so
    no mouse click is needed.
    """
    return DateDialog(parent, on_apply,
                      focus_date_entry=focus_date_entry)
