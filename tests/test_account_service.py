"""
Tests for the Ledger (Chart of Accounts) master service (Phase 1).

Verifies ledger CRUD, group assignment, opening balance + debit/credit
nature, active toggle, search, and reference-aware delete.
"""
import unittest

import config

config.DATABASE_PATH = ':memory:'

from database.database import db
from services.account_service import account_service
from services.voucher_service import voucher_service
from datetime import date


class TestAccountService(unittest.TestCase):
    """Ledger master service tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        cls.company_id = 1
        db.execute(
            """
            INSERT INTO companies (id, name, financial_year_start, financial_year_end)
            VALUES (?, ?, ?, ?)
            """,
            (cls.company_id, 'Ledger Test Co', '01-04', '31-03'),
        )

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")

    def test_create_account(self):
        account_id = account_service.create_account(
            self.company_id, 'Cash', 'CASH', 'Cash-in-Hand', 10000.0, 'Debit')
        account = account_service.get_account(account_id)
        self.assertEqual(account['name'], 'Cash')
        self.assertEqual(account['code'], 'CASH')
        self.assertEqual(account['account_group'], 'Cash-in-Hand')
        self.assertEqual(account['opening_balance'], 10000.0)
        self.assertEqual(account['opening_balance_type'], 'Debit')
        self.assertTrue(account['is_active'])

    def test_list_accounts_by_company(self):
        account_service.create_account(self.company_id, 'Cash', 'CASH', 'Cash-in-Hand', 0.0, 'Debit')
        account_service.create_account(self.company_id, 'Bank', 'BANK', 'Bank Accounts', 0.0, 'Debit')
        db.execute(
            """
            INSERT INTO companies (id, name, financial_year_start, financial_year_end)
            VALUES (?, ?, ?, ?)
            """,
            (2, 'Second Co', '01-04', '31-03'),
        )
        account_service.create_account(2, 'Other', 'OTH', 'Misc', 0.0, 'Debit')
        accounts = account_service.list_accounts(self.company_id)
        self.assertEqual(len(accounts), 2)

    def test_search_accounts(self):
        account_service.create_account(self.company_id, 'Sundry Debtors', 'DR', 'Sundry Debtors', 0.0, 'Debit')
        account_service.create_account(self.company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
        results = account_service.search_accounts(self.company_id, 'debt')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Sundry Debtors')
        # Search by code
        results = account_service.search_accounts(self.company_id, 'SAL')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Sales')

    def test_update_account(self):
        account_id = account_service.create_account(
            self.company_id, 'Cash', 'CASH', 'Cash-in-Hand', 1000.0, 'Debit')
        ok = account_service.update_account(
            account_id, opening_balance=5000.0, opening_balance_type='Credit')
        self.assertTrue(ok)
        account = account_service.get_account(account_id)
        self.assertEqual(account['opening_balance'], 5000.0)
        self.assertEqual(account['opening_balance_type'], 'Credit')

    def test_set_account_active(self):
        account_id = account_service.create_account(
            self.company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
        account_service.set_account_active(account_id, False)
        self.assertFalse(account_service.get_account(account_id)['is_active'])
        # Default search excludes inactive
        results = account_service.search_accounts(self.company_id, 'Rent')
        self.assertEqual(len(results), 0)
        # Include inactive
        results = account_service.search_accounts(self.company_id, 'Rent', include_inactive=True)
        self.assertEqual(len(results), 1)

    def test_list_groups_in_use(self):
        account_service.create_account(self.company_id, 'Cash', 'C', 'Cash-in-Hand', 0.0, 'Debit')
        account_service.create_account(self.company_id, 'Bank', 'B', 'Bank Accounts', 0.0, 'Debit')
        groups = account_service.list_groups(self.company_id)
        names = {g['account_group'] for g in groups}
        self.assertEqual(names, {'Cash-in-Hand', 'Bank Accounts'})

    def test_delete_account(self):
        account_id = account_service.create_account(
            self.company_id, 'Misc', 'M', 'Indirect Expense', 0.0, 'Debit')
        self.assertTrue(account_service.delete_account(account_id))
        self.assertIsNone(account_service.get_account(account_id))

    def test_referenced_account_cannot_be_deleted(self):
        account_id = account_service.create_account(
            self.company_id, 'Debtor A', 'D001', 'Sundry Debtors', 0.0, 'Debit')
        sales_id = account_service.create_account(
            self.company_id, 'Sales', 'S001', 'Sales Accounts', 0.0, 'Credit')
        rent_id = account_service.create_account(
            self.company_id, 'Rent', 'R002', 'Indirect Expense', 0.0, 'Debit')
        voucher_id = voucher_service.create_voucher(
            self.company_id, 'Sales Invoice', date.today(), 'INV-X1')
        voucher_service.add_voucher_detail(voucher_id, account_id, 1000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, sales_id, 0.0, 1000.0, 'Sale')
        self.assertTrue(account_service.is_account_referenced(account_id))
        self.assertTrue(account_service.is_account_referenced(sales_id))
        self.assertFalse(account_service.is_account_referenced(rent_id))


if __name__ == '__main__':
    unittest.main()
