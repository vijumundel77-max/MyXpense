"""
Tests for dashboard drill-downs.

Covers:
- per-bank-account balances (sum == dashboard bank balance)
- receivable / payable party lists (sum == dashboard totals)
- current-month receipts / payments detail (sum == dashboard month totals)
- the drill-down modal's column set and total label
- Esc closes the modal
"""
import unittest
from datetime import date, timedelta

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.account_service import AccountService  # noqa: E402
from services.voucher_service import VoucherService  # noqa: E402
from services.dashboard_service import DashboardService  # noqa: E402
from ui.dashboard import DashboardDetailDialog  # noqa: E402


def setup(company_id: int):
    cash = AccountService.create_account(
        company_id, 'Cash', 'CASH', 'Cash-in-Hand', 10000.0, 'Debit')
    bank1 = AccountService.create_account(
        company_id, 'Bank HDFC', 'HDFC', 'Bank Accounts', 15000.0, 'Debit')
    bank2 = AccountService.create_account(
        company_id, 'Bank ICICI', 'ICICI', 'Bank Accounts', 5000.0, 'Debit')
    debtor = AccountService.create_account(
        company_id, 'Customer A', 'C001', 'Sundry Debtors', 0.0, 'Debit')
    debtor2 = AccountService.create_account(
        company_id, 'Customer B', 'C002', 'Sundry Debtors', 0.0, 'Debit')
    creditor = AccountService.create_account(
        company_id, 'Supplier X', 'S001', 'Sundry Creditors', 0.0, 'Credit')
    sales = AccountService.create_account(
        company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
    expenses = AccountService.create_account(
        company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
    return {'cash': cash, 'bank1': bank1, 'bank2': bank2,
            'debtor': debtor, 'debtor2': debtor2, 'creditor': creditor,
            'sales': sales, 'expenses': expenses}


class TestDashboardDrilldowns(unittest.TestCase):
    """Detail rows behind the clickable dashboard cards."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        db.execute("DELETE FROM companies")
        cls.company_id = 1
        db.execute("INSERT INTO companies (id, name) VALUES (1, 'Dash Co')")
        cls.acct = setup(cls.company_id)
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        # Global date state must not leak across tests (e.g. from
        # test_date_control): the drill-down modal honors the F2 single date.
        from services.date_control_service import date_control
        date_control.reset()
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("UPDATE accounts SET is_active = 1")
        db.execute(
            "UPDATE accounts SET opening_balance = 10000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['cash'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 15000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['bank1'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 5000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['bank2'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 0.0, opening_balance_type = 'Debit' "
            "WHERE id IN (?, ?, ?)",
            (self.acct['debtor'], self.acct['debtor2'], self.acct['expenses']))
        db.execute(
            "UPDATE accounts SET opening_balance = 0.0, opening_balance_type = 'Credit' "
            "WHERE id IN (?, ?)", (self.acct['creditor'], self.acct['sales']))

    # ------------------------------------------------------------------ #
    # bank accounts
    # ------------------------------------------------------------------ #
    def test_bank_accounts_balances(self):
        # Money into HDFC only.
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['bank1'], 'debit_amount': 3000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 3000.0},
            ],
        )
        accounts = DashboardService.bank_accounts(self.company_id)
        by_name = {a['account_name']: a['balance'] for a in accounts}
        self.assertEqual(by_name['Bank HDFC'], 18000.0)
        self.assertEqual(by_name['Bank ICICI'], 5000.0)
        # Sum equals the dashboard's bank balance.
        self.assertEqual(
            round(sum(a['balance'] for a in accounts), 2),
            DashboardService.bank_balance(self.company_id))

    def test_bank_accounts_empty(self):
        # Inactive account must not appear; no active bank accounts -> empty.
        db.execute("UPDATE accounts SET is_active = 0 WHERE id = ?",
                   (self.acct['bank1'],))
        accounts = DashboardService.bank_accounts(self.company_id)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]['account_name'], 'Bank ICICI')

    # ------------------------------------------------------------------ #
    # receivables / payables
    # ------------------------------------------------------------------ #
    def test_receivable_parties(self):
        VoucherService.save_voucher(
            self.company_id, 'Journal', date.today(),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 1500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1500.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Journal', date.today(),
            [
                {'account_id': self.acct['debtor2'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        parties = DashboardService.receivable_parties(self.company_id)
        self.assertEqual(len(parties), 2)
        by_name = {p['party_name']: p['outstanding'] for p in parties}
        self.assertEqual(by_name['Customer A'], 1500.0)
        self.assertEqual(by_name['Customer B'], 500.0)
        self.assertEqual(
            round(sum(p['outstanding'] for p in parties), 2),
            DashboardService.receivables(self.company_id))

    def test_payable_parties(self):
        VoucherService.save_voucher(
            self.company_id, 'Journal', date.today(),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 800.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 800.0},
            ],
        )
        parties = DashboardService.payable_parties(self.company_id)
        self.assertEqual(len(parties), 1)
        self.assertEqual(parties[0]['party_name'], 'Supplier X')
        self.assertEqual(parties[0]['outstanding'], 800.0)
        self.assertEqual(
            round(sum(p['outstanding'] for p in parties), 2),
            DashboardService.payables(self.company_id))

    def test_parties_exclude_zero_balance(self):
        # No vouchers -> no receivable/payable parties.
        self.assertEqual(DashboardService.receivable_parties(self.company_id), [])
        self.assertEqual(DashboardService.payable_parties(self.company_id), [])

    # ------------------------------------------------------------------ #
    # monthly receipts / payments
    # ------------------------------------------------------------------ #
    def _seed_month_movements(self):
        today = date.today()
        first = date(today.year, today.month, 1)
        VoucherService.save_voucher(
            self.company_id, 'Receipt', first,
            [
                {'account_id': self.acct['cash'], 'debit_amount': 700.0, 'credit_amount': 0.0},
                {'account_id': self.acct['debtor'], 'debit_amount': 0.0, 'credit_amount': 700.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Receipt', today,
            [
                {'account_id': self.acct['bank1'], 'debit_amount': 1300.0, 'credit_amount': 0.0},
                {'account_id': self.acct['debtor2'], 'debit_amount': 0.0, 'credit_amount': 1300.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Payment', today,
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 400.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank2'], 'debit_amount': 0.0, 'credit_amount': 400.0},
            ],
        )
        # An out-of-month payment must not appear.
        VoucherService.save_voucher(
            self.company_id, 'Payment', today - timedelta(days=40),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 999.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 999.0},
            ],
        )
        return first

    def test_month_receipts_detail(self):
        self._seed_month_movements()
        receipts = DashboardService.month_receipts(self.company_id)
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(r['kind'] == 'Receipt' for r in receipts))
        self.assertEqual(
            round(sum(r['amount'] for r in receipts), 2),
            DashboardService.month_totals(self.company_id)['receipts'])
        # Each row carries the required display fields.
        for r in receipts:
            for field in ('date', 'party', 'voucher_number', 'amount'):
                self.assertIn(field, r)
        parties = {r['party'] for r in receipts}
        self.assertEqual(parties, {'Customer A', 'Customer B'})

    def test_month_payments_detail(self):
        self._seed_month_movements()
        payments = DashboardService.month_payments(self.company_id)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]['kind'], 'Payment')
        # The counterparty is the other side of the voucher: who was paid.
        self.assertEqual(payments[0]['party'], 'Rent')
        self.assertEqual(
            round(sum(p['amount'] for p in payments), 2),
            DashboardService.month_totals(self.company_id)['payments'])

    def test_month_receipts_amount_column_receipt_only(self):
        """Receipt rows only count the debit side; a payment line inside a
        Receipt voucher must not leak into the receipts detail."""
        self._seed_month_movements()
        for r in DashboardService.month_receipts(self.company_id):
            self.assertGreaterEqual(r['amount'], 0.0)

    def test_month_receipts_exclude_cancelled(self):
        today = date.today()
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, 'Receipt', today,
            [
                {'account_id': self.acct['cash'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        self.assertEqual(len(DashboardService.month_receipts(self.company_id)), 1)
        VoucherService.cancel_voucher(vid, self.company_id)
        self.assertEqual(DashboardService.month_receipts(self.company_id), [])

    # ------------------------------------------------------------------ #
    # modal
    # ------------------------------------------------------------------ #
    def _open_modal(self, key, root=None):
        root = root or self.root
        detail = DashboardDetailDialog(root, self.company_id, key, key)
        detail.update_idletasks()
        return detail

    def test_modal_bank_balance_columns_and_total(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['bank1'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        detail = self._open_modal('bank_balance')
        try:
            headings = [detail.tree.heading(c, 'text') for c in detail.tree['columns']]
            self.assertEqual(headings, ['Bank Account', 'Current Balance'])
            rows = detail.tree.get_children()
            self.assertEqual(len(rows), 2)
            total_text = detail.total_label.cget('text')
            self.assertIn('Total Bank Balance', total_text)
            self.assertIn('21,000.00', total_text)
        finally:
            detail._close()

    def test_modal_month_receipts_columns_and_total(self):
        self._seed_month_movements()
        detail = self._open_modal('month_receipts')
        try:
            headings = [detail.tree.heading(c, 'text') for c in detail.tree['columns']]
            self.assertEqual(headings,
                             ['Date', 'Party / Account', 'Voucher No.', 'Amount'])
            rows = detail.tree.get_children()
            self.assertEqual(len(rows), 2)
            total_text = detail.total_label.cget('text')
            self.assertIn('2,000.00', total_text)
        finally:
            detail._close()

    def test_modal_esc_closes(self):
        self._seed_month_movements()
        detail = self._open_modal('month_payments')
        # Esc is bound to _close on the toplevel.
        self.assertTrue(detail.bind('<Escape>'))
        detail._close()
        self.assertTrue(not detail.winfo_exists())

    # ------------------------------------------------------------------ #
    # as-on date (global F2 single date)
    # ------------------------------------------------------------------ #
    def test_modal_uses_global_single_date(self):
        """Drill-down modal reflects the F2-selected date, not today."""
        from services.date_control_service import date_control
        as_on = date.today() - timedelta(days=10)
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['bank1'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        date_control.set_single_date(as_on)
        try:
            detail = self._open_modal('bank_balance')
            try:
                rows = detail.tree.get_children()
                self.assertEqual(len(rows), 2)  # both banks, opening only
                self.assertEqual(detail.subtitle_label.cget('text'),
                                 f"As on {as_on.strftime(config.DISPLAY_DATE_FORMAT)}")
                by_name = {detail.tree.item(child, 'values')[0]:
                           detail.tree.item(child, 'values')[1] for child in rows}
                self.assertEqual(by_name, {'Bank HDFC': '15,000.00', 'Bank ICICI': '5,000.00'})
            finally:
                detail._close()
        finally:
            date_control.reset()


if __name__ == '__main__':
    unittest.main()
