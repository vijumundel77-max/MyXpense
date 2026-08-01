"""
Unit Tests for Party Ledger Service
Tests party ledger generation and related functionality
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal
from services.party_ledger_service import party_ledger_service
from services.account_service import account_service
from services.voucher_service import voucher_service
from database.database import db
import config


class TestPartyLedgerService(unittest.TestCase):
    """Test cases for Party Ledger Service"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and data"""
        # Use test database
        config.DATABASE_PATH = ':memory:'
        db.initialize_database()
        
        # Create test company
        cls.company_id = 1
        db.execute("""
            INSERT INTO companies (id, name, financial_year_start, financial_year_end)
            VALUES (?, ?, ?, ?)
        """, (cls.company_id, 'Test Company', '2026-04-01', '2027-03-31'))
        
        # Create test accounts
        cls.debtor_id = account_service.create_account(
            cls.company_id,
            'Customer A',
            'CUST001',
            'Sundry Debtors',
            1000.0,
            'Debit'
        )
        
        cls.creditor_id = account_service.create_account(
            cls.company_id,
            'Supplier B',
            'SUPP001',
            'Sundry Creditors',
            500.0,
            'Credit'
        )
        
        cls.sales_id = account_service.create_account(
            cls.company_id,
            'Sales',
            'SAL001',
            'Sales',
            0.0,
            'Credit'
        )
        
        cls.purchase_id = account_service.create_account(
            cls.company_id,
            'Purchases',
            'PUR001',
            'Purchases',
            0.0,
            'Debit'
        )
        
        cls.cash_id = account_service.create_account(
            cls.company_id,
            'Cash',
            'CASH001',
            'Cash',
            10000.0,
            'Debit'
        )
    
    def setUp(self):
        """Set up before each test"""
        # Clear vouchers
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
    
    def test_get_party_accounts_debtors(self):
        """Test getting debtor accounts"""
        accounts = party_ledger_service._get_party_accounts(self.company_id, 'Debtor')
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) > 0)
        
        # Check if debtor account is in the list
        debtor_codes = [acc['code'] for acc in accounts]
        self.assertIn('CUST001', debtor_codes)
    
    def test_get_party_accounts_creditors(self):
        """Test getting creditor accounts"""
        accounts = party_ledger_service._get_party_accounts(self.company_id, 'Creditor')
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) > 0)
        
        # Check if creditor account is in the list
        creditor_codes = [acc['code'] for acc in accounts]
        self.assertIn('SUPP001', creditor_codes)
    
    def test_get_party_accounts_all(self):
        """Test getting all party accounts"""
        accounts = party_ledger_service._get_party_accounts(self.company_id, 'All')
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) >= 2)
        
        # Check if both debtor and creditor are in the list
        codes = [acc['code'] for acc in accounts]
        self.assertIn('CUST001', codes)
        self.assertIn('SUPP001', codes)
    
    def test_calculate_opening_balance(self):
        """Test opening balance calculation"""
        # Create a sales invoice dated before the from_date
        past_date = date.today() - timedelta(days=30)
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            past_date,
            'INV001'
        )
        
        voucher_service.add_voucher_detail(
            voucher_id,
            self.debtor_id,
            5000.0,
            0.0,
            'Sale to Customer A'
        )
        
        voucher_service.add_voucher_detail(
            voucher_id,
            self.sales_id,
            0.0,
            5000.0,
            'Sale to Customer A'
        )
        
        voucher_service.post_voucher(voucher_id)
        
        # Calculate opening balance as of today
        account = account_service.get_account(self.debtor_id)
        opening_balance, opening_type = party_ledger_service._calculate_opening_balance(
            account, date.today()
        )
        
        # Opening balance should be 1000 (opening) + 5000 (invoice) = 6000 Debit
        self.assertEqual(opening_balance, 6000.0)
        self.assertEqual(opening_type, 'Debit')
    
    def test_get_party_transactions(self):
        """Test getting party transactions"""
        # Create transactions
        today = date.today()
        
        # Sales invoice
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV002'
        )
        
        voucher_service.add_voucher_detail(voucher_id1, self.debtor_id, 3000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 3000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Receipt
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Receipt',
            today,
            'REC001'
        )
        
        voucher_service.add_voucher_detail(voucher_id2, self.cash_id, 2000.0, 0.0, 'Payment received')
        voucher_service.add_voucher_detail(voucher_id2, self.debtor_id, 0.0, 2000.0, 'Payment received')
        voucher_service.post_voucher(voucher_id2)
        
        # Get transactions
        transactions = party_ledger_service._get_party_transactions(
            self.debtor_id,
            today,
            today
        )
        
        self.assertEqual(len(transactions), 2)
        
        # Check transaction details
        debit_txn = next(t for t in transactions if t['debit_amount'] > 0)
        credit_txn = next(t for t in transactions if t['credit_amount'] > 0)
        
        self.assertEqual(debit_txn['debit_amount'], 3000.0)
        self.assertEqual(credit_txn['credit_amount'], 2000.0)
    
    def test_generate_party_ledger_debtor(self):
        """Test generating party ledger for debtor"""
        # Create transactions
        today = date.today()
        from_date = today - timedelta(days=7)
        
        # Sales invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV003'
        )
        
        voucher_service.add_voucher_detail(voucher_id, self.debtor_id, 4000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 4000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Generate ledger
        ledger = party_ledger_service.generate_party_ledger(
            self.company_id,
            self.debtor_id,
            from_date,
            today
        )
        
        self.assertTrue(ledger['success'])
        self.assertEqual(ledger['report_type'], 'Party Ledger')
        self.assertIn('account', ledger)
        self.assertIn('transactions', ledger)
        self.assertIn('opening_balance', ledger)
        self.assertIn('closing_balance', ledger)
        
        # Check account details
        self.assertEqual(ledger['account']['id'], self.debtor_id)
        self.assertEqual(ledger['account']['name'], 'Customer A')
        
        # Check transactions
        self.assertTrue(len(ledger['transactions']) > 0)
        
        # Check closing balance
        self.assertGreater(ledger['closing_balance']['amount'], 0)
        self.assertEqual(ledger['closing_balance']['type'], 'Debit')
    
    def test_generate_party_ledger_creditor(self):
        """Test generating party ledger for creditor"""
        # Create transactions
        today = date.today()
        from_date = today - timedelta(days=7)
        
        # Purchase invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Purchase Invoice',
            today,
            'PINV001'
        )
        
        voucher_service.add_voucher_detail(voucher_id, self.purchase_id, 3000.0, 0.0, 'Purchase')
        voucher_service.add_voucher_detail(voucher_id, self.creditor_id, 0.0, 3000.0, 'Purchase')
        voucher_service.post_voucher(voucher_id)
        
        # Generate ledger
        ledger = party_ledger_service.generate_party_ledger(
            self.company_id,
            self.creditor_id,
            from_date,
            today
        )
        
        self.assertTrue(ledger['success'])
        self.assertEqual(ledger['account']['name'], 'Supplier B')
        
        # Check closing balance (should be credit for creditor)
        self.assertGreater(ledger['closing_balance']['amount'], 0)
        self.assertEqual(ledger['closing_balance']['type'], 'Credit')
    
    def test_generate_party_summary(self):
        """Test generating party summary"""
        # Create some transactions
        today = date.today()
        
        # Sales invoice
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV004'
        )
        
        voucher_service.add_voucher_detail(voucher_id1, self.debtor_id, 2000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 2000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Purchase invoice
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Purchase Invoice',
            today,
            'PINV002'
        )
        
        voucher_service.add_voucher_detail(voucher_id2, self.purchase_id, 1500.0, 0.0, 'Purchase')
        voucher_service.add_voucher_detail(voucher_id2, self.creditor_id, 0.0, 1500.0, 'Purchase')
        voucher_service.post_voucher(voucher_id2)
        
        # Generate summary for all parties
        summary = party_ledger_service.generate_party_summary(
            self.company_id,
            'All',
            today
        )
        
        self.assertTrue(summary['success'])
        self.assertEqual(summary['report_type'], 'Party Summary')
        self.assertIn('parties', summary)
        self.assertIn('totals', summary)
        
        # Check party count
        self.assertGreaterEqual(summary['party_count'], 2)
        
        # Check totals
        self.assertGreater(summary['totals']['net_receivable'], 0)
        self.assertGreater(summary['totals']['net_payable'], 0)
    
    def test_get_party_outstanding(self):
        """Test getting party outstanding balance"""
        today = date.today()
        
        # Create a sales invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV005'
        )
        
        voucher_service.add_voucher_detail(voucher_id, self.debtor_id, 5000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 5000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Get outstanding
        outstanding = party_ledger_service.get_party_outstanding(
            self.company_id,
            self.debtor_id,
            today
        )
        
        self.assertTrue(outstanding['success'])
        self.assertIn('outstanding_balance', outstanding)
        self.assertIn('balance_type', outstanding)
        self.assertTrue(outstanding['is_receivable'])
        self.assertFalse(outstanding['is_payable'])
        self.assertGreater(outstanding['outstanding_balance'], 0)
    
    def test_search_parties(self):
        """Test searching parties"""
        # Search for customer
        results = party_ledger_service.search_parties(
            self.company_id,
            'Debtor',
            'Customer'
        )
        
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # Check if search result contains the search term
        self.assertTrue(any('Customer' in r['name'] for r in results))
        
        # Search by code
        results = party_ledger_service.search_parties(
            self.company_id,
            'Debtor',
            'CUST001'
        )
        
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]['code'], 'CUST001')
    
    def test_export_party_ledger_to_csv(self):
        """Test exporting party ledger to CSV"""
        today = date.today()
        from_date = today - timedelta(days=7)
        
        # Generate ledger
        ledger = party_ledger_service.generate_party_ledger(
            self.company_id,
            self.debtor_id,
            from_date,
            today
        )
        
        # Export to CSV
        success, file_path = party_ledger_service.export_party_ledger_to_csv(
            ledger,
            'test_party_ledger'
        )
        
        self.assertTrue(success)
        self.assertIsInstance(file_path, str)
        self.assertTrue(file_path.endswith('.csv'))
    
    def test_export_party_summary_to_csv(self):
        """Test exporting party summary to CSV"""
        today = date.today()
        
        # Generate summary
        summary = party_ledger_service.generate_party_summary(
            self.company_id,
            'All',
            today
        )
        
        # Export to CSV
        success, file_path = party_ledger_service.export_party_summary_to_csv(
            summary,
            'test_party_summary'
        )
        
        self.assertTrue(success)
        self.assertIsInstance(file_path, str)
        self.assertTrue(file_path.endswith('.csv'))
    
    def test_invalid_account_id(self):
        """Test with invalid account ID"""
        today = date.today()
        from_date = today - timedelta(days=7)
        
        ledger = party_ledger_service.generate_party_ledger(
            self.company_id,
            99999,  # Invalid ID
            from_date,
            today
        )
        
        self.assertFalse(ledger['success'])
        self.assertIn('error', ledger)
    
    def test_running_balance_calculation(self):
        """Test running balance calculation in ledger"""
        today = date.today()
        from_date = today - timedelta(days=1)
        
        # Create multiple transactions
        # Invoice 1
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV006'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor_id, 1000.0, 0.0, 'Sale 1')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 1000.0, 'Sale 1')
        voucher_service.post_voucher(voucher_id1)
        
        # Receipt
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Receipt',
            today,
            'REC002'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.cash_id, 500.0, 0.0, 'Payment')
        voucher_service.add_voucher_detail(voucher_id2, self.debtor_id, 0.0, 500.0, 'Payment')
        voucher_service.post_voucher(voucher_id2)
        
        # Invoice 2
        voucher_id3 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV007'
        )
        voucher_service.add_voucher_detail(voucher_id3, self.debtor_id, 2000.0, 0.0, 'Sale 2')
        voucher_service.add_voucher_detail(voucher_id3, self.sales_id, 0.0, 2000.0, 'Sale 2')
        voucher_service.post_voucher(voucher_id3)
        
        # Generate ledger
        ledger = party_ledger_service.generate_party_ledger(
            self.company_id,
            self.debtor_id,
            from_date,
            today
        )
        
        self.assertTrue(ledger['success'])
        
        # Check that each transaction has a running balance
        transactions = ledger['transactions']
        self.assertTrue(all('running_balance' in t for t in transactions))
        self.assertTrue(all('balance_type' in t for t in transactions))
        
        # Check that running balance increases and decreases correctly
        # Opening: 1000, +1000 = 2000, -500 = 1500, +2000 = 3500
        self.assertGreater(ledger['closing_balance']['amount'], ledger['opening_balance']['amount'])


if __name__ == '__main__':
    unittest.main()
