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

    @staticmethod
    def recent_vouchers(company_id: int, limit: int = 8) -> List[Dict[str, Any]]:
        """Most recent non-cancelled vouchers."""
        vouchers = voucher_service.list_vouchers(
            company_id, include_cancelled=False)
        vouchers = voucher_service.enrich_vouchers_with_totals(vouchers)
        return vouchers[:limit]

    @staticmethod
    def get_dashboard(company_id: int) -> Dict[str, Any]:
        """Full dashboard dataset for a company."""
        today = date.today()
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
