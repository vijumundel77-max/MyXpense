# Party Ledger and Outstanding Reports

This document provides comprehensive information about the Party Ledger, Outstanding, and Ageing Reports modules in the Accounting System.

## Overview

The Party Reports module provides detailed analysis of transactions and outstanding balances for Sundry Debtors (Customers) and Sundry Creditors (Suppliers). It includes three main report types:

1. **Party Ledger Report** - Detailed transaction history for individual parties
2. **Outstanding Report** - Summary of outstanding receivables/payables with ageing
3. **Ageing Report** - Detailed ageing analysis with FIFO payment allocation

## Features

### Party Ledger Report

**Purpose:** Generate detailed ledger statements for individual customers or suppliers.

**Key Features:**
- Transaction-wise details with running balance
- Opening and closing balance calculation
- Debit/Credit segregation
- Date range filtering
- Party-wise summary view
- Export to CSV/JSON
- Outstanding balance check

**Service:** `services/party_ledger_service.py`
**UI:** `ui/party_ledger_report.py`

**Main Functions:**

```python
# Generate party ledger
ledger = party_ledger_service.generate_party_ledger(
    company_id=1,
    account_id=101,
    from_date=date(2026, 4, 1),
    to_date=date(2026, 7, 31)
)

# Generate party summary
summary = party_ledger_service.generate_party_summary(
    company_id=1,
    party_type='Debtor',  # 'Debtor', 'Creditor', or 'All'
    as_on_date=date(2026, 7, 31),
    from_date=date(2026, 4, 1)  # Optional
)

# Get outstanding balance
outstanding = party_ledger_service.get_party_outstanding(
    company_id=1,
    account_id=101,
    as_on_date=date(2026, 7, 31)
)

# Search parties
results = party_ledger_service.search_parties(
    company_id=1,
    party_type='Debtor',
    search_term='Customer'
)
```

**Report Structure:**

```python
{
    'success': True,
    'report_type': 'Party Ledger',
    'account': {
        'id': 101,
        'name': 'Customer A',
        'code': 'CUST001',
        'account_group': 'Sundry Debtors'
    },
    'from_date': '2026-04-01',
    'to_date': '2026-07-31',
    'opening_balance': {
        'amount': 5000.0,
        'type': 'Debit'
    },
    'transactions': [
        {
            'voucher_date': '2026-04-15',
            'voucher_number': 'INV001',
            'voucher_type': 'Sales Invoice',
            'reference_number': 'REF001',
            'debit_amount': 10000.0,
            'credit_amount': 0.0,
            'contra_account_name': 'Sales',
            'running_balance': 15000.0,
            'balance_type': 'Debit'
        }
    ],
    'totals': {
        'debit': 25000.0,
        'credit': 10000.0
    },
    'closing_balance': {
        'amount': 20000.0,
        'type': 'Debit'
    },
    'transaction_count': 15,
    'generated_at': '2026-07-31T22:48:00'
}
```

### Outstanding Report

**Purpose:** Analyze outstanding receivables/payables with ageing buckets.

**Key Features:**
- Outstanding balance calculation
- Ageing categorization (0-30, 31-60, 61-90, 91-180, 180+ days)
- Overdue invoice tracking
- Party-wise summary
- Invoice-level details
- Search and filter capabilities

**Service:** `services/outstanding_report_service.py`
**UI:** `ui/outstanding_report.py`

**Main Functions:**

```python
# Generate outstanding report
report = outstanding_report_service.generate_outstanding_report(
    company_id=1,
    outstanding_type='Receivable',  # 'Receivable', 'Payable', or 'All'
    as_on_date=date(2026, 7, 31),
    include_zero_balance=False
)

# Generate ageing summary
summary = outstanding_report_service.generate_ageing_summary(
    company_id=1,
    outstanding_type='Receivable',
    as_on_date=date(2026, 7, 31)
)

# Get overdue invoices
overdue = outstanding_report_service.get_overdue_invoices(
    company_id=1,
    outstanding_type='Receivable',
    as_on_date=date(2026, 7, 31)
)

# Search parties
filtered = outstanding_report_service.search_parties(
    outstanding_data=report,
    search_term='Customer A'
)
```

**Report Structure:**

```python
{
    'success': True,
    'report_type': 'Outstanding Report',
    'outstanding_type': 'Receivable',
    'as_on_date': '2026-07-31',
    'parties': [
        {
            'account_id': 101,
            'account_name': 'Customer A',
            'account_code': 'CUST001',
            'account_group': 'Sundry Debtors',
            'outstanding_balance': 15000.0,
            'balance_type': 'Debit',
            'is_receivable': True,
            'is_payable': False,
            'invoices': [
                {
                    'voucher_number': 'INV001',
                    'voucher_date': '2026-06-15',
                    'due_date': '2026-07-15',
                    'invoice_amount': 10000.0,
                    'outstanding_amount': 10000.0,
                    'ageing_days': 16,
                    'ageing_category': '0-30 days'
                }
            ],
            'invoice_count': 3
        }
    ],
    'totals': {
        'total_outstanding': 50000.0,
        'total_receivable': 50000.0,
        'total_payable': 0.0
    },
    'party_count': 5,
    'generated_at': '2026-07-31T22:48:00'
}
```

**Ageing Buckets:**

| Bucket | Days Range | Description |
|--------|------------|-------------|
| 0-30 days | 0-30 | Current/Recent |
| 31-60 days | 31-60 | Slightly overdue |
| 61-90 days | 61-90 | Overdue |
| 91-180 days | 91-180 | Seriously overdue |
| Above 180 days | 181+ | Long overdue |

### Ageing Report

**Purpose:** Detailed ageing analysis with FIFO payment allocation.

**Key Features:**
- FIFO (First In First Out) payment allocation
- Invoice-level ageing tracking
- Custom ageing buckets
- Party-wise ageing details
- Due date consideration
- Detailed invoice breakdown

**Service:** `services/ageing_report_service.py`
**UI:** `ui/ageing_report.py`

**Main Functions:**

```python
# Generate ageing report
report = ageing_report_service.generate_ageing_report(
    company_id=1,
    ageing_type='Receivable',  # 'Receivable' or 'Payable'
    as_on_date=date(2026, 7, 31),
    custom_buckets=None  # Optional custom buckets
)

# Generate ageing summary by party
summary = ageing_report_service.generate_ageing_summary_by_party(
    company_id=1,
    ageing_type='Receivable',
    as_on_date=date(2026, 7, 31)
)

# Get party ageing details
details = ageing_report_service.get_party_ageing_details(
    company_id=1,
    account_id=101,
    ageing_type='Receivable',
    as_on_date=date(2026, 7, 31)
)

# Custom buckets example
custom_buckets = [
    (0, 15, '0-15 days'),
    (16, 30, '16-30 days'),
    (31, 60, '31-60 days'),
    (61, 90, '61-90 days'),
    (91, 999, 'Above 90 days')
]
```

**Report Structure:**

```python
{
    'success': True,
    'report_type': 'Ageing Report',
    'ageing_type': 'Receivable',
    'as_on_date': '2026-07-31',
    'buckets': ['0-30 days', '31-60 days', '61-90 days', '91-180 days', 'Above 180 days'],
    'parties': [
        {
            'account_id': 101,
            'account_name': 'Customer A',
            'account_code': 'CUST001',
            'account_group': 'Sundry Debtors',
            'buckets': {
                '0-30 days': 5000.0,
                '31-60 days': 7000.0,
                '61-90 days': 3000.0,
                '91-180 days': 0.0,
                'Above 180 days': 0.0
            },
            'total': 15000.0,
            'invoices': [
                {
                    'voucher_number': 'INV001',
                    'voucher_date': '2026-06-15',
                    'due_date': '2026-07-15',
                    'outstanding_amount': 5000.0,
                    'ageing_days': 16,
                    'ageing_bucket': '0-30 days'
                }
            ],
            'invoice_count': 3
        }
    ],
    'totals': {
        '0-30 days': 20000.0,
        '31-60 days': 15000.0,
        '61-90 days': 10000.0,
        '91-180 days': 5000.0,
        'Above 180 days': 0.0
    },
    'grand_total': 50000.0,
    'party_count': 5,
    'generated_at': '2026-07-31T22:48:00'
}
```

## FIFO Payment Allocation

The ageing report uses FIFO (First In First Out) method to allocate payments to invoices:

**Algorithm:**
1. Sort invoices by date (oldest first)
2. Sort payments by date
3. Allocate each payment to oldest outstanding invoice first
4. Continue until payment is fully allocated or all invoices are paid
5. Calculate outstanding amount for each invoice

**Example:**

```
Invoices:
- INV001: 2026-06-01, Amount: 10,000
- INV002: 2026-06-15, Amount: 8,000
- INV003: 2026-07-01, Amount: 5,000

Payments:
- REC001: 2026-06-20, Amount: 7,000
- REC002: 2026-07-10, Amount: 6,000

Allocation:
1. REC001 (7,000) → INV001 (10,000)
   - INV001 outstanding: 3,000
   
2. REC002 (6,000) → INV001 (3,000) + INV002 (3,000)
   - INV001 outstanding: 0
   - INV002 outstanding: 5,000

Result:
- INV001: Fully paid
- INV002: 5,000 outstanding
- INV003: 5,000 outstanding (no payment allocated)
```

## UI Components

### Party Ledger Report UI

**Features:**
- Report type selection (Ledger/Summary)
- Party type filter (Debtors/Creditors/All)
- Party search and selection
- Date range selection
- Transaction display with running balance
- Opening/closing balance display
- Export options (CSV/JSON)
- Outstanding balance check

**Usage:**
```python
from ui.party_ledger_report import show_party_ledger_report

# Show in a frame
report_ui = show_party_ledger_report(parent_frame, company_id=1)
```

### Outstanding Report UI

**Features:**
- Report type selection (Outstanding/Ageing Summary/Overdue)
- Outstanding type filter (Receivable/Payable/All)
- As on date selection
- Zero balance inclusion option
- Party search functionality
- Double-click for invoice details
- Ageing bucket visualization
- Export options

**Usage:**
```python
from ui.outstanding_report import show_outstanding_report

# Show in a frame
report_ui = show_outstanding_report(parent_frame, company_id=1)
```

### Ageing Report UI

**Features:**
- Ageing type selection (Receivable/Payable)
- Custom ageing buckets option
- Party search functionality
- Bucket-wise breakdown
- Invoice-level details popup
- Export options
- Visual ageing summary

**Usage:**
```python
from ui.ageing_report import show_ageing_report

# Show in a frame
report_ui = show_ageing_report(parent_frame, company_id=1)
```

## Export Formats

### CSV Export

All reports can be exported to CSV format with proper formatting:

```python
# Party Ledger
success, file_path = party_ledger_service.export_party_ledger_to_csv(
    ledger_data,
    'party_ledger'
)

# Outstanding Report
success, file_path = outstanding_report_service.export_outstanding_report_to_csv(
    report_data,
    'outstanding_report'
)

# Ageing Report
success, file_path = ageing_report_service.export_ageing_report_to_csv(
    report_data,
    'ageing_report'
)
```

### JSON Export

All reports support JSON export for data integration:

```python
# Any report
success, file_path = service.export_to_json(
    report_data,
    'report_name'
)
```

## Testing

Comprehensive unit tests are provided:

```bash
# Test Party Ledger Service
python -m pytest tests/test_party_ledger_service.py -v

# Test Outstanding Report Service
python -m pytest tests/test_outstanding_report_service.py -v

# Test Ageing Report Service
python -m pytest tests/test_ageing_report_service.py -v

# Run all party report tests
python -m pytest tests/test_*_service.py -v -k "party or outstanding or ageing"
```

## Configuration

### Date Format

```python
# config.py
DISPLAY_DATE_FORMAT = '%d-%m-%Y'  # DD-MM-YYYY
DATABASE_DATE_FORMAT = '%Y-%m-%d'  # YYYY-MM-DD
```

### Export Directory

```python
# config.py
EXPORTS_DIR = Path('exports')
```

### Ageing Buckets

Default buckets can be customized in the service:

```python
# services/ageing_report_service.py
DEFAULT_BUCKETS = [
    (0, 30, '0-30 days'),
    (31, 60, '31-60 days'),
    (61, 90, '61-90 days'),
    (91, 180, '91-180 days'),
    (181, 99999, 'Above 180 days')
]
```

## Best Practices

### Performance Optimization

1. **Use date ranges wisely** - Limit date ranges for large datasets
2. **Index database columns** - Ensure proper indexing on voucher_date and account_id
3. **Cache results** - Cache frequently accessed reports
4. **Batch processing** - Use batch operations for multiple parties

### Data Accuracy

1. **Post vouchers** - Ensure all vouchers are posted before generating reports
2. **Reconcile regularly** - Regular reconciliation with party statements
3. **Verify opening balances** - Ensure accurate opening balances
4. **Check due dates** - Maintain accurate due dates for ageing analysis

### User Experience

1. **Provide search** - Enable quick party search
2. **Show progress** - Display progress for long-running reports
3. **Export options** - Provide multiple export formats
4. **Drill-down** - Allow drill-down to invoice details

## Common Use Cases

### 1. Monthly Customer Statement

```python
# Generate statement for a customer
ledger = party_ledger_service.generate_party_ledger(
    company_id=1,
    account_id=customer_id,
    from_date=date(2026, 7, 1),
    to_date=date(2026, 7, 31)
)

# Export to CSV for emailing
success, file_path = party_ledger_service.export_party_ledger_to_csv(
    ledger,
    f'statement_{customer_code}'
)
```

### 2. Receivables Ageing Analysis

```python
# Generate ageing report
report = ageing_report_service.generate_ageing_report(
    company_id=1,
    ageing_type='Receivable',
    as_on_date=date.today()
)

# Identify high-risk customers
high_risk = [
    party for party in report['parties']
    if party['buckets']['Above 180 days'] > 10000
]
```

### 3. Overdue Follow-up

```python
# Get overdue invoices
overdue = outstanding_report_service.get_overdue_invoices(
    company_id=1,
    outstanding_type='Receivable',
    as_on_date=date.today()
)

# Generate follow-up list
for party in overdue['parties']:
    for invoice in party['invoices']:
        if invoice['overdue_days'] > 30:
            print(f"Follow up: {party['account_name']} - {invoice['voucher_number']}")
```

### 4. Cash Flow Forecasting

```python
# Get outstanding by ageing
summary = outstanding_report_service.generate_ageing_summary(
    company_id=1,
    outstanding_type='Receivable',
    as_on_date=date.today()
)

# Estimate collections
buckets = summary['ageing_buckets']
estimated_collections = (
    buckets['0-30 days'] * 0.95 +
    buckets['31-60 days'] * 0.80 +
    buckets['61-90 days'] * 0.60
)
```

## Troubleshooting

### Issue: Incorrect Outstanding Balance

**Solution:**
- Verify all vouchers are posted
- Check opening balances
- Ensure proper debit/credit entries
- Reconcile with general ledger

### Issue: Ageing Not Matching

**Solution:**
- Verify due dates are set correctly
- Check FIFO allocation logic
- Ensure payment vouchers are properly linked
- Verify as_on_date parameter

### Issue: Performance Issues

**Solution:**
- Add database indexes
- Limit date ranges
- Use pagination for large datasets
- Optimize queries

## API Reference

See individual service files for complete API documentation:
- `services/party_ledger_service.py`
- `services/outstanding_report_service.py`
- `services/ageing_report_service.py`

## Version History

- **v1.0** - Initial release with Party Ledger, Outstanding, and Ageing Reports
- Date: July 30, 2026

## Support

For issues or questions, please refer to the main README.md or contact the development team.
