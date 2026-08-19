"""
Tests for the Tally-style Balance Sheet report screen (``ui/balance_sheet_report.py``).

Exercises the real BalanceSheetReportUI against an in-memory database:
two-column layout, group headings + subtotals + totals, keyboard row
navigation, account drill-down into the ledger dialog, group drill-down,
period carry-forward, and voucher opening from a ledger row.
"""
import unittest
from datetime import date
from unittest import mock

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.account_service import account_service  # noqa: E402
from services.group_service import group_service  # noqa: E402
from services.voucher_service import voucher_service  # noqa: E402
from ui.balance_sheet_report import (  # noqa: E402
    BalanceSheetReportUI,
)
from utils import theme  # noqa: E402


class BalanceSheetReportUITest(unittest.TestCase):
    """Balance Sheet report screen tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("INSERT INTO companies (id, name) VALUES (?, ?)", (1, "UI BS Co"))
        group_service.seed_default_groups(1)
        cls.root = ctk.CTk()
        cls.root.withdraw()
        theme.apply_theme(cls.root, mode="dark")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        self.acct = self._seed_accounts(1)
        self._seed_voucher()
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = BalanceSheetReportUI(self.root, company_id=1)
        self.ui.as_on_date_var.set("31-08-2026")
        self.ui._generate_report()
        self._sync()

    def tearDown(self):
        if getattr(self.ui, "_drill", None) is not None:
            try:
                self.ui._drill.destroy()
            except Exception:
                pass
            self.ui._drill = None
        try:
            self.ui.main_frame.destroy()
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _sync(self):
        self.root.update_idletasks()
        self.root.update()

    @staticmethod
    def _seed_accounts(company_id):
        cash = account_service.create_account(company_id, "Cash", "CASH",
                                              "Cash-in-Hand", 10000.0, "Debit")
        bank = account_service.create_account(company_id, "Bank", "BANK",
                                              "Bank Accounts", 20000.0, "Debit")
        creditor = account_service.create_account(
            company_id, "ABC Traders", "ABC", "Sundry Creditors", 0.0, "Credit")
        debtor = account_service.create_account(
            company_id, "MNO Buyers", "MNO", "Sundry Debtors", 0.0, "Debit")
        capital = account_service.create_account(
            company_id, "Capital", "CAP", "Capital", 30000.0, "Credit")
        rent = account_service.create_account(
            company_id, "Rent", "RENT", "Indirect Expense", 0.0, "Debit")
        sales = account_service.create_account(
            company_id, "Sales", "SALES", "Sales Accounts", 0.0, "Credit")
        return {"cash": cash, "bank": bank, "creditor": creditor,
                "debtor": debtor, "capital": capital, "rent": rent,
                "sales": sales}

    def _seed_voucher(self):
        """Rent Dr 1000 -> Bank Cr 1000 (Payment), Debtor +5000 / Sales -5000."""
        ok, _, pay_id = voucher_service.save_voucher(
            1, "Payment", date(2026, 8, 2),
            [
                {"account_id": self.acct["rent"],
                 "debit_amount": 1000.0, "credit_amount": 0.0},
                {"account_id": self.acct["bank"],
                 "debit_amount": 0.0, "credit_amount": 1000.0},
            ],
            narration="Rent paid by bank",
        )
        self.assertTrue(ok)
        ok, _, vid = voucher_service.save_voucher(
            1, "Journal", date(2026, 8, 1),
            [
                {"account_id": self.acct["debtor"],
                 "debit_amount": 5000.0, "credit_amount": 0.0},
                {"account_id": self.acct["sales"],
                 "debit_amount": 0.0, "credit_amount": 5000.0},
            ],
            narration="Credit sales",
        )
        self.assertTrue(ok)
        self.payment_voucher_id = pay_id
        return vid

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def test_two_equal_side_panels(self):
        self.assertIsNotNone(self.ui.left_panel)
        self.assertIsNotNone(self.ui.right_panel)
        self.assertEqual(self.ui.left_panel.grid_info()["column"], 0)
        self.assertEqual(self.ui.right_panel.grid_info()["column"], 1)

    def test_group_headings_subtotals_totals(self):
        left_rows = self.ui.left_panel.rows
        kinds = [r["kind"] for r in left_rows]
        self.assertIn("heading", kinds)      # "Liabilities" / "Capital & Equity"
        self.assertIn("subtotal", kinds)
        self.assertEqual(kinds[-1], "total")  # "Total Liabilities & Capital"
        right_rows = self.ui.right_panel.rows
        self.assertEqual(right_rows[-1]["kind"], "total")  # "Total Assets"
        self.assertIn("Total Liabilities & Capital",
                      left_rows[-1]["name"])
        self.assertIn("Total Assets", right_rows[-1]["name"])

    def test_balanced_summary(self):
        text = self.ui.status.status_var.get()
        self.assertIn("Balance Sheet as of", text)
        self.assertIn("Assets", text)
        self.assertIn("Liab+Capital", text)
        self.assertIn("Balanced", text)

    def test_summary_strip_shows_values_and_status(self):
        sv = self.ui._summary_values
        self.assertEqual(sv["date"].cget("text"), "31-08-2026")
        self.assertEqual(sv["liab_capital"].cget("text"), "₹ 34,000.00")
        self.assertEqual(sv["assets"].cget("text"), "₹ 34,000.00")
        self.assertEqual(sv["difference"].cget("text"), "₹ 0.00")
        self.assertIn("BALANCED", self.ui.status_chip.cget("text"))

    def test_assets_equal_liabilities_capital(self):
        left_total = float(self.ui.left_panel.rows[-1]["amount_text"].replace(",", ""))
        right_total = float(self.ui.right_panel.rows[-1]["amount_text"].replace(",", ""))
        self.assertEqual(left_total, right_total)

    # ------------------------------------------------------------------ #
    # compact layout / scrollbar
    # ------------------------------------------------------------------ #
    def test_scrollbar_hidden_when_rows_fit(self):
        """Both side scrollbars stay hidden while all rows fit the window."""
        for panel in (self.ui.left_panel, self.ui.right_panel):
            self._sync()
            self.assertFalse(panel._scrollbar_shown,
                             f"{panel.title} scrollbar should be hidden")

    def test_total_bars_exist_both_sides(self):
        self.assertIn("Total Liabilities & Capital",
                      self.ui.left_panel.total_label.cget("text"))
        self.assertIn("Total Assets",
                      self.ui.right_panel.total_label.cget("text"))

    # ------------------------------------------------------------------ #
    # keyboard navigation
    # ------------------------------------------------------------------ #
    def test_arrow_keys_move_selection(self):
        left = self.ui.left_panel
        left.tree.focus_set()
        left.select_index(0)
        self.ui._move_selection(left, 1)
        selected = left.selected_row()
        self.assertIsNotNone(selected)
        self.assertEqual(left.tree.index(left.tree.selection()[0]), 1)

    def test_left_right_switch_side(self):
        self.ui._switch_side("right")
        self.assertEqual(self.ui._focused_side, "right")
        self.assertEqual(self.ui.right_panel.tree.index(
            self.ui.right_panel.tree.selection()[0]), 0)

    # ------------------------------------------------------------------ #
    # drill-down: account -> ledger
    # ------------------------------------------------------------------ #
    def test_enter_on_account_opens_ledger_dialog(self):
        # MNO Buyers (Sundry Debtors) is an Asset -> RIGHT panel.
        right = self.ui.right_panel
        row = next(r for r in right.rows if r["kind"] == "account"
                   and r["entry"]["account_id"] == self.acct["debtor"])
        right.select_index(right.rows.index(row))
        self.ui._open_selected(right)
        self._sync()
        self.assertIsNotNone(self.ui._drill)
        dialog = self.ui._drill
        # Ledger dialog carries the statement rows with opening/closing.
        kinds = {r["kind"] for r in dialog.rows}
        self.assertIn("ledger_row", kinds)
        self.assertIn("opening", kinds)
        self.assertIn("closing", kinds)
        # Debtor ledger: opening 0, one journal (5000 debit), closing 5000.
        opening = next(r for r in dialog.rows if r["kind"] == "opening")
        self.assertEqual(opening["amount"], 0.0)
        closing = next(r for r in dialog.rows if r["kind"] == "closing")
        self.assertEqual(closing["amount"], 5000.0)

    def test_ledger_rows_carry_period_from_balance_sheet(self):
        right = self.ui.right_panel
        row = next(r for r in right.rows if r["kind"] == "account"
                   and r["entry"]["account_id"] == self.acct["bank"])
        right.select_index(right.rows.index(row))
        self.ui._open_selected(right)
        self._sync()
        dialog = self.ui._drill
        ledger_rows = [r for r in dialog.rows if r["kind"] == "ledger_row"]
        self.assertTrue(ledger_rows)
        # The seeded Payment (Rent Dr / Bank Cr) appears in the Bank ledger.
        self.assertEqual(ledger_rows[0]["voucher_number"], "PV-0001")
        # Closing = opening 20000 - 1000 = 19000 debit.
        closing = next(r for r in dialog.rows if r["kind"] == "closing")
        self.assertEqual(closing["amount"], 19000.0)

    def test_voucher_open_from_ledger_row(self):
        right = self.ui.right_panel
        row = next(r for r in right.rows if r["kind"] == "account"
                   and r["entry"]["account_id"] == self.acct["bank"])
        right.select_index(right.rows.index(row))
        self.ui._open_selected(right)
        self._sync()
        dialog = self.ui._drill
        ledger_row = next(r for r in dialog.rows if r["kind"] == "ledger_row")
        dialog.tree.selection_set(
            dialog.tree.get_children()[dialog.rows.index(ledger_row)])
        with mock.patch.object(self.ui, "_route_to_vouchers") as route:
            dialog._open_selected()
        route.assert_called_once()
        voucher = route.call_args[0][0]
        self.assertEqual(voucher["id"], self.payment_voucher_id)

    # ------------------------------------------------------------------ #
    # drill-down: group heading -> ledger list
    # ------------------------------------------------------------------ #
    def test_group_heading_opens_ledger_list(self):
        left = self.ui.left_panel
        row = next(r for r in left.rows if r["kind"] == "heading")
        left.select_index(left.rows.index(row))
        self.ui._open_selected(left)
        self._sync()
        self.assertIsNotNone(self.ui._drill)
        dialog = self.ui._drill
        kinds = {r["kind"] for r in dialog.rows}
        self.assertIn("account", kinds)
        self.assertIn("total", kinds)
        self.assertEqual(dialog.account_id, None)

    def test_group_ledger_list_drills_into_ledger(self):
        left = self.ui.left_panel
        row = next(r for r in left.rows if r["kind"] == "heading")
        left.select_index(left.rows.index(row))
        self.ui._open_selected(left)
        self._sync()
        dialog = self.ui._drill
        account_row = next(r for r in dialog.rows if r["kind"] == "account")
        dialog.tree.selection_set(dialog.tree.get_children()[dialog.rows.index(account_row)])
        with mock.patch.object(self.ui, "_open_account_ledger") as opener:
            dialog._open_selected()
        opener.assert_called_once()
        self.assertEqual(opener.call_args[0][0]["account_id"],
                         account_row["entry"]["account_id"])

    # ------------------------------------------------------------------ #
    # return state / esc
    # ------------------------------------------------------------------ #
    def test_esc_closes_drill_then_back(self):
        right = self.ui.right_panel
        row = next(r for r in right.rows if r["kind"] == "account")
        right.select_index(right.rows.index(row))
        self.ui._open_selected(right)
        self._sync()
        self.assertIsNotNone(self.ui._drill)
        # First Esc closes the drill-down only.
        self.ui._back()
        self.assertIsNone(self.ui._drill)
        # Second Esc triggers the report's own back handler (assigned by the
        # reports hub in the real app; set manually here).
        self.ui.on_keyboard_back = lambda: None
        with mock.patch.object(self.ui, "on_keyboard_back") as back:
            self.ui._back()
        back.assert_called_once()

    def test_report_regeneration_keeps_selection(self):
        left = self.ui.left_panel
        left.select_index(1)
        self.ui._saved_selection[0] = 1
        self.ui._generate_report()
        self._sync()
        self.assertEqual(left.tree.index(left.tree.selection()[0]), 1)


if __name__ == "__main__":
    unittest.main()
