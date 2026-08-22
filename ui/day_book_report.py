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
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    voucher_service,
)
from services.date_control_service import date_control
from ui.report_base import (
    ReportBackHeader,
    make_date_picker,
    make_readonly_combo,
    make_button,
    wire_report_keyboard,
)
from utils import dialogs


class DayBookReportUI:
    """Day Book (voucher register) — one row per voucher, ultra‑compact."""

    _COLUMNS = [
        {"id": "date", "heading": "Date", "width": 95, "anchor": "w", "stretch": False},
        {"id": "particulars", "heading": "Particulars", "width": 280, "anchor": "w", "stretch": True},
        {"id": "voucher_type", "heading": "Vch Type", "width": 110, "anchor": "center", "stretch": False},
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
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=6)

        # ---- header (ultra‑compact) ------------------------------------
        header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 2))
        ctk.CTkButton(
            header_frame, text="←", width=28, height=24,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            command=self._back,
        ).pack(side="left")
        title_block = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_block.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            title_block, text="📖  Day Book", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block, text="Voucher register / day‑wise transaction summary",
            font=ctk.CTkFont(size=10), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w")

        # ---- toolbar (action row) ---------------------------------------
        self._build_toolbar()

        # ---- compact single‑row filter bar -------------------------------
        self._build_filters(self.main_frame)

        # ---- high‑density scrollable table -------------------------------
        self._build_table()

        # ---- bottom shortcut bar ----------------------------------------
        self._build_shortcut_bar()

        wire_report_keyboard(self)

        # auto‑generate on open
        self._generate_report()

    # ------------------------------------------------------------------ #
    # toolbar – ultra‑compact, height 26px, pady=(0,2)
    # ------------------------------------------------------------------ #
    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
        )
        bar.pack(fill="x", pady=(0, 2))
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=1)

        btn_kwargs = {"height": 26, "corner_radius": config.BUTTON_CORNER_RADIUS}
        self.btn_new = ctk.CTkButton(inner, text="+ New Voucher", width=120,
                                     fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
                                     text_color="#FFFFFF", command=self._new_voucher, **btn_kwargs)
        self.btn_new.pack(side="left", padx=(0, 4))

        self.btn_open = ctk.CTkButton(inner, text="📝 Open / Edit", width=110,
                                      fg_color=config.VOUCHER_CARD_BG, border_width=1,
                                      border_color=config.VOUCHER_CARD_BORDER,
                                      text_color=config.COLOR_TEXT_PRIMARY, command=self._open_selected, **btn_kwargs)
        self.btn_open.pack(side="left", padx=(0, 4))

        self.btn_view = ctk.CTkButton(inner, text="👁 View", width=80,
                                      fg_color=config.VOUCHER_CARD_BG, border_width=1,
                                      border_color=config.VOUCHER_CARD_BORDER,
                                      text_color=config.COLOR_TEXT_PRIMARY, command=self._view_selected, **btn_kwargs)
        self.btn_view.pack(side="left", padx=(0, 4))

        self.btn_delete = ctk.CTkButton(inner, text="🗑 Delete", width=80,
                                        fg_color=config.VOUCHER_CARD_BG, border_width=1,
                                        border_color=config.VOUCHER_CARD_BORDER,
                                        text_color=config.COLOR_TEXT_PRIMARY, command=self._delete_selected, **btn_kwargs)
        self.btn_delete.pack(side="left", padx=(0, 4))

        self.btn_refresh = ctk.CTkButton(inner, text="↻ Refresh", width=90,
                                         fg_color=config.VOUCHER_CARD_BG, border_width=1,
                                         border_color=config.VOUCHER_CARD_BORDER,
                                         text_color=config.COLOR_TEXT_PRIMARY, command=self._generate_report, **btn_kwargs)
        self.btn_refresh.pack(side="left")

    # ------------------------------------------------------------------ #
    # ultra‑compact filter bar – single horizontal row, height ~42px
    # ------------------------------------------------------------------ #
    def _build_filters(self, parent) -> None:
        filter_card = ctk.CTkFrame(
            parent,
            height=44,
            fg_color="#10192E",
            border_color="#1B2848",
            border_width=1,
            corner_radius=8,
        )
        filter_card.pack(fill="x", pady=(0, 4), padx=0)
        filter_card.pack_propagate(False)

        inner = ctk.CTkFrame(filter_card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=10, pady=4)

        # 1. From Date
        ctk.CTkLabel(inner, text="From:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#94A3B8").pack(side="left", padx=(0, 4))
        self.from_date_entry = ctk.CTkEntry(inner, width=95, height=28,
                                            font=ctk.CTkFont(size=11))
        self.from_date_entry.pack(side="left", padx=(0, 10))

        # 2. To Date
        ctk.CTkLabel(inner, text="To:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#94A3B8").pack(side="left", padx=(0, 4))
        self.to_date_entry = ctk.CTkEntry(inner, width=95, height=28,
                                          font=ctk.CTkFont(size=11))
        self.to_date_entry.pack(side="left", padx=(0, 10))

        # Pre‑fill dates from date_control
        from_d, to_d = date_control.period(self.company_id)
        self.from_date_entry.insert(0, from_d.strftime("%d-%m-%Y"))
        self.to_date_entry.insert(0, to_d.strftime("%d-%m-%Y"))

        # 3. Voucher Type
        ctk.CTkLabel(inner, text="Type:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#94A3B8").pack(side="left", padx=(0, 4))
        self.voucher_type_menu = ctk.CTkOptionMenu(
            inner,
            values=["All", "Payment", "Receipt", "Contra", "Journal", "Sales", "Purchase"],
            width=100,
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.voucher_type_menu.pack(side="left", padx=(0, 10))

        # 4. Search Bar
        self.search_entry = ctk.CTkEntry(
            inner,
            placeholder_text="Search particulars, voucher no...",
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # 5. Generate / Refresh Button
        self.generate_btn = ctk.CTkButton(
            inner,
            text="⚡ Generate",
            width=100,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self._generate_report,
        )
        self.generate_btn.pack(side="right")

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
        container.pack(fill="both", expand=True, pady=(0, 4))
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
            rowheight=30,
            font=("Segoe UI", 10),
            borderwidth=0,
        )
        style.configure(
            "Compact.Treeview.Heading",
            background=config.VOUCHER_CARD_BORDER,
            foreground=config.COLOR_TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        style.map("Compact.Treeview", background=[("selected", "#162544")])

        # fixed header row (height 26)
        header = ctk.CTkFrame(container, fg_color=config.VOUCHER_CARD_BORDER, corner_radius=0, height=26)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        for idx, col in enumerate(self._COLUMNS):
            header.grid_columnconfigure(idx, weight=1 if col["stretch"] else 0)
            ctk.CTkLabel(
                header,
                text=col["heading"],
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
                anchor="w" if col["anchor"] == "w" else "e",
            ).grid(
                row=0,
                column=idx,
                sticky="ew",
                padx=(8 if idx == 0 else 4,
                      8 if idx == len(self._COLUMNS) - 1 else 4),
                pady=1,
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
        self.footer_frame = ctk.CTkFrame(container, fg_color=config.VOUCHER_CARD_BORDER, corner_radius=0, height=26)
        self.footer_frame.grid(row=2, column=0, sticky="ew")
        self.footer_frame.grid_propagate(False)
        self.footer_frame.grid_columnconfigure(0, weight=1)
        self.footer_frame.grid_columnconfigure(1, weight=0)

        self.footer_left = ctk.CTkLabel(
            self.footer_frame,
            text="Total Transactions: 0",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.footer_left.grid(row=0, column=0, sticky="w", padx=8, pady=2)

        self.footer_right = ctk.CTkLabel(
            self.footer_frame,
            text="",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY,
            anchor="e",
        )
        self.footer_right.grid(row=0, column=1, sticky="e", padx=8, pady=2)

    # ------------------------------------------------------------------ #
    # bottom shortcut bar – height 26px
    # ------------------------------------------------------------------ #
    def _build_shortcut_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.main_frame,
            fg_color=config.VOUCHER_CARD_BG,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1,
            border_color=config.VOUCHER_CARD_BORDER,
            height=26,
        )
        bar.pack(fill="x", pady=(0, 2))
        bar.pack_propagate(False)
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="both", padx=8, pady=1)

        ctk.CTkLabel(
            inner,
            text="ℹ Day Book shows all vouchers in chronological order on the selected date range.",
            font=ctk.CTkFont(size=9),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left")

        badges = [
            ("F5", "Refresh"),
            ("Ctrl+N", "New Voucher"),
            ("Enter", "Open / Edit"),
        ]
        for key, desc in badges:
            badge = ctk.CTkFrame(inner, fg_color=config.VOUCHER_CARD_BORDER, corner_radius=3)
            badge.pack(side="right", padx=(4, 0))
            ctk.CTkLabel(badge, text=key, font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=config.COLOR_TEXT_PRIMARY).pack(side="left", padx=5, pady=1)
            ctk.CTkLabel(badge, text=desc, font=ctk.CTkFont(size=9),
                         text_color=config.COLOR_TEXT_SECONDARY).pack(side="left", padx=(0,5), pady=1)

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
        self.from_date_entry.delete(0, tk.END)
        self.from_date_entry.insert(0, from_dt.strftime("%d-%m-%Y"))
        self.to_date_entry.delete(0, tk.END)
        self.to_date_entry.insert(0, to_dt.strftime("%d-%m-%Y"))
        self.voucher_type_menu.set("All")
        self.search_entry.delete(0, tk.END)
        self._show_empty("Select dates and generate the Day Book to begin.")

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
        from_date = self._parse_date(self.from_date_entry.get())
        to_date = self._parse_date(self.to_date_entry.get())
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
            voucher_type="" if self.voucher_type_menu.get() == "All" else self.voucher_type_menu.get(),
            search_term=self.search_entry.get().strip(),
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
            vtype_raw = v["vtype"]
            vtype = str(vtype_raw).strip().title()
            debit_amt = round(v["debit"], 2)
            credit_amt = round(v["credit"], 2)

            if vtype in ("Payment", "Purchase", "Debit Note"):
                debit_val = f"{debit_amt:,.2f}"
                credit_val = "—"
                amount_display = f"{debit_amt:,.2f} Dr"
                amount_tag = "debit"
            elif vtype in ("Receipt", "Sales", "Credit Note"):
                debit_val = "—"
                credit_val = f"{credit_amt:,.2f}"
                amount_display = f"{credit_amt:,.2f} Cr"
                amount_tag = "credit"
            elif vtype == "Contra":
                debit_val = f"{debit_amt:,.2f}"
                credit_val = f"{credit_amt:,.2f}"
                amount_display = f"{max(debit_amt, credit_amt):,.2f}"
                amount_tag = "odd"
            else:
                debit_val = f"{debit_amt:,.2f}"
                credit_val = "—"
                amount_display = f"{debit_amt:,.2f} Dr"
                amount_tag = "debit"

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
                    vtype_raw,
                    v["vno"],
                    debit_val,
                    credit_val,
                    amount_display,
                ),
                tags=tags,
            )

        self._update_footer(len(vouchers), total_debit, total_credit)

    def _update_footer(self, txn_count: int, tot_debit: float, tot_credit: float) -> None:
        diff = tot_debit - tot_credit
        diff_color = config.COLOR_INCOME if diff >= 0 else config.COLOR_WARNING
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