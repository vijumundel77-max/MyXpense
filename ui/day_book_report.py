"""
Expenzo — Day Book (Voucher Register) – Ultra‑Compact High‑Density Redesign
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
from services.date_control_service import date_control
from ui.report_base import (
    ReportBackHeader,
    ReportStatusBar,
    make_date_picker,
    make_readonly_combo,
    make_button,
    wire_report_keyboard,
)
from utils import dialogs


class DayBookReportUI:
    """Day Book (voucher register) — one row per voucher, ultra‑compact."""

    _COLUMNS = [
        {"id": "date", "heading": "Date", "width": 95, "anchor": "center", "stretch": False},
        {"id": "particulars", "heading": "Particulars", "width": 260, "anchor": "w", "stretch": True},
        {"id": "voucher_type", "heading": "Vch Type", "width": 100, "anchor": "center", "stretch": False},
        {"id": "voucher_no", "heading": "Vch No.", "width": 100, "anchor": "center", "stretch": False},
        {"id": "debit", "heading": "Debit (₹)", "width": 110, "anchor": "e", "stretch": False},
        {"id": "credit", "heading": "Credit (₹)", "width": 110, "anchor": "e", "stretch": False},
        {"id": "amount", "heading": "Amount (₹)", "width": 120, "anchor": "e", "stretch": False},
    ]

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_report_data: Optional[Dict[str, Any]] = None

        # ---- root frame -------------------------------------------------
        self.main_frame = ctk.CTkFrame(
            parent,
            corner_radius=0,
            fg_color=config.VOUCHER_BG_PRIMARY,          # #0B1329
        )
        self.main_frame.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        # ---- header -----------------------------------------------------
        ReportBackHeader(
            self.main_frame,
            "📖  Day Book",
            "Voucher register / day‑wise transaction summary",
            on_back=self._back,
        )

        # ---- toolbar (action row) ---------------------------------------
        self._build_toolbar()

        # ---- compact filter bar -----------------------------------------
        self._build_filters()

        # ---- high‑density scrollable table -------------------------------
        self._build_table()

        # ---- totals bar (inside table container) already built in _build_table

        # ---- bottom shortcut bar ----------------------------------------
        self._build_shortcut_bar()

        self.status = ReportStatusBar(self.main_frame)
        wire_report_keyboard(self)

        # auto‑generate on open
        self._generate_report()

    # ------------------------------------------------------------------ #
    # toolbar – height 30px, pady=(2,4)
    # ------------------------------------------------------------------ #
    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,            # #10192E
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,    # #1B2848
        )
        bar.pack(fill="x", pady=(2, 4))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=config.SPACING_LG, pady=2)

        self.btn_new = make_button(
            inner, "+ New Voucher", self._new_voucher, width=130, accent=True
        )
        self.btn_new.pack(side="left", padx=(0, config.SPACING_SM))

        self.btn_open = make_button(
            inner, "📝 Open / Edit", self._open_selected, width=130
        )
        self.btn_open.pack(side="left", padx=(0, config.SPACING_SM))

        self.btn_view = make_button(inner, "👁 View", self._view_selected, width=100)
        self.btn_view.pack(side="left", padx=(0, config.SPACING_SM))

        self.btn_delete = make_button(inner, "🗑 Delete", self._delete_selected, width=100)
        self.btn_delete.pack(side="left", padx=(0, config.SPACING_SM))

        self.btn_refresh = make_button(inner, "↻ Refresh", self._generate_report, width=110)
        self.btn_refresh.pack(side="left")

    # ------------------------------------------------------------------ #
    # compact filter bar – height ~60px, pady=(3,6)
    # ------------------------------------------------------------------ #
    def _build_filters(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(3, 6))
        body = ctk.CTkFrame(bar, fg_color="transparent")
        body.pack(fill="x", padx=config.SPACING_LG, pady=4)
        self.filters = bar

        # default period from date_control
        from_dt, to_dt = date_control.period(self.company_id)
        self.from_date_var = tk.StringVar(value=from_dt.strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var = tk.StringVar(value=to_dt.strftime(config.DISPLAY_DATE_FORMAT))
        self.type_var = tk.StringVar(value="All")
        self.search_var = tk.StringVar()

        # column 0 – From Date
        self._filter_field(body, 0, "From Date", make_date_picker(body, self.from_date_var))
        # column 1 – To Date
        self._filter_field(body, 1, "To Date", make_date_picker(body, self.to_date_var))
        # column 2 – Voucher Type
        self.type_combo = make_readonly_combo(
            body,
            ["All", "Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase"],
            self.type_var,
            150,
        )
        self._filter_field(body, 2, "Voucher Type", self.type_combo)

        # column 3 – Search (expands)
        self.search_entry = ctk.CTkEntry(
            body,
            textvariable=self.search_var,
            width=220,
            placeholder_text="Search particulars, ledger...",
            corner_radius=config.INPUT_CORNER_RADIUS,
            height=30,
        )
        self._filter_field(body, 3, "Search", self.search_entry)

        # column 4 – Generate / Refresh (custom height 32)
        gen_btn = ctk.CTkButton(
            body,
            text="⚡ Generate / Refresh",
            width=170,
            height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self._generate_report,
            fg_color=config.COLOR_PRIMARY,
            hover_color=config.COLOR_PRIMARY_HOVER,
            text_color="#FFFFFF",
        )
        gen_btn.grid(row=0, column=4, sticky="w", padx=(config.SPACING_MD, 0), pady=(config.SPACING_XS, 0))

        # make search column take remaining space
        body.grid_columnconfigure(3, weight=1)

    def _filter_field(self, parent, column: int, label: str, widget) -> None:
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else config.SPACING_LG, 0))
        ctk.CTkLabel(
            holder,
            text=label,
            font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w")
        widget.grid(row=1, column=0, sticky="w", pady=(2, 0))
        holder.search_entry = getattr(widget, "search_entry", None)

    # ------------------------------------------------------------------ #
    # high‑density scrollable table
    # ------------------------------------------------------------------ #
    def _build_table(self) -> None:
        container = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        container.pack(fill="both", expand=True, pady=(2, 4))
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self.table_container = container

        # ttk style for ultra‑compact rows
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Compact.Treeview",
            background=config.VOUCHER_CARD_BG,
            fieldbackground=config.VOUCHER_CARD_BG,
            foreground=config.COLOR_TEXT_PRIMARY,
            rowheight=34,
            font=("Segoe UI", 11),
            borderwidth=0,
        )
        style.configure(
            "Compact.Treeview.Heading",
            background=config.VOUCHER_CARD_BORDER,
            foreground=config.COLOR_TEXT_PRIMARY,
            font=("Segoe UI", 11, "bold"),
            relief="flat",
        )
        style.map("Compact.Treeview", background=[("selected", "#162544")])

        # fixed header row (height 28)
        header = ctk.CTkFrame(container, fg_color=config.VOUCHER_CARD_BORDER, corner_radius=0, height=28)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        for idx, col in enumerate(self._COLUMNS):
            header.grid_columnconfigure(idx, weight=1 if col["stretch"] else 0)
            ctk.CTkLabel(
                header,
                text=col["heading"],
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
                anchor="w" if col["anchor"] == "w" else "e",
            ).grid(
                row=0,
                column=idx,
                sticky="ew",
                padx=(config.SPACING_LG if idx == 0 else config.SPACING_SM,
                      config.SPACING_LG if idx == len(self._COLUMNS) - 1 else config.SPACING_SM),
                pady=2,
            )

        # scrollable body
        body = ctk.CTkScrollableFrame(
            container,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=config.VOUCHER_CARD_BORDER,
        )
        body.grid(row=1, column=0, sticky="nsew")
        self.table_body = body

        column_ids = [c["id"] for c in self._COLUMNS]
        self.tree = ttk.Treeview(
            body,
            columns=column_ids,
            show="",
            selectmode="browse",
            style="Compact.Treeview",
        )
        for col in self._COLUMNS:
            self.tree.heading(col["id"], text=col["heading"])
            self.tree.column(
                col["id"],
                width=col.get("width", 140),
                anchor=col.get("anchor", "w"),
                stretch=tk.YES if col.get("stretch") else tk.NO,
            )
        self.tree.pack(fill="both", expand=True)

        # tags for debit/credit colours and zebra striping
        self.tree.tag_configure("debit", foreground=config.COLOR_EXPENSE)      # red #EF4444
        self.tree.tag_configure("credit", foreground=config.COLOR_INCOME)      # green #10B981
        self.tree.tag_configure("odd", background=config.VOUCHER_BG_PRIMARY)  # #0B1329

        # interactions
        self.tree.bind("<ButtonRelease-1>", self._on_row_selected)
        self.tree.bind("<Return>", lambda _e: self._open_selected())
        self.tree.bind("<KP_Enter>", lambda _e: self._open_selected())
        self.tree.bind("<Double-Button-1>", lambda _e: self._open_selected())

        # empty state
        self.empty_label = ctk.CTkLabel(
            container,
            text="Select dates and generate the Day Book to begin.",
            font=ctk.CTkFont(size=13),
            text_color=config.COLOR_TEXT_MUTED,
        )
        self.empty_label.grid(row=1, column=0)

        # ---- footer strip inside table container (totals) ----
        self.footer_frame = ctk.CTkFrame(container, fg_color=config.VOUCHER_CARD_BORDER, corner_radius=0, height=36)
        self.footer_frame.grid(row=2, column=0, sticky="ew")
        self.footer_frame.grid_propagate(False)
        self.footer_frame.grid_columnconfigure(0, weight=1)
        self.footer_frame.grid_columnconfigure(1, weight=0)

        self.footer_left = ctk.CTkLabel(
            self.footer_frame,
            text="Total Transactions: 0",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.footer_left.grid(row=0, column=0, sticky="w", padx=config.SPACING_LG, pady=4)

        self.footer_right = ctk.CTkLabel(
            self.footer_frame,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY,
            anchor="e",
        )
        self.footer_right.grid(row=0, column=1, sticky="e", padx=config.SPACING_LG, pady=4)

    # ------------------------------------------------------------------ #
    # bottom shortcut bar – height 28px
    # ------------------------------------------------------------------ #
    def _build_shortcut_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
            height=28,
        )
        bar.pack(fill="x", pady=(2, 4))
        bar.pack_propagate(False)
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="both", padx=config.SPACING_LG, pady=2)

        # left info
        ctk.CTkLabel(
            inner,
            text="ℹ Day Book shows all vouchers in chronological order on the selected date range.",
            font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left")

        # right keyboard badges
        badges = [
            ("F5", "Refresh"),
            ("Ctrl+N", "New Voucher"),
            ("Enter", "Open / Edit"),
        ]
        for key, desc in badges:
            badge = ctk.CTkFrame(inner, fg_color=config.VOUCHER_CARD_BORDER, corner_radius=4)
            badge.pack(side="right", padx=(config.SPACING_SM, 0))
            ctk.CTkLabel(badge, text=key, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=config.COLOR_TEXT_PRIMARY).pack(side="left", padx=6, pady=2)
            ctk.CTkLabel(badge, text=desc, font=ctk.CTkFont(size=10),
                         text_color=config.COLOR_TEXT_SECONDARY).pack(side="left", padx=(0,6), pady=2)

    # ------------------------------------------------------------------ #
    # interactions
    # ------------------------------------------------------------------ #
    def _on_row_selected(self, _event=None) -> None:
        return None

    def _selected_voucher_id(self) -> Optional[int]:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except (ValueError, TypeError):
            return None

    def _selected_voucher(self) -> Optional[Dict[str, Any]]:
        vid = self._selected_voucher_id()
        if vid is None:
            return None
        return voucher_service.get_voucher_with_details(vid)

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
        if voucher.get("status") == STATUS_CANCELLED:
            dialogs.warn("Day Book", "This voucher is already cancelled.", parent=self.parent)
            return
        if not dialogs.confirm_destructive(
            "Delete Voucher", "voucher", voucher.get("voucher_number", ""), parent=self.parent
        ):
            return
        ok, msg = voucher_service.cancel_voucher(voucher["id"], self.company_id)
        if not ok:
            dialogs.error("Day Book", msg, parent=self.parent)
            return
        dialogs.info("Day Book", msg, parent=self.parent)
        self._generate_report()

    def _new_voucher(self) -> None:
        self._route_to_vouchers()

    def _open_voucher_in_editor(self, voucher: Dict[str, Any], read_only: bool = False) -> None:
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
    # data handling
    # ------------------------------------------------------------------ #
    def _back(self) -> None:
        back = getattr(self, "on_keyboard_back", None)
        if callable(back):
            back()

    def _clear_filters(self) -> None:
        from_dt, to_dt = date_control.period(self.company_id)
        self.from_date_var.set(from_dt.strftime(config.DISPLAY_DATE_FORMAT))
        self.to_date_var.set(to_dt.strftime(config.DISPLAY_DATE_FORMAT))
        self.type_var.set("All")
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
        d = self._parse_date(raw)
        return d.strftime(config.DISPLAY_DATE_FORMAT) if d else raw

    def _generate_report(self) -> None:
        from_date = self._parse_date(self.from_date_var.get())
        to_date = self._parse_date(self.to_date_var.get())
        if not from_date or not to_date:
            dialogs.warn("Day Book", "Invalid date. Use DD‑MM‑YYYY format.", parent=self.parent)
            return
        if from_date > to_date:
            dialogs.warn("Day Book", "From Date cannot be after To Date.", parent=self.parent)
            return

        report = voucher_register_service.generate_day_book(
            self.company_id,
            from_date,
            to_date,
            voucher_type="" if self.type_var.get() == "All" else self.type_var.get(),
            search_term=self.search_var.get().strip(),
        )
        if not report.get("success"):
            dialogs.error("Day Book", report.get("error", "Failed to generate report"), parent=self.parent)
            return

        self.current_report_data = report
        self._render(report)

    # ------------------------------------------------------------------ #
    # render – collapse ledger lines to one row per voucher
    # ------------------------------------------------------------------ #
    def _render(self, report: Dict[str, Any]) -> None:
        entries = report.get("entries", [])
        if not entries:
            self._show_empty("No vouchers found for the selected period.")
            self._update_footer(0, 0.0, 0.0)
            return
        self._hide_empty()

        for iid in self.tree.get_children():
            self.tree.delete(iid)

        vouchers: Dict[int, Dict[str, Any]] = {}
        for entry in entries:
            vid = int(entry.get("voucher_id", 0) or 0)
            if vid not in vouchers:
                particulars = self._voucher_particulars(entries, vid, entry)
                vouchers[vid] = {
                    "voucher_id": vid,
                    "date": entry.get("voucher_date", ""),
                    "particulars": particulars,
                    "vtype": entry.get("voucher_type", ""),
                    "vno": entry.get("voucher_number", ""),
                    "debit": 0.0,
                    "credit": 0.0,
                }
            v = vouchers[vid]
            v["debit"] += float(entry.get("debit_amount", 0) or 0)
            v["credit"] += float(entry.get("credit_amount", 0) or 0)

        total_debit = 0.0
        total_credit = 0.0
        for idx, v in enumerate(vouchers.values()):
            vtype = v["vtype"]
            debit_amt = round(v["debit"], 2)
            credit_amt = round(v["credit"], 2)

            if vtype in (VOUCHER_PAYMENT, "Purchase", "Debit"):
                amount_display = f"{debit_amt:,.2f} Dr"
                amount_tag = "debit"
            elif vtype in (VOUCHER_RECEIPT, "Sales", "Receipt", "Credit"):
                amount_display = f"{credit_amt:,.2f} Cr"
                amount_tag = "credit"
            else:
                if debit_amt >= credit_amt:
                    amount_display = f"{debit_amt:,.2f} Dr"
                    amount_tag = "debit"
                else:
                    amount_display = f"{credit_amt:,.2f} Cr"
                    amount_tag = "credit"

            total_debit += debit_amt
            total_credit += credit_amt

            tags = (amount_tag,)
            if idx % 2:
                tags = tags + ("odd",)

            self.tree.insert(
                "",
                tk.END,
                iid=str(v["voucher_id"]),
                values=(
                    self._format_date(v["date"]),
                    v["particulars"],
                    vtype,
                    v["vno"],
                    f"{debit_amt:,.2f}",
                    f"{credit_amt:,.2f}",
                    amount_display,
                ),
                tags=tags,
            )

        self._update_footer(len(vouchers), total_debit, total_credit)
        self.status.set(
            f"Day Book generated: {len(vouchers)} vouchers "
            f"({self._format_date(report.get('from_date', ''))} to "
            f"{self._format_date(report.get('to_date', ''))})"
        )

    def _update_footer(self, txn_count: int, tot_debit: float, tot_credit: float) -> None:
        diff = tot_debit - tot_credit
        diff_color = config.COLOR_INCOME if diff >= 0 else config.COLOR_WARNING  # green / amber
        self.footer_left.configure(text=f"Total Transactions: {txn_count}")
        self.footer_right.configure(
            text=f"Total Debit: ₹{tot_debit:,.2f}   Total Credit: ₹{tot_credit:,.2f}   Diff: ₹{diff:,.2f}"
        )
        self.footer_right.configure(text_color=diff_color)

    def _voucher_particulars(
        self, entries: List[Dict[str, Any]], voucher_id: int, fallback: Dict[str, Any]
    ) -> str:
        lines = [e for e in entries if int(e.get("voucher_id", 0) or 0) == voucher_id]
        if not lines:
            return fallback.get("account_name", "")
        party = None
        fallback_name = ""
        for line in lines:
            group = str(line.get("account_group", "") or "")
            name = str(line.get("account_name", "") or "")
            if not name:
                continue
            if group in ("Sundry Debtors", "Sundry Creditors"):
                party = name
                break
            if not fallback_name:
                fallback_name = name
        return party or fallback_name or fallback.get("account_name", "")

    def _show_empty(self, message: str) -> None:
        self.empty_label.configure(text=message)
        self.empty_label.lift()
        self.footer_left.configure(text="Total Transactions: 0")
        self.footer_right.configure(text="")

    def _hide_empty(self) -> None:
        self.empty_label.lower()

    # ------------------------------------------------------------------ #
    # exports (kept for keyboard shortcuts / menu)
    # ------------------------------------------------------------------ #
    def _export_to_png(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        ok, path = report_exporter.export_table_to_png(self.table_container, "day_book")
        if ok:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.warn("Export", path, parent=self.parent)

    def _export_to_csv(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        ok, path = voucher_register_service.export_day_book_to_csv(self.current_report_data, "day_book")
        if ok:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)

    def _export_to_json(self) -> None:
        if not self.current_report_data:
            dialogs.warn("Export", "Generate the report first.", parent=self.parent)
            return
        from utils.report_exporter import report_exporter
        ok, path = report_exporter.export_to_json(self.current_report_data, "day_book")
        if ok:
            dialogs.info("Export", f"Exported to:\n{path}", parent=self.parent)
        else:
            dialogs.error("Export", path, parent=self.parent)


def show_day_book_report(parent: tk.Widget, company_id: int) -> DayBookReportUI:
    return DayBookReportUI(parent, company_id)