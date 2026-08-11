"""
Trial Balance Service
Per-account debit/credit balances as of a date, from the Expenzo
double-entry accounting data (accounts + voucher_details).

Every account's balance = signed opening balance + voucher detail activity
up to the as-of date. Cancelled vouchers are excluded. The trial balance is
balanced when total debit equals total credit.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.party_ledger_service import PartyLedgerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATUS_CANCELLED = 'Cancelled'


class TrialBalanceService:
    """Trial balance from Expenzo voucher data."""

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
    def _accounts(company_id: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
        where = ["company_id = ?"]
        params: List[Any] = [company_id]
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
            accounts.append({
                'id': TrialBalanceService._row_value(row, 'id'),
                'company_id': TrialBalanceService._row_value(row, 'company_id'),
                'name': TrialBalanceService._row_value(row, 'name', ''),
                'code': TrialBalanceService._row_value(row, 'code', ''),
                'account_group': TrialBalanceService._row_value(row, 'account_group', ''),
                'opening_balance': float(TrialBalanceService._row_value(row, 'opening_balance', 0.0) or 0.0),
                'opening_balance_type': TrialBalanceService._row_value(row, 'opening_balance_type', 'Debit'),
                'is_active': bool(TrialBalanceService._row_value(row, 'is_active', 1)),
            })
        return accounts

    @staticmethod
    def _account_activity(company_id: int, from_date: date, to_date: date) -> Dict[int, Tuple[float, float]]:
        """Sum of debit and credit detail lines per account for the period,
        excluding cancelled vouchers."""
        rows = db.fetch_all(
            """
            SELECT vd.account_id,
                   COALESCE(SUM(vd.debit_amount), 0) AS total_debit,
                   COALESCE(SUM(vd.credit_amount), 0) AS total_credit
            FROM voucher_details vd
            JOIN vouchers v ON v.id = vd.voucher_id
            WHERE v.company_id = ?
              AND v.status != ?
              AND v.voucher_date >= ?
              AND v.voucher_date <= ?
            GROUP BY vd.account_id
            """,
            (company_id, STATUS_CANCELLED, from_date.isoformat(), to_date.isoformat()),
        )
        activity: Dict[int, Tuple[float, float]] = {}
        for row in rows:
            account_id = int(TrialBalanceService._row_value(row, 'account_id') or 0)
            activity[account_id] = (
                float(TrialBalanceService._row_value(row, 'total_debit', 0.0) or 0.0),
                float(TrialBalanceService._row_value(row, 'total_credit', 0.0) or 0.0),
            )
        return activity

    @staticmethod
    def generate_trial_balance(
        company_id: int,
        as_on_date: date,
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        """Trial balance as of a date.

        Opening balances (with their Dr/Cr nature) plus voucher activity from
        the beginning of time up to as_on_date.
        """
        try:
            accounts = TrialBalanceService._accounts(company_id, include_inactive)
            # Opening balance is always as of the start of the books; activity
            # counts everything up to the as-of date.
            activity = TrialBalanceService._account_activity(
                company_id, date(1900, 1, 1), as_on_date)

            rows: List[Dict[str, Any]] = []
            total_debit = 0.0
            total_credit = 0.0

            for account in accounts:
                opening = account['opening_balance']
                opening_type = account['opening_balance_type']
                debit, credit = activity.get(account['id'], (0.0, 0.0))

                if opening_type == 'Debit':
                    # Positive net = debit balance (natural side).
                    net = opening + debit - credit
                    if net >= 0:
                        account_debit = TrialBalanceService._round_amount(net)
                        account_credit = 0.0
                    else:
                        account_debit = 0.0
                        account_credit = TrialBalanceService._round_amount(abs(net))
                else:
                    # Credit-nature account: positive net = credit balance.
                    net = opening + credit - debit
                    if net >= 0:
                        account_debit = 0.0
                        account_credit = TrialBalanceService._round_amount(net)
                    else:
                        account_debit = TrialBalanceService._round_amount(abs(net))
                        account_credit = 0.0

                total_debit += account_debit
                total_credit += account_credit
                rows.append({
                    'account_id': account['id'],
                    'account_name': account['name'],
                    'account_code': account['code'],
                    'account_group': account['account_group'],
                    'debit': account_debit,
                    'credit': account_credit,
                })

            total_debit = TrialBalanceService._round_amount(total_debit)
            total_credit = TrialBalanceService._round_amount(total_credit)
            return {
                'success': True,
                'report_type': 'Trial Balance',
                'company_id': company_id,
                'as_on_date': as_on_date.isoformat(),
                'rows': rows,
                'totals': {'debit': total_debit, 'credit': total_credit},
                'is_balanced': abs(total_debit - total_credit) < 0.01,
                'row_count': len(rows),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error(f"Error generating trial balance: {exc}")
            return {'success': False, 'error': f"Failed to generate trial balance: {str(exc)}"}

    @staticmethod
    def search_rows(trial_balance: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        """Filter trial-balance rows by account name/code/group."""
        if not trial_balance.get('success'):
            return trial_balance
        term = search_term.lower()
        filtered = [
            row for row in trial_balance.get('rows', [])
            if term in str(row.get('account_name', '')).lower()
            or term in str(row.get('account_code', '')).lower()
            or term in str(row.get('account_group', '')).lower()
        ]
        data = dict(trial_balance)
        data['rows'] = filtered
        data['row_count'] = len(filtered)
        return data

    @staticmethod
    def export_trial_balance_to_csv(report_data: Dict[str, Any], filename: str = "trial_balance") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Trial Balance'])
                writer.writerow(['As On Date:', report_data.get('as_on_date', '')])
                writer.writerow([])
                writer.writerow(['Code', 'Account', 'Group', 'Debit', 'Credit'])
                for row in report_data.get('rows', []):
                    writer.writerow([
                        row.get('account_code', ''),
                        row.get('account_name', ''),
                        row.get('account_group', ''),
                        f"{row.get('debit', 0):,.2f}",
                        f"{row.get('credit', 0):,.2f}",
                    ])
                writer.writerow([])
                totals = report_data.get('totals', {})
                writer.writerow(['', 'TOTAL', '', f"{totals.get('debit', 0):,.2f}", f"{totals.get('credit', 0):,.2f}"])
                writer.writerow(['Balanced:', 'Yes' if report_data.get('is_balanced') else 'No'])
            return True, str(file_path)
        except Exception as exc:
            logger.error(f"Error exporting trial balance: {exc}")
            return False, f"Export failed: {str(exc)}"


trial_balance_service = TrialBalanceService()
