"""
Dashboard Service
Aggregates real accounting figures for the dashboard from the existing
Expenzo services — no duplicate data source. All figures are company-scoped,
exclude cancelled vouchers, and agree with the Cash Book / Bank Book /
Outstanding reports.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database.database import db
from services.cash_book_service import cash_book_service
from services.outstanding_report_service import outstanding_report_service
from services.voucher_service import (
    voucher_service,
    STATUS_CANCELLED,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DashboardService:
    """Real accounting dashboard metrics."""

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
    def company_name(company_id: int) -> str:
        row = db.fetch_one("SELECT name FROM companies WHERE id = ?", (company_id,))
        return str(DashboardService._row_value(row, 'name', '') or 'No Company')

    @staticmethod
    def cash_balance(company_id: int, as_on: Optional[date] = None) -> float:
        """Cash balance = Cash Book closing balance as of the given date."""
        as_on = as_on or date.today()
        report = cash_book_service.generate_cash_book(company_id, date(1900, 1, 1), as_on)
        if not report.get('success'):
            return 0.0
        closing = report.get('closing_balance', {})
        amount = float(closing.get('amount', 0.0) or 0.0)
        return -amount if closing.get('type') == 'Credit' else amount

    @staticmethod
    def bank_balance(company_id: int, as_on: Optional[date] = None) -> float:
        """Bank balance = Bank Book closing balance as of the given date."""
        as_on = as_on or date.today()
        report = cash_book_service.generate_bank_book(company_id, date(1900, 1, 1), as_on)
        if not report.get('success'):
            return 0.0
        closing = report.get('closing_balance', {})
        amount = float(closing.get('amount', 0.0) or 0.0)
        return -amount if closing.get('type') == 'Credit' else amount

    @staticmethod
    def receivables(company_id: int, as_on: Optional[date] = None) -> float:
        """Total receivables from the Outstanding report."""
        as_on = as_on or date.today()
        report = outstanding_report_service.generate_outstanding_report(
            company_id, 'Receivable', as_on, include_zero_balance=False)
        if not report.get('success'):
            return 0.0
        return float(report.get('totals', {}).get('total_receivable', 0.0) or 0.0)

    @staticmethod
    def payables(company_id: int, as_on: Optional[date] = None) -> float:
        """Total payables from the Outstanding report."""
        as_on = as_on or date.today()
        report = outstanding_report_service.generate_outstanding_report(
            company_id, 'Payable', as_on, include_zero_balance=False)
        if not report.get('success'):
            return 0.0
        return float(report.get('totals', {}).get('total_payable', 0.0) or 0.0)

    @staticmethod
    def _book_totals(company_id: int, from_date: date, to_date: date) -> Dict[str, float]:
        """Receipts (money in) and payments (money out) for cash + bank over
        a period, from the Cash Book and Bank Book."""
        receipts = 0.0
        payments = 0.0
        for generator in (cash_book_service.generate_cash_book, cash_book_service.generate_bank_book):
            report = generator(company_id, from_date, to_date)
            if report.get('success'):
                receipts += float(report.get('receipts', 0.0) or 0.0)
                payments += float(report.get('payments', 0.0) or 0.0)
        return {'receipts': round(receipts, 2), 'payments': round(payments, 2)}

    @staticmethod
    def today_totals(company_id: int, today: Optional[date] = None) -> Dict[str, float]:
        """Today's receipts and payments (cash + bank)."""
        today = today or date.today()
        return DashboardService._book_totals(company_id, today, today)

    @staticmethod
    def month_totals(company_id: int, today: Optional[date] = None) -> Dict[str, float]:
        """Receipts and payments for the current calendar month."""
        today = today or date.today()
        first = date(today.year, today.month, 1)
        return DashboardService._book_totals(company_id, first, today)

    _BOOK_GROUPS = ('Cash-in-Hand', 'Bank Accounts')

    @staticmethod
    def _active_accounts_in_group(company_id: int, group: str) -> List[Dict[str, Any]]:
        """Active accounts in a ledger group (read-only list for drill-downs)."""
        rows = db.fetch_all(
            """
            SELECT id, name, code FROM accounts
            WHERE company_id = ? AND LOWER(account_group) = LOWER(?) AND is_active = 1
            ORDER BY name
            """,
            (company_id, group),
        )
        return [
            {
                'id': DashboardService._row_value(row, 'id'),
                'name': DashboardService._row_value(row, 'name', ''),
                'code': DashboardService._row_value(row, 'code', ''),
            }
            for row in rows
        ]

    @staticmethod
    def bank_accounts(company_id: int, as_on: Optional[date] = None) -> List[Dict[str, Any]]:
        """Per-bank-account current balances.

        Each account's balance is the Bank Book closing balance as of the
        given date — the same generator behind ``bank_balance`` — so the
        account balances always sum to the dashboard's bank balance.
        """
        as_on = as_on or date.today()
        accounts: List[Dict[str, Any]] = []
        for account in DashboardService._active_accounts_in_group(company_id, 'Bank Accounts'):
            report = cash_book_service.generate_bank_book(
                company_id, date(1900, 1, 1), as_on, account_id=account['id'])
            if not report.get('success'):
                continue
            closing = report.get('closing_balance', {})
            amount = float(closing.get('amount', 0.0) or 0.0)
            signed = -amount if closing.get('type') == 'Credit' else amount
            accounts.append({
                'account_id': account['id'],
                'account_name': account['name'],
                'account_code': account['code'],
                'balance': signed,
            })
        return accounts

    @staticmethod
    def _party_outstanding(company_id: int, outstanding_type: str,
                           as_on: Optional[date] = None) -> List[Dict[str, Any]]:
        """Parties with a non-zero outstanding balance (receivable/payable)."""
        as_on = as_on or date.today()
        report = outstanding_report_service.generate_outstanding_report(
            company_id, outstanding_type, as_on, include_zero_balance=False)
        if not report.get('success'):
            return []
        return [
            {
                'party_id': DashboardService._row_value(party, 'account_id'),
                'party_name': DashboardService._row_value(party, 'account_name', ''),
                'party_code': DashboardService._row_value(party, 'account_code', ''),
                'outstanding': float(DashboardService._row_value(party, 'outstanding_balance', 0.0) or 0.0),
            }
            for party in report.get('parties', [])
        ]

    @staticmethod
    def receivable_parties(company_id: int, as_on: Optional[date] = None) -> List[Dict[str, Any]]:
        """Parties/customers money is owed to us by (receivables drill-down)."""
        return DashboardService._party_outstanding(company_id, 'Receivable', as_on)

    @staticmethod
    def payable_parties(company_id: int, as_on: Optional[date] = None) -> List[Dict[str, Any]]:
        """Parties/suppliers we owe money to (payables drill-down)."""
        return DashboardService._party_outstanding(company_id, 'Payable', as_on)

    @staticmethod
    def _month_book_movements(company_id: int, day: Optional[date] = None) -> List[Dict[str, Any]]:
        """Cash + bank detail lines for the current month with the
        counterparty account (the party on the other side of the voucher).

        Receipt/Payment classification mirrors the Cash/Bank Book logic:
        a book line with debit > credit is a Receipt, credit > debit is a
        Payment, so the line amounts always reconcile to ``month_totals``.
        """
        day = day or date.today()
        first = date(day.year, day.month, 1)
        placeholders = ','.join('?' * len(DashboardService._BOOK_GROUPS))
        rows = db.fetch_all(
            f"""
            SELECT
                v.id AS voucher_id,
                v.voucher_number,
                v.voucher_type,
                v.voucher_date,
                v.reference_number,
                v.narration,
                vd.id AS detail_id,
                vd.debit_amount,
                vd.credit_amount,
                a.name AS book_account,
                (SELECT GROUP_CONCAT(COALESCE(ca.name, ''))
                   FROM voucher_details od
                   LEFT JOIN accounts ca ON ca.id = od.account_id
                   WHERE od.voucher_id = v.id
                     AND od.id != vd.id
                     AND (od.debit_amount > 0 OR od.credit_amount > 0))
                  AS counterparties
            FROM voucher_details vd
            JOIN vouchers v ON v.id = vd.voucher_id
            LEFT JOIN accounts a ON a.id = vd.account_id
            WHERE v.company_id = ?
              AND v.status != ?
              AND LOWER(a.account_group) IN ({placeholders})
              AND a.is_active = 1
              AND v.voucher_date >= ?
              AND v.voucher_date <= ?
            ORDER BY v.voucher_date, v.id, vd.id
            """,
            tuple([company_id, STATUS_CANCELLED])
            + tuple(g.lower() for g in DashboardService._BOOK_GROUPS)
            + (first.isoformat(), day.isoformat()),
        )

        movements: List[Dict[str, Any]] = []
        for row in rows:
            debit = float(DashboardService._row_value(row, 'debit_amount', 0.0) or 0.0)
            credit = float(DashboardService._row_value(row, 'credit_amount', 0.0) or 0.0)
            party = (DashboardService._row_value(row, 'counterparties', '')
                     or DashboardService._row_value(row, 'book_account', ''))
            if debit > credit:
                movements.append({
                    'date': DashboardService._row_value(row, 'voucher_date', ''),
                    'party': party,
                    'voucher_number': DashboardService._row_value(row, 'voucher_number', ''),
                    'voucher_type': DashboardService._row_value(row, 'voucher_type', ''),
                    'amount': debit,
                    'kind': 'Receipt',
                })
            elif credit > debit:
                movements.append({
                    'date': DashboardService._row_value(row, 'voucher_date', ''),
                    'party': party,
                    'voucher_number': DashboardService._row_value(row, 'voucher_number', ''),
                    'voucher_type': DashboardService._row_value(row, 'voucher_type', ''),
                    'amount': credit,
                    'kind': 'Payment',
                })
        return movements

    @staticmethod
    def month_receipts(company_id: int, day: Optional[date] = None) -> List[Dict[str, Any]]:
        """All current-month receipts (money into cash/bank) up to ``day``."""
        return [m for m in DashboardService._month_book_movements(company_id, day)
                if m['kind'] == 'Receipt']

    @staticmethod
    def month_payments(company_id: int, day: Optional[date] = None) -> List[Dict[str, Any]]:
        """All current-month payments (money out of cash/bank) up to ``day``."""
        return [m for m in DashboardService._month_book_movements(company_id, day)
                if m['kind'] == 'Payment']

    @staticmethod
    def recent_vouchers(company_id: int, limit: int = 8) -> List[Dict[str, Any]]:
        """Most recent non-cancelled vouchers."""
        vouchers = voucher_service.list_vouchers(
            company_id, include_cancelled=False)
        vouchers = voucher_service.enrich_vouchers_with_totals(vouchers)
        return vouchers[:limit]

    @staticmethod
    def get_dashboard(company_id: int, as_on: Optional[date] = None) -> Dict[str, Any]:
        """Full dashboard dataset for a company.

        ``as_on`` controls the reference date for every metric (defaults to
        today): balances/receivables/payables are as-of that date and the
        day/month totals are computed for the day/month containing it.
        """
        today = as_on or date.today()
        day_totals = DashboardService.today_totals(company_id, today)
        month_totals = DashboardService.month_totals(company_id, today)
        return {
            'company_id': company_id,
            'company_name': DashboardService.company_name(company_id),
            'as_on': today.isoformat(),
            'cash_balance': round(DashboardService.cash_balance(company_id, today), 2),
            'bank_balance': round(DashboardService.bank_balance(company_id, today), 2),
            'receivables': round(DashboardService.receivables(company_id, today), 2),
            'payables': round(DashboardService.payables(company_id, today), 2),
            'today_receipts': day_totals['receipts'],
            'today_payments': day_totals['payments'],
            'month_receipts': month_totals['receipts'],
            'month_payments': month_totals['payments'],
            'recent_vouchers': DashboardService.recent_vouchers(company_id),
        }


dashboard_service = DashboardService()
