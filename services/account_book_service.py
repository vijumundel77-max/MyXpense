"""
Account Book Service
Generates account statement reports from the current MyXpense schema.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.cash_book_service import CashBookService
from services.party_ledger_service import PartyLedgerService
from utils.report_exporter import report_exporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AccountBookService:
    """Service for account book reports."""

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
    def _get_transactions(from_date: date, to_date: date, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
        # Read through the party-ledger reader so both the Expenzo voucher
        # schema and the legacy personal schema are supported.
        if account_id is not None:
            return PartyLedgerService._get_party_transactions(account_id, from_date, to_date)
        return CashBookService._get_transactions(from_date, to_date, account_id)

    @staticmethod
    def _get_party_items(company_id: int) -> List[Dict[str, Any]]:
        return PartyLedgerService._get_party_accounts(company_id, PartyLedgerService.PARTY_TYPE_ALL)

    @staticmethod
    def _classify_transaction(transaction: Dict[str, Any]) -> str:
        return CashBookService._classify_transaction(transaction)

    @staticmethod
    def _get_opening_balance(account: Dict[str, Any], from_date: date) -> Tuple[float, str]:
        return PartyLedgerService._calculate_opening_balance(account, from_date)

    @staticmethod
    def _get_closing_balance(opening_balance: float, opening_type: str, transactions: List[Dict[str, Any]]) -> Tuple[float, str]:
        return PartyLedgerService._calculate_closing_balance(opening_balance, opening_type, transactions)

    @staticmethod
    def generate_account_book(company_id: int, account_id: int, from_date: date, to_date: date) -> Dict[str, Any]:
        try:
            account = next((item for item in AccountBookService._get_party_items(company_id) if item['id'] == account_id), None)
            if not account:
                return {'success': False, 'error': 'Account not found'}

            opening_balance, opening_type = AccountBookService._get_opening_balance(account, from_date)
            transactions = AccountBookService._get_transactions(from_date, to_date, account_id)

            running_balance = opening_balance if opening_type == 'Debit' else -opening_balance
            receipts = 0.0
            payments = 0.0

            for transaction in transactions:
                txn_type = AccountBookService._classify_transaction(transaction)
                debit = float(transaction.get('debit_amount', 0.0) or 0.0)
                credit = float(transaction.get('credit_amount', 0.0) or 0.0)
                delta = debit - credit
                if txn_type == 'Receipt':
                    receipts += abs(delta)
                elif txn_type == 'Payment':
                    payments += abs(delta)
                running_balance += delta
                transaction['transaction_type'] = txn_type
                transaction['running_balance'] = AccountBookService._round_amount(abs(running_balance))
                transaction['balance_type'] = 'Debit' if running_balance >= 0 else 'Credit'

            closing_balance, closing_type = AccountBookService._get_closing_balance(opening_balance, opening_type, transactions)
            return {
                'success': True,
                'report_type': 'Account Book',
                'company_id': company_id,
                'account_id': account_id,
                'account': account,
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'opening_balance': {'amount': AccountBookService._round_amount(opening_balance), 'type': opening_type},
                'receipts': AccountBookService._round_amount(receipts),
                'payments': AccountBookService._round_amount(payments),
                'transactions': transactions,
                'closing_balance': {'amount': AccountBookService._round_amount(closing_balance), 'type': closing_type},
                'transaction_count': len(transactions),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating account book: {e}")
            return {'success': False, 'error': f"Failed to generate account book: {str(e)}"}

    @staticmethod
    def search_transactions(report_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        try:
            if not report_data.get('success'):
                return report_data
            search_lower = search_term.lower()
            filtered_transactions = [
                txn for txn in report_data.get('transactions', [])
                if search_lower in str(txn.get('reference_number', '')).lower()
                or search_lower in str(txn.get('narration', '')).lower()
                or search_lower in str(txn.get('transaction_type', '')).lower()
            ]
            filtered_data = report_data.copy()
            filtered_data['transactions'] = filtered_transactions
            filtered_data['transaction_count'] = len(filtered_transactions)
            return filtered_data
        except Exception as e:
            logger.error(f"Error searching transactions: {e}")
            return report_data

    @staticmethod
    def export_account_book_to_csv(report_data: Dict[str, Any], filename: str = "account_book") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Account Book'])
                writer.writerow(['Account:', report_data.get('account', {}).get('name', '')])
                writer.writerow(['Period:', f"{report_data.get('from_date', '')} to {report_data.get('to_date', '')}"])
                writer.writerow(['Opening Balance:', report_data.get('opening_balance', {}).get('amount', 0.0), report_data.get('opening_balance', {}).get('type', '')])
                writer.writerow(['Receipts:', report_data.get('receipts', 0.0)])
                writer.writerow(['Payments:', report_data.get('payments', 0.0)])
                writer.writerow(['Closing Balance:', report_data.get('closing_balance', {}).get('amount', 0.0), report_data.get('closing_balance', {}).get('type', '')])
                writer.writerow([])
                writer.writerow(['Date', 'Reference', 'Type', 'Narration', 'Debit', 'Credit', 'Running Balance', 'Dr/Cr'])
                for txn in report_data.get('transactions', []):
                    writer.writerow([
                        txn.get('transaction_date', ''),
                        txn.get('reference_number', ''),
                        txn.get('transaction_type', ''),
                        txn.get('narration', ''),
                        f"{txn.get('debit_amount', 0):,.2f}",
                        f"{txn.get('credit_amount', 0):,.2f}",
                        f"{txn.get('running_balance', 0):,.2f}",
                        txn.get('balance_type', ''),
                    ])
            return True, str(file_path)
        except Exception as e:
            logger.error(f"Error exporting account book to CSV: {e}")
            return False, f"Export failed: {str(e)}"

    @staticmethod
    def export_to_json(data: Dict[str, Any], filename: str) -> Tuple[bool, str]:
        return report_exporter.export_to_json(data, filename)


account_book_service = AccountBookService()
