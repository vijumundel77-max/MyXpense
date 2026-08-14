"""
Profit & Loss Service
Total Income vs Total Expense with Net Profit/Loss, from the Expenzo
double-entry accounting data (accounts + voucher_details).

Every account is classified by its ``account_group`` nature (Income or
Expense, resolved the same way as the Balance Sheet service).  Income and
expense activity is summed from non-cancelled vouchers in the date range;
Net Profit/Loss = Income - Expense.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.balance_sheet_service import (
    TYPE_INCOME,
    TYPE_EXPENSE,
    BalanceSheetService,
)
from services.trial_balance_service import TrialBalanceService, STATUS_CANCELLED

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProfitLossService:
    """Profit & Loss from Expenzo voucher data."""

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
    def _accounts(company_id: int) -> List[Dict[str, Any]]:
        rows = db.fetch_all(
            """
            SELECT id, company_id, name, code, account_group,
                   opening_balance, opening_balance_type, is_active
            FROM accounts
            WHERE company_id = ?
            ORDER BY name
            """,
            (company_id,),
        )
        accounts: List[Dict[str, Any]] = []
        for row in rows:
            accounts.append({
                'id': ProfitLossService._row_value(row, 'id'),
                'company_id': ProfitLossService._row_value(row, 'company_id'),
                'name': ProfitLossService._row_value(row, 'name', ''),
                'code': ProfitLossService._row_value(row, 'code', ''),
                'account_group': ProfitLossService._row_value(row, 'account_group', ''),
                'opening_balance': float(ProfitLossService._row_value(row, 'opening_balance', 0.0) or 0.0),
                'opening_balance_type': ProfitLossService._row_value(row, 'opening_balance_type', 'Debit'),
                'is_active': bool(ProfitLossService._row_value(row, 'is_active', 1)),
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
            account_id = int(ProfitLossService._row_value(row, 'account_id') or 0)
            activity[account_id] = (
                float(ProfitLossService._row_value(row, 'total_debit', 0.0) or 0.0),
                float(ProfitLossService._row_value(row, 'total_credit', 0.0) or 0.0),
            )
        return activity

    @staticmethod
    def generate_profit_loss(
        company_id: int,
        from_date: date,
        to_date: date,
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        """Profit & Loss for a period.

        Income rows: accounts whose nature is Income (credit activity counts
        positive, debit activity subtracts).  Expense rows: accounts whose
        nature is Expense (debit activity counts positive, credit subtracts).
        Net Profit/Loss = Income - Expense.
        """
        try:
            accounts = ProfitLossService._accounts(company_id)
            activity = ProfitLossService._account_activity(company_id, from_date, to_date)

            income_rows: List[Dict[str, Any]] = []
            expense_rows: List[Dict[str, Any]] = []
            income_total = 0.0
            expense_total = 0.0

            for account in accounts:
                if not include_inactive and not account['is_active']:
                    continue
                debit, credit = activity.get(account['id'], (0.0, 0.0))
                if debit <= 0 and credit <= 0:
                    continue
                group = account['account_group']
                name = account['name']
                opening_type = account['opening_balance_type']
                category = BalanceSheetService._classify(group, name, opening_type)

                # Credit-positive convention: income credits are positive,
                # expense debits are negative.
                net = ProfitLossService._round_amount(credit - debit)

                if category == TYPE_INCOME and abs(net) >= 0.005:
                    income_rows.append({
                        'account_id': account['id'],
                        'account_name': name,
                        'account_code': account['code'],
                        'account_group': group,
                        'debit': 0.0,
                        'credit': ProfitLossService._round_amount(net),
                    })
                    income_total += net
                elif category == TYPE_EXPENSE and abs(net) >= 0.005:
                    expense_rows.append({
                        'account_id': account['id'],
                        'account_name': name,
                        'account_code': account['code'],
                        'account_group': group,
                        'debit': ProfitLossService._round_amount(abs(net)),
                        'credit': 0.0,
                    })
                    # Expense totals are positive amounts; the net calculation
                    # subtracts them from income.
                    expense_total += abs(net)

            income_total = ProfitLossService._round_amount(income_total)
            expense_total = ProfitLossService._round_amount(expense_total)
            net_profit_loss = ProfitLossService._round_amount(income_total - expense_total)

            return {
                'success': True,
                'report_type': 'Profit & Loss',
                'company_id': company_id,
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'income_rows': income_rows,
                'expense_rows': expense_rows,
                'income_total': income_total,
                'expense_total': expense_total,
                'net_profit_loss': net_profit_loss,
                'is_profit': net_profit_loss >= 0,
                'row_count': len(income_rows) + len(expense_rows),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error(f"Error generating profit & loss: {exc}")
            return {'success': False, 'error': f"Failed to generate profit & loss: {str(exc)}"}

    @staticmethod
    def search_rows(profit_loss: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        """Filter P&L rows by account name/code/group."""
        if not profit_loss.get('success'):
            return profit_loss
        term = search_term.lower()
        data = dict(profit_loss)
        data['income_rows'] = [
            r for r in profit_loss.get('income_rows', [])
            if term in str(r.get('account_name', '')).lower()
            or term in str(r.get('account_code', '')).lower()
            or term in str(r.get('account_group', '')).lower()
        ]
        data['expense_rows'] = [
            r for r in profit_loss.get('expense_rows', [])
            if term in str(r.get('account_name', '')).lower()
            or term in str(r.get('account_code', '')).lower()
            or term in str(r.get('account_group', '')).lower()
        ]
        data['row_count'] = len(data['income_rows']) + len(data['expense_rows'])
        return data

    @staticmethod
    def export_profit_loss_to_csv(report_data: Dict[str, Any], filename: str = "profit_loss") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Profit & Loss'])
                writer.writerow(['Period:', f"{report_data.get('from_date', '')} to {report_data.get('to_date', '')}"])
                writer.writerow([])
                writer.writerow(['Income'])
                writer.writerow(['Account', 'Amount'])
                for row in report_data.get('income_rows', []):
                    writer.writerow([
                        row.get('account_name', ''),
                        f"{row.get('credit', 0):,.2f}",
                    ])
                writer.writerow(['Total Income', f"{report_data.get('income_total', 0):,.2f}"])
                writer.writerow([])
                writer.writerow(['Expense'])
                writer.writerow(['Account', 'Amount'])
                for row in report_data.get('expense_rows', []):
                    writer.writerow([
                        row.get('account_name', ''),
                        f"{row.get('debit', 0):,.2f}",
                    ])
                writer.writerow(['Total Expense', f"{report_data.get('expense_total', 0):,.2f}"])
                writer.writerow([])
                writer.writerow(['Net Profit / Loss', f"{report_data.get('net_profit_loss', 0):,.2f}"])
            return True, str(file_path)
        except Exception as exc:
            logger.error(f"Error exporting profit & loss: {exc}")
            return False, f"Export failed: {str(exc)}"


profit_loss_service = ProfitLossService()
