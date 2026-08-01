"""
Unit Tests for Ageing Report Service
Tests detailed ageing analysis and FIFO allocation
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal
from services.ageing_report_service import ageing_report_service
from services.account_service import account_service
from services.voucher_service import voucher_service
from database.database import db
import config


class TestAgeingReportService(unittest.TestCase):
    """Test cases for Ageing Report Service"""
    
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
        cls.debtor1_id = account_service.create_account(
            cls.company_id,
            'Customer A',
            'CUST001',
            'Sundry Debtors',
            0.0,
            'Debit'
        )
        
        cls.debtor2_id = account_service.create_account(
            cls.company_id,
            'Customer B',
            'CUST002',
            'Sundry Debtors',
            0.0,
            'Debit'
        )
        
        cls.creditor1_id = account_service.create_account(
            cls.company_id,
            'Supplier X',
            'SUPP001',
            'Sundry Creditors',
            0.0,
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
            100000.0,
            'Debit'
        )
    
    def setUp(self):
        """Set up before each test"""
        # Clear vouchers
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
    
    def test_get_party_accounts_receivable(self):
        """Test getting receivable accounts"""
        accounts = ageing_report_service._get_party_accounts(
            self.company_id,
            'Receivable'
        )
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) >= 2)
        
        codes = [acc['code'] for acc in accounts]
        self.assertIn('CUST001', codes)
        self.assertIn('CUST002', codes)
    
    def test_get_party_accounts_payable(self):
        """Test getting payable accounts"""
        accounts = ageing_report_service._get_party_accounts(
            self.company_id,
            'Payable'
        )
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) >= 1)
        
        codes = [acc['code'] for acc in accounts]
        self.assertIn('SUPP001', codes)
    
    def test_get_invoice_transactions(self):
        """Test getting invoice transactions"""
        today = date.today()
        
        # Create sales invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV001'
        )
        voucher_service.add_voucher_detail(voucher_id, self.debtor1_id, 5000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 5000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Get transactions
        transactions = ageing_report_service._get_invoice_transactions(
            self.debtor1_id,
            today
        )
        
        self.assertTrue(len(transactions) > 0)
        
        # Check transaction details
        txn = transactions[0]
        self.assertEqual(txn['voucher_number'], 'INV001')
        self.assertEqual(txn['net_amount'], 5000.0)
        self.assertTrue(txn['is_invoice'])
        self.assertFalse(txn['is_payment'])
    
    def test_calculate_ageing_days(self):
        """Test calculating ageing days"""
        reference_date = date(2026, 7, 1)
        as_on_date = date(2026, 7, 31)
        
        days = ageing_report_service._calculate_ageing_days(reference_date, as_on_date)
        
        self.assertEqual(days, 30)
        
        # Test with same date
        days = ageing_report_service._calculate_ageing_days(as_on_date, as_on_date)
        self.assertEqual(days, 0)
    
    def test_get_bucket_name(self):
        """Test getting bucket name for days"""
        buckets = ageing_report_service.DEFAULT_BUCKETS
        
        self.assertEqual(
            ageing_report_service._get_bucket_name(15, buckets),
            '0-30 days'
        )
        
        self.assertEqual(
            ageing_report_service._get_bucket_name(45, buckets),
            '31-60 days'
        )
        
        self.assertEqual(
            ageing_report_service._get_bucket_name(75, buckets),
            '61-90 days'
        )
        
        self.assertEqual(
            ageing_report_service._get_bucket_name(120, buckets),
            '91-180 days'
        )
        
        self.assertEqual(
            ageing_report_service._get_bucket_name(200, buckets),
            'Above 180 days'
        )
    
    def test_allocate_payments_fifo_full_payment(self):
        """Test FIFO allocation with full payment"""
        today = date.today()
        
        # Create invoices
        invoices = [
            {
                'voucher_id': 1,
                'voucher_number': 'INV001',
                'voucher_date': today - timedelta(days=30),
                'net_amount': 5000.0,
                'is_invoice': True
            },
            {
                'voucher_id': 2,
                'voucher_number': 'INV002',
                'voucher_date': today - timedelta(days=15),
                'net_amount': 3000.0,
                'is_invoice': True
            }
        ]
        
        # Create payment
        payments = [
            {
                'voucher_id': 3,
                'voucher_number': 'REC001',
                'voucher_date': today,
                'net_amount': -5000.0,  # Negative for payment
                'is_payment': True
            }
        ]
        
        # Allocate
        outstanding = ageing_report_service._allocate_payments_fifo(invoices, payments)
        
        # First invoice should be fully paid, second should remain
        self.assertEqual(len(outstanding), 1)
        self.assertEqual(outstanding[0]['voucher_number'], 'INV002')
        self.assertEqual(outstanding[0]['outstanding_amount'], 3000.0)
    
    def test_allocate_payments_fifo_partial_payment(self):
        """Test FIFO allocation with partial payment"""
        today = date.today()
        
        # Create invoices
        invoices = [
            {
                'voucher_id': 1,
                'voucher_number': 'INV001',
                'voucher_date': today - timedelta(days=30),
                'net_amount': 5000.0,
                'is_invoice': True
            },
            {
                'voucher_id': 2,
                'voucher_number': 'INV002',
                'voucher_date': today - timedelta(days=15),
                'net_amount': 3000.0,
                'is_invoice': True
            }
        ]
        
        # Create partial payment
        payments = [
            {
                'voucher_id': 3,
                'voucher_number': 'REC001',
                'voucher_date': today,
                'net_amount': -3000.0,
                'is_payment': True
            }
        ]
        
        # Allocate
        outstanding = ageing_report_service._allocate_payments_fifo(invoices, payments)
        
        # First invoice should have 2000 outstanding, second should be fully outstanding
        self.assertEqual(len(outstanding), 2)
        self.assertEqual(outstanding[0]['outstanding_amount'], 2000.0)
        self.assertEqual(outstanding[1]['outstanding_amount'], 3000.0)
    
    def test_allocate_payments_fifo_multiple_payments(self):
        """Test FIFO allocation with multiple payments"""
        today = date.today()
        
        # Create invoices
        invoices = [
            {
                'voucher_id': 1,
                'voucher_number': 'INV001',
                'voucher_date': today - timedelta(days=60),
                'net_amount': 10000.0,
                'is_invoice': True
            },
            {
                'voucher_id': 2,
                'voucher_number': 'INV002',
                'voucher_date': today - timedelta(days=30),
                'net_amount': 8000.0,
                'is_invoice': True
            },
            {
                'voucher_id': 3,
                'voucher_number': 'INV003',
                'voucher_date': today - timedelta(days=15),
                'net_amount': 5000.0,
                'is_invoice': True
            }
        ]
        
        # Create multiple payments
        payments = [
            {
                'voucher_id': 4,
                'voucher_number': 'REC001',
                'voucher_date': today - timedelta(days=25),
                'net_amount': -7000.0,
                'is_payment': True
            },
            {
                'voucher_id': 5,
                'voucher_number': 'REC002',
                'voucher_date': today - timedelta(days=10),
                'net_amount': -6000.0,
                'is_payment': True
            }
        ]
        
        # Allocate
        outstanding = ageing_report_service._allocate_payments_fifo(invoices, payments)
        
        # Total payments: 13000
        # INV001 (10000) - fully paid
        # INV002 (8000) - 3000 paid, 5000 outstanding
        # INV003 (5000) - fully outstanding
        self.assertEqual(len(outstanding), 2)
        
        inv002 = next(inv for inv in outstanding if inv['voucher_number'] == 'INV002')
        inv003 = next(inv for inv in outstanding if inv['voucher_number'] == 'INV003')
        
        self.assertEqual(inv002['outstanding_amount'], 5000.0)
        self.assertEqual(inv003['outstanding_amount'], 5000.0)
    
    def test_generate_ageing_report(self):
        """Test generating ageing report"""
        today = date.today()
        
        # Create invoices with different ages
        # Invoice 1 - 20 days old (0-30 bucket)
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=20),
            'INV001'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 5000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 5000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Invoice 2 - 45 days old (31-60 bucket)
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=45),
            'INV002'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.debtor1_id, 7000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id2, self.sales_id, 0.0, 7000.0, 'Sale')
        voucher_service.post_voucher(voucher_id2)
        
        # Invoice 3 - 75 days old (61-90 bucket)
        voucher_id3 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=75),
            'INV003'
        )
        voucher_service.add_voucher_detail(voucher_id3, self.debtor2_id, 3000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id3, self.sales_id, 0.0, 3000.0, 'Sale')
        voucher_service.post_voucher(voucher_id3)
        
        # Generate report
        report = ageing_report_service.generate_ageing_report(
            self.company_id,
            'Receivable',
            today
        )
        
        self.assertTrue(report['success'])
        self.assertEqual(report['report_type'], 'Ageing Report')
        self.assertEqual(report['ageing_type'], 'Receivable')
        self.assertIn('buckets', report)
        self.assertIn('parties', report)
        self.assertIn('totals', report)
        
        # Check buckets
        self.assertEqual(len(report['buckets']), 5)
        
        # Check totals
        totals = report['totals']
        self.assertGreater(totals['0-30 days'], 0)
        self.assertGreater(totals['31-60 days'], 0)
        self.assertGreater(totals['61-90 days'], 0)
        
        # Check grand total
        self.assertEqual(report['grand_total'], 15000.0)
    
    def test_generate_ageing_report_with_custom_buckets(self):
        """Test generating ageing report with custom buckets"""
        today = date.today()
        
        # Create invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=25),
            'INV004'
        )
        voucher_service.add_voucher_detail(voucher_id, self.debtor1_id, 4000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 4000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Custom buckets: 0-15, 16-45, 46-90, 91-999
        custom_buckets = [
            (0, 15, '0-15 days'),
            (16, 45, '16-45 days'),
            (46, 90, '46-90 days'),
            (91, 999, 'Above 90 days')
        ]
        
        # Generate report
        report = ageing_report_service.generate_ageing_report(
            self.company_id,
            'Receivable',
            today,
            custom_buckets
        )
        
        self.assertTrue(report['success'])
        self.assertEqual(len(report['buckets']), 4)
        
        # Invoice should be in 16-45 days bucket
        totals = report['totals']
        self.assertGreater(totals['16-45 days'], 0)
    
    def test_generate_ageing_summary_by_party(self):
        """Test generating ageing summary by party"""
        today = date.today()
        
        # Create invoices
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=30),
            'INV005'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 6000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 6000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Generate summary
        summary = ageing_report_service.generate_ageing_summary_by_party(
            self.company_id,
            'Receivable',
            today
        )
        
        self.assertTrue(summary['success'])
        self.assertEqual(summary['report_type'], 'Ageing Summary by Party')
        self.assertIn('parties', summary)
        self.assertIn('totals', summary)
        
        # Check party details
        parties = summary['parties']
        self.assertTrue(len(parties) > 0)
        
        party = parties[0]
        self.assertIn('account_code', party)
        self.assertIn('account_name', party)
        self.assertIn('buckets', party)
        self.assertIn('total', party)
    
    def test_get_party_ageing_details(self):
        """Test getting party ageing details"""
        today = date.today()
        
        # Create multiple invoices for one party
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=10),
            'INV006'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 2000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 2000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=50),
            'INV007'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.debtor1_id, 3500.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id2, self.sales_id, 0.0, 3500.0, 'Sale')
        voucher_service.post_voucher(voucher_id2)
        
        # Get party details
        details = ageing_report_service.get_party_ageing_details(
            self.company_id,
            self.debtor1_id,
            'Receivable',
            today
        )
        
        self.assertTrue(details['success'])
        self.assertEqual(details['report_type'], 'Party Ageing Details')
        self.assertIn('account', details)
        self.assertIn('buckets', details)
        self.assertIn('invoices', details)
        
        # Check account
        self.assertEqual(details['account']['name'], 'Customer A')
        
        # Check invoices
        self.assertEqual(details['invoice_count'], 2)
        
        # Check buckets
        buckets = details['buckets']
        self.assertGreater(buckets['0-30 days'], 0)
        self.assertGreater(buckets['31-60 days'], 0)
        
        # Check total
        self.assertEqual(details['total'], 5500.0)
    
    def test_search_parties(self):
        """Test searching parties in ageing report"""
        today = date.today()
        
        # Create invoices for different parties
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV008'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 1000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 1000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV009'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.debtor2_id, 2000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id2, self.sales_id, 0.0, 2000.0, 'Sale')
        voucher_service.post_voucher(voucher_id2)
        
        # Generate report
        report = ageing_report_service.generate_ageing_report(
            self.company_id,
            'Receivable',
            today
        )
        
        # Search for Customer A
        filtered = ageing_report_service.search_parties(report, 'Customer A')
        
        self.assertTrue(filtered['success'])
        self.assertEqual(filtered['party_count'], 1)
        self.assertEqual(filtered['parties'][0]['account_name'], 'Customer A')
        
        # Search by code
        filtered = ageing_report_service.search_parties(report, 'CUST002')
        
        self.assertEqual(filtered['party_count'], 1)
        self.assertEqual(filtered['parties'][0]['account_code'], 'CUST002')
    
    def test_export_ageing_report_to_csv(self):
        """Test exporting ageing report to CSV"""
        today = date.today()
        
        # Create invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=30),
            'INV010'
        )
        voucher_service.add_voucher_detail(voucher_id, self.debtor1_id, 4000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 4000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Generate report
        report = ageing_report_service.generate_ageing_report(
            self.company_id,
            'Receivable',
            today
        )
        
        # Export to CSV
        success, file_path = ageing_report_service.export_ageing_report_to_csv(
            report,
            'test_ageing_report'
        )
        
        self.assertTrue(success)
        self.assertIsInstance(file_path, str)
        self.assertTrue(file_path.endswith('.csv'))
    
    def test_ageing_with_due_date(self):
        """Test ageing calculation using due date"""
        today = date.today()
        invoice_date = today - timedelta(days=60)
        due_date = today - timedelta(days=30)
        
        # Create invoice with due date
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            invoice_date,
            'INV011',
            due_date=due_date
        )
        voucher_service.add_voucher_detail(voucher_id, self.debtor1_id, 5000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 5000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Generate report
        report = ageing_report_service.generate_ageing_report(
            self.company_id,
            'Receivable',
            today
        )
        
        # Invoice should be aged from due_date, not invoice_date
        # 30 days from due_date, should be in 0-30 days bucket
        parties = report['parties']
        party = next(p for p in parties if p['account_id'] == self.debtor1_id)
        
        invoices = party['invoices']
        invoice = invoices[0]
        
        self.assertEqual(invoice['ageing_days'], 30)
        self.assertEqual(invoice['ageing_bucket'], '0-30 days')
    
    def test_payable_ageing_report(self):
        """Test ageing report for payables"""
        today = date.today()
        
        # Create purchase invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Purchase Invoice',
            today - timedelta(days=40),
            'PINV001'
        )
        voucher_service.add_voucher_detail(voucher_id, self.purchase_id, 8000.0, 0.0, 'Purchase')
        voucher_service.add_voucher_detail(voucher_id, self.creditor1_id, 0.0, 8000.0, 'Purchase')
        voucher_service.post_voucher(voucher_id)
        
        # Generate payable ageing report
        report = ageing_report_service.generate_ageing_report(
            self.company_id,
            'Payable',
            today
        )
        
        self.assertTrue(report['success'])
        self.assertEqual(report['ageing_type'], 'Payable')
        self.assertGreater(report['grand_total'], 0)
        
        # Check that creditor is in the report
        parties = report['parties']
        creditor = next((p for p in parties if p['account_code'] == 'SUPP001'), None)
        
        self.assertIsNotNone(creditor)
        self.assertEqual(creditor['account_name'], 'Supplier X')


if __name__ == '__main__':
    unittest.main()
