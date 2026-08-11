"""
Tests for the Phase 4 dashboard service.

Covers cash balance, bank balance, receivables, payables, daily and monthly
receipts/payments, cancelled-voucher exclusion, company isolation, and the
empty-database case.
"""
import unittest
from datetime import date, timedelta

import config

config.DATABASE_PATH = ':memory:'

from database.database import db
from services.account_service import AccountService
from services.voucher_service import VoucherService
from services.dashboard_service import DashboardService, dashboard_service


def setup(company_id: int):
    cash = AccountService.create_account(
        company_id, 'Cash', 'CASH', 'Cash-in-Hand', 10000.0, 'Debit')
    bank = AccountService.create_account(
        company_id, 'Bank', 'BANK', 'Bank Accounts', 20000.0, 'Debit')
    debtor = AccountService.create_account(
        company_id, 'Customer A', 'C001', 'Sundry Debtors', 0.0, 'Debit')
    creditor = AccountService.create_account(
        company_id, 'Supplier X', 'S001', 'Sundry Creditors', 0.0, 'Credit')
    sales = AccountService.create_account(
        company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
    expenses = AccountService.create_account(
        company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
    return {'cash': cash, 'bank': bank, 'debtor': debtor, 'creditor': creditor,
            'sales': sales, 'expenses': expenses}


class TestDashboardService(unittest.TestCase):
    """Dashboard metrics from Expenzo voucher data."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        db.execute("DELETE FROM companies")
        cls.company_id = 1
        db.execute(
            "INSERT INTO companies (id, name) VALUES (1, 'Dash Co')")
        db.execute(
            "INSERT INTO companies (id, name) VALUES (2, 'Other Co')")
        cls.acct = setup(cls.company_id)

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        # Reset opening balances
        db.execute(
            "UPDATE accounts SET opening_balance = 10000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['cash'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 20000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['bank'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 0.0, opening_balance_type = 'Debit' "
            "WHERE id IN (?, ?)", (self.acct['debtor'], self.acct['expenses']))
        db.execute(
            "UPDATE accounts SET opening_balance = 0.0, opening_balance_type = 'Credit' "
            "WHERE id IN (?, ?)", (self.acct['creditor'], self.acct['sales']))

    # ------------------------------------------------------------------ #
    # balances
    # ------------------------------------------------------------------ #
    def test_cash_balance(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
        )
        # Opening 10000 + 2000 = 12000
        self.assertEqual(DashboardService.cash_balance(self.company_id), 12000.0)

    def test_bank_balance(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['bank'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
        )
        # Opening 20000 + 5000 = 25000
        self.assertEqual(DashboardService.bank_balance(self.company_id), 25000.0)

    def test_cash_and_bank_agree_with_books(self):
        """Dashboard balances must agree with the Cash/Bank Book closing."""
        from services.cash_book_service import cash_book_service
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 1500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1500.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Payment', date.today(),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 300.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 300.0},
            ],
        )
        cash_book = cash_book_service.generate_cash_book(
            self.company_id, date(1900, 1, 1), date.today())
        bank_book = cash_book_service.generate_bank_book(
            self.company_id, date(1900, 1, 1), date.today())
        self.assertEqual(DashboardService.cash_balance(self.company_id),
                         cash_book['closing_balance']['amount'])
        self.assertEqual(DashboardService.bank_balance(self.company_id),
                         bank_book['closing_balance']['amount'])

    # ------------------------------------------------------------------ #
    # receivables / payables
    # ------------------------------------------------------------------ #
    def test_receivables(self):
        VoucherService.save_voucher(
            self.company_id, 'Journal', date.today(),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 1500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1500.0},
            ],
        )
        self.assertEqual(DashboardService.receivables(self.company_id), 1500.0)

    def test_payables(self):
        VoucherService.save_voucher(
            self.company_id, 'Journal', date.today(),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 800.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 800.0},
            ],
        )
        self.assertEqual(DashboardService.payables(self.company_id), 800.0)

    def test_receivables_agree_with_outstanding(self):
        from services.outstanding_report_service import outstanding_report_service
        VoucherService.save_voucher(
            self.company_id, 'Journal', date.today(),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 2500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2500.0},
            ],
        )
        report = outstanding_report_service.generate_outstanding_report(
            self.company_id, 'Receivable', date.today(), False)
        self.assertEqual(
            DashboardService.receivables(self.company_id),
            report['totals']['total_receivable'])

    # ------------------------------------------------------------------ #
    # daily / monthly totals
    # ------------------------------------------------------------------ #
    def test_today_totals(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Payment', date.today(),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        totals = DashboardService.today_totals(self.company_id, date.today())
        self.assertEqual(totals['receipts'], 2000.0)
        self.assertEqual(totals['payments'], 500.0)

    def test_month_totals(self):
        today = date.today()
        first_of_month = date(today.year, today.month, 1)
        VoucherService.save_voucher(
            self.company_id, 'Receipt', first_of_month,
            [
                {'account_id': self.acct['cash'], 'debit_amount': 700.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 700.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Receipt', today,
            [
                {'account_id': self.acct['cash'], 'debit_amount': 1300.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1300.0},
            ],
        )
        # An out-of-range date must not count
        VoucherService.save_voucher(
            self.company_id, 'Receipt', today - timedelta(days=40),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 9999.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 9999.0},
            ],
        )
        totals = DashboardService.month_totals(self.company_id, today)
        self.assertEqual(totals['receipts'], 2000.0)
        self.assertEqual(totals['payments'], 0.0)

    # ------------------------------------------------------------------ #
    # cancelled vouchers
    # ------------------------------------------------------------------ #
    def test_cancelled_vouchers_excluded(self):
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
        )
        self.assertEqual(DashboardService.cash_balance(self.company_id), 12000.0)
        self.assertEqual(DashboardService.today_totals(self.company_id, date.today())['receipts'], 2000.0)

        VoucherService.cancel_voucher(vid, self.company_id)
        self.assertEqual(DashboardService.cash_balance(self.company_id), 10000.0)
        self.assertEqual(DashboardService.today_totals(self.company_id, date.today())['receipts'], 0.0)
        self.assertEqual(len(DashboardService.recent_vouchers(self.company_id)), 0)

    # ------------------------------------------------------------------ #
    # company isolation
    # ------------------------------------------------------------------ #
    def test_company_isolation(self):
        acct2 = setup(2)
        VoucherService.save_voucher(
            2, 'Receipt', date.today(),
            [
                {'account_id': acct2['cash'], 'debit_amount': 777.0, 'credit_amount': 0.0},
                {'account_id': acct2['sales'], 'debit_amount': 0.0, 'credit_amount': 777.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 123.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 123.0},
            ],
        )
        self.assertEqual(DashboardService.cash_balance(2), 10777.0)
        self.assertEqual(DashboardService.cash_balance(self.company_id), 10123.0)
        self.assertEqual(len(DashboardService.recent_vouchers(2)), 1)
        self.assertEqual(len(DashboardService.recent_vouchers(self.company_id)), 1)

    # ------------------------------------------------------------------ #
    # empty database
    # ------------------------------------------------------------------ #
    def test_empty_database(self):
        data = DashboardService.get_dashboard(self.company_id)
        self.assertEqual(data['cash_balance'], 10000.0)  # opening only, no vouchers
        self.assertEqual(data['bank_balance'], 20000.0)
        self.assertEqual(data['receivables'], 0.0)
        self.assertEqual(data['payables'], 0.0)
        self.assertEqual(data['today_receipts'], 0.0)
        self.assertEqual(data['today_payments'], 0.0)
        self.assertEqual(data['month_receipts'], 0.0)
        self.assertEqual(data['month_payments'], 0.0)
        self.assertEqual(data['recent_vouchers'], [])
        self.assertEqual(data['company_name'], 'Dash Co')

    def test_get_dashboard_shape(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date.today(),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        data = dashboard_service.get_dashboard(self.company_id)
        expected_keys = {
            'company_id', 'company_name', 'as_on', 'cash_balance', 'bank_balance',
            'receivables', 'payables', 'today_receipts', 'today_payments',
            'month_receipts', 'month_payments', 'recent_vouchers',
        }
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(len(data['recent_vouchers']), 1)


if __name__ == '__main__':
    unittest.main()
