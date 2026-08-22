"""
ui/dashboard.py
Expenzo Accounting — Ultra-Responsive High-Density Dashboard
Includes Deep Canvas Event Binding & Real-Time Company Sync.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from database.database import db
from services.date_control_service import date_control


class DashboardFrame(ctk.CTkFrame):
    def __init__(self, parent, controller=None, company_id=1, **kwargs):
        super().__init__(parent, fg_color="#0B1329", **kwargs)
        self.controller = controller or parent
        self.company_id = company_id
        self.period_var = tk.StringVar(value="This Month")
        self.pack(fill="both", expand=True)

        self._build_header()
        self._build_stat_cards_grid()
        self._build_lower_section()
        self._build_quick_actions_bar()

        self.refresh_dashboard()

    # =========================================================================
    # 1. DEEP EVENT BINDING (Fixes unclickable custom card issues)
    # =========================================================================
    def _bind_deep_click(self, widget, callback):
        """Recursively binds left-click to widget, its canvas, and all nested sub-elements."""
        def _handler(event):
            callback()
            return "break"

        try:
            widget.bind("<Button-1>", _handler)
            widget.configure(cursor="hand2")
        except Exception:
            pass

        # Intercept internal CustomTkinter rendering layers
        if hasattr(widget, "_canvas") and widget._canvas:
            widget._canvas.bind("<Button-1>", _handler)
        if hasattr(widget, "_text_label") and widget._text_label:
            widget._text_label.bind("<Button-1>", _handler)
        if hasattr(widget, "_image_label") and widget._image_label:
            widget._image_label.bind("<Button-1>", _handler)

        for child in widget.winfo_children():
            self._bind_deep_click(child, callback)

    def _add_hover_effect(self, card, normal_bg="#10192E", hover_bg="#162544", normal_border="#1B2848", hover_border="#3B82F6"):
        """Subtle hover feedback on cards."""
        def _on_enter(e):
            try:
                card.configure(fg_color=hover_bg, border_color=hover_border)
            except Exception:
                pass

        def _on_leave(e):
            try:
                card.configure(fg_color=normal_bg, border_color=normal_border)
            except Exception:
                pass

        card.bind("<Enter>", _on_enter)
        card.bind("<Leave>", _on_leave)
        if hasattr(card, "_canvas") and card._canvas:
            card._canvas.bind("<Enter>", _on_enter)
            card._canvas.bind("<Leave>", _on_leave)

    # =========================================================================
    # 2. UI LAYOUT BUILDERS
    # =========================================================================
    def _build_header(self):
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", height=42)
        self.header_frame.pack(fill="x", padx=16, pady=(6, 4))
        self.header_frame.pack_propagate(False)

        left = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        left.pack(side="left", fill="y")

        self.title_label = ctk.CTkLabel(
            left, 
            text="Dashboard", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#FFFFFF"
        )
        self.title_label.pack(side="left")

        self.company_badge = ctk.CTkLabel(
            left, 
            text="", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#60A5FA"
        )
        self.company_badge.pack(side="left", padx=(8, 0))

        self.subtitle_label = ctk.CTkLabel(
            left,
            text="— Here's what's happening in your business today.",
            font=ctk.CTkFont(size=11),
            text_color="#64748B"
        )
        self.subtitle_label.pack(side="left", padx=(8, 0), pady=(3, 0))

        right = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right.pack(side="right", fill="y")

        today_str = datetime.now().strftime("%d-%m-%Y")
        self.date_badge = ctk.CTkLabel(
            right,
            text=f"📅 Today: {today_str}",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#10192E",
            text_color="#94A3B8",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.date_badge.pack(side="left", padx=(0, 8))

        self.refresh_btn = ctk.CTkButton(
            right,
            text="↻ Refresh",
            width=80,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self.refresh_dashboard
        )
        self.refresh_btn.pack(side="left")

    def _create_stat_card(self, parent, icon, title, initial_amount, subtitle, text_color="#FFFFFF", icon_bg="#16223E"):
        card = ctk.CTkFrame(
            parent,
            fg_color="#10192E",
            border_color="#1B2848",
            border_width=1,
            corner_radius=10,
            height=82
        )
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        # Icon
        icon_lbl = ctk.CTkLabel(
            inner,
            text=icon,
            font=ctk.CTkFont(size=16),
            width=36,
            height=36,
            fg_color=icon_bg,
            corner_radius=8
        )
        icon_lbl.pack(side="left", padx=(0, 10))

        # Details
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        t_lbl = ctk.CTkLabel(info, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8", anchor="w")
        t_lbl.pack(fill="x")

        amt_lbl = ctk.CTkLabel(info, text=initial_amount, font=ctk.CTkFont(size=15, weight="bold"), text_color=text_color, anchor="w")
        amt_lbl.pack(fill="x")

        sub_lbl = ctk.CTkLabel(info, text=subtitle, font=ctk.CTkFont(size=10), text_color="#64748B", anchor="w")
        sub_lbl.pack(fill="x")

        self._add_hover_effect(card)
        return card, amt_lbl, sub_lbl

    def _build_stat_cards_grid(self):
        self.cards_container = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_container.pack(fill="x", padx=16, pady=(0, 6))

        # Row 1
        r1 = ctk.CTkFrame(self.cards_container, fg_color="transparent")
        r1.pack(fill="x", pady=(0, 6))
        for col in range(4):
            r1.grid_columnconfigure(col, weight=1, uniform="stat_cards")

        self.card_cash, self.lbl_cash_amt, self.lbl_cash_sub = self._create_stat_card(
            r1, "💵", "Cash Balance", "₹ 0.00", "Available Cash", "#10B981", "#064E3B"
        )
        self.card_cash.grid(row=0, column=0, padx=(0, 4), sticky="nsew")

        self.card_bank, self.lbl_bank_amt, self.lbl_bank_sub = self._create_stat_card(
            r1, "🏦", "Bank Balance", "₹ 0.00", "In Bank Accounts", "#60A5FA", "#1E3A8A"
        )
        self.card_bank.grid(row=0, column=1, padx=4, sticky="nsew")

        self.card_recv, self.lbl_recv_amt, self.lbl_recv_sub = self._create_stat_card(
            r1, "📥", "Receivables", "₹ 0.00", "Money to Receive", "#F59E0B", "#78350F"
        )
        self.card_recv.grid(row=0, column=2, padx=4, sticky="nsew")

        self.card_pay, self.lbl_pay_amt, self.lbl_pay_sub = self._create_stat_card(
            r1, "📤", "Payables", "₹ 0.00", "Money to Pay", "#EF4444", "#7F1D1D"
        )
        self.card_pay.grid(row=0, column=3, padx=(4, 0), sticky="nsew")

        # Row 2
        r2 = ctk.CTkFrame(self.cards_container, fg_color="transparent")
        r2.pack(fill="x")
        for col in range(4):
            r2.grid_columnconfigure(col, weight=1, uniform="stat_cards")

        self.card_today_r, self.lbl_today_r_amt, self.lbl_today_r_sub = self._create_stat_card(
            r2, "⬇️", "Today's Receipts", "₹ 0.00", "0 Vouchers", "#10B981", "#064E3B"
        )
        self.card_today_r.grid(row=0, column=0, padx=(0, 4), sticky="nsew")

        self.card_today_p, self.lbl_today_p_amt, self.lbl_today_p_sub = self._create_stat_card(
            r2, "⬆️", "Today's Payments", "₹ 0.00", "0 Vouchers", "#EF4444", "#7F1D1D"
        )
        self.card_today_p.grid(row=0, column=1, padx=4, sticky="nsew")

        self.card_month_r, self.lbl_month_r_amt, self.lbl_month_r_sub = self._create_stat_card(
            r2, "📅", "This Month's Receipts", "₹ 0.00", "0 Vouchers", "#10B981", "#064E3B"
        )
        self.card_month_r.grid(row=0, column=2, padx=4, sticky="nsew")

        self.card_month_p, self.lbl_month_p_amt, self.lbl_month_p_sub = self._create_stat_card(
            r2, "📆", "This Month's Payments", "₹ 0.00", "0 Vouchers", "#EF4444", "#7F1D1D"
        )
        self.card_month_p.grid(row=0, column=3, padx=(4, 0), sticky="nsew")

        # Bind deep clicks to all cards
        self._bind_deep_click(self.card_cash, lambda: self._show_generic_modal("Cash Balance", "Cash"))
        self._bind_deep_click(self.card_bank, lambda: self._show_generic_modal("Bank Balance", "Bank"))
        self._bind_deep_click(self.card_recv, lambda: self._show_generic_modal("Receivables", "Sundry Debtors"))
        self._bind_deep_click(self.card_pay, lambda: self._show_generic_modal("Payables", "Sundry Creditors"))
        self._bind_deep_click(self.card_today_r, lambda: self._show_vouchers_modal("Today's Receipts", "receipt", is_today=True))
        self._bind_deep_click(self.card_today_p, lambda: self._show_vouchers_modal("Today's Payments", "payment", is_today=True))
        self._bind_deep_click(self.card_month_r, lambda: self._show_vouchers_modal("This Month's Receipts", "receipt", is_today=False))
        self._bind_deep_click(self.card_month_p, lambda: self._show_vouchers_modal("This Month's Payments", "payment", is_today=False))

    def _build_lower_section(self):
        lower = ctk.CTkFrame(self, fg_color="transparent")
        lower.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        lower.grid_columnconfigure(0, weight=6)
        lower.grid_columnconfigure(1, weight=4)

        # Left: Expenses Overview
        self.expense_box = ctk.CTkFrame(lower, fg_color="#10192E", border_color="#1B2848", border_width=1, corner_radius=10)
        self.expense_box.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        exp_header = ctk.CTkFrame(self.expense_box, fg_color="transparent", height=32)
        exp_header.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(exp_header, text="Expenses Overview", font=ctk.CTkFont(size=13, weight="bold"), text_color="#FFFFFF").pack(side="left")

        # Period dropdown filter
        period_menu = ctk.CTkOptionMenu(
            exp_header,
            values=["Today", "This Week", "This Month", "This Year"],
            variable=self.period_var,
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#16223E",
            button_color="#3B82F6",
            text_color="#FFFFFF",
            corner_radius=6,
        )
        period_menu.pack(side="right", padx=(8, 0))

        # Manage button
        manage_btn = ctk.CTkButton(
            exp_header,
            text="⚙ Manage",
            width=90,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#16223E",
            hover_color="#3B82F6",
            text_color="#FFFFFF",
            corner_radius=6,
            command=self._open_manage_expenses_dialog,
        )
        manage_btn.pack(side="right", padx=(8, 0))

        # Expense Mini Cards
        exp_cards = ctk.CTkFrame(self.expense_box, fg_color="transparent")
        exp_cards.pack(fill="x", padx=12, pady=(0, 10))
        for i in range(3):
            exp_cards.grid_columnconfigure(i, weight=1)

        self.exp_total_card = self._create_mini_box(exp_cards, "Total Expenses", "₹ 0.00", "#A855F7", "#581C87", 0)
        self.exp_today_card = self._create_mini_box(exp_cards, "Today's Expenses", "₹ 0.00", "#38BDF8", "#0369A1", 1)
        self.exp_month_card = self._create_mini_box(exp_cards, "This Month's Expenses", "₹ 0.00", "#F59E0B", "#78350F", 2)

        self._bind_deep_click(self.exp_total_card, lambda: self._show_vouchers_modal("Expenses Overview", "payment", is_today=False))
        self._bind_deep_click(self.exp_today_card, lambda: self._show_vouchers_modal("Today's Expenses", "payment", is_today=True))
        self._bind_deep_click(self.exp_month_card, lambda: self._show_vouchers_modal("This Month's Expenses", "payment", is_today=False))

        # Placeholder message
        self.exp_msg_lbl = ctk.CTkLabel(
            self.expense_box,
            text="No expense ledgers tracked. Click Manage.",
            font=ctk.CTkFont(size=11),
            text_color="#64748B"
        )
        self.exp_msg_lbl.pack(expand=True)

        # Footer Total Expenses row
        self.exp_footer = ctk.CTkFrame(self.expense_box, fg_color="transparent")
        self.exp_footer.pack(fill="x", padx=12, pady=(0, 10))
        self.exp_total_lbl = ctk.CTkLabel(
            self.exp_footer,
            text="Total Expenses: ₹ 0.00",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#A855F7"
        )
        self.exp_total_lbl.pack(side="left")

        # Right: Donut / Circular Chart Placeholder
        self.status_box = ctk.CTkFrame(lower, fg_color="#10192E", border_color="#1B2848", border_width=1, corner_radius=10)
        self.status_box.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        ctk.CTkLabel(
            self.status_box,
            text="Expenses Donut",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FFFFFF"
        ).pack(anchor="w", padx=12, pady=(10, 6))

    # Canvas donut placeholder
        self.donut_canvas = tk.Canvas(self.status_box, width=180, height=180, bg="#0B1329", highlightthickness=0)
        self.donut_canvas.pack(expand=True, pady=(0, 12))
        # draw placeholder directly
        c = self.donut_canvas
        c.delete("all")
        w = int(c["width"])
        h = int(c["height"])
        cx, cy = w // 2, h // 2
        r_outer = min(w, h) // 2 - 10
        r_inner = r_outer // 2
        c.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer, outline="#1B2848", width=2)
        c.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner, outline="#1B2848", width=1)
        c.create_text(cx, cy, text="No Expenses\nRecorded", fill="#64748B", font=("Segoe UI", 10), justify="center")

    def _create_mini_box(self, parent, title, amt, text_color, border_col, col_idx):
        card = ctk.CTkFrame(parent, fg_color="#0B1329", border_color=border_col, border_width=1, corner_radius=8, height=60)
        card.grid(row=0, column=col_idx, padx=3, sticky="nsew")
        card.pack_propagate(False)

        amt_lbl = ctk.CTkLabel(card, text=amt, font=ctk.CTkFont(size=13, weight="bold"), text_color=text_color)
        amt_lbl.pack(pady=(8, 0))
        t_lbl = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=9), text_color="#64748B")
        t_lbl.pack()

        self._add_hover_effect(card, normal_bg="#0B1329", hover_bg="#16223E")
        card.amt_lbl = amt_lbl
        return card

    def _build_quick_actions_bar(self):
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent", height=34)
        bottom_bar.pack(fill="x", padx=16, pady=(0, 6))

        actions = [
            ("Masters", self._open_masters),
            ("Enter Voucher", self._open_vouchers),
            ("Open Reports", self._open_reports),
            ("Cash Book", lambda: self._open_report_direct("cash_book")),
            ("Bank Book", lambda: self._open_report_direct("bank_book")),
            ("Day Book", lambda: self._open_report_direct("day_book")),
        ]

        for text, cmd in actions:
            btn = ctk.CTkButton(
                bottom_bar,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#16223E",
                border_color="#1B2848",
                border_width=1,
                text_color="#94A3B8",
                hover_color="#1E3A8A",
                height=30,
                corner_radius=6,
                command=cmd
            )
            btn.pack(side="left", padx=(0, 6), expand=True, fill="x")

    # =========================================================================
    # 3. DATA REFRESH & ACCOUNTING CALCULATIONS
    # =========================================================================
    def refresh_dashboard(self):
        # 1. Update Active Company State & Title
        if hasattr(self.controller, "current_company_id") and self.controller.current_company_id:
            self.company_id = self.controller.current_company_id

        company_name = "Vijay"
        if hasattr(self.controller, "company_map") and self.controller.company_map:
            for name, cid in self.controller.company_map.items():
                if cid == self.company_id:
                    company_name = name
                    break
        elif hasattr(self.controller, "get_active_company_name"):
            company_name = self.controller.get_active_company_name() or "Vijay"

        self.company_badge.configure(text=company_name)

        today_str = datetime.now().strftime("%Y-%m-%d")
        month_prefix = datetime.now().strftime("%Y-%m")

        # 2. Fetch Balances
        cash_bal = self._get_group_balance(["Cash", "Cash-in-hand"])
        bank_bal = self._get_group_balance(["Bank Accounts", "Bank"])
        recv_bal = self._get_group_balance(["Sundry Debtors", "Receivables"])
        pay_bal = self._get_group_balance(["Sundry Creditors", "Payables"])

        self.lbl_cash_amt.configure(text=f"₹ {cash_bal:,.2f}")
        self.lbl_bank_amt.configure(text=f"₹ {bank_bal:,.2f}")
        self.lbl_recv_amt.configure(text=f"₹ {recv_bal:,.2f}")
        self.lbl_pay_amt.configure(text=f"₹ {pay_bal:,.2f}")

        # 3. Fetch Receipts & Payments (EXCLUDING CONTRA)
        today_r_amt, today_r_cnt = self._get_voucher_stats("Receipt", today_str)
        today_p_amt, today_p_cnt = self._get_voucher_stats("Payment", today_str)
        month_r_amt, month_r_cnt = self._get_voucher_stats("Receipt", month_prefix, is_month=True)
        month_p_amt, month_p_cnt = self._get_voucher_stats("Payment", month_prefix, is_month=True)

        self.lbl_today_r_amt.configure(text=f"₹ {today_r_amt:,.2f}")
        self.lbl_today_r_sub.configure(text=f"{today_r_cnt} Vouchers")

        self.lbl_today_p_amt.configure(text=f"₹ {today_p_amt:,.2f}")
        self.lbl_today_p_sub.configure(text=f"{today_p_cnt} Vouchers")

        self.lbl_month_r_amt.configure(text=f"₹ {month_r_amt:,.2f}")
        self.lbl_month_r_sub.configure(text=f"{month_r_cnt} Vouchers")

        self.lbl_month_p_amt.configure(text=f"₹ {month_p_amt:,.2f}")
        self.lbl_month_p_sub.configure(text=f"{month_p_cnt} Vouchers")

        # 4. Expenses Overview
        self.exp_total_card.amt_lbl.configure(text=f"₹ {month_p_amt:,.2f}")
        self.exp_today_card.amt_lbl.configure(text=f"₹ {today_p_amt:,.2f}")
        self.exp_month_card.amt_lbl.configure(text=f"₹ {month_p_amt:,.2f}")
        # Footer total expenses label
        self.exp_total_lbl.configure(text=f"Total Expenses: ₹ {month_p_amt:,.2f}")

    def _get_group_balance(self, group_names):
        try:
            placeholders = ",".join(["?"] * len(group_names))
            query = f"""
                SELECT SUM(a.opening_balance) as total
                FROM accounts a
                WHERE a.company_id = ? AND a.group_name IN ({placeholders})
            """
            row = db.fetch_one(query, [self.company_id] + group_names)
            return float(row['total'] or 0.0) if row and row['total'] else 0.0
        except Exception:
            return 0.0

    def _get_voucher_stats(self, vtype, date_pattern, is_month=False):
        """Strictly calculates voucher total amount & count, excluding Contra."""
        try:
            if is_month:
                query = """
                    SELECT COUNT(id) as cnt, SUM(total_amount) as total
                    FROM vouchers
                    WHERE company_id = ? 
                      AND LOWER(voucher_type) = LOWER(?)
                      AND voucher_date LIKE ?
                      AND voucher_no NOT LIKE 'CV-%'
                """
                params = [self.company_id, vtype, f"{date_pattern}%"]
            else:
                query = """
                    SELECT COUNT(id) as cnt, SUM(total_amount) as total
                    FROM vouchers
                    WHERE company_id = ? 
                      AND LOWER(voucher_type) = LOWER(?)
                      AND voucher_date = ?
                      AND voucher_no NOT LIKE 'CV-%'
                """
                params = [self.company_id, vtype, date_pattern]

            row = db.fetch_one(query, params)
            cnt = int(row['cnt'] or 0) if row and row['cnt'] else 0
            total = float(row['total'] or 0.0) if row and row['total'] else 0.0
            return total, cnt
        except Exception:
            return 0.0, 0

    # =========================================================================
    # 4. INSTANT MODAL DIALOGS
    # =========================================================================
    def _show_vouchers_modal(self, title, vtype, is_today=True):
        win = ctk.CTkToplevel(self)
        win.title(f"{title} — Expenzo")
        win.geometry("640x420")
        win.configure(fg_color="#0B1329")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        ctk.CTkLabel(win, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color="#FFFFFF").pack(anchor="w", padx=16, pady=(12, 4))
        date_info = datetime.now().strftime("%d-%m-%Y") if is_today else datetime.now().strftime("%B %Y")
        ctk.CTkLabel(win, text=f"As on {date_info} — Strictly Non-Contra Entries", font=ctk.CTkFont(size=10), text_color="#64748B").pack(anchor="w", padx=16, pady=(0, 8))

        # Treeview
        tree_frame = ctk.CTkFrame(win, fg_color="#10192E", border_color="#1B2848", border_width=1)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        cols = ("date", "party", "voucher_no", "amount")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=10)
        tree.heading("date", text="Date")
        tree.heading("party", text="Party / Account")
        tree.heading("voucher_no", text="Voucher No.")
        tree.heading("amount", text="Amount (₹)")

        tree.column("date", width=90, anchor="w")
        tree.column("party", width=220, anchor="w")
        tree.column("voucher_no", width=100, anchor="center")
        tree.column("amount", width=110, anchor="e")
        tree.pack(fill="both", expand=True, padx=2, pady=2)

        # Query Data
        date_pattern = datetime.now().strftime("%Y-%m-%d") if is_today else datetime.now().strftime("%Y-%m")
        query = """
            SELECT voucher_date, party_name, voucher_no, total_amount
            FROM vouchers
            WHERE company_id = ? 
              AND LOWER(voucher_type) = LOWER(?)
              AND voucher_date LIKE ?
              AND voucher_no NOT LIKE 'CV-%'
            ORDER BY voucher_date DESC
        """
        rows = db.fetch_all(query, [self.company_id, vtype, f"{date_pattern}%"])
        total_sum = 0.0
        for r in rows:
            amt = float(r.get('total_amount', 0.0) or 0.0)
            total_sum += amt
            tree.insert("", "end", values=(r.get('voucher_date'), r.get('party_name', '—'), r.get('voucher_no'), f"{amt:,.2f}"))

        # Footer inside modal
        bot = ctk.CTkFrame(win, fg_color="transparent")
        bot.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(bot, text=f"Total: ₹ {total_sum:,.2f}", font=ctk.CTkFont(size=13, weight="bold"), text_color="#10B981").pack(side="left")
        ctk.CTkButton(bot, text="Close", width=80, height=28, fg_color="#3B82F6", command=win.destroy).pack(side="right")

    def _show_generic_modal(self, title, group_filter):
        win = ctk.CTkToplevel(self)
        win.title(f"{title} Accounts — Expenzo")
        win.geometry("540x360")
        win.configure(fg_color="#0B1329")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        ctk.CTkLabel(win, text=f"{title} Breakdown", font=ctk.CTkFont(size=15, weight="bold"), text_color="#FFFFFF").pack(anchor="w", padx=16, pady=(12, 6))

        tree_frame = ctk.CTkFrame(win, fg_color="#10192E", border_color="#1B2848", border_width=1)
        tree_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        tree = ttk.Treeview(tree_frame, columns=("name", "balance"), show="headings")
        tree.heading("name", text="Account Name")
        tree.heading("balance", text="Balance (₹)")
        tree.column("name", width=300, anchor="w")
        tree.column("balance", width=140, anchor="e")
        tree.pack(fill="both", expand=True, padx=2, pady=2)

        rows = db.fetch_all("SELECT name, opening_balance FROM accounts WHERE company_id = ? AND group_name LIKE ?", [self.company_id, f"%{group_filter}%"])
        total_bal = 0.0
        for r in rows:
            bal = float(r.get('opening_balance', 0.0) or 0.0)
            total_bal += bal
            tree.insert("", "end", values=(r.get('name'), f"{bal:,.2f}"))

        bot = ctk.CTkFrame(win, fg_color="transparent")
        bot.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(bot, text=f"Net Total: ₹ {total_bal:,.2f}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#60A5FA").pack(side="left")
        ctk.CTkButton(bot, text="Close", width=75, height=26, fg_color="#3B82F6", command=win.destroy).pack(side="right")

    # =========================================================================
    # 5. NAVIGATION HELPERS
    # =========================================================================
    def _open_masters(self):
        if hasattr(self.controller, "show_masters"):
            self.controller.show_masters()

    def _open_vouchers(self):
        if hasattr(self.controller, "show_voucher_entry"):
            self.controller.show_voucher_entry()

    def _open_reports(self):
        if hasattr(self.controller, "show_reports"):
            self.controller.show_reports()

    def _open_report_direct(self, rep_name):
        if hasattr(self.controller, "open_report"):
            self.controller.open_report(rep_name)

    def _open_manage_expenses_dialog(self):
        """Open a simple manage expenses dialog (placeholder)."""
        win = ctk.CTkToplevel(self)
        win.title("Manage Expense Ledgers — Expenzo")
        win.geometry("400x300")
        win.configure(fg_color="#0B1329")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        ctk.CTkLabel(win, text="Manage Expense Ledgers", font=ctk.CTkFont(size=16, weight="bold"), text_color="#FFFFFF").pack(padx=16, pady=16)
        ctk.CTkLabel(win, text="Feature coming soon.", font=ctk.CTkFont(size=12), text_color="#64748B").pack(padx=16, pady=8)
        ctk.CTkButton(win, text="Close", width=80, height=28, fg_color="#3B82F6", command=win.destroy).pack(pady=16)


    # Alias to maintain backward compatibility with any other callers
DashboardView = DashboardFrame