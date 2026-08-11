"""
Cash Book Service
Generates cash / bank book reports from the Expenzo accounting schema.

The primary data source is ``voucher_details`` joined to ``vouchers`` for
accounts belonging to the Cash-in-Hand (cash book) or Bank Accounts (bank
book) groups. Cancelled vouchers are excluded. The legacy personal
``transactions`` path is retained as a read-only fallback so old data still
renders, but new entries always go through vouchers.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from utils.report_exporter import report_exporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GROUP_CASH = 'Cash-in-Hand'
GROUP_BANK = 'Bank Accounts'

STATUS_CANCELLED = 'Cancelled'


class CashBookService:
    """Service for cash and bank book reports (Expenzo voucher data)."""

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
    def _parse_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        return date(1900, 1, 1)

    @staticmethod
    def _book_accounts(company_id: int, book_group: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Active accounts in the given book group for a company."""
        where = ["company_id = ?", "LOWER(account_group) = LOWER(?)"]
        params: List[Any] = [company_id, book_group]
        if not include_inactive:
            where.append("is_active = 1")
        rows = db.fetch_all(
            f"""
            SELECT id, company_id, name, code, account_group,
                   opening_balance, opening_balance_type, is_active
            FROM accounts
            WHERE {' AND '.join(where)}
            ORDER BY name
            """,
            tuple(params),
        )
        accounts: List[Dict[str, Any]] = []
        for row in rows:
            opening = float(CashBookService._row_value(row, 'opening_balance', 0.0) or 0.0)
            opening_type = CashBookService._row_value(row, 'opening_balance_type', 'Debit')
            signed = opening if opening_type == 'Debit' else -opening
            accounts.append({
                'id': CashBookService._row_value(row, 'id'),
                'company_id': CashBookService._row_value(row, 'company_id'),
                'name': CashBookService._row_value(row, 'name', ''),
                'code': CashBookService._row_value(row, 'code', ''),
                'account_group': CashBookService._row_value(row, 'account_group', ''),
                'opening_balance': opening,
                'opening_balance_type': opening_type,
                'signed_opening': signed,
                'is_active': bool(CashBookService._row_value(row, 'is_active', 1)),
            })
        return accounts

    @staticmethod
    def _get_cash_sources(company_id: int) -> List[Dict[str, Any]]:
        """Cash + bank accounts combined (used by the account selector)."""
        return (
            CashBookService._book_accounts(company_id, GROUP_CASH)
            + CashBookService._book_accounts(company_id, GROUP_BANK)
        )

    @staticmethod
    def _get_expenzo_book_transactions(
        company_id: int,
        book_group: str,
        from_date: date,
        to_date: date,
        account_id: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        """Voucher detail lines for the book's accounts.

        Returns (transactions, opening_balance) where opening_balance is the
        sum of signed opening balances for the accounts in scope.
        """
        accounts = CashBookService._book_accounts(company_id, book_group)
        if account_id is not None:
            accounts = [a for a in accounts if a['id'] == account_id]

        opening_balance = sum(a['signed_opening'] for a in accounts)

        if not accounts:
            return [], opening_balance

        account_ids = [a['id'] for a in accounts]
        placeholders = ','.join('?' * len(account_ids))

        rows = db.fetch_all(
            f"""
            SELECT
                v.id AS voucher_id,
                v.voucher_number,
                v.voucher_type,
                v.voucher_date,
                v.reference_number,
                v.narration,
                v.status,
                vd.id AS detail_id,
                vd.debit_amount,
                vd.credit_amount,
                vd.narration AS detail_narration,
                vd.account_id,
                a.name AS account_name,
                a.code AS account_code
            FROM voucher_details vd
            JOIN vouchers v ON v.id = vd.voucher_id
            LEFT JOIN accounts a ON a.id = vd.account_id
            WHERE vd.account_id IN ({placeholders})
              AND v.company_id = ?
              AND v.status != ?
            ORDER BY v.voucher_date, v.id, vd.id
            """,
            tuple(account_ids) + (company_id, STATUS_CANCELLED),
        )

        transactions: List[Dict[str, Any]] = []
        for row in rows:
            txn_date = CashBookService._parse_date(
                CashBookService._row_value(row, 'voucher_date'))
            if txn_date < from_date or txn_date > to_date:
                continue
            debit = float(CashBookService._row_value(row, 'debit_amount', 0.0) or 0.0)
            credit = float(CashBookService._row_value(row, 'credit_amount', 0.0) or 0.0)
            transactions.append({
                'voucher_id': CashBookService._row_value(row, 'voucher_id'),
                'voucher_number': CashBookService._row_value(row, 'voucher_number', ''),
                'voucher_type': CashBookService._row_value(row, 'voucher_type', ''),
                'transaction_date': CashBookService._row_value(row, 'voucher_date', ''),
                'reference_number': CashBookService._row_value(row, 'reference_number', ''),
                'narration': (CashBookService._row_value(row, 'detail_narration', '')
                              or CashBookService._row_value(row, 'narration', '')),
                'debit_amount': debit,
                'credit_amount': credit,
                'account_id': CashBookService._row_value(row, 'account_id'),
                'account_name': CashBookService._row_value(row, 'account_name', ''),
                'account_code': CashBookService._row_value(row, 'account_code', ''),
                'status': CashBookService._row_value(row, 'status', ''),
            })
        return transactions, opening_balance

    @staticmethod
    def _classify_transaction(transaction: Dict[str, Any]) -> str:
        debit = float(transaction.get('debit_amount', 0.0) or 0.0)
        credit = float(transaction.get('credit_amount', 0.0) or 0.0)
        if debit > credit:
            return 'Receipt'
        if credit > debit:
            return 'Payment'
        return 'Transfer'

    @staticmethod
    def _legacy_transactions(from_date: date, to_date: date, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Read-only fallback over the legacy personal ``transactions`` table."""
        try:
            rows = db.fetch_all("PRAGMA table_info(transactions)")
            columns = [str(CashBookService._row_value(r, 'name', '')) for r in rows]
            if 'id' not in columns or 'transaction_date' not in columns:
                return []

            date_col = 'transaction_date'
            ref_col = 'reference_number' if 'reference_number' in columns else 'notes'
            narration_col = 'notes' if 'notes' in columns else 'title'
            amount_col = 'amount' if 'amount' in columns else None
            type_col = 'type' if 'type' in columns else None
            bank_col = 'bank_account_id' if 'bank_account_id' in columns else None
            mode_col = 'account_mode' if 'account_mode' in columns else None

            select_cols = [c for c in
                           ['id', date_col, ref_col, narration_col, amount_col,
                            type_col, bank_col, mode_col] if c]
            rows = db.fetch_all(
                f"SELECT {', '.join(select_cols)} FROM transactions ORDER BY {date_col}, id")

            transactions: List[Dict[str, Any]] = []
            for row in rows:
                tx_date = CashBookService._parse_date(row[date_col])
                if tx_date < from_date or tx_date > to_date:
                    continue
                if account_id is not None and bank_col and row[bank_col] != account_id:
                    continue
                amount = float(row[amount_col] or 0.0) if amount_col else 0.0
                txn_type = str(row[type_col] or '') if type_col else ''
                mode = str(row[mode_col] or '') if mode_col else ''
                if mode == 'Bank':
                    continue
                if txn_type == 'Expense':
                    debit, credit = 0.0, amount
                else:
                    debit, credit = amount, 0.0
                transactions.append({
                    'voucher_number': '',
                    'voucher_type': 'Legacy',
                    'transaction_date': row[date_col],
                    'reference_number': str(row[ref_col] or '') if ref_col else '',
                    'narration': str(row[narration_col] or '') if narration_col else '',
                    'debit_amount': debit,
                    'credit_amount': credit,
                    'account_name': '',
                    'account_code': '',
                })
            return transactions
        except Exception as exc:
            logger.error(f"Error reading legacy transactions: {exc}")
            return []

    @staticmethod
    def generate_cash_book(
        company_id: int,
        from_date: date,
        to_date: date,
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Cash book: accounts in the Cash-in-Hand group."""
        try:
            transactions, opening_balance = CashBookService._get_expenzo_book_transactions(
                company_id, GROUP_CASH, from_date, to_date, account_id)
            # Legacy fallback only when this company has no Expenzo vouchers
            # at all (so old personal cash data still renders).
            if not transactions:
                voucher_count = db.fetch_one(
                    "SELECT COUNT(*) AS count FROM vouchers WHERE company_id = ? AND status != ?",
                    (company_id, STATUS_CANCELLED),
                )
                count = int(CashBookService._row_value(voucher_count, 'count', 0) or 0) if voucher_count else 0
                if count == 0:
                    legacy = CashBookService._legacy_transactions(from_date, to_date, account_id)
                    if legacy:
                        transactions = legacy
                        opening_balance = 0.0

            return CashBookService._build_book(
                'Cash Book', company_id, from_date, to_date, transactions, opening_balance)
        except Exception as exc:
            logger.error(f"Error generating cash book: {exc}")
            return {'success': False, 'error': f"Failed to generate cash book: {str(exc)}"}

    @staticmethod
    def generate_bank_book(
        company_id: int,
        from_date: date,
        to_date: date,
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Bank book: accounts in the Bank Accounts group."""
        try:
            transactions, opening_balance = CashBookService._get_expenzo_book_transactions(
                company_id, GROUP_BANK, from_date, to_date, account_id)
            return CashBookService._build_book(
                'Bank Book', company_id, from_date, to_date, transactions, opening_balance)
        except Exception as exc:
            logger.error(f"Error generating bank book: {exc}")
            return {'success': False, 'error': f"Failed to generate bank book: {str(exc)}"}

    @staticmethod
    def _build_book(
        report_type: str,
        company_id: int,
        from_date: date,
        to_date: date,
        transactions: List[Dict[str, Any]],
        opening_balance: float,
    ) -> Dict[str, Any]:
        running_balance = opening_balance
        total_receipts = 0.0
        total_payments = 0.0

        for transaction in transactions:
            txn_type = CashBookService._classify_transaction(transaction)
            debit = float(transaction.get('debit_amount', 0.0) or 0.0)
            credit = float(transaction.get('credit_amount', 0.0) or 0.0)
            if txn_type == 'Receipt':
                running_balance += debit
                total_receipts += debit
            elif txn_type == 'Payment':
                running_balance -= credit
                total_payments += credit
            transaction['transaction_type'] = txn_type
            transaction['running_balance'] = CashBookService._round_amount(abs(running_balance))
            transaction['balance_type'] = 'Debit' if running_balance >= 0 else 'Credit'

        closing_balance = running_balance
        return {
            'success': True,
            'report_type': report_type,
            'company_id': company_id,
            'from_date': from_date.isoformat(),
            'to_date': to_date.isoformat(),
            'opening_balance': CashBookService._round_amount(opening_balance),
            'receipts': CashBookService._round_amount(total_receipts),
            'payments': CashBookService._round_amount(total_payments),
            'transactions': transactions,
            'closing_balance': {
                'amount': CashBookService._round_amount(abs(closing_balance)),
                'type': 'Debit' if closing_balance >= 0 else 'Credit',
            },
            'transaction_count': len(transactions),
            'generated_at': datetime.now().isoformat(),
        }

    @staticmethod
    def search_transactions(cash_book_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        try:
            if not cash_book_data.get('success'):
                return cash_book_data
            search_lower = search_term.lower()
            filtered = [
                txn for txn in cash_book_data.get('transactions', [])
                if search_lower in str(txn.get('reference_number', '')).lower()
                or search_lower in str(txn.get('narration', '')).lower()
                or search_lower in str(txn.get('voucher_number', '')).lower()
                or search_lower in str(txn.get('voucher_type', '')).lower()
            ]
            data = dict(cash_book_data)
            data['transactions'] = filtered
            data['transaction_count'] = len(filtered)
            return data
        except Exception as exc:
            logger.error(f"Error searching cash book: {exc}")
            return cash_book_data

    @staticmethod
    def export_cash_book_to_csv(report_data: Dict[str, Any], filename: str = "cash_book") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([report_data.get('report_type', 'Cash Book')])
                writer.writerow(['Period:', f"{report_data.get('from_date', '')} to {report_data.get('to_date', '')}"])
                writer.writerow(['Opening Balance:', f"{report_data.get('opening_balance', 0):,.2f}"])
                writer.writerow(['Receipts:', f"{report_data.get('receipts', 0):,.2f}"])
                writer.writerow(['Payments:', f"{report_data.get('payments', 0):,.2f}"])
                writer.writerow(['Closing Balance:', f"{report_data.get('closing_balance', {}).get('amount', 0):,.2f}",
                                 report_data.get('closing_balance', {}).get('type', '')])
                writer.writerow([])
                writer.writerow(['Date', 'Voucher No.', 'Type', 'Reference', 'Narration', 'Debit', 'Credit', 'Running Balance', 'Dr/Cr'])
                for txn in report_data.get('transactions', []):
                    writer.writerow([
                        txn.get('transaction_date', ''),
                        txn.get('voucher_number', ''),
                        txn.get('voucher_type', ''),
                        txn.get('reference_number', ''),
                        txn.get('narration', ''),
                        f"{txn.get('debit_amount', 0):,.2f}",
                        f"{txn.get('credit_amount', 0):,.2f}",
                        f"{txn.get('running_balance', 0):,.2f}",
                        txn.get('balance_type', ''),
                    ])
            return True, str(file_path)
        except Exception as exc:
            logger.error(f"Error exporting cash book: {exc}")
            return False, f"Export failed: {str(exc)}"

    @staticmethod
    def export_to_json(data: Dict[str, Any], filename: str) -> Tuple[bool, str]:
        return report_exporter.export_to_json(data, filename)


cash_book_service = CashBookService()
