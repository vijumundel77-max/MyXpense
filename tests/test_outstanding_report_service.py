"""
Unit Tests for Outstanding Report Service
Tests outstanding report generation and ageing analysis
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal
from services.outstanding_report_service import outstanding_report_service
from services.account_service import account_service
from services.voucher_service import voucher_service
from database.database import db
import config


class TestOutstandingReportService(unittest.TestCase):
    """Test cases for Outstanding Report Service"""
    
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
            50000.0,
            'Debit'
        )
    
    def setUp(self):
        """Set up before each test"""
        # Clear vouchers
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
    
    def test_get_party_accounts_receivable(self):
        """Test getting receivable accounts"""
        accounts = outstanding_report_service._get_party_accounts(
            self.company_id,
            'Receivable'
        )
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) >= 2)
        
        # Check if debtor accounts are in the list
        codes = [acc['code'] for acc in accounts]
        self.assertIn('CUST001', codes)
        self.assertIn('CUST002', codes)
    
    def test_get_party_accounts_payable(self):
        """Test getting payable accounts"""
        accounts = outstanding_report_service._get_party_accounts(
            self.company_id,
            'Payable'
        )
        
        self.assertIsInstance(accounts, list)
        self.assertTrue(len(accounts) >= 1)
        
        # Check if creditor account is in the list
        codes = [acc['code'] for acc in accounts]
        self.assertIn('SUPP001', codes)
    
    def test_calculate_outstanding_balance(self):
        """Test calculating outstanding balance"""
        today = date.today()
        
        # Create a sales invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV001'
        )
        
        voucher_service.add_voucher_detail(
            voucher_id,
            self.debtor1_id,
            5000.0,
            0.0,
            'Sale'
        )
        
        voucher_service.add_voucher_detail(
            voucher_id,
            self.sales_id,
            0.0,
            5000.0,
            'Sale'
        )
        
        voucher_service.post_voucher(voucher_id)
        
        # Calculate outstanding
        outstanding, balance_type = outstanding_report_service._calculate_outstanding_balance(
            self.debtor1_id,
            today
        )
        
        self.assertEqual(outstanding, 5000.0)
        self.assertEqual(balance_type, 'Debit')
    
    def test_get_outstanding_invoices(self):
        """Test getting outstanding invoices"""
        today = date.today()
        due_date = today + timedelta(days=30)
        
        # Create invoice with due date
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV002',
            due_date=due_date
        )
        
        voucher_service.add_voucher_detail(
            voucher_id,
            self.debtor1_id,
            3000.0,
            0.0,
            'Sale'
        )
        
        voucher_service.add_voucher_detail(
            voucher_id,
            self.sales_id,
            0.0,
            3000.0,
            'Sale'
        )
        
        voucher_service.post_voucher(voucher_id)
        
        # Get outstanding invoices
        invoices = outstanding_report_service._get_outstanding_invoices(
            self.debtor1_id,
            today
        )
        
        self.assertTrue(len(invoices) > 0)
        
        # Check invoice details
        invoice = invoices[0]
        self.assertEqual(invoice['voucher_number'], 'INV002')
        self.assertEqual(invoice['invoice_amount'], 3000.0)
        self.assertEqual(invoice['due_date'], due_date)
    
    def test_calculate_ageing_days(self):
        """Test calculating ageing days"""
        invoice_date = date(2026, 7, 1)
        as_on_date = date(2026, 7, 31)
        
        days = outstanding_report_service._calculate_ageing_days(
            invoice_date,
            as_on_date
        )
        
        self.assertEqual(days, 30)
        
        # Test with due date
        due_date = date(2026, 7, 15)
        days = outstanding_report_service._calculate_ageing_days(
            invoice_date,
            as_on_date,
            due_date
        )
        
        self.assertEqual(days, 16)
    
    def test_categorize_ageing(self):
        """Test ageing categorization"""
        self.assertEqual(
            outstanding_report_service._categorize_ageing(15),
            '0-30 days'
        )
        
        self.assertEqual(
            outstanding_report_service._categorize_ageing(45),
            '31-60 days'
        )
        
        self.assertEqual(
            outstanding_report_service._categorize_ageing(75),
            '61-90 days'
        )
        
        self.assertEqual(
            outstanding_report_service._categorize_ageing(120),
            '91-180 days'
        )
        
        self.assertEqual(
            outstanding_report_service._categorize_ageing(200),
            'Above 180 days'
        )
    
    def test_generate_outstanding_report(self):
        """Test generating outstanding report"""
        today = date.today()
        
        # Create sales invoices for different customers
        # Customer A - Invoice 1
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=10),
            'INV003'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 4000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 4000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Customer B - Invoice 2
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=45),
            'INV004'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.debtor2_id, 6000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id2, self.sales_id, 0.0, 6000.0, 'Sale')
        voucher_service.post_voucher(voucher_id2)
        
        # Generate report
        report = outstanding_report_service.generate_outstanding_report(
            self.company_id,
            'Receivable',
            today,
            False
        )
        
        self.assertTrue(report['success'])
        self.assertEqual(report['report_type'], 'Outstanding Report')
        self.assertEqual(report['outstanding_type'], 'Receivable')
        self.assertIn('parties', report)
        self.assertIn('totals', report)
        
        # Check party count
        self.assertGreaterEqual(report['party_count'], 2)
        
        # Check totals
        self.assertGreater(report['totals']['total_receivable'], 0)
        self.assertEqual(report['totals']['total_payable'], 0.0)
    
    def test_generate_outstanding_report_with_zero_balance(self):
        """Test generating report with zero balance option"""
        today = date.today()
        
        # Create and fully pay an invoice
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV005'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 1000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 1000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Payment
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Receipt',
            today,
            'REC001'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.cash_id, 1000.0, 0.0, 'Payment')
        voucher_service.add_voucher_detail(voucher_id2, self.debtor1_id, 0.0, 1000.0, 'Payment')
        voucher_service.post_voucher(voucher_id2)
        
        # Generate report without zero balance
        report1 = outstanding_report_service.generate_outstanding_report(
            self.company_id,
            'Receivable',
            today,
            False
        )
        
        # Generate report with zero balance
        report2 = outstanding_report_service.generate_outstanding_report(
            self.company_id,
            'Receivable',
            today,
            True
        )
        
        # Report with zero balance should have more or equal parties
        self.assertGreaterEqual(report2['party_count'], report1['party_count'])
    
    def test_generate_ageing_summary(self):
        """Test generating ageing summary"""
        today = date.today()
        
        # Create invoices with different ages
        # Recent invoice (0-30 days)
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=15),
            'INV006'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 2000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 2000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Older invoice (31-60 days)
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=45),
            'INV007'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.debtor2_id, 3000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id2, self.sales_id, 0.0, 3000.0, 'Sale')
        voucher_service.post_voucher(voucher_id2)
        
        # Generate ageing summary
        summary = outstanding_report_service.generate_ageing_summary(
            self.company_id,
            'Receivable',
            today
        )
        
        self.assertTrue(summary['success'])
        self.assertEqual(summary['report_type'], 'Ageing Summary')
        self.assertIn('ageing_buckets', summary)
        
        # Check that buckets have values
        buckets = summary['ageing_buckets']
        self.assertGreater(buckets['0-30 days'], 0)
        self.assertGreater(buckets['31-60 days'], 0)
    
    def test_get_overdue_invoices(self):
        """Test getting overdue invoices"""
        today = date.today()
        
        # Create overdue invoice
        past_due_date = today - timedelta(days=10)
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today - timedelta(days=40),
            'INV008',
            due_date=past_due_date
        )
        voucher_service.add_voucher_detail(voucher_id, self.debtor1_id, 5000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 5000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Get overdue invoices
        overdue = outstanding_report_service.get_overdue_invoices(
            self.company_id,
            'Receivable',
            today
        )
        
        self.assertTrue(overdue['success'])
        self.assertEqual(overdue['report_type'], 'Overdue Invoices')
        self.assertGreater(overdue['invoice_count'], 0)
        self.assertGreater(overdue['total_overdue'], 0)
        
        # Check overdue details
        parties = overdue['parties']
        self.assertTrue(len(parties) > 0)
        
        party = parties[0]
        invoice = party['invoices'][0]
        self.assertIn('overdue_days', invoice)
        self.assertGreater(invoice['overdue_days'], 0)
    
    def test_search_parties(self):
        """Test searching parties in outstanding report"""
        today = date.today()
        
        # Create invoices
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV009'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 1000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 1000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV010'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.debtor2_id, 2000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id2, self.sales_id, 0.0, 2000.0, 'Sale')
        voucher_service.post_voucher(voucher_id2)
        
        # Generate report
        report = outstanding_report_service.generate_outstanding_report(
            self.company_id,
            'Receivable',
            today,
            False
        )
        
        # Search for Customer A
        filtered = outstanding_report_service.search_parties(report, 'Customer A')
        
        self.assertTrue(filtered['success'])
        self.assertEqual(filtered['party_count'], 1)
        self.assertEqual(filtered['parties'][0]['account_name'], 'Customer A')
    
    def test_export_outstanding_report_to_csv(self):
        """Test exporting outstanding report to CSV"""
        today = date.today()
        
        # Create invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV011'
        )
        voucher_service.add_voucher_detail(voucher_id, self.debtor1_id, 3000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id, self.sales_id, 0.0, 3000.0, 'Sale')
        voucher_service.post_voucher(voucher_id)
        
        # Generate report
        report = outstanding_report_service.generate_outstanding_report(
            self.company_id,
            'Receivable',
            today,
            False
        )
        
        # Export to CSV
        success, file_path = outstanding_report_service.export_outstanding_report_to_csv(
            report,
            'test_outstanding_report'
        )
        
        self.assertTrue(success)
        self.assertIsInstance(file_path, str)
        self.assertTrue(file_path.endswith('.csv'))
    
    def test_outstanding_with_partial_payment(self):
        """Test outstanding calculation with partial payment"""
        today = date.today()
        
        # Create invoice
        voucher_id1 = voucher_service.create_voucher(
            self.company_id,
            'Sales Invoice',
            today,
            'INV012'
        )
        voucher_service.add_voucher_detail(voucher_id1, self.debtor1_id, 10000.0, 0.0, 'Sale')
        voucher_service.add_voucher_detail(voucher_id1, self.sales_id, 0.0, 10000.0, 'Sale')
        voucher_service.post_voucher(voucher_id1)
        
        # Partial payment
        voucher_id2 = voucher_service.create_voucher(
            self.company_id,
            'Receipt',
            today,
            'REC002'
        )
        voucher_service.add_voucher_detail(voucher_id2, self.cash_id, 6000.0, 0.0, 'Payment')
        voucher_service.add_voucher_detail(voucher_id2, self.debtor1_id, 0.0, 6000.0, 'Payment')
        voucher_service.post_voucher(voucher_id2)
        
        # Calculate outstanding
        outstanding, balance_type = outstanding_report_service._calculate_outstanding_balance(
            self.debtor1_id,
            today
        )
        
        # Should be 10000 - 6000 = 4000
        self.assertEqual(outstanding, 4000.0)
        self.assertEqual(balance_type, 'Debit')
    
    def test_payable_outstanding(self):
        """Test outstanding for payables (creditors)"""
        today = date.today()
        
        # Create purchase invoice
        voucher_id = voucher_service.create_voucher(
            self.company_id,
            'Purchase Invoice',
            today,
            'PINV001'
        )
        voucher_service.add_voucher_detail(voucher_id, self.purchase_id, 8000.0, 0.0, 'Purchase')
        voucher_service.add_voucher_detail(voucher_id, self.creditor1_id, 0.0, 8000.0, 'Purchase')
        voucher_service.post_voucher(voucher_id)
        
        # Generate payable report
        report = outstanding_report_service.generate_outstanding_report(
            self.company_id,
            'Payable',
            today,
            False
        )
        
        self.assertTrue(report['success'])
        self.assertEqual(report['outstanding_type'], 'Payable')
        self.assertGreater(report['totals']['total_payable'], 0)
        self.assertEqual(report['totals']['total_receivable'], 0.0)


if __name__ == '__main__':
    unittest.main()
