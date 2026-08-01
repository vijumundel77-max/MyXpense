"""
Party Ledger Service
Service for generating party-wise ledger reports (Debtors/Creditors)
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PartyLedgerService:
    """Service for Party Ledger Reports"""

    PARTY_TYPE_DEBTOR = 'Debtor'
    PARTY_TYPE_CREDITOR = 'Creditor'
    PARTY_TYPE_ALL = 'All'

    DEBTOR_GROUPS = ['Sundry Debtors']
    CREDITOR_GROUPS = ['Sundry Creditors']

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
    def _table_columns(table_name: str) -> List[str]:
        try:
            rows = db.fetch_all(f"PRAGMA table_info({table_name})")
            return [str(PartyLedgerService._row_value(row, 'name', '')) for row in rows]
        except Exception:
            return []

    @staticmethod
    def _pick_column(columns: List[str], candidates: List[str]) -> Optional[str]:
        lower_map = {column.lower(): column for column in columns}
        for candidate in candidates:
            if candidate.lower() in lower_map:
                return lower_map[candidate.lower()]
        return None

    @staticmethod
    def _party_filters(party_type: str) -> List[str]:
        if party_type == PartyLedgerService.PARTY_TYPE_DEBTOR:
            return PartyLedgerService.DEBTOR_GROUPS
        if party_type == PartyLedgerService.PARTY_TYPE_CREDITOR:
            return PartyLedgerService.CREDITOR_GROUPS
        return PartyLedgerService.DEBTOR_GROUPS + PartyLedgerService.CREDITOR_GROUPS

    @staticmethod
    def _get_party_accounts(company_id: int, party_type: str) -> List[Dict[str, Any]]:
        try:
            columns = PartyLedgerService._table_columns('parties')
            if not columns:
                return []

            id_col = PartyLedgerService._pick_column(columns, ['id'])
            company_col = PartyLedgerService._pick_column(columns, ['company_id'])
            name_col = PartyLedgerService._pick_column(columns, ['name', 'party_name'])
            code_col = PartyLedgerService._pick_column(columns, ['code', 'party_code'])
            group_col = PartyLedgerService._pick_column(columns, ['account_group', 'party_group', 'group_name', 'type'])
            opening_col = PartyLedgerService._pick_column(columns, ['opening_balance', 'balance', 'opening_amount'])
            balance_type_col = PartyLedgerService._pick_column(columns, ['opening_balance_type', 'balance_type', 'opening_type'])
            active_col = PartyLedgerService._pick_column(columns, ['is_active', 'active', 'status'])

            select_columns = [
                c for c in [id_col, company_col, name_col, code_col, group_col, opening_col, balance_type_col, active_col]
                if c
            ]
            if not select_columns:
                return []

            where_clauses = []
            params: List[Any] = []
            if company_col:
                where_clauses.append(f"{company_col} = ?")
                params.append(company_id)

            groups = PartyLedgerService._party_filters(party_type)
            if group_col and groups and party_type != PartyLedgerService.PARTY_TYPE_ALL:
                placeholders = ','.join('?' * len(groups))
                where_clauses.append(f"{group_col} IN ({placeholders})")
                params.extend(groups)

            if active_col and active_col.lower() != 'status':
                where_clauses.append(f"COALESCE({active_col}, 1) = 1")

            query = f"""
                SELECT {', '.join(select_columns)}
                FROM parties
                {('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''}
                ORDER BY {name_col or id_col}
            """
            rows = db.fetch_all(query, tuple(params))

            accounts: List[Dict[str, Any]] = []
            for row in rows:
                accounts.append({
                    'id': PartyLedgerService._row_value(row, id_col, PartyLedgerService._row_value(row, 'id')),
                    'company_id': PartyLedgerService._row_value(row, company_col, company_id) if company_col else company_id,
                    'name': PartyLedgerService._row_value(row, name_col, ''),
                    'code': PartyLedgerService._row_value(row, code_col, ''),
                    'account_group': PartyLedgerService._row_value(row, group_col, ''),
                    'opening_balance': float(PartyLedgerService._row_value(row, opening_col, 0.0) or 0.0),
                    'opening_balance_type': PartyLedgerService._row_value(row, balance_type_col, 'Debit'),
                    'is_active': bool(PartyLedgerService._row_value(row, active_col, 1)),
                })
            return accounts
        except Exception as e:
            logger.error(f"Error getting party accounts: {e}")
            return []

    @staticmethod
    def _get_party_transactions(account_id: int, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        try:
            columns = PartyLedgerService._table_columns('transactions')
            if not columns:
                return []

            party_col = PartyLedgerService._pick_column(columns, ['party_id', 'account_id', 'customer_id', 'supplier_id'])
            date_col = PartyLedgerService._pick_column(columns, ['transaction_date', 'date', 'txn_date', 'entry_date'])
            ref_col = PartyLedgerService._pick_column(columns, ['reference_number', 'reference', 'ref_no', 'voucher_number'])
            type_col = PartyLedgerService._pick_column(columns, ['transaction_type', 'type', 'voucher_type', 'entry_type'])
            narration_col = PartyLedgerService._pick_column(columns, ['narration', 'description', 'remarks', 'note'])
            due_date_col = PartyLedgerService._pick_column(columns, ['due_date', 'payment_due_date'])
            debit_col = PartyLedgerService._pick_column(columns, ['debit_amount', 'debit'])
            credit_col = PartyLedgerService._pick_column(columns, ['credit_amount', 'credit'])
            status_col = PartyLedgerService._pick_column(columns, ['status', 'is_posted', 'posted'])
            id_col = PartyLedgerService._pick_column(columns, ['id'])

            if not party_col or not date_col:
                return []

            select_columns = [c for c in [id_col, party_col, date_col, ref_col, type_col, narration_col, due_date_col, debit_col, credit_col, status_col] if c]
            query = f"""
                SELECT {', '.join(select_columns)}
                FROM transactions
                WHERE {party_col} = ?
                  AND {date_col} BETWEEN ? AND ?
                ORDER BY {date_col}, {id_col or date_col}
            """
            rows = db.fetch_all(query, (account_id, from_date.isoformat(), to_date.isoformat()))

            transactions: List[Dict[str, Any]] = []
            for row in rows:
                txn_date_value = PartyLedgerService._row_value(row, date_col)
                debit_value = float(PartyLedgerService._row_value(row, debit_col, 0.0) or 0.0) if debit_col else 0.0
                credit_value = float(PartyLedgerService._row_value(row, credit_col, 0.0) or 0.0) if credit_col else 0.0
                if debit_col is None and credit_col is None:
                    amount = float(PartyLedgerService._row_value(row, 'amount', 0.0) or 0.0)
                    direction = str(PartyLedgerService._row_value(row, 'direction', 'debit')).lower()
                    debit_value = amount if direction in ('debit', 'dr', 'in') else 0.0
                    credit_value = amount if direction in ('credit', 'cr', 'out') else 0.0

                transactions.append({
                    'voucher_id': PartyLedgerService._row_value(row, id_col, None) if id_col else None,
                    'voucher_number': PartyLedgerService._row_value(row, ref_col, ''),
                    'voucher_type': PartyLedgerService._row_value(row, type_col, ''),
                    'voucher_date': txn_date_value,
                    'reference_number': PartyLedgerService._row_value(row, ref_col, ''),
                    'narration': PartyLedgerService._row_value(row, narration_col, ''),
                    'detail_id': PartyLedgerService._row_value(row, id_col, None) if id_col else None,
                    'debit_amount': debit_value,
                    'credit_amount': credit_value,
                    'detail_narration': PartyLedgerService._row_value(row, narration_col, ''),
                    'contra_account_name': '',
                    'contra_account_group': '',
                    'due_date': PartyLedgerService._row_value(row, due_date_col, None) if due_date_col else None,
                    'status': PartyLedgerService._row_value(row, status_col, '') if status_col else '',
                })
            return transactions
        except Exception as e:
            logger.error(f"Error getting party transactions: {e}")
            return []

    @staticmethod
    def _calculate_opening_balance(account: Dict[str, Any], from_date: date) -> Tuple[float, str]:
        try:
            opening_balance = float(account.get('opening_balance', 0.0) or 0.0)
            opening_type = account.get('opening_balance_type', 'Debit')

            transactions = PartyLedgerService._get_party_transactions(account['id'], date(1900, 1, 1), from_date)
            total_debit = sum(float(txn.get('debit_amount', 0.0) or 0.0) for txn in transactions if txn.get('voucher_date') and txn['voucher_date'] < from_date.isoformat())
            total_credit = sum(float(txn.get('credit_amount', 0.0) or 0.0) for txn in transactions if txn.get('voucher_date') and txn['voucher_date'] < from_date.isoformat())

            if opening_type == 'Debit':
                net_balance = opening_balance + total_debit - total_credit
            else:
                net_balance = opening_balance + total_credit - total_debit

            if net_balance >= 0:
                return PartyLedgerService._round_amount(net_balance), 'Debit'
            return PartyLedgerService._round_amount(abs(net_balance)), 'Credit'
        except Exception as e:
            logger.error(f"Error calculating opening balance: {e}")
            return 0.0, 'Debit'

    @staticmethod
    def _calculate_closing_balance(
        opening_balance: float,
        opening_type: str,
        transactions: List[Dict[str, Any]],
    ) -> Tuple[float, str]:
        try:
            balance = opening_balance if opening_type == 'Debit' else -opening_balance
            for txn in transactions:
                balance += float(txn.get('debit_amount', 0.0) or 0.0) - float(txn.get('credit_amount', 0.0) or 0.0)
            if balance >= 0:
                return PartyLedgerService._round_amount(balance), 'Debit'
            return PartyLedgerService._round_amount(abs(balance)), 'Credit'
        except Exception as e:
            logger.error(f"Error calculating closing balance: {e}")
            return 0.0, 'Debit'

    @staticmethod
    def generate_party_ledger(company_id: int, account_id: int, from_date: date, to_date: date) -> Dict[str, Any]:
        try:
            account = next((a for a in PartyLedgerService._get_party_accounts(company_id, PartyLedgerService.PARTY_TYPE_ALL) if a['id'] == account_id), None)
            if not account:
                return {'success': False, 'error': 'Account not found'}

            opening_balance, opening_type = PartyLedgerService._calculate_opening_balance(account, from_date)
            transactions = PartyLedgerService._get_party_transactions(account_id, from_date, to_date)

            running_balance = opening_balance if opening_type == 'Debit' else -opening_balance
            for txn in transactions:
                running_balance += float(txn.get('debit_amount', 0.0) or 0.0) - float(txn.get('credit_amount', 0.0) or 0.0)
                txn['running_balance'] = abs(running_balance)
                txn['balance_type'] = 'Debit' if running_balance >= 0 else 'Credit'
                txn['voucher_date'] = txn['voucher_date'] if isinstance(txn['voucher_date'], str) else (txn['voucher_date'].isoformat() if hasattr(txn['voucher_date'], 'isoformat') else txn['voucher_date'])
                if txn.get('due_date') and hasattr(txn['due_date'], 'isoformat'):
                    txn['due_date'] = txn['due_date'].isoformat()

            closing_balance, closing_type = PartyLedgerService._calculate_closing_balance(opening_balance, opening_type, transactions)
            total_debit = sum(float(txn.get('debit_amount', 0.0) or 0.0) for txn in transactions)
            total_credit = sum(float(txn.get('credit_amount', 0.0) or 0.0) for txn in transactions)

            return {
                'success': True,
                'report_type': 'Party Ledger',
                'account': account,
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'opening_balance': {'amount': opening_balance, 'type': opening_type},
                'transactions': transactions,
                'totals': {'debit': PartyLedgerService._round_amount(total_debit), 'credit': PartyLedgerService._round_amount(total_credit)},
                'closing_balance': {'amount': closing_balance, 'type': closing_type},
                'transaction_count': len(transactions),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating party ledger: {e}")
            return {'success': False, 'error': f"Failed to generate party ledger: {str(e)}"}

    @staticmethod
    def generate_party_summary(
        company_id: int,
        party_type: str,
        as_on_date: date,
        from_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        try:
            accounts = PartyLedgerService._get_party_accounts(company_id, party_type)
            if not accounts:
                return {
                    'success': True,
                    'report_type': 'Party Summary',
                    'party_type': party_type,
                    'as_on_date': as_on_date.isoformat(),
                    'parties': [],
                    'totals': {'total_debit': 0.0, 'total_credit': 0.0, 'net_receivable': 0.0, 'net_payable': 0.0},
                    'party_count': 0,
                    'generated_at': datetime.now().isoformat(),
                }

            if not from_date:
                from_date = date(1900, 1, 1)

            party_summaries: List[Dict[str, Any]] = []
            total_debit = 0.0
            total_credit = 0.0

            for account in accounts:
                opening_balance, opening_type = PartyLedgerService._calculate_opening_balance(account, from_date)
                transactions = PartyLedgerService._get_party_transactions(account['id'], from_date, as_on_date)
                closing_balance, closing_type = PartyLedgerService._calculate_closing_balance(opening_balance, opening_type, transactions)
                txn_debit = sum(float(txn.get('debit_amount', 0.0) or 0.0) for txn in transactions)
                txn_credit = sum(float(txn.get('credit_amount', 0.0) or 0.0) for txn in transactions)

                total_debit += txn_debit
                total_credit += txn_credit

                party_summaries.append({
                    'account_id': account['id'],
                    'account_name': account['name'],
                    'account_code': account['code'],
                    'account_group': account['account_group'],
                    'opening_balance': opening_balance,
                    'opening_type': opening_type,
                    'debit_total': PartyLedgerService._round_amount(txn_debit),
                    'credit_total': PartyLedgerService._round_amount(txn_credit),
                    'closing_balance': closing_balance,
                    'closing_type': closing_type,
                    'transaction_count': len(transactions),
                })

            net_receivable = sum(p['closing_balance'] for p in party_summaries if p['closing_type'] == 'Debit')
            net_payable = sum(p['closing_balance'] for p in party_summaries if p['closing_type'] == 'Credit')

            return {
                'success': True,
                'report_type': 'Party Summary',
                'party_type': party_type,
                'as_on_date': as_on_date.isoformat(),
                'from_date': from_date.isoformat() if from_date != date(1900, 1, 1) else None,
                'parties': party_summaries,
                'totals': {
                    'total_debit': PartyLedgerService._round_amount(total_debit),
                    'total_credit': PartyLedgerService._round_amount(total_credit),
                    'net_receivable': PartyLedgerService._round_amount(net_receivable),
                    'net_payable': PartyLedgerService._round_amount(net_payable),
                },
                'party_count': len(party_summaries),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error generating party summary: {e}")
            return {'success': False, 'error': f"Failed to generate party summary: {str(e)}"}

    @staticmethod
    def get_party_outstanding(company_id: int, account_id: int, as_on_date: date) -> Dict[str, Any]:
        try:
            account = next((a for a in PartyLedgerService._get_party_accounts(company_id, PartyLedgerService.PARTY_TYPE_ALL) if a['id'] == account_id), None)
            if not account:
                return {'success': False, 'error': 'Account not found'}

            opening_balance, opening_type = PartyLedgerService._calculate_opening_balance(account, date(1900, 1, 1))
            transactions = PartyLedgerService._get_party_transactions(account_id, date(1900, 1, 1), as_on_date)
            closing_balance, closing_type = PartyLedgerService._calculate_closing_balance(opening_balance, opening_type, transactions)

            return {
                'success': True,
                'account': account,
                'as_on_date': as_on_date.isoformat(),
                'outstanding_balance': closing_balance,
                'balance_type': closing_type,
                'is_receivable': closing_type == 'Debit',
                'is_payable': closing_type == 'Credit',
            }
        except Exception as e:
            logger.error(f"Error getting party outstanding: {e}")
            return {'success': False, 'error': f"Failed to get outstanding: {str(e)}"}

    @staticmethod
    def search_parties(company_id: int, party_type: str, search_term: str) -> List[Dict[str, Any]]:
        try:
            accounts = PartyLedgerService._get_party_accounts(company_id, party_type)
            search_lower = search_term.lower()
            return [
                account for account in accounts
                if search_lower in str(account.get('name', '')).lower()
                or search_lower in str(account.get('code', '')).lower()
            ]
        except Exception as e:
            logger.error(f"Error searching parties: {e}")
            return []

    @staticmethod
    def export_party_ledger_to_csv(ledger_data: Dict[str, Any], filename: str = "party_ledger") -> Tuple[bool, str]:
        try:
            if not ledger_data.get('success'):
                return False, "Invalid ledger data"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                account = ledger_data.get('account', {})
                writer.writerow(['Party Ledger'])
                writer.writerow(['Account:', account.get('name', '')])
                writer.writerow(['Code:', account.get('code', '')])
                writer.writerow(['Period:', f"{ledger_data.get('from_date', '')} to {ledger_data.get('to_date', '')}"])
                writer.writerow([])
                opening = ledger_data.get('opening_balance', {})
                writer.writerow(['Opening Balance:', f"{opening.get('amount', 0):,.2f} {opening.get('type', '')}"])
                writer.writerow([])
                writer.writerow(['Date', 'Voucher No.', 'Type', 'Reference', 'Particulars', 'Debit', 'Credit', 'Balance', 'Dr/Cr'])
                for txn in ledger_data.get('transactions', []):
                    writer.writerow([
                        txn.get('voucher_date', ''),
                        txn.get('voucher_number', ''),
                        txn.get('voucher_type', ''),
                        txn.get('reference_number', ''),
                        txn.get('contra_account_name', ''),
                        f"{txn.get('debit_amount', 0):,.2f}",
                        f"{txn.get('credit_amount', 0):,.2f}",
                        f"{txn.get('running_balance', 0):,.2f}",
                        txn.get('balance_type', ''),
                    ])
                writer.writerow([])
                totals = ledger_data.get('totals', {})
                writer.writerow(['Total', '', '', '', '', f"{totals.get('debit', 0):,.2f}", f"{totals.get('credit', 0):,.2f}", '', ''])
                closing = ledger_data.get('closing_balance', {})
                writer.writerow(['Closing Balance:', f"{closing.get('amount', 0):,.2f} {closing.get('type', '')}"])

            return True, str(file_path)
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return False, f"Export failed: {str(e)}"

    @staticmethod
    def export_party_summary_to_csv(summary_data: Dict[str, Any], filename: str = "party_summary") -> Tuple[bool, str]:
        try:
            if not summary_data.get('success'):
                return False, "Invalid summary data"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Party Summary'])
                writer.writerow(['Party Type:', summary_data.get('party_type', '')])
                writer.writerow(['As On Date:', summary_data.get('as_on_date', '')])
                writer.writerow([])
                writer.writerow(['Code', 'Name', 'Group', 'Opening', 'Type', 'Debit', 'Credit', 'Closing', 'Type', 'Transactions'])
                for party in summary_data.get('parties', []):
                    writer.writerow([
                        party.get('account_code', ''),
                        party.get('account_name', ''),
                        party.get('account_group', ''),
                        f"{party.get('opening_balance', 0):,.2f}",
                        party.get('opening_type', ''),
                        f"{party.get('debit_total', 0):,.2f}",
                        f"{party.get('credit_total', 0):,.2f}",
                        f"{party.get('closing_balance', 0):,.2f}",
                        party.get('closing_type', ''),
                        party.get('transaction_count', 0),
                    ])
                writer.writerow([])
                totals = summary_data.get('totals', {})
                writer.writerow(['Totals'])
                writer.writerow(['Total Debit:', f"{totals.get('total_debit', 0):,.2f}"])
                writer.writerow(['Total Credit:', f"{totals.get('total_credit', 0):,.2f}"])
                writer.writerow(['Net Receivable:', f"{totals.get('net_receivable', 0):,.2f}"])
                writer.writerow(['Net Payable:', f"{totals.get('net_payable', 0):,.2f}"])

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


party_ledger_service = PartyLedgerService()
