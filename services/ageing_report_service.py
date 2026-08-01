"""
Ageing Report Service
Service for generating detailed ageing analysis reports for receivables/payables
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from services.outstanding_report_service import OutstandingReportService
from services.party_ledger_service import PartyLedgerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgeingReportService:
    """Service for Ageing Reports"""

    AGEING_TYPE_RECEIVABLE = 'Receivable'
    AGEING_TYPE_PAYABLE = 'Payable'

    RECEIVABLE_GROUPS = PartyLedgerService.DEBTOR_GROUPS
    PAYABLE_GROUPS = PartyLedgerService.CREDITOR_GROUPS

    DEFAULT_BUCKETS = [
        (0, 30, '0-30 days'),
        (31, 60, '31-60 days'),
        (61, 90, '61-90 days'),
        (91, 180, '91-180 days'),
        (181, 99999, 'Above 180 days'),
    ]

    @staticmethod
    def _round_amount(value: float) -> float:
        return round(float(value or 0.0), 2)

    @staticmethod
    def _bucket_names(buckets: List[Tuple[int, int, str]]) -> List[str]:
        return [bucket[2] for bucket in buckets]

    @staticmethod
    def _get_bucket_name(days: int, buckets: List[Tuple[int, int, str]]) -> str:
        for min_days, max_days, name in buckets:
            if min_days <= days <= max_days:
                return name
        return buckets[-1][2]

    @staticmethod
    def _calculate_ageing_days(reference_date: date, as_on_date: date) -> int:
        try:
            return max(0, (as_on_date - reference_date).days)
        except Exception as e:
            logger.error(f"Error calculating ageing days: {e}")
            return 0

    @staticmethod
    def _get_party_accounts(company_id: int, ageing_type: str) -> List[Dict[str, Any]]:
        if ageing_type == AgeingReportService.AGEING_TYPE_RECEIVABLE:
            party_type = PartyLedgerService.PARTY_TYPE_DEBTOR
        else:
            party_type = PartyLedgerService.PARTY_TYPE_CREDITOR
        return PartyLedgerService._get_party_accounts(company_id, party_type)

    @staticmethod
    def _get_invoice_transactions(account_id: int, as_on_date: date) -> List[Dict[str, Any]]:
        try:
            transactions = PartyLedgerService._get_party_transactions(account_id, date(1900, 1, 1), as_on_date)
            filtered: List[Dict[str, Any]] = []
            for txn in transactions:
                debit = float(txn.get('debit_amount', 0.0) or 0.0)
                credit = float(txn.get('credit_amount', 0.0) or 0.0)
                net_amount = debit - credit
                if abs(net_amount) <= 0.01:
                    continue
                voucher_date = txn.get('voucher_date')
                due_date = txn.get('due_date')
                if hasattr(voucher_date, 'isoformat'):
                    voucher_date = voucher_date.isoformat()
                if hasattr(due_date, 'isoformat'):
                    due_date = due_date.isoformat()
                filtered.append({
                    'voucher_id': txn.get('voucher_id'),
                    'voucher_number': txn.get('voucher_number', ''),
                    'voucher_type': txn.get('voucher_type', ''),
                    'voucher_date': voucher_date,
                    'reference_number': txn.get('reference_number', ''),
                    'due_date': due_date,
                    'debit_amount': debit,
                    'credit_amount': credit,
                    'net_amount': net_amount,
                    'is_invoice': net_amount > 0,
                    'is_payment': net_amount < 0,
                })
            return filtered
        except Exception as e:
            logger.error(f"Error getting invoice transactions: {e}")
            return []

    @staticmethod
    def _allocate_payments_fifo(invoices: List[Dict[str, Any]], payments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            sorted_invoices = sorted(invoices, key=lambda x: x['voucher_date'])
            sorted_payments = sorted(payments, key=lambda x: x['voucher_date'])
            for invoice in sorted_invoices:
                invoice['outstanding_amount'] = abs(invoice['net_amount'])
            for payment in sorted_payments:
                payment_amount = abs(payment['net_amount'])
                for invoice in sorted_invoices:
                    if payment_amount <= 0:
                        break
                    if invoice['outstanding_amount'] > 0:
                        allocation = min(payment_amount, invoice['outstanding_amount'])
                        invoice['outstanding_amount'] -= allocation
                        payment_amount -= allocation
            return [invoice for invoice in sorted_invoices if invoice['outstanding_amount'] > 0.01]
        except Exception as e:
            logger.error(f"Error allocating payments: {e}")
            return invoices

    @staticmethod
    def generate_ageing_report(company_id: int, ageing_type: str, as_on_date: date, custom_buckets: Optional[List[Tuple[int, int, str]]] = None) -> Dict[str, Any]:
        try:
            buckets = custom_buckets if custom_buckets else AgeingReportService.DEFAULT_BUCKETS
            outstanding_type = OutstandingReportService.OUTSTANDING_TYPE_RECEIVABLE if ageing_type == AgeingReportService.AGEING_TYPE_RECEIVABLE else OutstandingReportService.OUTSTANDING_TYPE_PAYABLE
            outstanding_report = OutstandingReportService.generate_outstanding_report(company_id, outstanding_type, as_on_date, include_zero_balance=False)
            if not outstanding_report.get('success'):
                return outstanding_report

            parties: List[Dict[str, Any]] = []
            bucket_totals = {bucket[2]: 0.0 for bucket in buckets}
            grand_total = 0.0

            for party in outstanding_report.get('parties', []):
                invoices = party.get('invoices', [])
                if not invoices:
                    continue
                outstanding_invoices = AgeingReportService._allocate_payments_fifo(
                    [inv for inv in invoices if inv.get('is_debit', False)],
                    [inv for inv in invoices if not inv.get('is_debit', False)],
                )
                if not outstanding_invoices:
                    continue

                party_buckets = {bucket[2]: 0.0 for bucket in buckets}
                for invoice in outstanding_invoices:
                    voucher_date_raw = invoice.get('voucher_date')
                    due_date_raw = invoice.get('due_date')
                    voucher_date = datetime.fromisoformat(voucher_date_raw).date() if isinstance(voucher_date_raw, str) else voucher_date_raw
                    due_date = datetime.fromisoformat(due_date_raw).date() if isinstance(due_date_raw, str) else due_date_raw
                    reference_date = due_date or voucher_date
                    ageing_days = AgeingReportService._calculate_ageing_days(reference_date, as_on_date)
                    bucket_name = AgeingReportService._get_bucket_name(ageing_days, buckets)
                    invoice['ageing_days'] = ageing_days
                    invoice['ageing_bucket'] = bucket_name
                    party_buckets[bucket_name] += float(invoice.get('outstanding_amount', 0.0) or 0.0)

                party_total = sum(party_buckets.values())
                for bucket_name, amount in party_buckets.items():
                    bucket_totals[bucket_name] += amount
                grand_total += party_total

                for bucket_name in party_buckets:
                    party_buckets[bucket_name] = AgeingReportService._round_amount(party_buckets[bucket_name])

                parties.append({
                    'account_id': party['account_id'],
                    'account_name': party['account_name'],
                    'account_code': party['account_code'],
                    'account_group': party['account_group'],
                    'buckets': party_buckets,
                    'total': AgeingReportService._round_amount(party_total),
                    'invoices': outstanding_invoices,
                    'invoice_count': len(outstanding_invoices),
                })

            for bucket_name in bucket_totals:
                bucket_totals[bucket_name] = AgeingReportService._round_amount(bucket_totals[bucket_name])

            return {
                'success': True,
                'report_type': 'Ageing Report',
                'ageing_type': ageing_type,
                'as_on_date': as_on_date.isoformat(),
                'buckets': AgeingReportService._bucket_names(buckets),
                'parties': parties,
                'totals': bucket_totals,
                'grand_total': AgeingReportService._round_amount(grand_total),
                'party_count': len(parties),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating ageing report: {e}")
            return {'success': False, 'error': f"Failed to generate ageing report: {str(e)}"}

    @staticmethod
    def generate_ageing_summary_by_party(company_id: int, ageing_type: str, as_on_date: date) -> Dict[str, Any]:
        try:
            ageing_report = AgeingReportService.generate_ageing_report(company_id, ageing_type, as_on_date)
            if not ageing_report.get('success'):
                return ageing_report
            return {
                'success': True,
                'report_type': 'Ageing Summary by Party',
                'ageing_type': ageing_type,
                'as_on_date': as_on_date.isoformat(),
                'buckets': ageing_report.get('buckets', []),
                'parties': [
                    {
                        'account_code': party['account_code'],
                        'account_name': party['account_name'],
                        'buckets': party['buckets'],
                        'total': party['total'],
                    }
                    for party in ageing_report.get('parties', [])
                ],
                'totals': ageing_report.get('totals', {}),
                'grand_total': ageing_report.get('grand_total', 0.0),
                'party_count': ageing_report.get('party_count', 0),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating ageing summary: {e}")
            return {'success': False, 'error': f"Failed to generate ageing summary: {str(e)}"}

    @staticmethod
    def get_party_ageing_details(company_id: int, account_id: int, ageing_type: str, as_on_date: date) -> Dict[str, Any]:
        try:
            account = next((item for item in AgeingReportService._get_party_accounts(company_id, ageing_type) if item['id'] == account_id), None)
            if not account:
                return {'success': False, 'error': 'Account not found'}

            transactions = AgeingReportService._get_invoice_transactions(account_id, as_on_date)
            invoices = [txn for txn in transactions if txn['is_invoice']]
            payments = [txn for txn in transactions if txn['is_payment']]
            outstanding_invoices = AgeingReportService._allocate_payments_fifo(invoices, payments)

            buckets = AgeingReportService.DEFAULT_BUCKETS
            party_buckets = {bucket[2]: 0.0 for bucket in buckets}
            for invoice in outstanding_invoices:
                voucher_date_raw = invoice.get('voucher_date')
                due_date_raw = invoice.get('due_date')
                voucher_date = datetime.fromisoformat(voucher_date_raw).date() if isinstance(voucher_date_raw, str) else voucher_date_raw
                due_date = datetime.fromisoformat(due_date_raw).date() if isinstance(due_date_raw, str) else due_date_raw
                reference_date = due_date or voucher_date
                ageing_days = AgeingReportService._calculate_ageing_days(reference_date, as_on_date)
                bucket_name = AgeingReportService._get_bucket_name(ageing_days, buckets)
                invoice['ageing_days'] = ageing_days
                invoice['ageing_bucket'] = bucket_name
                party_buckets[bucket_name] += float(invoice.get('outstanding_amount', 0.0) or 0.0)

            for bucket_name in party_buckets:
                party_buckets[bucket_name] = AgeingReportService._round_amount(party_buckets[bucket_name])

            total = AgeingReportService._round_amount(sum(party_buckets.values()))
            return {
                'success': True,
                'report_type': 'Party Ageing Details',
                'account': {
                    'id': account['id'],
                    'name': account['name'],
                    'code': account['code'],
                    'account_group': account['account_group'],
                },
                'ageing_type': ageing_type,
                'as_on_date': as_on_date.isoformat(),
                'buckets': party_buckets,
                'total': total,
                'invoices': outstanding_invoices,
                'invoice_count': len(outstanding_invoices),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error getting party ageing details: {e}")
            return {'success': False, 'error': f"Failed to get party ageing details: {str(e)}"}

    @staticmethod
    def search_parties(ageing_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        try:
            if not ageing_data.get('success'):
                return ageing_data

            search_lower = search_term.lower()
            filtered_parties = [
                party for party in ageing_data.get('parties', [])
                if search_lower in str(party.get('account_name', '')).lower()
                or search_lower in str(party.get('account_code', '')).lower()
            ]

            buckets = ageing_data.get('buckets', [])
            bucket_totals = {bucket: 0.0 for bucket in buckets}
            grand_total = 0.0
            for party in filtered_parties:
                for bucket_name, amount in party.get('buckets', {}).items():
                    bucket_totals[bucket_name] += float(amount or 0.0)
                grand_total += float(party.get('total', 0.0) or 0.0)

            for bucket_name in bucket_totals:
                bucket_totals[bucket_name] = AgeingReportService._round_amount(bucket_totals[bucket_name])

            filtered_data = ageing_data.copy()
            filtered_data['parties'] = filtered_parties
            filtered_data['party_count'] = len(filtered_parties)
            filtered_data['totals'] = bucket_totals
            filtered_data['grand_total'] = AgeingReportService._round_amount(grand_total)
            return filtered_data
        except Exception as e:
            logger.error(f"Error searching parties: {e}")
            return ageing_data

    @staticmethod
    def export_ageing_report_to_csv(report_data: Dict[str, Any], filename: str = "ageing_report") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Ageing Report'])
                writer.writerow(['Type:', report_data.get('ageing_type', '')])
                writer.writerow(['As On Date:', report_data.get('as_on_date', '')])
                writer.writerow([])
                buckets = report_data.get('buckets', [])
                writer.writerow(['Code', 'Party Name'] + buckets + ['Total'])
                for party in report_data.get('parties', []):
                    row = [party.get('account_code', ''), party.get('account_name', '')]
                    for bucket in buckets:
                        row.append(f"{party.get('buckets', {}).get(bucket, 0):,.2f}")
                    row.append(f"{party.get('total', 0):,.2f}")
                    writer.writerow(row)
                writer.writerow([])
                totals = report_data.get('totals', {})
                total_row = ['', 'TOTAL']
                for bucket in buckets:
                    total_row.append(f"{totals.get(bucket, 0):,.2f}")
                total_row.append(f"{report_data.get('grand_total', 0):,.2f}")
                writer.writerow(total_row)

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


ageing_report_service = AgeingReportService()
