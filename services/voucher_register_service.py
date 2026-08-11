"""
Voucher Register Service (Day Book)
Lists all vouchers for a company as a chronological register with line
details, used by the Day Book report and voucher history screens.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.voucher_service import (
    VoucherService,
    STATUS_CANCELLED,
    VOUCHER_TYPES,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VoucherRegisterService:
    """Day Book / voucher register service."""

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
    def generate_day_book(
        company_id: int,
        from_date: date,
        to_date: date,
        voucher_type: str = "",
        search_term: str = "",
    ) -> Dict[str, Any]:
        """Day Book register: one row per voucher detail line."""
        try:
            where = ["v.company_id = ?", "v.voucher_date >= ?", "v.voucher_date <= ?",
                     "v.status != ?"]
            params: List[Any] = [company_id, from_date.isoformat(), to_date.isoformat(),
                                 STATUS_CANCELLED]
            if voucher_type:
                where.append("v.voucher_type = ?")
                params.append(voucher_type)
            if search_term:
                term = f"%{search_term.lower()}%"
                where.append(
                    "(LOWER(v.voucher_number) LIKE ? OR LOWER(v.reference_number) LIKE ? "
                    "OR LOWER(v.narration) LIKE ? OR LOWER(a.name) LIKE ?)"
                )
                params.extend([term, term, term, term])

            rows = db.fetch_all(
                f"""
                SELECT
                    v.id AS voucher_id,
                    v.voucher_number,
                    v.voucher_type,
                    v.voucher_date,
                    v.reference_number,
                    v.narration,
                    v.due_date,
                    v.status,
                    vd.id AS detail_id,
                    vd.debit_amount,
                    vd.credit_amount,
                    vd.narration AS detail_narration,
                    a.id AS account_id,
                    a.name AS account_name,
                    a.code AS account_code,
                    a.account_group
                FROM voucher_details vd
                JOIN vouchers v ON v.id = vd.voucher_id
                LEFT JOIN accounts a ON a.id = vd.account_id
                WHERE {' AND '.join(where)}
                ORDER BY v.voucher_date, v.id, vd.id
                """,
                tuple(params),
            )

            entries: List[Dict[str, Any]] = []
            total_debit = 0.0
            total_credit = 0.0
            for row in rows:
                debit = float(VoucherRegisterService._row_value(row, 'debit_amount', 0.0) or 0.0)
                credit = float(VoucherRegisterService._row_value(row, 'credit_amount', 0.0) or 0.0)
                total_debit += debit
                total_credit += credit
                entries.append({
                    'voucher_id': VoucherRegisterService._row_value(row, 'voucher_id'),
                    'voucher_number': VoucherRegisterService._row_value(row, 'voucher_number', ''),
                    'voucher_type': VoucherRegisterService._row_value(row, 'voucher_type', ''),
                    'voucher_date': VoucherRegisterService._row_value(row, 'voucher_date', ''),
                    'reference_number': VoucherRegisterService._row_value(row, 'reference_number', ''),
                    'narration': VoucherRegisterService._row_value(row, 'narration', ''),
                    'due_date': VoucherRegisterService._row_value(row, 'due_date'),
                    'detail_id': VoucherRegisterService._row_value(row, 'detail_id'),
                    'account_id': VoucherRegisterService._row_value(row, 'account_id'),
                    'account_name': VoucherRegisterService._row_value(row, 'account_name', ''),
                    'account_code': VoucherRegisterService._row_value(row, 'account_code', ''),
                    'account_group': VoucherRegisterService._row_value(row, 'account_group', ''),
                    'detail_narration': VoucherRegisterService._row_value(row, 'detail_narration', ''),
                    'debit_amount': debit,
                    'credit_amount': credit,
                    'status': VoucherRegisterService._row_value(row, 'status', ''),
                })

            return {
                'success': True,
                'report_type': 'Day Book',
                'company_id': company_id,
                'from_date': from_date.isoformat(),
                'to_date': to_date.isoformat(),
                'entries': entries,
                'totals': {
                    'debit': round(total_debit, 2),
                    'credit': round(total_credit, 2),
                },
                'entry_count': len(entries),
                'generated_at': datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.error(f"Error generating day book: {exc}")
            return {'success': False, 'error': f"Failed to generate day book: {str(exc)}"}

    @staticmethod
    def export_day_book_to_csv(report_data: Dict[str, Any], filename: str = "day_book") -> Tuple[bool, str]:
        try:
            if not report_data.get('success'):
                return False, "Invalid report data"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Day Book'])
                writer.writerow(['Period:', f"{report_data.get('from_date', '')} to {report_data.get('to_date', '')}"])
                writer.writerow([])
                writer.writerow(['Date', 'Voucher No.', 'Type', 'Reference', 'Account', 'Narration', 'Debit', 'Credit'])
                for entry in report_data.get('entries', []):
                    writer.writerow([
                        entry.get('voucher_date', ''),
                        entry.get('voucher_number', ''),
                        entry.get('voucher_type', ''),
                        entry.get('reference_number', ''),
                        entry.get('account_name', ''),
                        entry.get('detail_narration', '') or entry.get('narration', ''),
                        f"{entry.get('debit_amount', 0):,.2f}",
                        f"{entry.get('credit_amount', 0):,.2f}",
                    ])
                writer.writerow([])
                totals = report_data.get('totals', {})
                writer.writerow(['Totals', '', '', '', '', '', f"{totals.get('debit', 0):,.2f}", f"{totals.get('credit', 0):,.2f}"])
            return True, str(file_path)
        except Exception as exc:
            logger.error(f"Error exporting day book: {exc}")
            return False, f"Export failed: {str(exc)}"


voucher_register_service = VoucherRegisterService()
