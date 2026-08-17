"""
Expenzo — Global Date Control Service

A single, app-wide date mechanism behind Alt+F2 (Date Period) and F2
(Single Date).  The service owns the *state* (the currently selected
period / single date) and knows how to *dispatch* it to the active screen:

    period:  (from_date, to_date)  applied via view.on_global_date_period()
    single:  date                  applied via view.on_global_single_date()

Every date-dependent screen implements the matching hook (or none at all
if it does not use that kind of date), so the mechanism is ONE global
control rather than N screen-specific implementations.  Screens that
already expose ``from_date_var`` / ``to_date_var`` (reports, cash/bank
books, party ledgers, …) get a default adapter automatically.

Default range comes from the active company's Financial Year; the
initial selection is the application's existing/current-date behavior.
No accounting calculation is changed — this only filters what is
displayed.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from database.database import db

DISPLAY_FORMAT = "%d-%m-%Y"


class DateControlService:
    """Global date state + dispatch to the active screen."""

    def __init__(self) -> None:
        self._period_from: Optional[date] = None
        self._period_to: Optional[date] = None
        self._single_date: Optional[date] = None
        self._company_id: Optional[int] = None

    # ------------------------------------------------------------------ #
    # company financial year (default valid range)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_dmy(value: Any) -> Optional[date]:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            for fmt in (DISPLAY_FORMAT, "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _parse_mm_dd(value: Any) -> Optional[tuple]:
        """Parse a ``DD-MM`` (no year) financial-year marker -> (month, day).

        A fixed year is appended so Python never hits ambiguous year-less
        date parsing; only month/day are used by the caller.
        """
        if isinstance(value, str):
            raw = value.strip().replace("/", "-")
            try:
                parsed = datetime.strptime(f"{raw}-2000", "%d-%m-%Y")
                return parsed.month, parsed.day
            except ValueError:
                pass
        return None

    @staticmethod
    def _row_get(row: Any, key: str, default: Any = None) -> Any:
        """Read a column from either a sqlite3.Row or a dict."""
        try:
            if hasattr(row, "keys"):
                keys = row.keys()
                if key in keys:
                    return row[key]
            return row[key]  # type: ignore[index]
        except Exception:
            return default

    def company_financial_year(self, company_id: int) -> Tuple[date, date]:
        """The active company's Financial Year as (start, end) dates.

        Financial year is stored as ``DD-MM`` (e.g. 01-04 / 31-03).  The
        year is resolved so the range contains today: if the FY start is
        after today, it belongs to the previous calendar year.  Falls back
        to books-begin .. FY-end (or today) when the company row is missing.
        """
        today = date.today()
        from_date = date(today.year, 4, 1)
        to_date = date(today.year, 3, 31)
        try:
            row = db.fetch_one(
                "SELECT financial_year_start, financial_year_end, books_begin_date "
                "FROM companies WHERE id = ?",
                (int(company_id),),
            )
        except Exception:
            row = None
        if row:
            start_raw = self._row_get(row, "financial_year_start", "01-04")
            end_raw = self._row_get(row, "financial_year_end", "31-03")
            books_begin = self._row_get(row, "books_begin_date", "")

            start_md = self._parse_mm_dd(start_raw) or (4, 1)
            end_md = self._parse_mm_dd(end_raw) or (3, 31)

            # FY that contains today.
            start = date(today.year, start_md[0], start_md[1])
            if start > today:
                start = date(today.year - 1, start_md[0], start_md[1])
            from_date = start
            end = date(start.year, end_md[0], end_md[1])
            if end < start:
                end = date(start.year + 1, end_md[0], end_md[1])
            to_date = end

            if books_begin:
                begin = self._parse_dmy(books_begin)
                if begin and begin > from_date:
                    from_date = begin
        return from_date, to_date

    # ------------------------------------------------------------------ #
    # state
    # ------------------------------------------------------------------ #
    def set_company(self, company_id: int) -> None:
        company_id = int(company_id)
        if self._company_id != company_id:
            changed = self._company_id is not None
            self._company_id = company_id
            # Reset to defaults only when switching to a different company.
            if changed:
                self.reset()

    def reset(self) -> None:
        self._period_from = None
        self._period_to = None
        self._single_date = None

    @property
    def has_period(self) -> bool:
        return self._period_from is not None and self._period_to is not None

    @property
    def has_single_date(self) -> bool:
        return self._single_date is not None

    def period(self, company_id: int) -> Tuple[date, date]:
        """Current period, defaulting to today (existing app behavior)."""
        if self.has_period:
            return self._period_from, self._period_to  # type: ignore[return-value]
        today = date.today()
        return today, today

    def single_date(self, company_id: int) -> date:
        """Current single date, defaulting to today."""
        if self.has_single_date:
            return self._single_date  # type: ignore[return-value]
        return date.today()

    def set_period(self, from_date: date, to_date: date) -> None:
        self._period_from = from_date
        self._period_to = to_date

    def set_single_date(self, day: date) -> None:
        self._single_date = day

    def fmt(self, day: date) -> str:
        return day.strftime(DISPLAY_FORMAT)

    # ------------------------------------------------------------------ #
    # dispatch to the active screen
    # ------------------------------------------------------------------ #
    @staticmethod
    def _set_string_var(view: Any, attr: str, day: date) -> None:
        var = getattr(view, attr, None)
        if var is not None and hasattr(var, "set"):
            try:
                var.set(day.strftime(DISPLAY_FORMAT))
            except Exception:
                pass

    def apply_to(self, view: Any, company_id: int) -> None:
        """Push the current global date state into the active screen.

        Dispatch order:
          1. the view's explicit hooks (on_global_date_period /
             on_global_single_date) — screens with custom semantics;
          2. otherwise, the shared adapter for screens exposing
             ``from_date_var`` / ``to_date_var`` / ``single_date_var``
             (reports, cash/bank books, ledgers, vouchers register…).
        The screen is responsible for regenerating its data (call its
        refresh / generate).  Nothing here touches accounting data.
        """
        if view is None:
            return
        self.set_company(company_id)

        used_hook = False
        period_hook = getattr(view, "on_global_date_period", None)
        if callable(period_hook):
            try:
                period_hook(self._period_from, self._period_to)
                used_hook = True
            except Exception:
                pass
        else:
            # Shared adapter: screens that expose from/to date vars.
            if hasattr(view, "from_date_var") and self._period_from is not None:
                self._set_string_var(view, "from_date_var", self._period_from)
            if hasattr(view, "to_date_var") and self._period_to is not None:
                self._set_string_var(view, "to_date_var", self._period_to)

        single_hook = getattr(view, "on_global_single_date", None)
        if callable(single_hook):
            try:
                single_hook(self._single_date)
                used_hook = True
            except Exception:
                pass
        elif hasattr(view, "single_date_var") and self._single_date is not None:
            self._set_string_var(view, "single_date_var", self._single_date)
        elif hasattr(view, "as_on_date_var") and self._single_date is not None:
            self._set_string_var(view, "as_on_date_var", self._single_date)

        # A screen with an explicit hook already regenerated its data; only
        # fall through to the generic refresh when the shared adapter set
        # date vars (so the screen re-renders with the new dates).
        if used_hook:
            return
        refresh = None
        for name in ("on_keyboard_refresh", "refresh", "refresh_vouchers",
                     "_generate_report", "on_global_date_refresh"):
            refresh = getattr(view, name, None)
            if callable(refresh):
                break
        if refresh is not None:
            try:
                refresh()
            except Exception:
                pass


date_control = DateControlService()
