"""
Outstanding Report Service
Service for generating outstanding receivables/payables reports with ageing analysis
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.party_ledger_service import PartyLedgerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OutstandingReportService:
    """Service for Outstanding Reports"""

    OUTSTANDING_TYPE_RECEIVABLE = 'Receivable'
    OUTSTANDING_TYPE_PAYABLE = 'Payable'
    OUTSTANDING_TYPE_ALL = 'All'

    RECEIVABLE_GROUPS = PartyLedgerService.DEBTOR_GROUPS
    PAYABLE_GROUPS = PartyLedgerService.CREDITOR_GROUPS

    @staticmethod
    def _round_amount(value: float) -> float:
        return round(float(value or 0.0), 2)

    @staticmethod
    def _row_value(row: Any, key: str, default: Any = None) -> Any:
        if row is None:
            return default
        try:
            return row[key]
        except Exception:
            try:
                return row.get(key, default)  # type: ignore[attr-defined]
            except Exception:
                return default

    @staticmethod
    def _get_party_accounts(company_id: int, outstanding_type: str) -> List[Dict[str, Any]]:
        if outstanding_type == OutstandingReportService.OUTSTANDING_TYPE_RECEIVABLE:
            party_type = PartyLedgerService.PARTY_TYPE_DEBTOR
        elif outstanding_type == OutstandingReportService.OUTSTANDING_TYPE_PAYABLE:
            party_type = PartyLedgerService.PARTY_TYPE_CREDITOR
        else:
            party_type = PartyLedgerService.PARTY_TYPE_ALL
        return PartyLedgerService._get_party_accounts(company_id, party_type)

    @staticmethod
    def _calculate_outstanding_balance(account_id: int, as_on_date: date, company_id: int = 1) -> Tuple[float, str]:
        try:
            account = next((item for item in PartyLedgerService._get_party_accounts(company_id, PartyLedgerService.PARTY_TYPE_ALL) if item['id'] == account_id), None)
            if not account:
                columns = PartyLedgerService._table_columns('parties')
                id_col = PartyLedgerService._pick_column(columns, ['id'])
                opening_col = PartyLedgerService._pick_column(columns, ['opening_balance', 'balance', 'opening_amount'])
                balance_type_col = PartyLedgerService._pick_column(columns, ['opening_balance_type', 'balance_type', 'opening_type'])
                if id_col:
                    row = db.fetch_one(
                        f"SELECT {', '.join([c for c in [id_col, opening_col, balance_type_col] if c])} FROM parties WHERE {id_col} = ?",
                        (account_id,),
                    )
                    if row:
                        account = {
                            'id': account_id,
                            'opening_balance': float(PartyLedgerService._row_value(row, opening_col, 0.0) or 0.0) if opening_col else 0.0,
                            'opening_balance_type': PartyLedgerService._row_value(row, balance_type_col, 'Debit') if balance_type_col else 'Debit',
                        }
            if not account:
                account = {'id': account_id, 'opening_balance': 0.0, 'opening_balance_type': 'Debit'}
            opening_balance, opening_type = PartyLedgerService._calculate_opening_balance(account, date(1900, 1, 1))
            transactions = PartyLedgerService._get_party_transactions(account_id, date(1900, 1, 1), as_on_date)
            return PartyLedgerService._calculate_closing_balance(opening_balance, opening_type, transactions)
        except Exception as e:
            logger.error(f"Error calculating outstanding balance: {e}")
            return 0.0, 'Debit'

    @staticmethod
    def _get_outstanding_invoices(account_id: int, as_on_date: date) -> List[Dict[str, Any]]:
        try:
            from services.ageing_report_service import AgeingReportService

            transactions = PartyLedgerService._get_party_transactions(account_id, date(1900, 1, 1), as_on_date)
            invoices: List[Dict[str, Any]] = []
            payments: List[Dict[str, Any]] = []
            total_debit = 0.0
            total_credit = 0.0
            for txn in transactions:
                debit_amount = float(txn.get('debit_amount', 0.0) or 0.0)
                credit_amount = float(txn.get('credit_amount', 0.0) or 0.0)
                total_debit += debit_amount
                total_credit += credit_amount

                voucher_date = txn.get('voucher_date')
                if hasattr(voucher_date, 'isoformat'):
                    voucher_date = voucher_date.isoformat()
                due_date = txn.get('due_date')
                if hasattr(due_date, 'isoformat'):
                    due_date = due_date.isoformat()
                voucher_date = PartyLedgerService._parse_date(voucher_date)
                due_date = PartyLedgerService._parse_date(due_date) if due_date else None

                entry = {
                    'voucher_id': txn.get('voucher_id'),
                    'voucher_number': txn.get('voucher_number', ''),
                    'voucher_type': txn.get('voucher_type', ''),
                    'voucher_date': voucher_date,
                    'reference_number': txn.get('reference_number', ''),
                    'due_date': due_date,
                    'net_amount': debit_amount - credit_amount,
                    'is_debit': debit_amount > credit_amount,
                }
                # For debtors (net debit) the invoice side is debit; for
                # creditors (net credit) the invoice side is credit.
                if total_debit >= total_credit:
                    if debit_amount > credit_amount:
                        invoices.append(entry)
                    elif credit_amount > debit_amount:
                        payments.append(entry)
                else:
                    if credit_amount > debit_amount:
                        invoices.append(entry)
                    elif debit_amount > credit_amount:
                        payments.append(entry)

            netted = AgeingReportService._allocate_payments_fifo_shared(invoices, payments)
            for inv in netted:
                inv['invoice_amount'] = inv['outstanding_amount']
            return netted
        except Exception as e:
            logger.error(f"Error getting outstanding invoices: {e}")
            return []

    @staticmethod
    def _calculate_ageing_days(invoice_date: date, as_on_date: date, due_date: Optional[date] = None) -> int:
        try:
            reference_date = due_date if due_date else invoice_date
            delta = as_on_date - reference_date
            return max(0, delta.days)
        except Exception as e:
            logger.error(f"Error calculating ageing days: {e}")
            return 0

    @staticmethod
    def _categorize_ageing(days: int) -> str:
        if days <= 30:
            return '0-30 days'
        if days <= 60:
            return '31-60 days'
        if days <= 90:
            return '61-90 days'
        if days <= 180:
            return '91-180 days'
        return 'Above 180 days'

    @staticmethod
    def generate_outstanding_report(company_id: int, outstanding_type: str, as_on_date: date, include_zero_balance: bool = False) -> Dict[str, Any]:
        try:
            accounts = OutstandingReportService._get_party_accounts(company_id, outstanding_type)
            if not accounts:
                return {
                    'success': True,
                    'report_type': 'Outstanding Report',
                    'outstanding_type': outstanding_type,
                    'as_on_date': as_on_date.isoformat(),
                    'parties': [],
                    'totals': {'total_outstanding': 0.0, 'total_receivable': 0.0, 'total_payable': 0.0},
                    'party_count': 0,
                    'generated_at': datetime.now().isoformat(),
                }

            party_outstandings: List[Dict[str, Any]] = []
            total_receivable = 0.0
            total_payable = 0.0

            for account in accounts:
                opening_balance, opening_type = PartyLedgerService._calculate_opening_balance(account, date(1900, 1, 1))
                transactions = PartyLedgerService._get_party_transactions(account['id'], date(1900, 1, 1), as_on_date)
                outstanding_balance, balance_type = PartyLedgerService._calculate_closing_balance(opening_balance, opening_type, transactions)

                if not include_zero_balance and abs(outstanding_balance) < 0.01:
                    continue

                invoices = OutstandingReportService._get_outstanding_invoices(account['id'], as_on_date)
                for invoice in invoices:
                    voucher_date_raw = invoice.get('voucher_date')
                    due_date_raw = invoice.get('due_date')
                    voucher_date = datetime.fromisoformat(voucher_date_raw).date() if isinstance(voucher_date_raw, str) else voucher_date_raw
                    due_date = datetime.fromisoformat(due_date_raw).date() if isinstance(due_date_raw, str) else due_date_raw
                    ageing_days = OutstandingReportService._calculate_ageing_days(voucher_date, as_on_date, due_date)
                    invoice['ageing_days'] = ageing_days
                    invoice['ageing_category'] = OutstandingReportService._categorize_ageing(ageing_days)

                if balance_type == 'Debit':
                    total_receivable += outstanding_balance
                else:
                    total_payable += outstanding_balance

                party_outstandings.append({
                    'account_id': account['id'],
                    'account_name': account['name'],
                    'account_code': account['code'],
                    'account_group': account['account_group'],
                    'outstanding_balance': outstanding_balance,
                    'balance_type': balance_type,
                    'is_receivable': balance_type == 'Debit',
                    'is_payable': balance_type == 'Credit',
                    'invoices': invoices,
                    'invoice_count': len(invoices),
                })

            total_outstanding = total_receivable + total_payable
            return {
                'success': True,
                'report_type': 'Outstanding Report',
                'outstanding_type': outstanding_type,
                'as_on_date': as_on_date.isoformat(),
                'parties': party_outstandings,
                'totals': {
                    'total_outstanding': OutstandingReportService._round_amount(total_outstanding),
                    'total_receivable': OutstandingReportService._round_amount(total_receivable),
                    'total_payable': OutstandingReportService._round_amount(total_payable),
                },
                'party_count': len(party_outstandings),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating outstanding report: {e}")
            return {'success': False, 'error': f"Failed to generate outstanding report: {str(e)}"}

    @staticmethod
    def generate_ageing_summary(company_id: int, outstanding_type: str, as_on_date: date) -> Dict[str, Any]:
        try:
            outstanding_report = OutstandingReportService.generate_outstanding_report(company_id, outstanding_type, as_on_date, False)
            if not outstanding_report.get('success'):
                return outstanding_report

            ageing_buckets = {'0-30 days': 0.0, '31-60 days': 0.0, '61-90 days': 0.0, '91-180 days': 0.0, 'Above 180 days': 0.0}
            for party in outstanding_report.get('parties', []):
                for invoice in party.get('invoices', []):
                    category = invoice.get('ageing_category', '0-30 days')
                    ageing_buckets[category] += float(invoice.get('outstanding_amount', 0.0) or 0.0)

            for category in ageing_buckets:
                ageing_buckets[category] = OutstandingReportService._round_amount(ageing_buckets[category])

            return {
                'success': True,
                'report_type': 'Ageing Summary',
                'outstanding_type': outstanding_type,
                'as_on_date': as_on_date.isoformat(),
                'ageing_buckets': ageing_buckets,
                'total_outstanding': outstanding_report.get('totals', {}).get('total_outstanding', 0.0),
                'party_count': outstanding_report.get('party_count', 0),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating ageing summary: {e}")
            return {'success': False, 'error': f"Failed to generate ageing summary: {str(e)}"}

    @staticmethod
    def get_overdue_invoices(company_id: int, outstanding_type: str, as_on_date: date) -> Dict[str, Any]:
        try:
            outstanding_report = OutstandingReportService.generate_outstanding_report(company_id, outstanding_type, as_on_date, False)
            if not outstanding_report.get('success'):
                return outstanding_report

            overdue_invoices: List[Dict[str, Any]] = []
            total_overdue = 0.0

            for party in outstanding_report.get('parties', []):
                party_overdue = []
                for invoice in party.get('invoices', []):
                    due_date_raw = invoice.get('due_date')
                    due_date = datetime.fromisoformat(due_date_raw).date() if isinstance(due_date_raw, str) else due_date_raw
                    if due_date and due_date < as_on_date:
                        overdue_days = (as_on_date - due_date).days
                        invoice['overdue_days'] = overdue_days
                        party_overdue.append(invoice)
                        total_overdue += float(invoice.get('outstanding_amount', 0.0) or 0.0)

                if party_overdue:
                    overdue_invoices.append({
                        'account_id': party['account_id'],
                        'account_name': party['account_name'],
                        'account_code': party['account_code'],
                        'invoices': party_overdue,
                        'party_overdue_amount': sum(float(inv.get('outstanding_amount', 0.0) or 0.0) for inv in party_overdue),
                    })

            return {
                'success': True,
                'report_type': 'Overdue Invoices',
                'outstanding_type': outstanding_type,
                'as_on_date': as_on_date.isoformat(),
                'parties': overdue_invoices,
                'total_overdue': OutstandingReportService._round_amount(total_overdue),
                'party_count': len(overdue_invoices),
                'invoice_count': sum(len(p['invoices']) for p in overdue_invoices),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting overdue invoices: {e}")
            return {'success': False, 'error': f"Failed to get overdue invoices: {str(e)}"}

    @staticmethod
    def search_parties(outstanding_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        try:
            if not outstanding_data.get('success'):
                return outstanding_data

            search_lower = search_term.lower()
            filtered_parties = [
                party for party in outstanding_data.get('parties', [])
                if search_lower in str(party.get('account_name', '')).lower() or search_lower in str(party.get('account_code', '')).lower()
            ]

            total_receivable = sum(
                float(p.get('outstanding_balance', 0.0) or 0.0)
                for p in filtered_parties
                if p.get('is_receivable', False)
            )
            total_payable = sum(
                float(p.get('outstanding_balance', 0.0) or 0.0)
                for p in filtered_parties
                if p.get('is_payable', False)
            )

            filtered_data = outstanding_data.copy()
            filtered_data['parties'] = filtered_parties
            filtered_data['party_count'] = len(filtered_parties)
            filtered_data['totals'] = {
                'total_outstanding': OutstandingReportService._round_amount(total_receivable + total_payable),
                'total_receivable': OutstandingReportService._round_amount(total_receivable),
                'total_payable': OutstandingReportService._round_amount(total_payable),
            }
            return filtered_data
        except Exception as e:
            logger.error(f"Error searching parties: {e}")
            return outstanding_data

    @staticmethod
    def export_outstanding_report_to_csv(report_data: Dict[str, Any], filename: str = "outstanding_report") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Outstanding Report'])
                writer.writerow(['Type:', report_data.get('outstanding_type', '')])
                writer.writerow(['As On Date:', report_data.get('as_on_date', '')])
                writer.writerow([])
                writer.writerow(['Code', 'Name', 'Outstanding', 'Type', 'Invoices'])
                for party in report_data.get('parties', []):
                    writer.writerow([
                        party.get('account_code', ''),
                        party.get('account_name', ''),
                        f"{party.get('outstanding_balance', 0):,.2f}",
                        party.get('balance_type', ''),
                        party.get('invoice_count', 0),
                    ])
                writer.writerow([])
                totals = report_data.get('totals', {})
                writer.writerow(['Total Receivable:', f"{totals.get('total_receivable', 0):,.2f}"])
                writer.writerow(['Total Payable:', f"{totals.get('total_payable', 0):,.2f}"])
                writer.writerow(['Total Outstanding:', f"{totals.get('total_outstanding', 0):,.2f}"])

            return True, str(file_path)
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False, f"Export failed: {str(e)}"

    @staticmethod
    def export_to_json(data: Dict[str, Any], filename: str) -> Tuple[bool, str]:
        try:
            if not data.get('success'):
                return False, "Invalid data"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.json"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file, indent=2, default=str)
            return True, str(file_path)
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return False, f"Export failed: {str(e)}"


outstanding_report_service = OutstandingReportService()
