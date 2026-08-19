"""
Balance Sheet Service
Assets = Liabilities + Capital (equity), as of a date, from the Expenzo
double-entry accounting data.

Classification: each account is resolved to a group type (Assets /
Liabilities / Capital / Income / Expense) via its ``account_group`` name,
falling back to common account names and finally to the Dr/Cr nature of the
balance. Income and Expense accounts fold into Capital as retained earnings,
so the balance sheet always reconciles.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.trial_balance_service import (
    TrialBalanceService,
    STATUS_CANCELLED,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TYPE_ASSETS = 'Assets'
TYPE_LIABILITIES = 'Liabilities'
TYPE_CAPITAL = 'Capital'
TYPE_INCOME = 'Income'
TYPE_EXPENSE = 'Expense'

# Group-name keywords -> balance-sheet type.
_ASSET_KEYWORDS = ('asset', 'cash', 'bank', 'debtor', 'receivable', 'fixed',
                   'investment', 'loan', 'advance', 'inventory', 'stock')
_LIABILITY_KEYWORDS = ('liabilit', 'creditor', 'payable', 'duty', 'tax',
                       'provision', 'loan', 'borrow')
_CAPITAL_KEYWORDS = ('capital', 'reserve', 'surplus', 'equity', 'drawing',
                     'owner', 'proprietor')
_INCOME_KEYWORDS = ('sales', 'income', 'revenue', 'receipt', 'interest', 'commission')
_EXPENSE_KEYWORDS = ('purchase', 'expense', 'expenditure', 'salary', 'rent',
                     'wages', 'electricity', 'telephone', 'repair', 'insurance',
                     'depreciation', 'advertising', 'miscellaneous')


class BalanceSheetService:
    """Balance sheet from Expenzo voucher data."""

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
    def _classify(group: str, name: str, opening_type: str) -> str:
        """Classify an account into a balance-sheet type."""
        group_lower = (group or '').lower()
        name_lower = (name or '').lower()
        haystack = f"{group_lower} {name_lower}"

        # Exact group names from the standard CoA seed.
        exact = {
            'cash-in-hand': TYPE_ASSETS,
            'bank accounts': TYPE_ASSETS,
            'sundry debtors': TYPE_ASSETS,
            'sundry creditors': TYPE_LIABILITIES,
            'fixed assets': TYPE_ASSETS,
            'current assets': TYPE_ASSETS,
            'current liabilities': TYPE_LIABILITIES,
            'loans & advances': TYPE_ASSETS,
            'duties & taxes': TYPE_LIABILITIES,
            'provisions': TYPE_LIABILITIES,
            'reserves & surplus': TYPE_CAPITAL,
            'sales accounts': TYPE_INCOME,
            'purchase accounts': TYPE_EXPENSE,
            'direct income': TYPE_INCOME,
            'indirect income': TYPE_INCOME,
            'direct expense': TYPE_EXPENSE,
            'indirect expense': TYPE_EXPENSE,
        }
        if group_lower in exact:
            return exact[group_lower]

        # Keyword scoring (longest keyword match wins).
        for keyword in _CAPITAL_KEYWORDS:
            if keyword in haystack:
                return TYPE_CAPITAL
        for keyword in _INCOME_KEYWORDS:
            if keyword in haystack:
                return TYPE_INCOME
        for keyword in _EXPENSE_KEYWORDS:
            if keyword in haystack:
                return TYPE_EXPENSE
        for keyword in _LIABILITY_KEYWORDS:
            if keyword in haystack:
                return TYPE_LIABILITIES
        for keyword in _ASSET_KEYWORDS:
            if keyword in haystack:
                return TYPE_ASSETS

        # Fall back to the Dr/Cr nature of the balance.
        return TYPE_ASSETS if opening_type == 'Debit' else TYPE_LIABILITIES

    @staticmethod
    def _opening_balance_adjustment(company_id: int) -> float:
        """Net opening balances (Debit total - Credit total).

        Double-entry requires every opening asset to be funded by an opening
        liability/capital.  When the books only carry opening balances on the
        Dr side (no balancing Capital entry), the trial balance is off by
        exactly this amount.  Adding it as a Credit capital entry makes the
        balance sheet reconcile without touching the data.
        """
        row = db.fetch_one(
            """
            SELECT
                COALESCE(SUM(CASE WHEN opening_balance_type = 'Debit'
                                  THEN opening_balance ELSE 0 END), 0) AS debit_total,
                COALESCE(SUM(CASE WHEN opening_balance_type = 'Credit'
                                  THEN opening_balance ELSE 0 END), 0) AS credit_total
            FROM accounts
            WHERE company_id = ? AND is_active = 1
            """,
            (company_id,),
        )
        debit_total = float(BalanceSheetService._row_value(row, 'debit_total', 0.0) or 0.0)
        credit_total = float(BalanceSheetService._row_value(row, 'credit_total', 0.0) or 0.0)
        return BalanceSheetService._round_amount(debit_total - credit_total)

    @staticmethod
    def generate_balance_sheet(
        company_id: int,
        as_on_date: date,
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        """Balance sheet as of a date. Income/Expense fold into Capital."""
        try:
            tb = TrialBalanceService.generate_trial_balance(
                company_id, as_on_date, include_inactive=include_inactive)
            if not tb.get('success'):
                return tb

            sections: Dict[str, List[Dict[str, Any]]] = {
                TYPE_ASSETS: [], TYPE_LIABILITIES: [], TYPE_CAPITAL: [],
            }
            income_total = 0.0
            expense_total = 0.0

            for row in tb.get('rows', []):
                account_id = row['account_id']
                account_row = db.fetch_one(
                    "SELECT name, account_group, opening_balance_type FROM accounts WHERE id = ?",
                    (account_id,),
                )
                name = BalanceSheetService._row_value(account_row, 'name', row['account_name'])
                group = BalanceSheetService._row_value(account_row, 'account_group', row['account_group'])
                opening_type = BalanceSheetService._row_value(
                    account_row, 'opening_balance_type', 'Debit')

                category = BalanceSheetService._classify(group, name, opening_type)
                # Signed net with credit-positive convention (income credits
                # are positive, expense debits are negative).
                net = float(row.get('credit', 0.0) or 0.0) - float(row.get('debit', 0.0) or 0.0)

                entry = {
                    'account_id': account_id,
                    'account_name': name,
                    'account_code': row.get('account_code', ''),
                    'account_group': group,
                    'net_balance': BalanceSheetService._round_amount(abs(net)),
                    'balance_type': 'Credit' if net >= 0 else 'Debit',
                }

                if category == TYPE_INCOME:
                    income_total += net
                elif category == TYPE_EXPENSE:
                    expense_total += net
                elif category in sections:
                    sections[category].append(entry)

            # Retained earnings = income + expense (credit-positive convention:
            # income credits are positive, expense debits are negative).
            retained_earnings = income_total + expense_total
            capital_entries = sections[TYPE_CAPITAL]
            if abs(retained_earnings) >= 0.01:
                capital_entries.append({
                    'account_id': None,
                    'account_name': 'Retained Earnings (Income - Expense)',
                    'account_code': '',
                    'account_group': 'P&L Summary',
                    'net_balance': BalanceSheetService._round_amount(abs(retained_earnings)),
                    'balance_type': 'Credit' if retained_earnings >= 0 else 'Debit',
                })

            # Opening balances must be funded by an opening liability/capital
            # (double entry).  When the books carry only Dr-side opening
            # balances, add the net as an Opening Capital Adjustment so the
            # balance sheet reconciles (Assets = Liabilities + Capital).
            opening_adjustment = BalanceSheetService._opening_balance_adjustment(company_id)
            if abs(opening_adjustment) >= 0.01:
                capital_entries.append({
                    'account_id': None,
                    'account_name': 'Opening Balance Adjustment',
                    'account_code': '',
                    'account_group': 'Capital',
                    'net_balance': BalanceSheetService._round_amount(abs(opening_adjustment)),
                    'balance_type': 'Credit' if opening_adjustment >= 0 else 'Debit',
                })

            def section_total(entries: List[Dict[str, Any]], debit_positive: bool) -> float:
                """Sum section balances. For Assets, Debit is positive; for
                Liabilities/Capital, Credit is positive."""
                total = 0.0
                for entry in entries:
                    is_debit = entry['balance_type'] == 'Debit'
                    if debit_positive:
                        signed = entry['net_balance'] if is_debit else -entry['net_balance']
                    else:
                        signed = entry['net_balance'] if not is_debit else -entry['net_balance']
                    total += signed
                return BalanceSheetService._round_amount(total)

            total_assets = section_total(sections[TYPE_ASSETS], debit_positive=True)
            total_liabilities = section_total(sections[TYPE_LIABILITIES], debit_positive=False)
            total_capital = section_total(sections[TYPE_CAPITAL], debit_positive=False)
            total_liab_capital = BalanceSheetService._round_amount(total_liabilities + total_capital)

            return {
                'success': True,
                'report_type': 'Balance Sheet',
                'company_id': company_id,
                'as_on_date': as_on_date.isoformat(),
                'sections': sections,
                'income_total': BalanceSheetService._round_amount(income_total),
                'expense_total': BalanceSheetService._round_amount(expense_total),
                'retained_earnings': BalanceSheetService._round_amount(retained_earnings),
                'totals': {
                    'total_assets': total_assets,
                    'total_liabilities': total_liabilities,
                    'total_capital': total_capital,
                    'total_liabilities_capital': total_liab_capital,
                },
                'is_balanced': abs(total_assets - total_liab_capital) < 0.01,
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error(f"Error generating balance sheet: {exc}")
            return {'success': False, 'error': f"Failed to generate balance sheet: {str(exc)}"}

    @staticmethod
    def export_balance_sheet_to_csv(report_data: Dict[str, Any], filename: str = "balance_sheet") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Balance Sheet'])
                writer.writerow(['As On Date:', report_data.get('as_on_date', '')])
                writer.writerow([])
                writer.writerow(['LIABILITIES & CAPITAL', '', 'ASSETS', ''])
                writer.writerow(['Account', 'Amount', 'Account', 'Amount'])
                sections = report_data.get('sections', {})
                liability_entries = sections.get(TYPE_LIABILITIES, [])
                capital_entries = sections.get(TYPE_CAPITAL, [])
                asset_entries = sections.get(TYPE_ASSETS, [])
                left = liability_entries + capital_entries
                right = asset_entries
                for i in range(max(len(left), len(right))):
                    l_entry = left[i] if i < len(left) else {}
                    r_entry = right[i] if i < len(right) else {}
                    writer.writerow([
                        l_entry.get('account_name', ''),
                        f"{l_entry.get('net_balance', 0):,.2f}" if l_entry else '',
                        r_entry.get('account_name', ''),
                        f"{r_entry.get('net_balance', 0):,.2f}" if r_entry else '',
                    ])
                writer.writerow([])
                totals = report_data.get('totals', {})
                writer.writerow([
                    'Total Liabilities & Capital',
                    f"{totals.get('total_liabilities_capital', 0):,.2f}",
                    'Total Assets',
                    f"{totals.get('total_assets', 0):,.2f}",
                ])
                writer.writerow(['Balanced:', 'Yes' if report_data.get('is_balanced') else 'No'])
            return True, str(file_path)
        except Exception as exc:
            logger.error(f"Error exporting balance sheet: {exc}")
            return False, f"Export failed: {str(exc)}"


balance_sheet_service = BalanceSheetService()
