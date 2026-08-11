"""
Tests for the Voucher Register (Day Book) service and report integration
(Phase 2): cancelled vouchers are excluded from report readers.
"""
import unittest
from datetime import date

import config

config.DATABASE_PATH = ':memory:'

from database.database import db
from services.account_service import AccountService
from services.voucher_service import (
    VoucherService,
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    VOUCHER_JOURNAL,
)
from services.voucher_register_service import voucher_register_service
from services.party_ledger_service import PartyLedgerService


def setup_accounts(company_id: int):
    cash = AccountService.create_account(company_id, 'Cash', 'CASH', 'Cash-in-Hand', 0.0, 'Debit')
    bank = AccountService.create_account(company_id, 'Bank', 'BANK', 'Bank Accounts', 0.0, 'Debit')
    debtor = AccountService.create_account(company_id, 'Customer A', 'C001', 'Sundry Debtors', 0.0, 'Debit')
    sales = AccountService.create_account(company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
    expenses = AccountService.create_account(company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
    return {'cash': cash, 'bank': bank, 'debtor': debtor, 'sales': sales, 'expenses': expenses}


class TestVoucherRegisterService(unittest.TestCase):
    """Day Book + report integration tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        # Reset shared tables so this class owns the fixture set regardless
        # of which test file ran before on the shared in-memory singleton.
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        db.execute("DELETE FROM companies")
        cls.company_id = 1
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (?, ?, ?, ?)",
            (cls.company_id, 'Register Co', '01-04', '31-03'),
        )
        cls.acct = setup_accounts(cls.company_id)

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")

    def test_generate_day_book(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
            reference_number='CHQ-1', narration='Rent',
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_RECEIPT, date(2026, 8, 2),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 900.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 900.0},
            ],
            narration='Sale',
        )
        report = voucher_register_service.generate_day_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertTrue(report['success'])
        self.assertEqual(report['entry_count'], 4)
        self.assertEqual(report['totals']['debit'], 1400.0)
        self.assertEqual(report['totals']['credit'], 1400.0)
        # Account names resolved
        account_names = {e['account_name'] for e in report['entries']}
        self.assertIn('Rent', account_names)
        self.assertIn('Bank', account_names)

    def test_day_book_type_filter(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_RECEIPT, date(2026, 8, 2),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 900.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 900.0},
            ],
        )
        report = voucher_register_service.generate_day_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31),
            voucher_type=VOUCHER_PAYMENT)
        self.assertEqual(report['entry_count'], 2)

    def test_day_book_excludes_cancelled(self):
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        VoucherService.cancel_voucher(vid, self.company_id)
        report = voucher_register_service.generate_day_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['entry_count'], 0)

    def test_cancelled_voucher_excluded_from_party_ledger(self):
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
            narration='Credit sale',
        )
        # Ledger shows the entry
        txns = PartyLedgerService._get_party_transactions(
            self.acct['debtor'], date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(len(txns), 1)
        # Cancel it; ledger must no longer show it
        VoucherService.cancel_voucher(vid, self.company_id)
        txns = PartyLedgerService._get_party_transactions(
            self.acct['debtor'], date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(len(txns), 0)

    def test_export_day_book_csv(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        report = voucher_register_service.generate_day_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        success, path = voucher_register_service.export_day_book_to_csv(report, 'test_day_book')
        self.assertTrue(success)
        self.assertTrue(path.endswith('.csv'))


if __name__ == '__main__':
    unittest.main()
