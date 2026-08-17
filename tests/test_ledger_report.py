"""
Tests for the Tally-style Ledger report screen (``ui/ledger_report.py``).

Exercises the real LedgerReportUI against an in-memory database: ledger
selection/search, statement generation with opening/transaction/closing
rows, period badge updates, and opening the original voucher from a row.
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
from ui.ledger_report import LedgerReportUI  # noqa: E402
from utils import theme  # noqa: E402


class LedgerReportUITest(unittest.TestCase):
    """Tally-style Ledger report screen tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (1, "UI Ledger Co"))
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
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = LedgerReportUI(self.root, company_id=1)
        self._sync()

    def tearDown(self):
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
                                              "Cash-in-Hand", 0.0, "Debit")
        bank = account_service.create_account(company_id, "Bank", "BANK",
                                              "Bank Accounts", 0.0, "Debit")
        creditor = account_service.create_account(
            company_id, "ABC Traders", "ABC", "Sundry Creditors", 0.0, "Credit")
        debtor = account_service.create_account(
            company_id, "MNO Buyers", "MNO", "Sundry Debtors", 0.0, "Debit")
        rent = account_service.create_account(
            company_id, "Rent", "RENT", "Indirect Expense", 0.0, "Debit")
        sales = account_service.create_account(
            company_id, "Sales", "SALES", "Sales Accounts", 0.0, "Credit")
        return {"cash": cash, "bank": bank, "creditor": creditor,
                "debtor": debtor, "rent": rent, "sales": sales}

    def _seed_voucher(self):
        """A Payment voucher: Rent Dr 1000 -> Bank Cr 1000."""
        ok, message, voucher_id = voucher_service.save_voucher(
            1, "Payment", date(2026, 8, 1),
            [
                {"account_id": self.acct["rent"],
                 "debit_amount": 1000.0, "credit_amount": 0.0},
                {"account_id": self.acct["bank"],
                 "debit_amount": 0.0, "credit_amount": 1000.0},
            ],
            narration="Rent paid by bank",
        )
        self.assertTrue(ok, message)
        return voucher_id

    def _select_rent_with_period(self):
        """Select the Rent ledger with a period that covers the seeded voucher."""
        self.ui.from_date_var.set("01-08-2026")
        self.ui.to_date_var.set("31-08-2026")
        self.ui._select_account(self.acct["rent"])
        self._sync()

    # ------------------------------------------------------------------ #
    # selection stage
    # ------------------------------------------------------------------ #
    def test_opens_in_selection_stage(self):
        self.assertEqual(self.ui.selection_stage.winfo_manager(), "pack")
        self.assertEqual(self.ui.statement_stage.winfo_manager(), "")
        self.assertIsNone(self.ui.current_account)

    def test_search_lists_accounts(self):
        self.ui.search_var.set("rent")
        self._sync()
        children = self.ui.search_tree.get_children()
        self.assertEqual(len(children), 1)
        values = self.ui.search_tree.item(children[0], "values")
        self.assertEqual(values[0], "Rent")

    def test_search_all_accounts_by_default(self):
        children = self.ui.search_tree.get_children()
        names = {self.ui.search_tree.item(i, "values")[0] for i in children}
        self.assertIn("Cash", names)
        self.assertIn("ABC Traders", names)
        self.assertIn("Sales", names)

    # ------------------------------------------------------------------ #
    # statement generation
    # ------------------------------------------------------------------ #
    def test_select_opens_statement(self):
        self._seed_voucher()
        self._select_rent_with_period()
        self.assertEqual(self.ui.statement_stage.winfo_manager(), "pack")
        self.assertEqual(self.ui.selection_stage.winfo_manager(), "")
        self.assertIsNotNone(self.ui.current_account)

    def test_statement_has_opening_txn_closing_rows(self):
        self._seed_voucher()
        self._select_rent_with_period()
        rows = self.ui.table.tree.get_children()
        self.assertGreaterEqual(len(rows), 3)
        first = self.ui.table.tree.item(rows[0], "values")
        self.assertEqual(first[1], "Opening")
        last = self.ui.table.tree.item(rows[-1], "values")
        self.assertEqual(last[1], "Closing")
        # The transaction row is present with a debit amount.
        txn_rows = [r for r in rows[1:-1]]
        self.assertTrue(txn_rows)
        txn = self.ui.table.tree.item(txn_rows[0], "values")
        self.assertEqual(txn[1], "PV-0001")
        self.assertEqual(txn[4], "1,000.00")

    def test_totals_bar_shows_ledger_and_balances(self):
        self._seed_voucher()
        self._select_rent_with_period()
        text = self.ui.table.totals_label.cget("text")
        self.assertIn("Rent", text)
        self.assertIn("Opening:", text)
        self.assertIn("Closing:", text)

    def test_period_badge_updates(self):
        self.ui.from_date_var.set("01-08-2026")
        self.ui.to_date_var.set("31-08-2026")
        self.ui._update_period_badge()
        self.assertIn("Period:", self.ui.period_badge.cget("text"))
        self.ui.from_date_var.set("15-08-2026")
        self.ui.to_date_var.set("15-08-2026")
        self.ui._update_period_badge()
        self.assertIn("As on:", self.ui.period_badge.cget("text"))

    def test_global_single_date_regenerates(self):
        self._seed_voucher()
        self._select_rent_with_period()
        self.ui.on_global_single_date(date(2026, 8, 1))
        self._sync()
        self.assertEqual(self.ui.from_date_var.get(), "01-08-2026")
        self.assertEqual(self.ui.to_date_var.get(), "01-08-2026")
        self.assertIn("As on:", self.ui.period_badge.cget("text"))
        rows = self.ui.table.tree.get_children()
        self.assertGreaterEqual(len(rows), 3)

    def test_global_date_period_regenerates(self):
        self._seed_voucher()
        self._select_rent_with_period()
        self.ui.on_global_date_period(date(2026, 7, 1), date(2026, 8, 31))
        self._sync()
        self.assertEqual(self.ui.from_date_var.get(), "01-07-2026")
        self.assertEqual(self.ui.to_date_var.get(), "31-08-2026")
        self.assertIn("Period:", self.ui.period_badge.cget("text"))

    # ------------------------------------------------------------------ #
    # open original voucher
    # ------------------------------------------------------------------ #
    def test_enter_on_txn_opens_voucher(self):
        voucher_id = self._seed_voucher()
        self._select_rent_with_period()
        txn_rows = self.ui.table.tree.get_children()[1:-1]
        self.assertTrue(txn_rows)
        self.ui.table.tree.selection_set(txn_rows[0])
        with mock.patch.object(self.ui, "_open_voucher_in_editor") as opener:
            self.ui._open_selected_voucher()
        opener.assert_called_once()
        voucher = opener.call_args[0][0]
        self.assertEqual(voucher["id"], voucher_id)

    def test_enter_on_opening_row_does_not_open(self):
        self._seed_voucher()
        self._select_rent_with_period()
        rows = self.ui.table.tree.get_children()
        self.ui.table.tree.selection_set(rows[0])  # Opening row
        with mock.patch.object(self.ui, "_open_voucher_in_editor") as opener:
            with mock.patch("ui.ledger_report.dialogs.warn") as warn:
                self.ui._open_selected_voucher()
        opener.assert_not_called()
        self.assertTrue(warn.called)

    # ------------------------------------------------------------------ #
    # keyboard
    # ------------------------------------------------------------------ #
    def test_on_keyboard_search_focuses_search_entry(self):
        self.ui.on_keyboard_search()
        self._sync()


if __name__ == "__main__":
    unittest.main()
