"""
Tests for Phase 5: Trial Balance and Balance Sheet services.

Covers correct debit/credit classification, reconciliation (debits =
credits and Assets = Liabilities + Capital), as-of date filtering,
cancelled-voucher exclusion, company isolation, and retained earnings.
"""
import unittest
from datetime import date, timedelta

import config

config.DATABASE_PATH = ':memory:'

from database.database import db
from services.account_service import AccountService
from services.voucher_service import VoucherService
from services.trial_balance_service import TrialBalanceService, trial_balance_service
from services.balance_sheet_service import BalanceSheetService, balance_sheet_service


def setup_books(company_id: int):
    # Defensive: remove any prior vouchers/accounts for this company so the
    # shared in-memory singleton doesn't collide across test classes.
    db.execute(
        "DELETE FROM voucher_details WHERE account_id IN "
        "(SELECT id FROM accounts WHERE company_id = ?)", (company_id,))
    db.execute("DELETE FROM accounts WHERE company_id = ?", (company_id,))
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
    purchases = AccountService.create_account(
        company_id, 'Purchases', 'PUR', 'Purchase Accounts', 0.0, 'Debit')
    capital = AccountService.create_account(
        company_id, 'Capital', 'CAP', 'Capital', 30000.0, 'Credit')
    return {'cash': cash, 'bank': bank, 'debtor': debtor, 'creditor': creditor,
            'sales': sales, 'purchases': purchases, 'capital': capital}


def seed_standard_activity(acct):
    """Debtor +5000/Sales -5000; Purchases +2000/Cash -2000; Purchases +800/Creditor -800."""
    VoucherService.save_voucher(
        1, 'Journal', date(2026, 8, 1),
        [
            {'account_id': acct['debtor'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
            {'account_id': acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
        ],
    )
    VoucherService.save_voucher(
        1, 'Payment', date(2026, 8, 2),
        [
            {'account_id': acct['purchases'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
            {'account_id': acct['cash'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
        ],
    )
    VoucherService.save_voucher(
        1, 'Journal', date(2026, 8, 3),
        [
            {'account_id': acct['purchases'], 'debit_amount': 800.0, 'credit_amount': 0.0},
            {'account_id': acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 800.0},
        ],
    )


class TestTrialBalanceService(unittest.TestCase):
    """Trial balance tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        db.execute("DELETE FROM companies")
        db.execute("INSERT INTO companies (id, name) VALUES (1, 'TB Co')")
        db.execute("INSERT INTO companies (id, name) VALUES (2, 'Other Co')")
        cls.acct = setup_books(1)

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute(
            "UPDATE accounts SET opening_balance = 0.0 WHERE id IN "
            "(SELECT id FROM accounts WHERE company_id = 1)")
        db.execute(
            "UPDATE accounts SET opening_balance = 10000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['cash'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 20000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['bank'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 30000.0, opening_balance_type = 'Credit' "
            "WHERE id = ?", (self.acct['capital'],))

    def test_trial_balance_balanced(self):
        seed_standard_activity(self.acct)
        tb = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        self.assertTrue(tb['success'])
        self.assertTrue(tb['is_balanced'])
        self.assertEqual(tb['totals']['debit'], tb['totals']['credit'])

    def test_trial_balance_debit_credit_direction(self):
        seed_standard_activity(self.acct)
        tb = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        rows = {r['account_name']: r for r in tb['rows']}
        # Cash: 10000 - 2000 = 8000 debit
        self.assertEqual(rows['Cash']['debit'], 8000.0)
        self.assertEqual(rows['Cash']['credit'], 0.0)
        # Bank: 20000 debit
        self.assertEqual(rows['Bank']['debit'], 20000.0)
        # Debtor: 5000 debit
        self.assertEqual(rows['Customer A']['debit'], 5000.0)
        # Purchases: 2800 debit
        self.assertEqual(rows['Purchases']['debit'], 2800.0)
        # Sales: 5000 credit
        self.assertEqual(rows['Sales']['credit'], 5000.0)
        # Creditor: 800 credit
        self.assertEqual(rows['Supplier X']['credit'], 800.0)
        # Capital: 30000 credit
        self.assertEqual(rows['Capital']['credit'], 30000.0)

    def test_trial_balance_totals(self):
        seed_standard_activity(self.acct)
        tb = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        # Debit: 8000 + 20000 + 5000 + 2800 = 35800
        # Credit: 30000 + 5000 + 800 = 35800
        self.assertEqual(tb['totals']['debit'], 35800.0)
        self.assertEqual(tb['totals']['credit'], 35800.0)

    def test_trial_balance_as_of_date(self):
        seed_standard_activity(self.acct)
        # Only the first voucher (Aug 1) is before Aug 2
        tb = trial_balance_service.generate_trial_balance(1, date(2026, 8, 1))
        self.assertEqual(tb['totals']['debit'], tb['totals']['credit'])
        rows = {r['account_name']: r for r in tb['rows']}
        self.assertEqual(rows['Customer A']['debit'], 5000.0)
        self.assertEqual(rows['Sales']['credit'], 5000.0)
        self.assertEqual(rows['Cash']['debit'], 10000.0)  # no payment yet
        self.assertEqual(rows['Purchases']['debit'], 0.0)

    def test_cancelled_voucher_excluded(self):
        # Baseline totals (opening balances only)
        base = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        base_debit = base['totals']['debit']
        ok, _, vid = VoucherService.save_voucher(
            1, 'Receipt', date(2026, 8, 10),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 9999.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 9999.0},
            ],
        )
        tb_before = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        self.assertEqual(tb_before['totals']['debit'], base_debit + 9999.0)
        VoucherService.cancel_voucher(vid, 1)
        tb_after = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        self.assertEqual(tb_after['totals']['debit'], base_debit)

    def test_company_isolation(self):
        acct2 = setup_books(2)
        VoucherService.save_voucher(
            2, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': acct2['cash'], 'debit_amount': 777.0, 'credit_amount': 0.0},
                {'account_id': acct2['sales'], 'debit_amount': 0.0, 'credit_amount': 777.0},
            ],
        )
        tb1 = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        tb2 = trial_balance_service.generate_trial_balance(2, date(2026, 8, 31))
        # Company 2: cash 10000 + 777 + bank 20000 = 30777 debit; capital 30000 credit + sales 777 = 30777
        self.assertEqual(tb2['totals']['debit'], 30777.0)
        self.assertEqual(tb2['totals']['credit'], 30777.0)
        self.assertTrue(tb2['is_balanced'])
        # Company 1 is untouched by company 2's voucher.
        rows1 = {r['account_name']: r for r in tb1['rows']}
        self.assertEqual(rows1['Cash']['debit'], 10000.0)

    def test_search_rows(self):
        seed_standard_activity(self.acct)
        tb = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        filtered = trial_balance_service.search_rows(tb, 'cash')
        self.assertEqual(filtered['row_count'], 1)
        self.assertEqual(filtered['rows'][0]['account_name'], 'Cash')

    def test_export_csv(self):
        seed_standard_activity(self.acct)
        tb = trial_balance_service.generate_trial_balance(1, date(2026, 8, 31))
        success, path = trial_balance_service.export_trial_balance_to_csv(tb, 'test_tb')
        self.assertTrue(success)
        self.assertTrue(path.endswith('.csv'))


class TestBalanceSheetService(unittest.TestCase):
    """Balance sheet tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        db.execute("DELETE FROM companies")
        db.execute("INSERT INTO companies (id, name) VALUES (1, 'BS Co')")
        db.execute("INSERT INTO companies (id, name) VALUES (2, 'Other Co')")
        cls.acct = setup_books(1)

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute(
            "UPDATE accounts SET opening_balance = 0.0 WHERE id IN "
            "(SELECT id FROM accounts WHERE company_id = 1)")
        db.execute(
            "UPDATE accounts SET opening_balance = 10000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['cash'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 20000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['bank'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 30000.0, opening_balance_type = 'Credit' "
            "WHERE id = ?", (self.acct['capital'],))

    def test_balance_sheet_reconciles(self):
        seed_standard_activity(self.acct)
        bs = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 31))
        self.assertTrue(bs['success'])
        self.assertTrue(bs['is_balanced'])
        # Assets: cash 8000 + bank 20000 + debtor 5000 = 33000
        self.assertEqual(bs['totals']['total_assets'], 33000.0)
        # Liabilities: creditor 800
        self.assertEqual(bs['totals']['total_liabilities'], 800.0)
        # Capital: 30000 + retained (income 5000 - expense 2800 = 2200) = 32200
        self.assertEqual(bs['totals']['total_capital'], 32200.0)
        self.assertEqual(bs['totals']['total_liabilities_capital'], 33000.0)

    def test_retained_earnings(self):
        seed_standard_activity(self.acct)
        bs = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 31))
        self.assertEqual(bs['income_total'], 5000.0)
        self.assertEqual(bs['expense_total'], -2800.0)
        self.assertEqual(bs['retained_earnings'], 2200.0)
        capital_names = [e['account_name'] for e in bs['sections']['Capital']]
        self.assertIn('Retained Earnings (Income - Expense)', capital_names)

    def test_balance_sheet_as_of_date(self):
        seed_standard_activity(self.acct)
        bs = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 1))
        self.assertTrue(bs['is_balanced'])
        # Only the debtor/sales journal exists: assets 10000(cash) + 20000(bank) + 5000(debtor)
        self.assertEqual(bs['totals']['total_assets'], 35000.0)
        # Capital: 30000 + retained 5000 = 35000
        self.assertEqual(bs['totals']['total_capital'], 35000.0)

    def test_cancelled_voucher_excluded_from_balance_sheet(self):
        ok, _, vid = VoucherService.save_voucher(
            1, 'Receipt', date(2026, 8, 10),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
        )
        bs_before = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 31))
        self.assertEqual(bs_before['totals']['total_assets'], 35000.0)
        VoucherService.cancel_voucher(vid, 1)
        bs_after = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 31))
        self.assertEqual(bs_after['totals']['total_assets'], 30000.0)
        self.assertTrue(bs_after['is_balanced'])

    def test_balance_sheet_company_isolation(self):
        acct2 = setup_books(2)
        VoucherService.save_voucher(
            2, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': acct2['cash'], 'debit_amount': 777.0, 'credit_amount': 0.0},
                {'account_id': acct2['sales'], 'debit_amount': 0.0, 'credit_amount': 777.0},
            ],
        )
        bs1 = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 31))
        bs2 = balance_sheet_service.generate_balance_sheet(2, date(2026, 8, 31))
        # Company 1 assets: cash 10000 + bank 20000 = 30000 (untouched)
        self.assertEqual(bs1['totals']['total_assets'], 30000.0)
        # Company 2 assets: cash 10000 + 777 + bank 20000 = 30777
        self.assertEqual(bs2['totals']['total_assets'], 30777.0)
        self.assertTrue(bs2['is_balanced'])

    def test_export_csv(self):
        seed_standard_activity(self.acct)
        bs = balance_sheet_service.generate_balance_sheet(1, date(2026, 8, 31))
        success, path = balance_sheet_service.export_balance_sheet_to_csv(bs, 'test_bs')
        self.assertTrue(success)
        self.assertTrue(path.endswith('.csv'))


if __name__ == '__main__':
    unittest.main()
