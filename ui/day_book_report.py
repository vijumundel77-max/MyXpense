"""
Expenzo — Day Book (Voucher Register)

A chronological register of vouchers for the selected company and date range.
Each row is ONE voucher (not one ledger line):

    Date | Particulars | Vch Type | Vch No. | Amount

The Amount column shows the voucher's money movement ONCE:
  - Payment   (money OUT)  -> amount RED
  - Receipt   (money IN)   -> amount GREEN
  - Contra / Journal       -> neutral amount (no single direction)

The full debit/credit ledger lines stay in the accounting data and are shown
in the existing voucher editor (Enter / double-click / Open opens it).  The
accounting engine, schema and posting logic are untouched — only the Day Book
display changes.
"""
from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import customtkinter as ctk
from tkinter import ttk

import config
from services.voucher_register_service import voucher_register_service
from services.voucher_service import (
    VOUCHER_TYPES,
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    voucher_service,
)
from ui.report_base import (
    ReportBackHeader,
    ReportStatusBar,
    ReportActionBar,
    make_date_picker,
    make_readonly_combo,
    make_button,
    wire_report_keyboard,
)
from utils import dialogs


class DayBookReportUI:
    """Day Book (voucher register) — one row per voucher."""

    # One-row-per-voucher column order.
    _COLUMNS = [
        {"id": "date", "heading": "Date", "width": 100},
        {"id": "particulars", "heading": "Particulars", "width": 260},
        {"id": "vtype", "heading": "Vch Type", "width": 90},
        {"id": "vno", "heading": "Vch No.", "width": 110},
        {"id": "amount", "heading": "Amount", "width": 140, "anchor": "e"},
    ]

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL,
                             pady=config.SPACING_XL)

        ReportBackHeader(self.main_frame, "Day Book",
                         "Voucher register / day-wise transaction summary",
                         on_back=self._back)

        self._build_toolbar()
        self._build_filters()
        self._build_table()
        self._build_totals()

        ReportActionBar(
            self.main_frame,
            refresh=self._generate_report,
            exports=[("Export CSV", self._export_to_csv),
                     ("Export JSON", self._export_to_json),
                     ("Export PNG", self._export_to_png)],
            clear=self._clear_filters,
            back=self._back,
        )

        self.status = ReportStatusBar(self.main_frame)
        wire_report_keyboard(self)

    # ------------------------------------------------------------------ #
    # layout — toolbar
    # ------------------------------------------------------------------ #
    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, config.SPACING_LG))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_SM)

        self.btn_new = make_button(inner, "New Voucher", self._new_voucher, width=120)
        self.btn_new.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_open = make_button(inner, "Open / Edit", self._open_selected, width=120)
        self.btn_open.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_view = make_button(inner, "View", self._view_selected, width=90)
        self.btn_view.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_delete = make_button(inner, "Delete", self._delete_selected, width=90)
        self.btn_delete.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_refresh = make_button(inner, "Refresh", self._generate_report, width=100)
        self.btn_refresh.pack(side="left")

    # ------------------------------------------------------------------ #
    # layout — compact Tally-style filter area
    # ------------------------------------------------------------------ #
    def _build_filters(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, config.SPACING_LG))
        body = ctk.CTkFrame(bar, fg_color="transparent")
        body.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_SM)
        self.filters = bar

        self.from_date_var = tk.StringVar(
            value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(
            value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.type_var = tk.StringVar(value="All Types")
        self.search_var = tk.StringVar()

        self._filter_field(body, 0, "From Date",
                           make_date_picker(body, self.from_date_var))
        self._filter_field(body, 1, "To Date",
                           make_date_picker(body, self.to_date_var))
        self.type_combo = make_readonly_combo(
            body, ["All Types"] + list(VOUCHER_TYPES), self.type_var, 150)
        self._filter_field(body, 2, "Voucher Type", self.type_combo)

        # Search is clearly labelled so the box is never an unexplained blank.
        self.search_entry = ctk.CTkEntry(
            body, textvariable=self.search_var, width=220,
            placeholder_text="Search voucher / party / account / narration",
            corner_radius=config.INPUT_CORNER_RADIUS, height=30,
        )
        self._filter_field(body, 3, "Search", self.search_entry)

        make_button(body, "Generate / Refresh", self._generate_report,
                    width=150, accent=True).grid(
            row=0, column=8, sticky="w", padx=(config.SPACING_MD, 0),
            pady=(config.SPACING_XS, 0))

    def _filter_field(self, parent, column: int, label: str, widget) -> None:
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(row=0, column=column, sticky="w",
                    padx=(0 if column == 0 else config.SPACING_LG, 0))
        ctk.CTkLabel(
            holder, text=label, font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(anchor="w")
        widget.grid(row=1, column=0, sticky="w", pady=(2, 0))
        holder.search_entry = getattr(widget, "search_entry", None)

    # ------------------------------------------------------------------ #
    # layout — large full-window Tally-style table
    # ------------------------------------------------------------------ #
    def _build_table(self) -> None:
        container = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self.table_container = container

        # Fixed column header row (never scrolls away).
        header = ctk.CTkFrame(container, fg_color=config.COLOR_BG_TERTIARY,
                              corner_radius=0, height=32)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        for index, col in enumerate(self._COLUMNS):
            header.grid_columnconfigure(index, weight=1 if index in (1,) else 0)
            ctk.CTkLabel(
                header, text=col["heading"],
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
                anchor="w" if col.get("anchor", "w") == "w" else "e",
            ).grid(row=0, column=index, sticky="ew",
                   padx=(config.SPACING_LG if index == 0 else config.SPACING_SM,
                         config.SPACING_LG if index == len(self._COLUMNS) - 1 else config.SPACING_SM),
                   pady=4)

        # Scrollable body holding the ttk.Treeview.
        body = ctk.CTkScrollableFrame(
            container, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=config.COLOR_BG_TERTIARY,
        )
        body.grid(row=1, column=0, sticky="nsew")
        self.table_body = body

        column_ids = [c["id"] for c in self._COLUMNS]
        self.tree = ttk.Treeview(
            body, columns=column_ids, show="", selectmode="browse")
        for col in self._COLUMNS:
            self.tree.heading(col["id"], text=col["heading"])
            self.tree.column(
                col["id"], width=col.get("width", 140),
                anchor=col.get("anchor", "w"),
            )
        self.tree.pack(fill="both", expand=True)

        # Money direction is shown by the amount colour: money OUT (Payment)
        # is red, money IN (Receipt) is green.  The row keeps the theme
        # background and a clear selection highlight.
        self.tree.tag_configure("out", foreground=config.COLOR_EXPENSE)
        self.tree.tag_configure("in", foreground=config.COLOR_INCOME)
        self.tree.tag_configure("odd", background=config.COLOR_BG_MUTED)

        # Tally-style interactions: single click selects, Enter / double-click
        # open the voucher for edit.
        self.tree.bind("<ButtonRelease-1>", self._on_row_selected)
        self.tree.bind("<Return>", lambda _e: self._open_selected())
        self.tree.bind("<KP_Enter>", lambda _e: self._open_selected())
        self.tree.bind("<Double-Button-1>", lambda _e: self._open_selected())

        self.empty_label = ctk.CTkLabel(
            container, text="Select dates and generate the Day Book to begin.",
            font=ctk.CTkFont(size=14), text_color=config.COLOR_TEXT_MUTED,
        )
        self.empty_label.grid(row=1, column=0)

    # ------------------------------------------------------------------ #
    # layout — totals
    # ------------------------------------------------------------------ #
    def _build_totals(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(config.SPACING_MD, 0))
        self.totals_label = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY, anchor="e",
        )
        self.totals_label.pack(fill="x", padx=config.SPACING_LG,
                               pady=config.SPACING_SM)

    # ------------------------------------------------------------------ #
    # interactions
    # ------------------------------------------------------------------ #
    def _on_row_selected(self, _event=None) -> None:
        """Single click selects a row; the voucher is ready for Open/View."""
        return None

    def _selected_voucher_id(self) -> Optional[int]:
        selection = self.tree.selection()
        if not selection:
            return None
        # Rows are keyed by the voucher id.
        try:
            return int(selection[0])
        except (ValueError, TypeError):
            return None

    def _selected_voucher(self) -> Optional[Dict[str, Any]]:
        voucher_id = self._selected_voucher_id()
        if voucher_id is None:
            return None
        return voucher_service.get_voucher_with_details(voucher_id)

    def _open_selected(self) -> None:
        voucher = self._selected_voucher()
        if voucher is None:
            dialogs.warn("Day Book", "Select a voucher to open.", parent=self.parent)
            return
        self._open_voucher_in_editor(voucher)

    def _view_selected(self) -> None:
        voucher = self._selected_voucher()
        if voucher is None:
            dialogs.warn("Day Book", "Select a voucher to view.", parent=self.parent)
            return
        self._open_voucher_in_editor(voucher, read_only=True)

    def _delete_selected(self) -> None:
        voucher = self._selected_voucher()
        if voucher is None:
            dialogs.warn("Day Book", "Select a voucher to delete.", parent=self.parent)
            return
        from services.voucher_service import STATUS_CANCELLED
        if voucher.get('status') == STATUS_CANCELLED:
            dialogs.warn("Day Book", "This voucher is already cancelled.",
                         parent=self.parent)
            return
        if not dialogs.confirm_destructive(
                "Delete Voucher", "voucher", voucher.get('voucher_number', ''),
                parent=self.parent):
            return
        ok, message = voucher_service.cancel_voucher(voucher['id'], self.company_id)
        if not ok:
            dialogs.error("Day Book", message, parent=self.parent)
            return
        dialogs.info("Day Book", message, parent=self.parent)
        self._generate_report()

    def _new_voucher(self) -> None:
        """Route to the existing Voucher Entry screen (new voucher)."""
        self._route_to_vouchers()

    def _open_voucher_in_editor(self, voucher: Dict[str, Any],
                                read_only: bool = False) -> None:
        """Open the existing Voucher Entry screen and load the voucher."""
        self._route_to_vouchers()
        try:
            app = self.winfo_toplevel()
            view = getattr(app, "current_view", None)
            if view is not None and hasattr(view, "_load_voucher"):
                view._load_voucher(voucher)
                if read_only:
                    view._set_read_only(True)
        except Exception:
            pass

    def _route_to_vouchers(self) -> None:
        try:
            app = self.winfo_toplevel()
            if hasattr(app, "show_vouchers"):
                app.show_vouchers()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _clear_filters(self) -> None:
        self.from_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.type_var.set("All Types")
        self.search_var.set("")
        self._show_empty("Select dates and generate the Day Book to begin.")
        self.status.set("Filters cleared")

    def _parse_date(self, raw: str) -> Optional[date]:
        for fmt in (config.DISPLAY_DATE_FORMAT, config.DB_DATE_FORMAT):
            try:
                return datetime.strptime(raw.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _format_date(self, raw: str) -> str:
        """Display dates as DD-MM-YYYY (database ISO stays unchanged)."""
        d = self._parse_date(raw)
        if d is None:
            return raw
        return d.strftime(config.DISPLAY_DATE_FORMAT)

    def _generate_report(self) -> None:
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Day Book", "Invalid date. Use DD-MM-YYYY format.",
                         parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Day Book", "From Date cannot be after To Date.",
                         parent=self.parent)
            return
        report = voucher_register_service.generate_day_book(
            self.company_id,
            from_date,
            to_date,
            voucher_type="" if self.type_var.get() == "All Types" else self.type_var.get(),
            search_term=self.search_var.get().strip(),
        )
        if not report.get('success'):
            dialogs.error("Day Book", report.get('error', 'Failed to generate report'),
                          parent=self.parent)
            return
        self.current_report_data = report
        self._render(report)

    def _render(self, report: Dict[str, Any]) -> None:
        entries = report.get('entries', [])
        self._show_empty("No vouchers found for the selected period.") if not entries \
            else self._hide_empty()
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Collapse the per-ledger-line entries into ONE row per voucher.  The
        # particulars show the party/counter-party ledger; the amount is the
        # voucher's money movement shown once (red for money out / Payment,
        # green for money in / Receipt).  The full Dr/Cr lines remain in the
        # accounting data and are visible in the voucher editor.
        vouchers: Dict[int, Dict[str, Any]] = {}
        for entry in entries:
            voucher_id = int(entry.get('voucher_id', 0) or 0)
            if voucher_id not in vouchers:
                particulars = self._voucher_particulars(entries, voucher_id, entry)
                vouchers[voucher_id] = {
                    'voucher_id': voucher_id,
                    'date': entry.get('voucher_date', ''),
                    'particulars': particulars,
                    'vtype': entry.get('voucher_type', ''),
                    'vno': entry.get('voucher_number', ''),
                    'debit': 0.0,
                    'credit': 0.0,
                }
            voucher = vouchers[voucher_id]
            voucher['debit'] += float(entry.get('debit_amount', 0) or 0)
            voucher['credit'] += float(entry.get('credit_amount', 0) or 0)

        total_out = 0.0
        total_in = 0.0
        for index, voucher in enumerate(vouchers.values()):
            # A balanced voucher's debit and credit totals are equal — the
            # amount is the money moved (shown once), so take the larger side.
            amount = round(max(voucher['debit'], voucher['credit']), 2)
            vtype = voucher['vtype']
            # Money OUT (Payment) -> red; money IN (Receipt) -> green.
            if vtype == VOUCHER_PAYMENT:
                total_out += amount
                tags = ("out",)
            elif vtype == VOUCHER_RECEIPT:
                total_in += amount
                tags = ("in",)
            else:
                # Contra / Journal move money within the books — neutral.
                tags = ()
            if index % 2:
                tags = tags + ("odd",)
            self.tree.insert("", tk.END, iid=str(voucher['voucher_id']), values=(
                self._format_date(voucher['date']),
                voucher['particulars'],
                vtype,
                voucher['vno'],
                f"{amount:,.2f}",
            ), tags=tags)
        self.totals_label.configure(
            text=f"Total Out: {total_out:,.2f}    "
                 f"Total In: {total_in:,.2f}    "
                 f"({len(vouchers)} vouchers)")
        self.status.set(
            f"Day Book generated: {len(vouchers)} vouchers "
            f"({self._format_date(report.get('from_date', ''))} to "
            f"{self._format_date(report.get('to_date', ''))})"
        )

    def _voucher_particulars(self, entries: List[Dict[str, Any]],
                             voucher_id: int, fallback: Dict[str, Any]) -> str:
        """The party/counter-party ledger for a voucher's row.

        Prefers the party account (Sundry Debtors / Sundry Creditors) so the
        Day Book reads like a cash book (Anita, SBI Bank); falls back to the
        first non-cash/bank ledger, then any account name.
        """
        lines = [e for e in entries if int(e.get('voucher_id', 0) or 0) == voucher_id]
        if not lines:
            return fallback.get('account_name', '')
        party = None
        fallback_name = ""
        for line in lines:
            group = str(line.get('account_group', '') or '')
            name = str(line.get('account_name', '') or '')
            if not name:
                continue
            if group in ("Sundry Debtors", "Sundry Creditors"):
                party = name
                break
            if not fallback_name:
                fallback_name = name
        return party or fallback_name or fallback.get('account_name', '')

    def _show_empty(self, message: str) -> None:
        self.empty_label.configure(text=message)
        self.empty_label.lift()
        self.totals_label.configure(text="")

    def _hide_empty(self) -> None:
        self.empty_label.lower()

    # ------------------------------------------------------------------ #
    # export
    # ------------------------------------------------------------------ #
    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_table_to_png(self.table_container,
                                                            "day_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        success, path = voucher_register_service.export_day_book_to_csv(
            self.current_report_data, "day_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        success, path = report_exporter.export_to_json(self.current_report_data,
                                                       "day_book")
        if success:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_day_book_report(parent: tk.Widget, company_id: int) -> DayBookReportUI:
    return DayBookReportUI(parent, company_id)
