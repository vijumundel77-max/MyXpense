"""
Expenzo — Dashboard
Modern dark-themed accounting dashboard with KPI cards, analytics split,
donut chart, and quick-action bar.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import os

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import config
from services.dashboard_service import dashboard_service
from database import database as db


class DashboardFrame(ctk.CTkFrame):
    """Modern accounting dashboard for the current company."""

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

        # UI containers
        self.kpi_cards_row1: Dict[str, ctk.CTkFrame] = {}
        self.kpi_labels_row1: Dict[str, ctk.CTkLabel] = {}
        self.kpi_cards_row2: Dict[str, ctk.CTkFrame] = {}
        self.kpi_labels_row2: Dict[str, ctk.CTkLabel] = {}

        self._build_update_banner()
        self._build_header()
        self._build_kpi_rows()
        self._build_analytics_section()
        self._build_quick_actions_bar()
        self._build_status()
        self.refresh()

        # Background update check
        self._check_updates_async()

    # ------------------------------------------------------------------ #
    # Tracked expense ledgers persistence
    # ------------------------------------------------------------------ #
    @property
    def _tracked_ledgers_path(self) -> str:
        return os.path.join(config.DATA_DIR, "dashboard_tracked_ledgers.json")

    def _load_tracked_ledgers(self) -> List[int]:
        """Return list of ledger ids the user wants to track."""
        try:
            with open(self._tracked_ledgers_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [int(x) for x in data.get("ledger_ids", [])]
        except Exception:
            return []

    def _save_tracked_ledgers(self, ledger_ids: List[int]) -> None:
        try:
            with open(self._tracked_ledgers_path, "w", encoding="utf-8") as f:
                json.dump({"ledger_ids": ledger_ids}, f)
        except Exception:
            pass

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
                text_color=config.COLOR_TEXT_PRIMARY,
            ).pack(side="left")
            ctk.CTkLabel(
                inner,
                text=f"New version available — Expenzo v{version}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
            ).pack(side="left", padx=(config.SPACING_SM, 0))

            ctk.CTkButton(
                inner, text="Later", width=80, height=28,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                fg_color="transparent", border_width=1,
                border_color=config.COLOR_TEXT_PRIMARY, text_color=config.COLOR_TEXT_PRIMARY,
                hover_color=config.COLOR_EXPENSE_HOVER,
                command=self._dismiss_update_banner,
            ).pack(side="right")
            ctk.CTkButton(
                inner, text="Update Now", width=110, height=28,
                corner_radius=config.BUTTON_CORNER_RADIUS,
                fg_color=config.COLOR_TEXT_PRIMARY, text_color=config.COLOR_BG_PRIMARY,
                hover_color=config.COLOR_BG_TERTIARY,
                command=self._on_update_now,
            ).pack(side="right", padx=(0, config.SPACING_SM))
        except Exception:
            pass

    def _dismiss_update_banner(self) -> None:
        try:
            self.update_banner.pack_forget()
        except Exception:
            pass

    def _on_update_now(self) -> None:
        info = self._update_info
        if not info:
            return
        try:
            from services.update_manager import update_manager
            progress = UpdateProgressDialog(self.winfo_toplevel())

            def _download() -> None:
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
        self.header.pack(fill="x", padx=config.SPACING_XL, pady=(8, 4))

        # Left side: title + company badge inline
        left = ctk.CTkFrame(self.header, fg_color="transparent")
        left.pack(side="left", fill="y")

        title_frame = ctk.CTkFrame(left, fg_color="transparent")
        title_frame.pack(anchor="w")
        ctk.CTkLabel(
            title_frame, text="Dashboard",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(side="left")
        self.company_label = ctk.CTkLabel(
            title_frame, text="", font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
            text_color=config.COLOR_PRIMARY,
        )
        self.company_label.pack(side="left", padx=(config.SPACING_SM, 0))

        self.subtitle_label = ctk.CTkLabel(
            left, text="Here's what's happening in your business today.",
            font=ctk.CTkFont(size=11), text_color=config.COLOR_TEXT_SECONDARY,
        )
        self.subtitle_label.pack(anchor="w", pady=(2,0))

        # Right side: refresh button + date pill (compact 28px)
        right = ctk.CTkFrame(self.header, fg_color="transparent")
        right.pack(side="right", fill="y")

        ctk.CTkButton(
            right, text="↻ Refresh", width=88, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.refresh,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="right", padx=(config.SPACING_SM, 0))

        today_str = date.today().strftime(config.DISPLAY_DATE_FORMAT)
        self.today_label = ctk.CTkLabel(
            right, text=f"📅 Today: {today_str}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=config.COLOR_TEXT_SECONDARY,
            fg_color=config.COLOR_BG_TERTIARY, corner_radius=6, padx=10, pady=2,
            height=28,
        )
        self.today_label.pack(side="right", padx=(config.SPACING_SM, 0))

    def _build_kpi_rows(self) -> None:
        # Row 1 – Balances
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=config.SPACING_XL, pady=(4, 0))

        self.kpi_cards_row1 = {}
        self.kpi_labels_row1 = {}
        self.kpi_badges_row1 = {}
        specs_row1 = [
            ("cash_balance", "Cash Balance", "Available Cash", config.COLOR_INCOME, "💵"),
            ("bank_balance", "Bank Balance", "In Bank Accounts", config.COLOR_PRIMARY, "🏦"),
            ("receivables", "Receivables", "Money to Receive", config.COLOR_WARNING, "📥"),
            ("payables", "Payables", "Money to Pay", config.COLOR_EXPENSE, "📤"),
        ]

        for idx, (key, title, subtitle, accent, icon) in enumerate(specs_row1):
            card = ctk.CTkFrame(
                row1, fg_color=config.COLOR_BG_SECONDARY, corner_radius=10,
                border_width=1, border_color=config.COLOR_CARD_BORDER,
                cursor="hand2" if key in {"bank_balance", "receivables", "payables"} else "",
                height=72,
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=(0, 4))
            card.grid_propagate(False)
            self.kpi_cards_row1[key] = card

            if key in {"bank_balance", "receivables", "payables"}:
                self._make_card_clickable(card, key)

            # Grid inside card: column 0 badge, column 1 info
            card.grid_columnconfigure(0, weight=0)
            card.grid_columnconfigure(1, weight=1)
            card.grid_rowconfigure(0, weight=1)

            # Badge
            badge = ctk.CTkLabel(
                card, text=icon, width=42, height=42,
                font=ctk.CTkFont(size=18),
                text_color=accent,
                fg_color=self._tint_color(accent, 0.15),
                corner_radius=21,
            )
            badge.grid(row=0, column=0, padx=(12,8), pady=12, sticky="n")
            self.kpi_badges_row1[key] = badge

            # Info frame
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=1, sticky="nsew", padx=(0,12), pady=8)
            info.grid_rowconfigure(0, weight=1)
            info.grid_rowconfigure(1, weight=1)
            info.grid_rowconfigure(2, weight=1)

            ctk.CTkLabel(
                info, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
            ).grid(row=0, column=0, sticky="sw")
            val = ctk.CTkLabel(
                info, text="₹ 0.00", font=ctk.CTkFont(size=16, weight="bold"),
                text_color=accent,
            )
            val.grid(row=1, column=0, sticky="w")
            ctk.CTkLabel(
                info, text=subtitle, font=ctk.CTkFont(size=9),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).grid(row=2, column=0, sticky="nw")
            self.kpi_labels_row1[key] = val

        for c in range(4):
            row1.grid_columnconfigure(c, weight=1)

        # Row 2 – Voucher Summaries
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=config.SPACING_XL, pady=(0, 6))

        self.kpi_cards_row2 = {}
        self.kpi_labels_row2 = {}
        self.kpi_badges_row2 = {}
        specs_row2 = [
            ("today_receipts", "Today's Receipts", "0 Vouchers", config.COLOR_INCOME, "↓"),
            ("today_payments", "Today's Payments", "0 Vouchers", config.COLOR_EXPENSE, "↑"),
            ("month_receipts", "This Month's Receipts", "0 Vouchers", config.COLOR_INCOME, "📅"),
            ("month_payments", "This Month's Payments", "0 Vouchers", config.COLOR_EXPENSE, "📅"),
        ]

        for idx, (key, title, subtitle, accent, icon) in enumerate(specs_row2):
            card = ctk.CTkFrame(
                row2, fg_color=config.COLOR_BG_SECONDARY, corner_radius=10,
                border_width=1, border_color=config.COLOR_CARD_BORDER,
                cursor="hand2" if key in {"month_receipts", "month_payments"} else "",
                height=72,
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=(0, 4))
            card.grid_propagate(False)
            self.kpi_cards_row2[key] = card

            if key in {"month_receipts", "month_payments"}:
                self._make_card_clickable(card, key)

            card.grid_columnconfigure(0, weight=0)
            card.grid_columnconfigure(1, weight=1)
            card.grid_rowconfigure(0, weight=1)

            badge = ctk.CTkLabel(
                card, text=icon, width=42, height=42,
                font=ctk.CTkFont(size=18),
                text_color=accent,
                fg_color=self._tint_color(accent, 0.15),
                corner_radius=21,
            )
            badge.grid(row=0, column=0, padx=(12,8), pady=12, sticky="n")
            self.kpi_badges_row2[key] = badge

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=1, sticky="nsew", padx=(0,12), pady=8)
            info.grid_rowconfigure(0, weight=1)
            info.grid_rowconfigure(1, weight=1)
            info.grid_rowconfigure(2, weight=1)

            ctk.CTkLabel(
                info, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                text_color=config.COLOR_TEXT_PRIMARY,
            ).grid(row=0, column=0, sticky="sw")
            val = ctk.CTkLabel(
                info, text="₹ 0.00", font=ctk.CTkFont(size=16, weight="bold"),
                text_color=accent,
            )
            val.grid(row=1, column=0, sticky="w")
            ctk.CTkLabel(
                info, text=subtitle, font=ctk.CTkFont(size=9),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).grid(row=2, column=0, sticky="nw")
            self.kpi_labels_row2[key] = val

        for c in range(4):
            row2.grid_columnconfigure(c, weight=1)

    def _tint_color(self, hex_color: str, factor: float) -> str:
        """Tint a color toward the current theme's card background (BG_TERTIARY)."""
        # Use the active theme's tertiary background so the badge works in both modes.
        bg_hex = config.COLOR_BG_TERTIARY
        bg = tuple(int(bg_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r * factor + bg[0] * (1 - factor))
        g = int(g * factor + bg[1] * (1 - factor))
        b = int(b * factor + bg[2] * (1 - factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _build_analytics_section(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=config.SPACING_XL,
                       pady=(4, 6))

        # Left box (60%) – fixed height ~240
        left_box = ctk.CTkFrame(
            container, fg_color=config.COLOR_BG_SECONDARY, corner_radius=10,
            border_width=1, border_color=config.COLOR_CARD_BORDER,
            height=240,
        )
        left_box.pack(side="left", fill="both", expand=True, padx=(0, config.SPACING_MD))
        left_box.pack_propagate(False)

        # Header with dropdown
        hdr = ctk.CTkFrame(left_box, fg_color="transparent")
        hdr.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_MD, 0))
        ctk.CTkLabel(
            hdr, text="Expenses Overview", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY,
        ).pack(side="left")
        # Manage button
        manage_btn = ctk.CTkButton(
            hdr, text="⚙ Manage", width=90, height=26,
            corner_radius=6, fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_PRIMARY,
            text_color=config.COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._open_manage_expenses_dialog,
        )
        manage_btn.pack(side="right", padx=(config.SPACING_SM, 0))
        self.period_var = tk.StringVar(value="This Month")
        period_menu = ctk.CTkOptionMenu(
            hdr, values=["Today", "This Week", "This Month", "This Year"],
            variable=self.period_var, width=120, height=28,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color=config.COLOR_BG_TERTIARY, button_color=config.COLOR_PRIMARY,
            text_color=config.COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(size=11),
        )
        period_menu.pack(side="right")
        # refresh analytics when period changes
        self.period_var.trace_add("write", lambda *_: self._update_analytics())

        # Mini stat chips
        chips_frame = ctk.CTkFrame(left_box, fg_color="transparent")
        chips_frame.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_SM, 0))
        chip_data = [
            ("Total Expenses", config.COLOR_TRANSFER),
            ("Today's Expenses", config.COLOR_PRIMARY),
            ("This Month's Expenses", config.COLOR_WARNING),
        ]
        self.chip_value_labels = []
        for label_text, color in chip_data:
            chip = ctk.CTkFrame(chips_frame, fg_color=self._tint_color(color, 0.15),
                                corner_radius=8, border_width=1, border_color=color)
            chip.pack(side="left", padx=(0, config.SPACING_SM), fill="y")
            val_lbl = ctk.CTkLabel(
                chip, text="₹ 0.00", font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color,
            )
            val_lbl.pack(padx=config.SPACING_MD, pady=config.SPACING_XS)
            self.chip_value_labels.append(val_lbl)
            ctk.CTkLabel(
                chip, text=label_text, font=ctk.CTkFont(size=9),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(padx=config.SPACING_MD, pady=(0, config.SPACING_XS))

        # Category breakdown with progress bars
        self.category_rows = []
        cat_frame = ctk.CTkFrame(left_box, fg_color="transparent")
        cat_frame.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(config.SPACING_SM, config.SPACING_MD))
        self.cat_frame = cat_frame
        # Dynamic rows will be created in _update_analytics based on tracked ledgers

        # Total expenses subtotal
        total_row = ctk.CTkFrame(left_box, fg_color="transparent")
        total_row.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_MD))
        ctk.CTkLabel(total_row, text="Total Expenses", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=config.COLOR_TEXT_PRIMARY).pack(side="left")
        self.total_expenses_lbl = ctk.CTkLabel(total_row, text="₹ 0.00",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color=config.COLOR_TEXT_PRIMARY)
        self.total_expenses_lbl.pack(side="right")

        # Right box (40%) – fixed height ~240
        right_box = ctk.CTkFrame(
            container, fg_color=config.COLOR_BG_SECONDARY, corner_radius=10,
            border_width=1, border_color=config.COLOR_CARD_BORDER, width=400,
            height=240,
        )
        right_box.pack(side="right", fill="y", padx=(config.SPACING_MD, 0))
        right_box.pack_propagate(False)

        # Donut chart - initialize with theme-aware colors
        is_dark = ctk.get_appearance_mode() == "Dark"
        chart_bg = "#10192E" if is_dark else "#FFFFFF"
        
        chart_frame = ctk.CTkFrame(right_box, fg_color="transparent")
        chart_frame.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(config.SPACING_MD, config.SPACING_SM))
        self.fig = Figure(figsize=(3.6, 2.8), dpi=100)
        self.fig.patch.set_facecolor(chart_bg)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(chart_bg)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Legend placeholder
        self.legend_frame = ctk.CTkFrame(right_box, fg_color="transparent")
        self.legend_frame.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_SM))

        # Mini stat cards
        mini_frame = ctk.CTkFrame(right_box, fg_color="transparent")
        mini_frame.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_MD))
        
        # Average Daily Expense
        avg_card = ctk.CTkFrame(mini_frame, fg_color=config.COLOR_BG_TERTIARY,
                                corner_radius=8, border_width=1, border_color=config.COLOR_CARD_BORDER)
        avg_card.pack(side="left", fill="both", expand=True, padx=(0, config.SPACING_SM))
        ctk.CTkLabel(avg_card, text="Average Daily Expense", font=ctk.CTkFont(size=10),
                     text_color=config.COLOR_TEXT_SECONDARY).pack(padx=config.SPACING_MD, pady=(config.SPACING_XS, 0))
        self.avg_daily_lbl = ctk.CTkLabel(avg_card, text="₹ 0.00",
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          text_color=config.COLOR_PRIMARY)
        self.avg_daily_lbl.pack(padx=config.SPACING_MD, pady=(0, config.SPACING_XS))
        
        spark = ctk.CTkLabel(avg_card, text="▁▂▃▅▆▇", font=ctk.CTkFont(size=9),
                             text_color=config.COLOR_TEXT_MUTED)
        spark.pack(padx=config.SPACING_MD, pady=(0, config.SPACING_XS))

        # Days in Month vs Days Passed
        days_card = ctk.CTkFrame(mini_frame, fg_color=config.COLOR_BG_TERTIARY,
                                 corner_radius=8, border_width=1, border_color=config.COLOR_CARD_BORDER)
        days_card.pack(side="left", fill="both", expand=True, padx=(config.SPACING_SM, 0))
        ctk.CTkLabel(days_card, text="Days in Month vs Days Passed", font=ctk.CTkFont(size=10),
                     text_color=config.COLOR_TEXT_SECONDARY).pack(padx=config.SPACING_MD, pady=(config.SPACING_XS, 0))
        self.days_lbl = ctk.CTkLabel(days_card, text="0 / 30",
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     text_color=config.COLOR_WARNING)
        self.days_lbl.pack(padx=config.SPACING_MD, pady=(0, config.SPACING_XS))
        self.days_progress = ctk.CTkProgressBar(days_card, progress_color=config.COLOR_WARNING,
                                               fg_color=config.COLOR_BG_SECONDARY, corner_radius=4)
        self.days_progress.set(0)
        self.days_progress.pack(padx=config.SPACING_MD, pady=(0, config.SPACING_XS), fill="x")

    # ------------------------------------------------------------------ #
    # analytics update using tracked ledgers
    # ------------------------------------------------------------------ #
    def _update_analytics(self) -> None:
        from database.database import db

        # 1. Get saved tracked ledger IDs (fallback to all expense account IDs if empty)
        tracked_ids = getattr(self, "tracked_ledger_ids", [])
        if not tracked_ids:
            tracked_ids = self._load_tracked_ledgers()
        if not tracked_ids:
            rows = db.fetch_all("SELECT id FROM accounts WHERE company_id = ? AND (LOWER(account_group) LIKE '%expense%' OR LOWER(account_group) LIKE '%direct%' OR LOWER(account_group) LIKE '%indirect%')", (self.company_id,))
            tracked_ids = [r['id'] for r in rows]

        items = []
        total_spent = 0.0

        if tracked_ids:
            placeholders = ",".join(["?"] * len(tracked_ids))
            query = f"""
                SELECT 
                    a.id,
                    a.name,
                    COALESCE(SUM(vd.debit_amount), 0.0) AS spent
                FROM accounts a
                LEFT JOIN voucher_details vd ON a.id = vd.account_id
                WHERE a.id IN ({placeholders}) AND a.company_id = ?
                GROUP BY a.id, a.name
                ORDER BY spent DESC, a.name ASC
            """
            params = tuple(tracked_ids) + (self.company_id,)
            rows = db.fetch_all(query, params)
            for r in rows:
                d = dict(r)
                amt = float(d.get('spent') or 0.0)
                total_spent += amt
                items.append({'id': d['id'], 'name': d['name'], 'amount': amt})

        # 2. Update Top 3 Stat Chips
        self.total_expenses_lbl.configure(text=f"₹ {total_spent:,.2f}")

        # 3. Dynamic Progress Rows in Left Box
        for w in self.cat_frame.winfo_children():
            w.destroy()

        palette = ["#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899", "#06B6D4", "#EF4444"]

        # Get theme-aware colors
        is_dark = ctk.get_appearance_mode() == "Dark"
        text_primary = config.COLOR_TEXT_PRIMARY if is_dark else config.LIGHT_TEXT_PRIMARY
        text_secondary = config.COLOR_TEXT_SECONDARY if is_dark else config.LIGHT_TEXT_SECONDARY
        text_muted = config.COLOR_TEXT_MUTED if is_dark else config.LIGHT_TEXT_MUTED
        bg_secondary = config.COLOR_BG_SECONDARY if is_dark else config.LIGHT_BG_SECONDARY
        bg_tertiary = config.COLOR_BG_TERTIARY if is_dark else config.LIGHT_BG_TERTIARY
        card_border = config.COLOR_CARD_BORDER if is_dark else config.LIGHT_CARD_BORDER
        chart_bg = "#10192E" if is_dark else "#FFFFFF"
        chart_edge = chart_bg
        chart_text = "#FFFFFF" if is_dark else "#0F172A"
        progress_bg = config.COLOR_BG_TERTIARY

        if not items:
            ctk.CTkLabel(self.cat_frame, text="No expense ledgers tracked. Click Manage.", text_color=text_muted).pack(pady=20)
        else:
            for idx, item in enumerate(items):
                col = palette[idx % len(palette)]
                amt = item['amount']
                pct = (amt / total_spent * 100) if total_spent > 0 else 0

                row = ctk.CTkFrame(self.cat_frame, fg_color="transparent")
                row.pack(fill="x", pady=3)

                ctk.CTkLabel(row, text=item['name'], font=ctk.CTkFont(size=11), text_color=text_primary, width=140, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"₹ {amt:,.2f}", font=ctk.CTkFont(size=11, weight="bold"), text_color=col, width=90, anchor="e").pack(side="left", padx=4)

                pbar = ctk.CTkProgressBar(row, progress_color=col, fg_color=progress_bg, corner_radius=4, height=8)
                pbar.set(pct / 100.0)
                pbar.pack(side="left", padx=8, fill="x", expand=True)

                ctk.CTkLabel(row, text=f"{pct:.0f}%", font=ctk.CTkFont(size=10), text_color=text_muted, width=40, anchor="e").pack(side="left")

        # 4. Donut Chart & Legend in Right Box
        self.ax.clear()
        self.fig.patch.set_facecolor(chart_bg)
        self.ax.set_facecolor(chart_bg)

        # Only pass slices that have spent > 0
        active_items = [it for it in items if it['amount'] > 0]
        if active_items and total_spent > 0:
            sizes = [it['amount'] for it in active_items]
            chart_colors = palette[:len(active_items)]
            self.ax.pie(sizes, colors=chart_colors, startangle=90, wedgeprops=dict(width=0.4, edgecolor=chart_edge))
            self.ax.text(0, 0, f"Total\n₹{total_spent:,.0f}", ha='center', va='center', fontsize=10, fontweight='bold', color=chart_text)
        else:
            placeholder_color = bg_tertiary
            self.ax.pie([1], startangle=90, colors=[placeholder_color], wedgeprops=dict(width=0.4, edgecolor=chart_edge))
            self.ax.text(0, 0, "No Expenses\nRecorded", ha='center', va='center', fontsize=9, fontweight='bold', color=text_muted)

        self.canvas.draw()

        # 5. Legend in Right Box
        for widget in self.legend_frame.winfo_children():
            widget.destroy()
        if active_items and total_spent > 0:
            for idx, it in enumerate(active_items):
                col = palette[idx % len(palette)]
                row = ctk.CTkFrame(self.legend_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                dot = ctk.CTkLabel(row, text="●", text_color=col, font=ctk.CTkFont(size=12))
                dot.pack(side="left", padx=(0, config.SPACING_SM))
                ctk.CTkLabel(row, text=it['name'], font=ctk.CTkFont(size=11), text_color=text_primary).pack(side="left")
                ctk.CTkLabel(row, text=f"₹ {it['amount']:,.0f} ({(it['amount']/total_spent*100):.0f}%)", font=ctk.CTkFont(size=11), text_color=text_secondary).pack(side="right")

        self.canvas.draw()

    def _fetch_ledger_totals(self, ledger_ids: List[int], from_date: date, to_date: date) -> Dict[int, float]:
        """Return dict ledger_id -> total debit amount for vouchers in date range."""
        if not ledger_ids:
            return {}
        placeholders = ",".join(["%s"] * len(ledger_ids))
        query = f"""
            SELECT e.ledger_id, SUM(e.debit) as total
            FROM voucher_entries e
            JOIN vouchers v ON e.voucher_id = v.id
            WHERE v.company_id = %s
              AND v.voucher_date BETWEEN %s AND %s
              AND e.ledger_id IN ({placeholders})
            GROUP BY e.ledger_id
        """
        params = [self.company_id, from_date, to_date] + ledger_ids
        try:
            rows = db.fetch_all(query, params)
            return {int(r["ledger_id"]): float(r["total"] or 0.0) for r in rows}
        except Exception:
            return {}

    def _build_quick_actions_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=config.SPACING_XL, pady=(config.SPACING_XL, config.SPACING_XL))

        actions = [
            ("Masters", "show_masters"),
            ("Enter Voucher", "show_vouchers"),
            ("Open Reports", "show_reports"),
            ("Cash Book", "show_cash_book"),
            ("Bank Book", "show_bank_book"),
            ("Day Book", "show_day_book"),
        ]
        for idx, (txt, method) in enumerate(actions):
            btn = ctk.CTkButton(
                bar, text=txt, height=38,
                corner_radius=19,
                fg_color=config.COLOR_BG_TERTIARY,
                hover_color=config.COLOR_PRIMARY,
                text_color=config.COLOR_TEXT_PRIMARY,
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda m=method: self._navigate(m),
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else config.SPACING_SM, 0))

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
        card.configure(cursor="hand2")
        for widget in [card] + list(card.winfo_children()):
            try:
                widget.bind("<Button-1>", lambda e, k=key: self._on_card_click(k))
                widget.bind("<Enter>", lambda e, k=key: self._on_card_hover(k, True))
                widget.bind("<Leave>", lambda e, k=key: self._on_card_hover(k, False))
            except Exception:
                pass

    def _on_card_hover(self, key: str, hovered: bool) -> None:
        card = self.kpi_cards_row1.get(key) or self.kpi_cards_row2.get(key)
        if card is None:
            return
        try:
            is_dark = ctk.get_appearance_mode() == "Dark"
            if hovered:
                card.configure(border_color=config.COLOR_PRIMARY,
                               fg_color="#112244" if is_dark else "#DBEAFE")
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

    def _open_manage_expenses_dialog(self) -> None:
        """Open the Manage Expense Ledgers modal."""
        print(f"[DEBUG] Manage button clicked, opening dialog for company {self.company_id}")
        dlg = ManageExpenseLedgersDialog(self.winfo_toplevel(), self.company_id, dashboard=self, on_save=self.refresh)
        dlg.grab_set()
        dlg.focus_set()

    def on_keyboard_back(self) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, "on_keyboard_back"):
            app.on_keyboard_back()

    def _resolve_company_id(self) -> int:
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None)
        if company_id is not None:
            return int(company_id)
        row = self._db_fetch("SELECT id FROM companies ORDER BY id LIMIT 1")
        return int(row["id"]) if row else 1

    def _global_single_date(self) -> Optional[date]:
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
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None)
        if company_id is not None:
            self.company_id = int(company_id)
        self.data = dashboard_service.get_dashboard(self.company_id, self._global_single_date())

        self.company_label.configure(text=self.data.get('company_name', ''))

        # Row 1 KPIs
        for key, label in self.kpi_labels_row1.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")

        # Row 2 KPIs
        for key, label in self.kpi_labels_row2.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")

        self._update_analytics()
        self._sync_date_labels()
        self.status_var.set(
            f"Updated {date.today().strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

    def refresh_theme(self) -> None:
        """Refresh theme-dependent colors (chart, stat chips, badges, category rows)."""
        # Refresh KPI badge backgrounds using current theme
        for badge_dict in (getattr(self, "kpi_badges_row1", {}), getattr(self, "kpi_badges_row2", {})):
            for key, badge in badge_dict.items():
                try:
                    accent = badge.cget("text_color")
                    badge.configure(fg_color=self._tint_color(accent, 0.15))
                except Exception:
                    pass

        # Update chart background
        chart_bg = config.COLOR_BG_PRIMARY
        try:
            self.fig.patch.set_facecolor(chart_bg)
            self.ax.set_facecolor(chart_bg)
            self.canvas.draw_idle()
        except Exception:
            pass
        
        # Refresh stat chips (they use _tint_color which is now theme-aware)
        chip_data = [
            ("Total Expenses", config.COLOR_TRANSFER),
            ("Today's Expenses", config.COLOR_PRIMARY),
            ("This Month's Expenses", config.COLOR_WARNING),
        ]
        for idx, (label_text, color) in enumerate(chip_data):
            try:
                chip_frame = self.chip_value_labels[idx].master
                chip_frame.configure(fg_color=self._tint_color(color, 0.15), border_color=color)
            except Exception:
                pass
        
        # Refresh category rows (re-run analytics to rebuild with new colors)
        self._update_analytics()

    def _sync_date_labels(self) -> None:
        try:
            from services.date_control_service import date_control
            day = self._global_single_date()
            self.today_label.configure(text=f"📅 Today: {day.strftime(config.DISPLAY_DATE_FORMAT)}")
            if date_control.has_period:
                f, t = date_control.period(self.company_id)
                self.subtitle_label.configure(
                    text=f"Period: {f.strftime(config.DISPLAY_DATE_FORMAT)} to "
                         f"{t.strftime(config.DISPLAY_DATE_FORMAT)}")
            else:
                self.subtitle_label.configure(text="Here's what's happening in your business today.")
        except Exception:
            pass

    def on_global_date_period(self, from_date, to_date) -> None:
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
        self._sync_date_labels()
        self.status_var.set(
            f"Period {from_date.strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{to_date.strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

    def on_global_single_date(self, day) -> None:
        from services.voucher_service import voucher_service
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None) or self.company_id
        self.data = dashboard_service.get_dashboard(int(company_id), day)
        for key, label in self.kpi_labels_row1.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")
        for key, label in self.kpi_labels_row2.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")
        self._update_analytics()
        self._sync_date_labels()
        self.status_var.set(
            f"Date {day.strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

    def _navigate(self, method_name: str) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, method_name):
            getattr(app, method_name)()


class DashboardDetailDialog(ctk.CTkToplevel):
    """Accounting-style detail modal for a drill-down dashboard card."""

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
        self.detail_title = title if title not in self.FRIENDLY_TITLES \
            else self.FRIENDLY_TITLES[title]

        self.title(f"{self.detail_title} — {config.APP_NAME}")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.configure(fg_color=config.COLOR_BG_PRIMARY)

        width = 620 if key in {"bank_balance", "receivables", "payables"} else 720
        height = 480
        self.geometry(f"{width}x{height}")
        self.minsize(width, height)
        self.resizable(False, False)

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

    def _build(self) -> None:
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

        self.subtitle_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_MUTED, anchor="w",
        )
        self.subtitle_label.pack(fill="x", padx=config.SPACING_XL,
                                 pady=(config.SPACING_XS, 0))

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

    def _load_data(self) -> None:
        rows: List[Dict[str, Any]] = []
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


class ManageExpenseLedgersDialog(ctk.CTkToplevel):
    """Modal to select which expense ledgers the dashboard should track."""

    def __init__(self, parent, company_id: int, dashboard, on_save):
        super().__init__(parent)
        self.company_id = company_id
        self.dashboard = dashboard
        self.on_save = on_save
        self.title("Select Expense Ledgers to Track")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.configure(fg_color=config.COLOR_BG_PRIMARY)
        self.geometry("520x600")
        self.minsize(520, 600)
        self.resizable(False, False)

        # Center over parent
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - 520) // 2
            y = py + (ph - 600) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self._build_ui()
        self._load_ledgers()
        self.grab_set()
        self.focus_set()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_MD))
        ctk.CTkLabel(hdr, text="Select Expense Ledgers to Track",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=config.COLOR_TEXT_PRIMARY).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=30, height=30,
                      corner_radius=6, fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_PRIMARY,
                      text_color=config.COLOR_TEXT_PRIMARY,
                      command=self._close).pack(side="right")

        # Search bar
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_list())
        search_entry = ctk.CTkEntry(self, placeholder_text="🔍 Search ledger…",
                                    textvariable=self.search_var,
                                    fg_color=config.COLOR_BG_TERTIARY,
                                    border_color=config.COLOR_CARD_BORDER,
                                    text_color=config.COLOR_TEXT_PRIMARY)
        search_entry.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_MD))

        # Action bar
        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_MD))
        ctk.CTkButton(action_bar, text="Select All", width=100, height=28,
                      corner_radius=config.BUTTON_CORNER_RADIUS,
                      fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
                      command=self._select_all).pack(side="left", padx=(0, config.SPACING_SM))
        ctk.CTkButton(action_bar, text="Deselect All", width=100, height=28,
                      corner_radius=config.BUTTON_CORNER_RADIUS,
                      fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_PRIMARY,
                      text_color=config.COLOR_TEXT_PRIMARY,
                      command=self._deselect_all).pack(side="left")

        # Scrollable list
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=config.COLOR_BG_SECONDARY,
                                             corner_radius=8, border_width=1,
                                             border_color=config.COLOR_CARD_BORDER)
        self.scroll.pack(fill="both", expand=True, padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
        self.checkbox_vars = {}   # ledger_id -> BooleanVar
        self.checkbox_widgets = {}  # ledger_id -> CTkCheckBox

        # Footer buttons
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
        ctk.CTkButton(footer, text="Cancel", width=110, height=34,
                      corner_radius=config.BUTTON_CORNER_RADIUS,
                      fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_PRIMARY,
                      text_color=config.COLOR_TEXT_PRIMARY,
                      command=self._close).pack(side="right", padx=(config.SPACING_SM, 0))
        ctk.CTkButton(footer, text="Save Changes", width=130, height=34,
                      corner_radius=config.BUTTON_CORNER_RADIUS,
                      fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
                      command=self._save).pack(side="right")

    def _fetch_expense_ledgers(self) -> list:
        """Auto-detect tables & columns, then fetch expense ledger rows for the current company."""
        from database.database import db

        print(f"\n--- [DEBUG] FETCHING LEDGERS FOR COMPANY ID: {self.company_id} ---")

        # 1. List all tables
        tables = [r['name'] for r in db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")]
        print(f"[DEBUG] Available Tables: {tables}")

        # 2. Choose target table
        target_table = None
        for tbl in ['ledgers', 'accounts', 'account_masters', 'parties']:
            if tbl in tables:
                target_table = tbl
                break

        if not target_table:
            print("[DEBUG] No suitable ledger/account table found in database!")
            return []

        # 3. Inspect columns
        cols = [r['name'] for r in db.fetch_all(f"PRAGMA table_info({target_table})")]
        print(f"[DEBUG] Table '{target_table}' Columns: {cols}")

        # 4. Build query – prefer expense‑specific filter when possible
        has_comp = 'company_id' in cols
        name_col = 'name' if 'name' in cols else cols[1]
        id_col = 'id' if 'id' in cols else cols[0]

        # If we have an accounts table with account_group, use a focused expense query
        if target_table == 'accounts' and 'account_group' in cols:
            sql = """
                SELECT id, name, account_group AS group_name
                FROM accounts
                WHERE company_id = ?
                  AND (
                      LOWER(account_group) LIKE '%expense%'
                      OR LOWER(account_group) LIKE '%direct expense%'
                      OR LOWER(account_group) LIKE '%indirect expense%'
                      OR LOWER(name) IN ('food', 'fuel', 'rent', 'alka exp', 'office expense', 'electricity')
                  )
                  AND LOWER(account_group) NOT LIKE '%income%'
                ORDER BY account_group ASC, name ASC
            """
            rows = db.fetch_all(sql, (self.company_id,))
            # fallback if nothing matched
            if not rows:
                print("[DEBUG] Expense filter returned zero rows, falling back to all accounts for company...")
                sql_fallback = f"SELECT {id_col} AS id, {name_col} AS name, account_group AS group_name FROM {target_table}"
                if has_comp:
                    sql_fallback += f" WHERE company_id = ? ORDER BY {name_col} ASC"
                    rows = db.fetch_all(sql_fallback, (self.company_id,))
                else:
                    sql_fallback += f" ORDER BY {name_col} ASC"
                    rows = db.fetch_all(sql_fallback)
        else:
            # Generic safe query for other tables
            grp_col = "'' AS group_name"
            for g in ['account_group', 'group_name', 'group_id', 'type', 'category']:
                if g in cols:
                    grp_col = f"{g} AS group_name"
                    break
            base_sql = f"SELECT {id_col} AS id, {name_col} AS name, {grp_col} FROM {target_table}"
            if has_comp:
                sql = f"{base_sql} WHERE company_id = ? ORDER BY {name_col} ASC"
                rows = db.fetch_all(sql, (self.company_id,))
                if not rows:
                    print("[DEBUG] Zero rows with company_id, trying fallback without company_id filter...")
                    rows = db.fetch_all(f"{base_sql} ORDER BY {name_col} ASC")
            else:
                sql = f"{base_sql} ORDER BY {name_col} ASC"
                rows = db.fetch_all(sql)

        print(f"[DEBUG] Total Rows Fetched from '{target_table}': {len(rows)}")
        if rows:
            print(f"[DEBUG] Sample Row: {dict(rows[0])}")

        return rows

    def _load_ledgers(self):
        """Fetch expense ledgers and render checkboxes in the scrollable frame."""
        # Clear any existing widgets
        for widget in self.scroll.winfo_children():
            widget.destroy()

        rows = self._fetch_expense_ledgers()
        print(f"[DEBUG] Modal Opened -> Company ID: {self.company_id} | Total Rows to Display: {len(rows)}")

        if not rows:
            ctk.CTkLabel(
                self.scroll,
                text="No ledgers found. Please verify company ID and ledger groups.",
                text_color=config.COLOR_EXPENSE,
                font=ctk.CTkFont(size=12)
            ).pack(pady=20)
            self.all_ledgers = []
            return

        tracked = set(self.dashboard._load_tracked_ledgers())
        self.all_ledgers = []
        for row in rows:
            # Convert sqlite3.Row to dict safely
            acc = dict(row)
            acc_id = int(acc["id"])
            name = acc["name"]
            grp = acc.get("group_name") or acc.get("account_group") or "Expense"

            self.all_ledgers.append((acc_id, name, grp))

            var = tk.BooleanVar(value=acc_id in tracked)
            self.checkbox_vars[acc_id] = var

            row_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
            row_frame.pack(fill="x", padx=10, pady=4, anchor="w")

            cb = ctk.CTkCheckBox(
                row_frame,
                text=f"{name}  —  [{grp}]",
                variable=var,
                font=ctk.CTkFont(size=12),
                text_color=config.COLOR_TEXT_PRIMARY,
                fg_color=config.COLOR_PRIMARY,
                hover_color=config.COLOR_PRIMARY_HOVER
            )
            cb.pack(side="left", fill="x", expand=True)
            self.checkbox_widgets[acc_id] = cb

    def _filter_list(self):
        term = self.search_var.get().lower()
        for ledger_id, name, group in self.all_ledgers:
            label = f"{name}  —  [{group}]".lower()
            cb = self.checkbox_widgets.get(ledger_id)
            if cb:
                if term in label:
                    cb.pack(fill="x", padx=config.SPACING_MD, pady=5, anchor="w")
                else:
                    cb.pack_forget()

    def _select_all(self):
        for var in self.checkbox_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self.checkbox_vars.values():
            var.set(False)

    def _save(self):
        selected = [lid for lid, var in self.checkbox_vars.items() if var.get()]
        # Persist using dashboard frame's save method
        self.dashboard._save_tracked_ledgers(selected)
        print(f"[DEBUG] Saved {len(selected)} tracked ledgers")
        self._close()
        if self.on_save:
            self.on_save()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()


class UpdateProgressDialog(ctk.CTkToplevel):
    """Modal progress dialog shown while the update installer downloads."""

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
        self.protocol("WM_DELETE_WINDOW", lambda: None)
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