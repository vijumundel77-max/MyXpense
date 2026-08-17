"""
Expenzo — Dashboard
Real accounting overview for the currently selected company: cash/bank
balances, receivables/payables, today's and monthly receipts/payments,
recent vouchers, and quick actions.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import date
from typing import Any, Dict, List, Optional

import customtkinter as ctk

import config
from services.dashboard_service import dashboard_service


class DashboardFrame(ctk.CTkFrame):
    """Accounting dashboard for the current company."""

    # Cards that drill down into a detail modal.
    DRILLDOWN_CARDS = (
        ("bank_balance", "Bank Balance"),
        ("receivables", "Receivables"),
        ("payables", "Payables"),
        ("month_receipts", "This Month's Receipts"),
        ("month_payments", "This Month's Payments"),
    )

    def __init__(self, parent, company_id: Optional[int] = None):
        super().__init__(parent)
        self.parent = parent
        self.pack(fill="both", expand=True)
        self.company_id = company_id or self._resolve_company_id()
        self.data: Dict[str, Any] = {}
        self._update_info: Optional[Dict[str, Any]] = None

        self._build_update_banner()
        self._build_header()
        self._build_kpi_row()
        self._build_movement_row()
        self._build_recent_vouchers()
        self._build_quick_actions()
        self._build_status()
        self.refresh()

        # Check for updates in the background — never blocks startup and the
        # app runs normally when the network is unavailable.
        self._check_updates_async()

    # ------------------------------------------------------------------ #
    # update banner
    # ------------------------------------------------------------------ #
    def _build_update_banner(self) -> None:
        self.update_banner = ctk.CTkFrame(
            self, fg_color=config.COLOR_EXPENSE, corner_radius=0,
        )
        # Not packed until an update is actually available.

    def _check_updates_async(self) -> None:
        import queue
        import threading
        self._update_queue: "queue.Queue" = queue.Queue()

        def _work() -> None:
            try:
                from services.update_manager import update_manager
                info, _error = update_manager.check()
            except Exception:
                info = None
            self._update_queue.put(info)

        threading.Thread(target=_work, daemon=True).start()
        # Poll the queue from the main thread (thread-safe: worker only puts).
        self.after(300, self._poll_update_queue)

    def _poll_update_queue(self) -> None:
        try:
            while True:
                info = self._update_queue.get_nowait()
                self._on_update_check_result(info)
        except Exception:
            pass
        # Keep polling until the check completes.
        if not getattr(self, "_update_poll_done", False):
            self.after(300, self._poll_update_queue)

    def _on_update_check_result(self, info: Optional[Dict[str, Any]]) -> None:
        self._update_poll_done = True
        if info is None:
            return
        self._update_info = info
        self._show_update_banner(info)

    def _show_update_banner(self, info: Dict[str, Any]) -> None:
        version = info.get("version", "")
        try:
            self.update_banner.pack(fill="x")
            for child in self.update_banner.winfo_children():
                child.destroy()

            inner = ctk.CTkFrame(self.update_banner, fg_color="transparent")
            inner.pack(fill="x", padx=config.SPACING_XL, pady=config.SPACING_SM)

            ctk.CTkLabel(
                inner, text="⚠", font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#FFFFFF",
            ).pack(side="left")
            ctk.CTkLabel(
                inner,
                text=f"New version available — Expenzo v{version}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#FFFFFF",
            ).pack(side="left", padx=(config.SPACING_SM, 0))

            ctk.CTkButton(
                inner, text="Later", width=80, height=28,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                fg_color="transparent", border_width=1,
                border_color="#FFFFFF", text_color="#FFFFFF",
                hover_color=config.COLOR_EXPENSE_HOVER,
                command=self._dismiss_update_banner,
            ).pack(side="right")
            ctk.CTkButton(
                inner, text="Update Now", width=110, height=28,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                fg_color="#FFFFFF", text_color=config.COLOR_EXPENSE,
                hover_color="#F3F4F6",
                command=self._on_update_now,
            ).pack(side="right", padx=(0, config.SPACING_SM))
        except Exception:
            pass

    def _dismiss_update_banner(self) -> None:
        """Later: hide the banner for the rest of this session only.  The
        next app startup checks again."""
        try:
            self.update_banner.pack_forget()
        except Exception:
            pass

    def _on_update_now(self) -> None:
        """Update Now: download the installer with progress, then launch it
        and close the app."""
        info = self._update_info
        if not info:
            return
        try:
            from services.update_manager import update_manager
            progress = UpdateProgressDialog(self.winfo_toplevel())

            def _download() -> None:
                # Worker thread: never touch Tk directly — enqueue results;
                # the dialog's main-thread poll drives the UI.
                try:
                    path = update_manager.download(
                        progress_callback=progress.set_progress,
                        release_info=info,
                    )
                    progress._progress_queue.put(("done", str(path)))
                except Exception as exc:
                    progress._progress_queue.put(("error", str(exc)))

            import threading
            threading.Thread(target=_download, daemon=True).start()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_header(self) -> None:
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.pack(fill="x", padx=config.SPACING_XL, pady=(config.SPACING_XL, 0))
        ctk.CTkLabel(
            self.header, text="Dashboard",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        self.company_label = ctk.CTkLabel(
            self.header, text="", font=ctk.CTkFont(size=config.FONT_BODY_SIZE),
            text_color=config.COLOR_PRIMARY,
        )
        self.company_label.pack(side="left", padx=(config.SPACING_MD, 0))

        # Date context: Today + active Period (Alt+F2), always visible.
        self.today_label = ctk.CTkLabel(
            self.header,
            text=f"Today: {date.today().strftime(config.DISPLAY_DATE_FORMAT)}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
            fg_color=config.COLOR_BG_TERTIARY, corner_radius=6, padx=10, pady=3,
        )
        self.today_label.pack(side="right", padx=(config.SPACING_SM, 0))
        self.period_label = ctk.CTkLabel(
            self.header, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=config.COLOR_PRIMARY,
            fg_color=config.COLOR_BG_TERTIARY, corner_radius=6, padx=10, pady=3,
        )
        self.period_label.pack(side="right", padx=(config.SPACING_SM, 0))
        ctk.CTkButton(
            self.header, text="↻ Refresh", width=96, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.refresh,
        ).pack(side="right", padx=(0, config.SPACING_MD))

    def _build_kpi_row(self) -> None:
        self.kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        self.kpi_row.pack(fill="x", padx=config.SPACING_XL, pady=(config.SPACING_XL, 0))

        self.kpi_labels: Dict[str, ctk.CTkLabel] = {}
        self.kpi_cards: Dict[str, ctk.CTkFrame] = {}
        self.kpi_colors: Dict[str, str] = {
            "cash_balance": config.COLOR_INCOME,
            "bank_balance": config.COLOR_PRIMARY,
            "receivables": config.COLOR_WARNING,
            "payables": config.COLOR_EXPENSE,
        }
        for index, (key, title, icon) in enumerate([
            ("cash_balance", "Cash Balance", "₹"),
            ("bank_balance", "Bank Balance", "₹"),
            ("receivables", "Receivables", "₹"),
            ("payables", "Payables", "₹"),
        ]):
            card = ctk.CTkFrame(
                self.kpi_row, fg_color=config.COLOR_BG_SECONDARY,
                corner_radius=config.CARD_CORNER_RADIUS, height=104,
                border_width=1, border_color=config.COLOR_CARD_BORDER,
                cursor="hand2" if key in {"bank_balance", "receivables", "payables"} else "",
            )
            card.grid(row=0, column=index, sticky="nsew", padx=(0, config.SPACING_MD))
            card.grid_propagate(False)
            self.kpi_cards[key] = card

            if key in {"bank_balance", "receivables", "payables"}:
                self._make_card_clickable(card, key)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, 0))
            chip = ctk.CTkLabel(
                top, text=icon, width=30, height=30,
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
                fg_color=config.COLOR_BG_TERTIARY,
                corner_radius=8,
            )
            chip.pack(side="left")
            ctk.CTkLabel(
                top, text=title, font=ctk.CTkFont(size=13),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(side="left", padx=(config.SPACING_SM, 0))

            value_label = ctk.CTkLabel(
                card, text="₹ 0.00", font=ctk.CTkFont(size=21, weight="bold"),
                text_color=self.kpi_colors[key],
            )
            value_label.pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_SM, 0))
            self.kpi_labels[key] = value_label

        for column in range(4):
            self.kpi_row.grid_columnconfigure(column, weight=1)

    def _build_movement_row(self) -> None:
        self.movement_row = ctk.CTkFrame(self, fg_color="transparent")
        self.movement_row.pack(fill="x", padx=config.SPACING_XL, pady=(config.SPACING_MD, 0))

        self.movement_labels: Dict[str, ctk.CTkLabel] = {}
        self.movement_cards: Dict[str, ctk.CTkFrame] = {}
        for index, (key, title) in enumerate([
            ("today_receipts", "Today's Receipts"),
            ("today_payments", "Today's Payments"),
            ("month_receipts", "This Month's Receipts"),
            ("month_payments", "This Month's Payments"),
        ]):
            card = ctk.CTkFrame(
                self.movement_row, fg_color=config.COLOR_BG_SECONDARY,
                corner_radius=config.CARD_CORNER_RADIUS, height=84,
                border_width=1, border_color=config.COLOR_CARD_BORDER,
                cursor="hand2" if key in {"month_receipts", "month_payments"} else "",
            )
            card.grid(row=0, column=index, sticky="nsew", padx=(0, config.SPACING_MD))
            card.grid_propagate(False)
            self.movement_cards[key] = card
            if key in {"month_receipts", "month_payments"}:
                self._make_card_clickable(card, key)
            ctk.CTkLabel(
                card, text=title, font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_MD, 0))
            is_receipt = key.endswith("receipts")
            value_label = ctk.CTkLabel(
                card, text="₹ 0.00", font=ctk.CTkFont(size=16, weight="bold"),
                text_color=(config.COLOR_INCOME if is_receipt else config.COLOR_EXPENSE),
            )
            value_label.pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_XS, 0))
            self.movement_labels[key] = value_label

        for column in range(4):
            self.movement_row.grid_columnconfigure(column, weight=1)

    def _build_recent_vouchers(self) -> None:
        section = ctk.CTkFrame(self, fg_color="transparent")
        section.pack(fill="both", expand=True, padx=config.SPACING_XL,
                     pady=(config.SPACING_XL, 0))

        ctk.CTkLabel(
            section, text="Recent Vouchers", font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", pady=(0, config.SPACING_SM))

        table = ctk.CTkFrame(
            section, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        table.pack(fill="both", expand=True)
        table.pack_propagate(False)

        columns = ("number", "type", "date", "reference", "narration", "debit", "credit", "status")
        self.voucher_tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("number", "Voucher No.", 110),
            ("type", "Type", 90),
            ("date", "Date", 95),
            ("reference", "Reference", 120),
            ("narration", "Narration", 210),
            ("debit", "Debit", 105),
            ("credit", "Credit", 105),
            ("status", "Status", 80),
        ]:
            self.voucher_tree.heading(col, text=heading)
            self.voucher_tree.column(col, width=width,
                                     anchor="w" if col not in {"debit", "credit"} else "e")
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.voucher_tree.yview)
        self.voucher_tree.configure(yscrollcommand=vsb.set)
        self.voucher_tree.pack(side="left", fill="both", expand=True,
                               padx=config.SPACING_LG, pady=config.SPACING_LG)
        vsb.pack(side="right", fill="y", pady=config.SPACING_LG)

        # Friendlier empty state: icon + hint on a subtle panel.
        empty = ctk.CTkFrame(
            section, fg_color=config.COLOR_BG_MUTED,
            corner_radius=config.CARD_CORNER_RADIUS, height=90,
        )
        empty.pack(fill="x", pady=(0, config.SPACING_LG))
        empty.pack_propagate(False)
        ctk.CTkLabel(
            empty, text="📒", font=ctk.CTkFont(size=22),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(pady=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            empty, text="No vouchers yet — enter your first voucher to get started.",
            font=ctk.CTkFont(size=13), text_color=config.COLOR_TEXT_MUTED,
        ).pack(pady=(2, config.SPACING_MD))
        self.voucher_empty_panel = empty
        self.voucher_empty_panel.pack_forget()

    def _build_quick_actions(self) -> None:
        panel = ctk.CTkFrame(
            self, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        panel.pack(fill="x", padx=config.SPACING_XL, pady=(0, config.SPACING_XL))

        inner = ctk.CTkFrame(panel, fg_color="transparent")
        inner.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_MD)

        ctk.CTkLabel(
            inner, text="Quick Actions", font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        for text, method_name in [
            ("Enter Voucher", "show_vouchers"),
            ("Open Reports", "show_reports"),
            ("Masters", "show_masters"),
        ]:
            ctk.CTkButton(
                inner, text=text, width=126, height=32,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                command=lambda m=method_name: self._navigate(m),
            ).pack(side="right", padx=(config.SPACING_SM, 0))

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            self, textvariable=self.status_var, anchor="w",
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x", padx=config.SPACING_XL, pady=(0, config.SPACING_SM))

    # ------------------------------------------------------------------ #
    # drill-down interaction
    # ------------------------------------------------------------------ #
    def _make_card_clickable(self, card, key: str) -> None:
        """Make a card (and its children) clickable with a hover highlight."""
        card.configure(cursor="hand2")
        bind_to = [card] + list(card.winfo_children())
        for widget in bind_to:
            try:
                widget.bind("<Button-1>", lambda e, k=key: self._on_card_click(k))
                widget.bind("<Enter>", lambda e, k=key: self._on_card_hover(k, True))
                widget.bind("<Leave>", lambda e, k=key: self._on_card_hover(k, False))
            except Exception:
                pass

    def _on_card_hover(self, key: str, hovered: bool) -> None:
        card = self.kpi_cards.get(key) or self.movement_cards.get(key)
        if card is None:
            return
        try:
            if hovered:
                card.configure(border_color=config.COLOR_PRIMARY,
                               fg_color=config.COLOR_BG_TERTIARY)
            else:
                card.configure(border_color=config.COLOR_CARD_BORDER,
                               fg_color=config.COLOR_BG_SECONDARY)
        except Exception:
            pass

    def _on_card_click(self, key: str) -> None:
        title = dict(self.DRILLDOWN_CARDS).get(key, key)
        self._open_detail(key, title)

    def _open_detail(self, key: str, title: str) -> None:
        detail = DashboardDetailDialog(
            self.winfo_toplevel(), self.company_id, key, title)
        detail.grab_set()
        detail.focus_set()

    # ------------------------------------------------------------------ #
    # keyboard
    # ------------------------------------------------------------------ #
    def on_keyboard_back(self) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, "on_keyboard_back"):
            app.on_keyboard_back()

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _resolve_company_id(self) -> int:
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None)
        if company_id is not None:
            return int(company_id)
        row = self._db_fetch("SELECT id FROM companies ORDER BY id LIMIT 1")
        return int(row["id"]) if row else 1

    def _global_single_date(self) -> Optional[date]:
        """The active F2 single date, or today when none was selected."""
        try:
            from services.date_control_service import date_control
            if date_control.has_single_date:
                return date_control.single_date(self.company_id)
        except Exception:
            pass
        return date.today()

    @staticmethod
    def _db_fetch(query: str):
        from database.database import db
        return db.fetch_one(query)

    def refresh(self) -> None:
        """(Re)load the dashboard for the current company."""
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None)
        if company_id is not None:
            self.company_id = int(company_id)
        self.data = dashboard_service.get_dashboard(self.company_id, self._global_single_date())

        self.company_label.configure(text=self.data.get('company_name', ''))
        for key, label in self.kpi_labels.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")
        for key, label in self.movement_labels.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")

        self._render_recent_vouchers()
        self._sync_date_labels()
        self.status_var.set(
            f"Updated {date.today().strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

    def _sync_date_labels(self) -> None:
        """Keep the Today / Period header labels in sync with the global
        date control (Alt+F2 period, F2 single date)."""
        try:
            from services.date_control_service import date_control
            day = self._global_single_date()
            self.today_label.configure(text=f"Today: {day.strftime(config.DISPLAY_DATE_FORMAT)}")
            if date_control.has_period:
                f, t = date_control.period(self.company_id)
                self.period_label.configure(
                    text=f"Period: {f.strftime(config.DISPLAY_DATE_FORMAT)} to "
                         f"{t.strftime(config.DISPLAY_DATE_FORMAT)}")
            else:
                self.period_label.configure(text="")
        except Exception:
            pass

    def on_global_date_period(self, from_date, to_date) -> None:
        """Global Alt+F2 hook: re-render the dashboard for the chosen period.

        Dashboard KPI totals are always as-of today (existing behavior);
        the Recent Vouchers list respects the global period.
        """
        from services.voucher_service import voucher_service
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None) or self.company_id
        try:
            vouchers = voucher_service.list_vouchers(
                int(company_id),
                from_date=from_date,
                to_date=to_date,
                include_cancelled=False,
            )
            vouchers = voucher_service.enrich_vouchers_with_totals(vouchers)
        except Exception:
            vouchers = []
        self._render_recent_vouchers_from(vouchers)
        self._sync_date_labels()
        self.status_var.set(
            f"Period {from_date.strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{to_date.strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

    def on_global_single_date(self, day) -> None:
        """Global F2 hook: re-render the whole dashboard for the selected
        single date (today chip, balances, day/month figures, vouchers)."""
        from services.voucher_service import voucher_service
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None) or self.company_id
        self.data = dashboard_service.get_dashboard(int(company_id), day)
        for key, label in self.kpi_labels.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")
        for key, label in self.movement_labels.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")
        try:
            vouchers = voucher_service.list_vouchers(
                int(company_id),
                from_date=day,
                to_date=day,
                include_cancelled=False,
            )
            vouchers = voucher_service.enrich_vouchers_with_totals(vouchers)
        except Exception:
            vouchers = []
        self._render_recent_vouchers_from(vouchers)
        self._sync_date_labels()
        self.status_var.set(
            f"Date {day.strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

    def _render_recent_vouchers_from(self, vouchers) -> None:
        for item in self.voucher_tree.get_children():
            self.voucher_tree.delete(item)
        if not vouchers:
            self.voucher_empty_panel.pack(fill="x", pady=(0, config.SPACING_LG))
            self.voucher_tree.pack_forget()
            return
        self.voucher_tree.pack(side="left", fill="both", expand=True,
                               padx=config.SPACING_LG, pady=config.SPACING_LG)
        self.voucher_empty_panel.pack_forget()
        for index, voucher in enumerate(vouchers[:8]):
            cancelled = str(voucher.get('status', '')).lower() == 'cancelled'
            self.voucher_tree.insert("", tk.END, values=(
                voucher.get('voucher_number', ''),
                voucher.get('voucher_type', ''),
                voucher.get('voucher_date', ''),
                voucher.get('reference_number', ''),
                voucher.get('narration', ''),
                f"{voucher.get('total_debit', 0):,.2f}",
                f"{voucher.get('total_credit', 0):,.2f}",
                voucher.get('status', ''),
            ), tags=('cancelled',) if cancelled else ('even' if index % 2 == 0 else 'odd',))

    def _render_recent_vouchers(self) -> None:
        for item in self.voucher_tree.get_children():
            self.voucher_tree.delete(item)
        vouchers = self.data.get('recent_vouchers', [])
        if not vouchers:
            self.voucher_empty_panel.pack(fill="x", pady=(0, config.SPACING_LG))
            self.voucher_tree.pack_forget()
            return
        self.voucher_tree.pack(side="left", fill="both", expand=True,
                               padx=config.SPACING_LG, pady=config.SPACING_LG)
        self.voucher_empty_panel.pack_forget()
        for index, voucher in enumerate(vouchers):
            cancelled = str(voucher.get('status', '')).lower() == 'cancelled'
            self.voucher_tree.insert("", tk.END, values=(
                voucher.get('voucher_number', ''),
                voucher.get('voucher_type', ''),
                voucher.get('voucher_date', ''),
                voucher.get('reference_number', ''),
                voucher.get('narration', ''),
                f"{voucher.get('total_debit', 0):,.2f}",
                f"{voucher.get('total_credit', 0):,.2f}",
                voucher.get('status', ''),
            ), tags=('cancelled',) if cancelled else ('even' if index % 2 == 0 else 'odd',))

    def _navigate(self, method_name: str) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, method_name):
            getattr(app, method_name)()


class DashboardDetailDialog(ctk.CTkToplevel):
    """Accounting-style detail modal for a drill-down dashboard card.

    Rows are loaded from the existing dashboard/ledger services (never a
    duplicate data source) and the footer always shows the total of the
    rows displayed — which reconciles with the dashboard card value.
    """

    COLUMN_DEFS: Dict[str, List[tuple]] = {
        "bank_balance": [
            ("account_name", "Bank Account", 260),
            ("balance", "Current Balance", 180),
        ],
        "receivables": [
            ("party_name", "Party", 260),
            ("outstanding", "Outstanding", 180),
        ],
        "payables": [
            ("party_name", "Party", 260),
            ("outstanding", "Outstanding", 180),
        ],
        "month_receipts": [
            ("date", "Date", 100),
            ("party", "Party / Account", 220),
            ("voucher_number", "Voucher No.", 110),
            ("amount", "Amount", 130),
        ],
        "month_payments": [
            ("date", "Date", 100),
            ("party", "Party / Account", 220),
            ("voucher_number", "Voucher No.", 110),
            ("amount", "Amount", 130),
        ],
    }

    ROW_ALIGN: Dict[str, Dict[str, str]] = {
        "bank_balance": {"balance": "e"},
        "receivables": {"outstanding": "e"},
        "payables": {"outstanding": "e"},
        "month_receipts": {"amount": "e"},
        "month_payments": {"amount": "e"},
    }

    COLORS: Dict[str, str] = {
        "bank_balance": config.COLOR_PRIMARY,
        "receivables": config.COLOR_WARNING,
        "payables": config.COLOR_EXPENSE,
        "month_receipts": config.COLOR_INCOME,
        "month_payments": config.COLOR_EXPENSE,
    }

    FRIENDLY_TITLES: Dict[str, str] = {
        "bank_balance": "Bank Balance",
        "receivables": "Receivables",
        "payables": "Payables",
        "month_receipts": "This Month's Receipts",
        "month_payments": "This Month's Payments",
    }

    def __init__(self, parent, company_id: int, key: str, title: str):
        super().__init__(parent)
        self.company_id = company_id
        self.key = key
        # Fall back to a friendly title when the caller passes a raw key.
        self.detail_title = title if title not in self.FRIENDLY_TITLES \
            else self.FRIENDLY_TITLES[title]

        self.title(f"{self.detail_title} — {config.APP_NAME}")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.configure(fg_color=config.COLOR_BG_PRIMARY)

        # Accounting-style fixed size.
        width = 620 if key in {"bank_balance", "receivables", "payables"} else 720
        height = 480
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)
        self.resizable(False, False)

        # Center over the parent.
        self.update_idletasks()
        try:
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_w = parent.winfo_width()
            parent_h = parent.winfo_height()
            x = parent_x + (parent_w - width) // 2
            y = parent_y + (parent_h - height) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self._build()
        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Control-w>", lambda _e: self._close())
        self.focus_set()

        self._load_data()

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        # Header: title + close button.
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=config.SPACING_XL, pady=(config.SPACING_XL, 0))
        ctk.CTkLabel(
            header, text=self.detail_title, font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="✕", width=34, height=30,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_PRIMARY_HOVER,
            text_color=config.COLOR_TEXT_PRIMARY, command=self._close,
        ).pack(side="right")

        # Subtitle: as-on date.
        self.subtitle_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_MUTED, anchor="w",
        )
        self.subtitle_label.pack(fill="x", padx=config.SPACING_XL,
                                 pady=(config.SPACING_XS, 0))

        # Table.
        table_frame = ctk.CTkFrame(
            self, fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
        )
        table_frame.pack(fill="both", expand=True, padx=config.SPACING_XL,
                         pady=config.SPACING_MD)
        table_frame.pack_propagate(False)

        column_keys = [c[0] for c in self.COLUMN_DEFS[self.key]]
        self.tree = ttk.Treeview(table_frame, columns=column_keys,
                                 show="headings", selectmode="browse")
        for column_key, heading, width in self.COLUMN_DEFS[self.key]:
            self.tree.heading(column_key, text=heading)
            self.tree.column(column_key, width=width,
                             anchor=self.ROW_ALIGN[self.key].get(column_key, "w"))
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True,
                       padx=(config.SPACING_LG, 0), pady=config.SPACING_LG)
        vsb.pack(side="right", fill="y", padx=(0, config.SPACING_LG),
                 pady=config.SPACING_LG)

        # Footer: total + close/back button.
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=config.SPACING_XL, pady=(0, config.SPACING_XL))

        self.total_label = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=15, weight="bold"),
            text_color=self.COLORS[self.key], anchor="w",
        )
        self.total_label.pack(side="left")

        ctk.CTkButton(
            footer, text="Close", width=110, height=34,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self._close,
        ).pack(side="right")
        ctk.CTkLabel(
            footer, text="Esc  Close", font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="right", padx=config.SPACING_MD)

    # ------------------------------------------------------------------ #
    # data
    # ------------------------------------------------------------------ #
    def _load_data(self) -> None:
        rows: List[Dict[str, Any]] = []
        # Reference date: the global F2 single date when one is active,
        # otherwise today — so drill-downs agree with the dashboard cards.
        day = date.today()
        try:
            from services.date_control_service import date_control
            if date_control.has_single_date:
                day = date_control.single_date(self.company_id)
        except Exception:
            pass
        if self.key == "bank_balance":
            rows = dashboard_service.bank_accounts(self.company_id, day)
        elif self.key in {"receivables", "payables"}:
            rows = dashboard_service.receivable_parties(
                self.company_id, day) if self.key == "receivables" \
                else dashboard_service.payable_parties(self.company_id, day)
        elif self.key == "month_receipts":
            rows = dashboard_service.month_receipts(self.company_id, day)
        elif self.key == "month_payments":
            rows = dashboard_service.month_payments(self.company_id, day)

        total = round(sum(float(r.get(self._total_key(), 0.0) or 0.0) for r in rows), 2)

        self.subtitle_label.configure(
            text=f"As on {day.strftime(config.DISPLAY_DATE_FORMAT)}" if self.key in {
                "bank_balance", "receivables", "payables"}
            else f"{day.strftime('%B %Y')} — as on {day.strftime(config.DISPLAY_DATE_FORMAT)}")
        self.total_label.configure(
            text=f"Total {self.detail_title}: {config.CURRENCY_SYMBOL}{total:,.2f}")

        for row in rows:
            values = []
            for column_key, _heading, _width in self.COLUMN_DEFS[self.key]:
                value = row.get(column_key, "")
                if column_key in self.ROW_ALIGN[self.key]:
                    value = f"{float(value or 0.0):,.2f}"
                else:
                    value = str(value or "")
                values.append(value)
            self.tree.insert("", tk.END, values=values)

    def _total_key(self) -> str:
        return {
            "bank_balance": "balance",
            "receivables": "outstanding",
            "payables": "outstanding",
            "month_receipts": "amount",
            "month_payments": "amount",
        }[self.key]

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class UpdateProgressDialog(ctk.CTkToplevel):
    """Modal progress dialog shown while the update installer downloads.

    ``set_progress`` is called from the download worker thread, so it only
    enqueues values; a main-thread poll updates the widgets (thread-safe).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Updating Expenzo")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(fg_color=config.COLOR_BG_SECONDARY)

        ctk.CTkLabel(
            self, text="Downloading Expenzo update…",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(padx=config.SPACING_XL, pady=(config.SPACING_LG, config.SPACING_XS))
        self.detail_var = tk.StringVar(value="Connecting…")
        ctk.CTkLabel(
            self, textvariable=self.detail_var,
            font=ctk.CTkFont(size=12), text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(padx=config.SPACING_XL)

        self.progress = ctk.CTkProgressBar(self, width=320)
        self.progress.set(0)
        self.progress.pack(padx=config.SPACING_XL, pady=config.SPACING_MD)

        self.status_var = tk.StringVar(value="0%")
        ctk.CTkLabel(
            self, textvariable=self.status_var, font=ctk.CTkFont(size=11),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(padx=config.SPACING_XL, pady=(0, config.SPACING_LG))

        import queue
        self._progress_queue: "queue.Queue" = queue.Queue()
        self._failed = False
        self.update_idletasks()
        try:
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            self.geometry(f"+{parent_x + (parent.winfo_width() - w) // 2}+"
                          f"{parent_y + (parent.winfo_height() - h) // 2}")
        except Exception:
            pass
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # not closable mid-download
        self.after(100, self._poll_progress)

    def _poll_progress(self) -> None:
        try:
            while True:
                item = self._progress_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    _done, _total = item[1], item[2]
                    self._render_progress(_done, _total)
                elif kind == "done":
                    self._failed = True
                    self._complete(str(item[1]))
                    return
                elif kind == "error":
                    self._failed = True
                    self._fail(str(item[1]))
                    return
        except Exception:
            pass
        if self.winfo_exists() and not self._failed:
            self.after(100, self._poll_progress)

    def set_progress(self, done: int, total: Optional[int]) -> None:
        # Worker thread: only enqueue; never touch Tk here.
        try:
            self._progress_queue.put(("progress", done, total))
        except Exception:
            pass

    def _render_progress(self, done: int, total: Optional[int]) -> None:
        try:
            if total and total > 0:
                fraction = min(1.0, done / total)
                self.progress.set(fraction)
                self.status_var.set(f"{int(fraction * 100)}%")
                self.detail_var.set(f"{done // 1024} KB / {total // 1024} KB")
            else:
                self.detail_var.set(f"{done // 1024} KB downloaded")
        except Exception:
            pass

    def _complete(self, installer_path: str) -> None:
        """Download finished: close the dialog, launch the installer, and
        close the app.  All on the main thread."""
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass
        try:
            from services.update_manager import update_manager
            app = self.winfo_toplevel()

            def _close() -> None:
                try:
                    app.destroy()
                except Exception:
                    pass

            update_manager.launch_installer(installer_path, close_app=_close)
        except Exception:
            pass

    def _fail(self, message: str) -> None:
        """Download failed: close the dialog, leave the app fully intact."""
        try:
            self.grab_release()
            self.destroy()
        except Exception:
            pass
        try:
            from utils import dialogs
            dialogs.error("Update Failed",
                          f"Could not download the update.\n\n{message}\n\n"
                          "Your current Expenzo version is unchanged and safe.",
                          parent=self.master)
        except Exception:
            pass
