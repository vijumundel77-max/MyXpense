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
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.dashboard_service import dashboard_service


class DashboardFrame(ctk.CTkFrame):
    """Accounting dashboard for the current company."""

    def __init__(self, parent, company_id: Optional[int] = None):
        super().__init__(parent)
        self.parent = parent
        self.pack(fill="both", expand=True)
        self.company_id = company_id or self._resolve_company_id()
        self.data: Dict[str, Any] = {}

        self._build_header()
        self._build_kpi_row()
        self._build_movement_row()
        self._build_recent_vouchers()
        self._build_quick_actions()
        self._build_status()
        self.refresh()

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
        ctk.CTkButton(
            self.header, text="↻ Refresh", width=96, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS, command=self.refresh,
        ).pack(side="right")

    def _build_kpi_row(self) -> None:
        self.kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        self.kpi_row.pack(fill="x", padx=config.SPACING_XL, pady=(config.SPACING_XL, 0))

        self.kpi_labels: Dict[str, ctk.CTkLabel] = {}
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
            )
            card.grid(row=0, column=index, sticky="nsew", padx=(0, config.SPACING_MD))
            card.grid_propagate(False)

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
            )
            card.grid(row=0, column=index, sticky="nsew", padx=(0, config.SPACING_MD))
            card.grid_propagate(False)
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
            ("Bank Accounts", "show_bank_accounts"),
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
    # data
    # ------------------------------------------------------------------ #
    def _resolve_company_id(self) -> int:
        app = self.winfo_toplevel()
        company_id = getattr(app, "current_company_id", None)
        if company_id is not None:
            return int(company_id)
        row = self._db_fetch("SELECT id FROM companies ORDER BY id LIMIT 1")
        return int(row["id"]) if row else 1

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
        self.data = dashboard_service.get_dashboard(self.company_id)

        self.company_label.configure(text=self.data.get('company_name', ''))
        for key, label in self.kpi_labels.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")
        for key, label in self.movement_labels.items():
            label.configure(text=f"₹ {self.data.get(key, 0.0):,.2f}")

        self._render_recent_vouchers()
        self.status_var.set(
            f"Updated {date.today().strftime(config.DISPLAY_DATE_FORMAT)} — "
            f"{self.data.get('company_name', '')}"
        )

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
