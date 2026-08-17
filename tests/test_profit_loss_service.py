"""
Tests for the Profit & Loss service (6-voucher accounting integration).

Covers income vs expense classification, net profit/loss, date-range
filtering, cancelled-voucher exclusion, and the 6 voucher types feeding the
report.
"""
import unittest
from datetime import date

import config

config.DATABASE_PATH = ':memory:'

from database.database import db  # noqa: E402
from services.account_service import AccountService  # noqa: E402
from services.voucher_service import (  # noqa: E402
    VoucherService,
    VOUCHER_SALES,
    VOUCHER_PURCHASE,
    VOUCHER_RECEIPT,
    VOUCHER_PAYMENT,
)
from services.profit_loss_service import profit_loss_service  # noqa: E402


def setup_books(company_id: int):
    db.execute(
        "DELETE FROM voucher_details WHERE account_id IN "
        "(SELECT id FROM accounts WHERE company_id = ?)", (company_id,))
    db.execute("DELETE FROM accounts WHERE company_id = ?", (company_id,))
    cash = AccountService.create_account(
        company_id, 'Cash', 'CASH', 'Cash-in-Hand', 0.0, 'Debit')
    debtor = AccountService.create_account(
        company_id, 'Customer A', 'C001', 'Sundry Debtors', 0.0, 'Debit')
    creditor = AccountService.create_account(
        company_id, 'Supplier X', 'S001', 'Sundry Creditors', 0.0, 'Credit')
    sales = AccountService.create_account(
        company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
    purchases = AccountService.create_account(
        company_id, 'Purchases', 'PUR', 'Purchase Accounts', 0.0, 'Debit')
    rent = AccountService.create_account(
        company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
    return {'cash': cash, 'debtor': debtor, 'creditor': creditor,
            'sales': sales, 'purchases': purchases, 'rent': rent}


class TestProfitLossService(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM companies")
        cls.company_id = 1
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)",
            (cls.company_id, 'P&L Co'),
        )
        cls.acct = setup_books(cls.company_id)

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")

    def test_income_and_expense_totals(self):
        # Sales (income) 5000; Purchases 2000 + Rent 1000 (expenses).
        VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PURCHASE, date(2026, 8, 2),
            [
                {'account_id': self.acct['purchases'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 3),
            [
                {'account_id': self.acct['rent'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        report = profit_loss_service.generate_profit_loss(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertTrue(report['success'])
        self.assertEqual(report['income_total'], 5000.0)
        self.assertEqual(report['expense_total'], 3000.0)
        self.assertEqual(report['net_profit_loss'], 2000.0)
        self.assertTrue(report['is_profit'])
        # Income row only has credit; expense rows only have debit.
        self.assertEqual(len(report['income_rows']), 1)
        self.assertEqual(len(report['expense_rows']), 2)

    def test_net_loss_when_expenses_exceed_income(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_RECEIPT, date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PURCHASE, date(2026, 8, 2),
            [
                {'account_id': self.acct['purchases'], 'debit_amount': 3000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 3000.0},
            ],
        )
        report = profit_loss_service.generate_profit_loss(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['income_total'], 1000.0)
        self.assertEqual(report['expense_total'], 3000.0)
        self.assertEqual(report['net_profit_loss'], -2000.0)
        self.assertFalse(report['is_profit'])

    def test_date_range_filters_activity(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 20),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 7000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 7000.0},
            ],
        )
        # Only the first sale falls in the range.
        report = profit_loss_service.generate_profit_loss(
            self.company_id, date(2026, 8, 1), date(2026, 8, 15))
        self.assertEqual(report['income_total'], 5000.0)

    def test_cancelled_voucher_excluded(self):
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
        )
        VoucherService.cancel_voucher(vid, self.company_id)
        report = profit_loss_service.generate_profit_loss(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['income_total'], 0.0)
        self.assertEqual(report['expense_total'], 0.0)

    def test_empty_period_zero_totals(self):
        report = profit_loss_service.generate_profit_loss(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertTrue(report['success'])
        self.assertEqual(report['income_total'], 0.0)
        self.assertEqual(report['expense_total'], 0.0)
        self.assertEqual(report['net_profit_loss'], 0.0)

    def test_export_profit_loss_csv(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
        )
        report = profit_loss_service.generate_profit_loss(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        success, path = profit_loss_service.export_profit_loss_to_csv(report, 'test_pl')
        self.assertTrue(success)
        self.assertTrue(path.endswith('.csv'))


if __name__ == '__main__':
    unittest.main()
