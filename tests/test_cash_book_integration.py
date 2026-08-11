"""
Tests for Phase 3: Cash/Bank Book integration with Expenzo vouchers.

Covers Receipt / Payment / Contra voucher flows into the cash and bank
books, cancelled-voucher exclusion, company isolation, opening balances,
cash/bank balance correctness, date filtering, and report totals.
"""
import unittest
from datetime import date

import config

config.DATABASE_PATH = ':memory:'

from database.database import db
from services.account_service import AccountService
from services.voucher_service import VoucherService
from services.cash_book_service import CashBookService, cash_book_service
from services.voucher_register_service import voucher_register_service


def setup_books(company_id: int):
    """Standard ledgers for cash/bank book testing."""
    cash = AccountService.create_account(
        company_id, 'Cash', 'CASH', 'Cash-in-Hand', 10000.0, 'Debit')
    bank = AccountService.create_account(
        company_id, 'Bank', 'BANK', 'Bank Accounts', 50000.0, 'Debit')
    debtor = AccountService.create_account(
        company_id, 'Customer A', 'C001', 'Sundry Debtors', 0.0, 'Debit')
    creditor = AccountService.create_account(
        company_id, 'Supplier X', 'S001', 'Sundry Creditors', 0.0, 'Credit')
    sales = AccountService.create_account(
        company_id, 'Sales', 'SAL', 'Sales Accounts', 0.0, 'Credit')
    purchases = AccountService.create_account(
        company_id, 'Purchases', 'PUR', 'Purchase Accounts', 0.0, 'Debit')
    expenses = AccountService.create_account(
        company_id, 'Rent', 'RENT', 'Indirect Expense', 0.0, 'Debit')
    return {'cash': cash, 'bank': bank, 'debtor': debtor, 'creditor': creditor,
            'sales': sales, 'purchases': purchases, 'expenses': expenses}


class TestCashBankIntegration(unittest.TestCase):
    """Voucher -> cash/bank book integration."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        db.execute("DELETE FROM companies")
        cls.company_id = 1
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (?, ?, ?, ?)",
            (cls.company_id, 'Cash Co', '01-04', '31-03'),
        )
        db.execute(
            "INSERT INTO companies (id, name) VALUES (2, 'Second Co')")
        cls.acct = setup_books(cls.company_id)

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        # Reset opening balances to baseline
        db.execute("UPDATE accounts SET opening_balance = 0.0 WHERE company_id = ?", (self.company_id,))
        db.execute(
            "UPDATE accounts SET opening_balance = 10000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['cash'],))
        db.execute(
            "UPDATE accounts SET opening_balance = 50000.0, opening_balance_type = 'Debit' "
            "WHERE id = ?", (self.acct['bank'],))

    # ------------------------------------------------------------------ #
    # receipt / payment / contra
    # ------------------------------------------------------------------ #
    def test_receipt_appears_in_cash_book(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
            reference_number='R-1', narration='Cash sale',
        )
        report = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['receipts'], 2000.0)
        self.assertEqual(report['payments'], 0.0)
        self.assertEqual(report['opening_balance'], 10000.0)
        self.assertEqual(report['closing_balance']['amount'], 12000.0)
        self.assertEqual(report['transaction_count'], 1)
        txn = report['transactions'][0]
        self.assertEqual(txn['transaction_type'], 'Receipt')
        self.assertEqual(txn['debit_amount'], 2000.0)

    def test_payment_appears_in_cash_book(self):
        VoucherService.save_voucher(
            self.company_id, 'Payment', date(2026, 8, 2),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
            reference_number='P-1', narration='Rent',
        )
        report = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['payments'], 500.0)
        self.assertEqual(report['closing_balance']['amount'], 9500.0)

    def test_contra_moves_between_cash_and_bank(self):
        VoucherService.save_voucher(
            self.company_id, 'Contra', date(2026, 8, 3),
            [
                {'account_id': self.acct['bank'], 'debit_amount': 3000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 3000.0},
            ],
            narration='Cash to bank',
        )
        cash_book = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        bank_book = cash_book_service.generate_bank_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        # Cash: opening 10000 - 3000 = 7000
        self.assertEqual(cash_book['payments'], 3000.0)
        self.assertEqual(cash_book['closing_balance']['amount'], 7000.0)
        # Bank: opening 50000 + 3000 = 53000
        self.assertEqual(bank_book['receipts'], 3000.0)
        self.assertEqual(bank_book['closing_balance']['amount'], 53000.0)

    def test_contra_not_double_counted(self):
        """A contra credits cash AND debits bank — both books count their
        own side exactly once (no double counting)."""
        VoucherService.save_voucher(
            self.company_id, 'Contra', date(2026, 8, 3),
            [
                {'account_id': self.acct['bank'], 'debit_amount': 3000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 3000.0},
            ],
        )
        cash_book = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(cash_book['transaction_count'], 1)
        self.assertEqual(cash_book['payments'], 3000.0)
        # Totals must balance overall: cash out = bank in
        self.assertEqual(cash_book['payments'], 3000.0)

    # ------------------------------------------------------------------ #
    # cancelled vouchers
    # ------------------------------------------------------------------ #
    def test_cancelled_voucher_excluded_from_cash_book(self):
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
        )
        report_before = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report_before['receipts'], 2000.0)

        VoucherService.cancel_voucher(vid, self.company_id)
        report_after = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report_after['receipts'], 0.0)
        self.assertEqual(report_after['transaction_count'], 0)
        self.assertEqual(report_after['closing_balance']['amount'], 10000.0)

    def test_cancelled_voucher_excluded_from_day_book(self):
        ok, _, vid = VoucherService.save_voucher(
            self.company_id, 'Payment', date(2026, 8, 2),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 500.0},
            ],
        )
        report_before = voucher_register_service.generate_day_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report_before['entry_count'], 2)
        VoucherService.cancel_voucher(vid, self.company_id)
        report_after = voucher_register_service.generate_day_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report_after['entry_count'], 0)

    # ------------------------------------------------------------------ #
    # opening balance & signed direction
    # ------------------------------------------------------------------ #
    def test_opening_balance_from_account(self):
        report = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['opening_balance'], 10000.0)
        self.assertEqual(report['closing_balance']['amount'], 10000.0)
        self.assertEqual(report['closing_balance']['type'], 'Debit')

    def test_credit_opening_balance_is_negative(self):
        """A cash/bank account with Credit opening balance should pull the
        book's opening balance down (signed direction)."""
        db.execute(
            "UPDATE accounts SET opening_balance = 500.0, opening_balance_type = 'Credit' "
            "WHERE id = ?", (self.acct['cash'],))
        report = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report['opening_balance'], -500.0)
        self.assertEqual(report['closing_balance']['type'], 'Credit')

    # ------------------------------------------------------------------ #
    # company isolation
    # ------------------------------------------------------------------ #
    def test_company_isolation(self):
        acct2 = setup_books(2)
        VoucherService.save_voucher(
            2, 'Receipt', date(2026, 8, 5),
            [
                {'account_id': acct2['cash'], 'debit_amount': 777.0, 'credit_amount': 0.0},
                {'account_id': acct2['sales'], 'debit_amount': 0.0, 'credit_amount': 777.0},
            ],
        )
        report1 = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        report2 = cash_book_service.generate_cash_book(
            2, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(report1['receipts'], 0.0)
        self.assertEqual(report2['receipts'], 777.0)
        self.assertEqual(report2['opening_balance'], 10000.0)

    # ------------------------------------------------------------------ #
    # date filtering
    # ------------------------------------------------------------------ #
    def test_date_filtering(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 1000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 1000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date(2026, 8, 10),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
        )
        full = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(full['receipts'], 3000.0)
        partial = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 5), date(2026, 8, 31))
        self.assertEqual(partial['receipts'], 2000.0)
        self.assertEqual(partial['transaction_count'], 1)
        # Opening balance for the filtered range starts at the baseline
        self.assertEqual(partial['opening_balance'], 10000.0)

    # ------------------------------------------------------------------ #
    # report totals
    # ------------------------------------------------------------------ #
    def test_cash_book_totals_balance(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 4000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 4000.0},
            ],
        )
        VoucherService.save_voucher(
            self.company_id, 'Payment', date(2026, 8, 2),
            [
                {'account_id': self.acct['expenses'], 'debit_amount': 1500.0, 'credit_amount': 0.0},
                {'account_id': self.acct['cash'], 'debit_amount': 0.0, 'credit_amount': 1500.0},
            ],
        )
        report = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        # opening + receipts - payments = closing
        self.assertEqual(
            report['opening_balance'] + report['receipts'] - report['payments'],
            report['closing_balance']['amount'])
        self.assertEqual(report['opening_balance'] + report['receipts'] - report['payments'], 12500.0)

    def test_bank_book_account_selector(self):
        sources = cash_book_service._get_cash_sources(self.company_id)
        self.assertEqual(len(sources), 2)
        bank_only = [s for s in sources if s['account_group'] == 'Bank Accounts']
        self.assertEqual(len(bank_only), 1)

    def test_search_transactions(self):
        VoucherService.save_voucher(
            self.company_id, 'Receipt', date(2026, 8, 1),
            [
                {'account_id': self.acct['cash'], 'debit_amount': 2000.0, 'credit_amount': 0.0},
                {'account_id': self.acct['sales'], 'debit_amount': 0.0, 'credit_amount': 2000.0},
            ],
            reference_number='SEARCH-ME',
        )
        report = cash_book_service.generate_cash_book(
            self.company_id, date(2026, 8, 1), date(2026, 8, 31))
        filtered = cash_book_service.search_transactions(report, 'SEARCH')
        self.assertEqual(filtered['transaction_count'], 1)
        filtered2 = cash_book_service.search_transactions(report, 'nonexistent')
        self.assertEqual(filtered2['transaction_count'], 0)


if __name__ == '__main__':
    unittest.main()
