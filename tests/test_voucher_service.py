"""
Tests for the double-entry Voucher Service (Phase 2).

Covers Payment / Receipt / Contra / Journal entry, debit-credit balancing,
company isolation, inactive-account validation, persistence, numbering,
edit, and cancel/delete.
"""
import os
import tempfile
import unittest
from datetime import date

import config

from database import Database
from services.account_service import AccountService
from services.voucher_service import (
    VoucherService,
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    VOUCHER_CONTRA,
    VOUCHER_JOURNAL,
    VOUCHER_SALES,
    VOUCHER_PURCHASE,
    STATUS_CANCELLED,
    STATUS_POSTED,
)


def setup_accounts(account_service: AccountService, company_id: int):
    """Create a standard set of ledgers for a test company."""
    cash = account_service.create_account(company_id, 'Cash', 'CASH', 'Cash-in-Hand', 0.0, 'Debit')
    bank = account_service.create_account(company_id, 'Bank', 'BANK', 'Bank Accounts', 0.0, 'Debit')
    debtor = account_service.create_account(company_id, 'Customer A', 'C001', 'Sundry Debtors', 0.0, 'Debit')
    creditor = account_service.create_account(company_id, 'Supplier X', 'S001', 'Sundry Creditors', 0.0, 'Credit')
    sales = account_service.create_account(company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
    purchases = account_service.create_account(company_id, 'Purchases', 'PUR', 'Purchase Accounts', 0.0, 'Debit')
    expenses = account_service.create_account(company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
    return {
        'cash': cash, 'bank': bank, 'debtor': debtor, 'creditor': creditor,
        'sales': sales, 'purchases': purchases, 'expenses': expenses,
    }


class TestVoucherService(unittest.TestCase):
    """Voucher double-entry service tests."""

    @classmethod
    def setUpClass(cls):
        config.DATABASE_PATH = ':memory:'
        from database.database import db as shared_db
        cls.db = shared_db
        shared_db.initialize_database()
        # Reset shared tables so this class owns the fixture set regardless
        # of which test file ran before on the shared in-memory singleton.
        cls.db.execute("DELETE FROM voucher_details")
        cls.db.execute("DELETE FROM vouchers")
        cls.db.execute("DELETE FROM accounts")
        cls.db.execute("DELETE FROM companies")
        cls.account_service = AccountService()
        cls.company_id = 1
        cls.db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (?, ?, ?, ?)",
            (cls.company_id, 'Voucher Co', '01-04', '31-03'),
        )
        cls.db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (?, ?, ?, ?)",
            (2, 'Second Co', '01-04', '31-03'),
        )
        cls.acct = setup_accounts(cls.account_service, cls.company_id)

    def setUp(self):
        self.db.execute("DELETE FROM voucher_details")
        self.db.execute("DELETE FROM vouchers")

    def tearDown(self):
        pass

    # ------------------------------------------------------------------ #
    # basic entry types
    # ------------------------------------------------------------------ #
    def test_payment_voucher(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0,
                 'narration': 'Rent'},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0,
                 'narration': 'Rent'},
            ],
            reference_number='CHQ-001', narration='Rent paid by cheque',
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher_with_details(voucher_id)
        self.assertEqual(voucher['voucher_type'], VOUCHER_PAYMENT)
        self.assertEqual(voucher['status'], STATUS_POSTED)
        self.assertEqual(voucher['voucher_number'], 'PV-0001')
        self.assertEqual(voucher['reference_number'], 'CHQ-001')
        self.assertEqual(len(voucher['details']), 2)
        totals = VoucherService.get_voucher_totals(voucher_id)
        self.assertEqual(totals['debit_total'], 500.0)
        self.assertEqual(totals['credit_total'], 500.0)

    def test_receipt_voucher(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_RECEIPT, date(2026, 8, 2),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher(voucher_id)
        self.assertEqual(voucher['voucher_type'], VOUCHER_RECEIPT)
        self.assertEqual(voucher['voucher_number'], 'RV-0001')

    def test_contra_voucher(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_CONTRA, date(2026, 8, 3),
            [
                {'account_id': self.acct['bank'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
            narration='Cash deposited to bank',
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher(voucher_id)
        self.assertEqual(voucher['voucher_type'], VOUCHER_CONTRA)
        self.assertEqual(voucher['voucher_number'], 'CV-0001')

    def test_journal_voucher(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 4),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 300.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 300.0},
            ],
            narration='Credit sale entry',
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher(voucher_id)
        self.assertEqual(voucher['voucher_type'], VOUCHER_JOURNAL)
        self.assertEqual(voucher['voucher_number'], 'JV-0001')

    # ------------------------------------------------------------------ #
    # 6-voucher types: Sales / Purchase + per-type validation rules
    # ------------------------------------------------------------------ #
    def test_sales_voucher(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 5),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 5000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 5000.0},
            ],
            narration='Credit sale to Customer A',
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher(voucher_id)
        self.assertEqual(voucher['voucher_type'], VOUCHER_SALES)
        self.assertEqual(voucher['voucher_number'], 'SV-0001')
        totals = VoucherService.get_voucher_totals(voucher_id)
        self.assertEqual(totals['debit_total'], 5000.0)
        self.assertEqual(totals['credit_total'], 5000.0)

    def test_purchase_voucher(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PURCHASE, date(2026, 8, 6),
            [
                {'account_id': self.acct['purchases'], 'debit_amount': 8000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 8000.0},
            ],
            narration='Credit purchase from Supplier X',
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher(voucher_id)
        self.assertEqual(voucher['voucher_type'], VOUCHER_PURCHASE)
        self.assertEqual(voucher['voucher_number'], 'PC-0001')

    def test_sales_cash_receipt_allowed(self):
        """A cash sale: Cash Dr / Sales Cr is a valid SALES voucher."""
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 5),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 250.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 250.0},
            ],
        )
        self.assertTrue(ok, message)

    def test_purchase_cash_payment_allowed(self):
        """A cash purchase: Purchases Dr / Cash Cr is a valid PURCHASE."""
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_PURCHASE, date(2026, 8, 6),
            [
                {'account_id': self.acct['purchases'], 'debit_amount': 400.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 400.0},
            ],
        )
        self.assertTrue(ok, message)

    def test_contra_rejects_non_cash_bank(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_CONTRA, date(2026, 8, 3),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 200.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 200.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('contra', message.lower())
        self.assertIn('cash or bank', message.lower())
        self.assertIsNone(voucher_id)

    def test_journal_rejects_cash_bank(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 4),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('journal', message.lower())
        self.assertIn('cash or bank', message.lower())

    def test_payment_requires_cash_bank_credit(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('cash or bank', message.lower())

    def test_receipt_requires_cash_bank_debit(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_RECEIPT, date(2026, 8, 2),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('cash or bank', message.lower())

    def test_sales_requires_income_credit(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 5),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('sales/income', message.lower())

    def test_purchase_requires_expense_debit(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_PURCHASE, date(2026, 8, 6),
            [
                {'account_id': self.acct['sales'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('purchase / expense / asset', message.lower())

    def test_get_voucher_by_id_alias(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_SALES, date(2026, 8, 5),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertTrue(ok)
        self.assertIsNotNone(voucher_id)
        fetched = VoucherService.get_voucher_by_id(voucher_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched['id'], voucher_id)

    def test_voucher_numbering_per_type(self):
        # Type-appropriate balanced entry pairs for each voucher type.
        entries_by_type = {
            VOUCHER_PAYMENT: [
                {'account_id': self.acct['expenses'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
            VOUCHER_RECEIPT: [
                {'account_id': self.acct['cash'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
            VOUCHER_CONTRA: [
                {'account_id': self.acct['bank'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
            VOUCHER_JOURNAL: [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
            VOUCHER_SALES: [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
            VOUCHER_PURCHASE: [
                {'account_id': self.acct['purchases'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['creditor'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        }
        for vtype, prefix in [(VOUCHER_PAYMENT, 'PV'), (VOUCHER_RECEIPT, 'RV'),
                              (VOUCHER_CONTRA, 'CV'), (VOUCHER_JOURNAL, 'JV'),
                              (VOUCHER_SALES, 'SV'), (VOUCHER_PURCHASE, 'PC')]:
            for i in range(1, 4):
                ok, _, _ = VoucherService.save_voucher(
                    self.company_id, vtype, date(2026, 8, 1),
                    [dict(e) for e in entries_by_type[vtype]],
                )
                self.assertTrue(ok, f"{vtype} entry rejected")
                number = VoucherService.next_voucher_number(self.company_id, vtype)
                self.assertEqual(number, f"{prefix}-{i + 1:04d}")

    # ------------------------------------------------------------------ #
    # balancing and validation
    # ------------------------------------------------------------------ #
    def test_unbalanced_voucher_rejected(self):
        ok, message, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 90.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('balanced', message.lower())
        self.assertIsNone(voucher_id)

    def test_zero_amount_rejected(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 0.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 0.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('greater than zero', message.lower())

    def test_negative_amount_rejected(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': -100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('negative', message.lower())

    def test_entry_cannot_be_both_debit_and_credit(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 50.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)

    def test_empty_entries_rejected(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1), [])
        self.assertFalse(ok)
        self.assertIn('at least one', message.lower())

    def test_invalid_voucher_type_rejected(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, 'Expense', date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('invalid voucher type', message.lower())

    # ------------------------------------------------------------------ #
    # company isolation / account ownership
    # ------------------------------------------------------------------ #
    def test_inactive_account_rejected(self):
        self.account_service.set_account_active(self.acct['expenses'], False)
        try:
            ok, message, _ = VoucherService.save_voucher(
                self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
                [
                    {'account_id': self.acct['expenses'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                    {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 100.0},
                ],
            )
            self.assertFalse(ok)
            self.assertIn('inactive', message.lower())
        finally:
            self.account_service.set_account_active(self.acct['expenses'], True)

    def test_cross_company_account_rejected(self):
        other_account = self.account_service.create_account(
            2, 'Other Cash', 'OC', 'Cash-in-Hand', 0.0, 'Debit')
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': other_account, 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('different company', message.lower())

    def test_nonexistent_account_rejected(self):
        ok, message, _ = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': 99999, 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('does not exist', message.lower())

    def test_company_isolation_listing(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        # Same ledger set for company 2
        acct2 = setup_accounts(self.account_service, 2)
        VoucherService.save_voucher(
            2, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': acct2['expenses'], 'debit_amount': 250.0, 'credit_amount': 0.0},
                {'account_id': acct2['bank'], 'debit_amount': 0.0, 'credit_amount': 250.0},
            ],
        )
        company1 = VoucherService.list_vouchers(self.company_id)
        company2 = VoucherService.list_vouchers(2)
        self.assertEqual(len(company1), 1)
        self.assertEqual(len(company2), 1)

    # ------------------------------------------------------------------ #
    # persistence
    # ------------------------------------------------------------------ #
    def test_persistence_across_reopen(self):
        """Vouchers survive a database re-open (file-backed DB)."""
        tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(tmpdir.name, 'persist.db')
        db1 = Database(db_path=db_path)
        db1.initialize_database()
        db1.execute(
            "INSERT INTO companies (id, name) VALUES (1, 'Persist Co')")
        cash = AccountService.create_account(1, 'Cash', 'CASH', 'Cash-in-Hand', 0.0, 'Debit')
        sales = AccountService.create_account(1, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
        ok, _, vid = VoucherService.save_voucher(
            1, VOUCHER_RECEIPT, date(2026, 8, 5),
            [
                {'account_id': cash, 'debit_amount': 750.0, 'credit_amount': 0.0},
                {'account_id': sales, 'debit_amount': 0.0, 'credit_amount': 750.0},
            ],
        )
        self.assertTrue(ok)
        db1.close()

        # Re-open the same file
        db2 = Database(db_path=db_path)
        db2.initialize_database()
        voucher = VoucherService.get_voucher_with_details(vid)
        self.assertIsNotNone(voucher)
        self.assertEqual(voucher['voucher_number'], 'RV-0001')
        self.assertEqual(len(voucher['details']), 2)
        totals = VoucherService.get_voucher_totals(vid)
        self.assertEqual(totals['debit_total'], 750.0)
        self.assertEqual(totals['credit_total'], 750.0)
        db2.close()
        tmpdir.cleanup()

    # ------------------------------------------------------------------ #
    # edit / cancel / delete
    # ------------------------------------------------------------------ #
    def test_update_voucher(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        ok, message = VoucherService.update_voucher(
            voucher_id, self.company_id, VOUCHER_PAYMENT, date(2026, 8, 2),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 700.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 700.0},
            ],
            reference_number='CHQ-002',
        )
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher_with_details(voucher_id)
        self.assertEqual(voucher['voucher_date'], '2026-08-02')
        self.assertEqual(voucher['reference_number'], 'CHQ-002')
        totals = VoucherService.get_voucher_totals(voucher_id)
        self.assertEqual(totals['debit_total'], 700.0)

    def test_update_unbalanced_rejected(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 100.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        ok, message = VoucherService.update_voucher(
            voucher_id, self.company_id, VOUCHER_JOURNAL, date(2026, 8, 1),
            [
                {'account_id': self.acct['debtor'], 'debit_amount': 200.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 100.0},
            ],
        )
        self.assertFalse(ok)
        # Original data must remain intact
        totals = VoucherService.get_voucher_totals(voucher_id)
        self.assertEqual(totals['debit_total'], 100.0)

    def test_cancel_voucher(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        ok, message = VoucherService.cancel_voucher(voucher_id, self.company_id)
        self.assertTrue(ok, message)
        voucher = VoucherService.get_voucher(voucher_id)
        self.assertEqual(voucher['status'], STATUS_CANCELLED)
        # Default listing includes cancelled; active-only excludes it.
        self.assertEqual(len(VoucherService.list_vouchers(self.company_id)), 1)
        self.assertEqual(
            len(VoucherService.list_vouchers(self.company_id, include_cancelled=False)), 0)

    def test_cancel_voucher_blocks_update(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        VoucherService.cancel_voucher(voucher_id, self.company_id)
        ok, message = VoucherService.update_voucher(
            voucher_id, self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 600.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 600.0},
            ],
        )
        self.assertFalse(ok)
        self.assertIn('cancelled', message.lower())

    def test_cross_company_cancel_rejected(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        ok, message = VoucherService.cancel_voucher(voucher_id, 2)
        self.assertFalse(ok)
        self.assertIn('different company', message.lower())

    def test_delete_voucher(self):
        ok, _, voucher_id = VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        ok, message = VoucherService.delete_voucher(voucher_id, self.company_id)
        self.assertTrue(ok, message)
        self.assertIsNone(VoucherService.get_voucher(voucher_id))
        self.assertEqual(len(VoucherService.list_vouchers(self.company_id)), 0)

    # ------------------------------------------------------------------ #
    # list / filter
    # ------------------------------------------------------------------ #
    def test_list_filters(self):
        VoucherService.save_voucher(
            self.company_id, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['bank'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
            reference_number='CHQ-001',
        )
        VoucherService.save_voucher(
            self.company_id, VOUCHER_RECEIPT, date(2026, 8, 10),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 800.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 800.0},
            ],
        )
        self.assertEqual(len(VoucherService.list_vouchers(self.company_id)), 2)
        self.assertEqual(
            len(VoucherService.list_vouchers(self.company_id, voucher_type=VOUCHER_PAYMENT)), 1)
        self.assertEqual(
            len(VoucherService.list_vouchers(self.company_id, from_date=date(2026, 8, 5))), 1)
        self.assertEqual(
            len(VoucherService.list_vouchers(self.company_id, to_date=date(2026, 8, 5))), 1)
        self.assertEqual(
            len(VoucherService.list_vouchers(self.company_id, search_term='CHQ')), 1)


if __name__ == '__main__':
    unittest.main()
