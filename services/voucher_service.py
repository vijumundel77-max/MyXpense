"""
Voucher Service
Double-entry voucher CRUD over the Expenzo ``vouchers`` / ``voucher_details``
schema. Every saved voucher carries balanced debit and credit entries.

Legacy helpers (create_voucher / add_voucher_detail / post_voucher) are kept
for the report-service tests; new UI flows use the atomic save_voucher /
update_voucher / cancel_voucher API.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from database.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VOUCHER_PAYMENT = 'Payment'
VOUCHER_RECEIPT = 'Receipt'
VOUCHER_CONTRA = 'Contra'
VOUCHER_JOURNAL = 'Journal'
VOUCHER_SALES = 'Sales'
VOUCHER_PURCHASE = 'Purchase'

VOUCHER_TYPES = (
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    VOUCHER_CONTRA,
    VOUCHER_JOURNAL,
    VOUCHER_SALES,
    VOUCHER_PURCHASE,
)

VOUCHER_TYPE_PREFIX = {
    VOUCHER_PAYMENT: 'PV',
    VOUCHER_RECEIPT: 'RV',
    VOUCHER_CONTRA: 'CV',
    VOUCHER_JOURNAL: 'JV',
    VOUCHER_SALES: 'SV',
    VOUCHER_PURCHASE: 'PC',
}

STATUS_POSTED = 'Posted'
STATUS_CANCELLED = 'Cancelled'

ACTIVE_STATUSES = (STATUS_POSTED,)

# Ledger groups that represent physical money (used by Contra / Journal
# rules).  Kept in sync with the seeded Chart of Accounts group names.
CASH_GROUPS = ('Cash-in-Hand',)
BANK_GROUPS = ('Bank Accounts',)
CASH_BANK_GROUPS = CASH_GROUPS + BANK_GROUPS
PARTY_GROUPS = ('Sundry Debtors', 'Sundry Creditors')
INCOME_GROUPS = ('Sales Accounts', 'Direct Incomes', 'Indirect Incomes',
                 'Retained Earnings')
EXPENSE_GROUPS = ('Purchase Accounts', 'Direct Expenses', 'Indirect Expenses',
                  'Misc. Expenses (ASSET)')


class VoucherValidationError(Exception):
    """Raised when a voucher entry fails validation."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class VoucherService:
    """Service for double-entry voucher CRUD."""

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

    # ------------------------------------------------------------------ #
    # legacy API (kept for report-service tests)
    # ------------------------------------------------------------------ #
    @staticmethod
    def create_voucher(
        company_id: int,
        voucher_type: str,
        voucher_date: date,
        voucher_number: str,
        reference_number: str = "",
        narration: str = "",
        due_date: Optional[date] = None,
        status: str = 'Draft',
    ) -> int:
        return db.execute(
            """
            INSERT INTO vouchers (
                company_id, voucher_type, voucher_date, voucher_number,
                reference_number, narration, due_date, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                voucher_type,
                voucher_date.isoformat(),
                voucher_number,
                reference_number,
                narration,
                due_date.isoformat() if due_date else None,
                status,
            ),
        )

    @staticmethod
    def add_voucher_detail(
        voucher_id: int,
        account_id: int,
        debit_amount: float = 0.0,
        credit_amount: float = 0.0,
        narration: str = "",
        contra_account_id: Optional[int] = None,
    ) -> int:
        return db.execute(
            """
            INSERT INTO voucher_details (
                voucher_id, account_id, debit_amount, credit_amount,
                narration, contra_account_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (voucher_id, account_id, debit_amount, credit_amount, narration, contra_account_id),
        )

    @staticmethod
    def post_voucher(voucher_id: int) -> bool:
        db.execute(
            "UPDATE vouchers SET status = ? WHERE id = ?",
            (STATUS_POSTED, voucher_id),
        )
        return True

    # ------------------------------------------------------------------ #
    # new double-entry API
    # ------------------------------------------------------------------ #
    @staticmethod
    def next_voucher_number(company_id: int, voucher_type: str) -> str:
        """Next sequential voucher number for a company + type, e.g. PV-0001.

        The sequence is derived from existing voucher numbers (not the
        autoincrement id) so test databases that clear rows still number
        from 1.
        """
        prefix = VOUCHER_TYPE_PREFIX.get(voucher_type, 'JV')
        rows = db.fetch_all(
            """
            SELECT voucher_number FROM vouchers
            WHERE company_id = ? AND voucher_type = ?
            """,
            (company_id, voucher_type),
        )
        max_seq = 0
        for row in rows:
            number = VoucherService._row_value(row, 'voucher_number', '')
            if number and '-' in str(number):
                try:
                    seq = int(str(number).rsplit('-', 1)[1])
                    max_seq = max(max_seq, seq)
                except ValueError:
                    continue
        return f"{prefix}-{max_seq + 1:04d}"

    @staticmethod
    def _account_group(account_id: int) -> str:
        """The account_group for a ledger id (cached per call-site)."""
        row = db.fetch_one("SELECT account_group FROM accounts WHERE id = ?", (account_id,))
        return str(VoucherService._row_value(row, 'account_group', '') or '')

    @staticmethod
    def _group_is_cash_bank(group: str) -> bool:
        return str(group or '').strip().lower() in {g.lower() for g in CASH_BANK_GROUPS}

    @staticmethod
    def _group_is_party(group: str) -> bool:
        return str(group or '').strip().lower() in {g.lower() for g in PARTY_GROUPS}

    @staticmethod
    def _group_is_income(group: str) -> bool:
        return str(group or '').strip().lower() in {g.lower() for g in INCOME_GROUPS}

    @staticmethod
    def _group_is_expense_or_asset(group: str) -> bool:
        low = str(group or '').strip().lower()
        if low in {g.lower() for g in EXPENSE_GROUPS}:
            return True
        if low in ('fixed assets', 'current assets', 'investments',
                   'loans & advances', 'stock-in-hand', 'capital account'):
            return True
        return False

    @staticmethod
    def _validate_entries(
        company_id: int,
        entries: List[Dict[str, Any]],
        voucher_type: str = "",
    ) -> None:
        """Validate a double-entry list. Raises VoucherValidationError.

        Universal rules (all voucher types):
          - non-empty, amounts > 0, no negatives, no entry that is both
            Dr and Cr, account exists / active / owned by the company
          - sum(DEBIT) == sum(CREDIT)

        Per-type rules (the 6-voucher Tally-style model):
          - CONTRA   : every ledger must be Cash/Bank.
          - PAYMENT  : >= 1 Credit on Cash/Bank and >= 1 Debit on a
                       non-Cash/Bank ledger (expense / party / asset).
          - RECEIPT  : >= 1 Debit on Cash/Bank and >= 1 Credit on a
                       non-Cash/Bank ledger (income / party / capital).
          - JOURNAL  : no Cash or Bank ledger allowed.
          - SALES    : >= 1 Credit on a Sales/Income ledger and >= 1 Debit
                       on a party (Sundry Debtor) or Cash/Bank ledger.
          - PURCHASE : >= 1 Debit on a Purchase/Expense/Asset ledger and
                       >= 1 Credit on a party (Sundry Creditor) or Cash/Bank.
        """
        if not entries:
            raise VoucherValidationError("At least one debit and one credit entry are required.")

        debit_total = 0.0
        credit_total = 0.0
        account_names: Dict[int, str] = {}
        entry_groups: Dict[int, str] = {}
        debit_entries: List[Dict[str, Any]] = []
        credit_entries: List[Dict[str, Any]] = []

        for entry in entries:
            account_id = entry.get('account_id')
            debit = float(entry.get('debit_amount', 0.0) or 0.0)
            credit = float(entry.get('credit_amount', 0.0) or 0.0)

            if not account_id:
                raise VoucherValidationError("Every entry needs an account.")
            if debit < 0 or credit < 0:
                raise VoucherValidationError("Amounts cannot be negative.")
            if debit > 0 and credit > 0:
                raise VoucherValidationError("An entry cannot be both debit and credit.")

            account = db.fetch_one(
                "SELECT id, name, is_active, company_id FROM accounts WHERE id = ?",
                (account_id,),
            )
            if not account:
                raise VoucherValidationError("Selected account does not exist.")
            if int(account['company_id']) != int(company_id):
                raise VoucherValidationError(
                    f"Account '{account['name']}' belongs to a different company.")
            if not bool(account['is_active']):
                raise VoucherValidationError(
                    f"Account '{account['name']}' is inactive and cannot be used.")
            account_names[account_id] = account['name']
            group = VoucherService._account_group(account_id)
            entry_groups[account_id] = group

            debit_total += debit
            credit_total += credit
            if debit > 0:
                debit_entries.append({'account_id': account_id, 'amount': debit,
                                      'group': group})
            if credit > 0:
                credit_entries.append({'account_id': account_id, 'amount': credit,
                                       'group': group})

        if debit_total <= 0 and credit_total <= 0:
            raise VoucherValidationError("Amount must be greater than zero.")
        if round(debit_total, 2) != round(credit_total, 2):
            raise VoucherValidationError(
                f"Voucher is not balanced: Debit {debit_total:,.2f} != Credit {credit_total:,.2f}")

        # ---- per-type rules ------------------------------------------------- #
        if voucher_type == VOUCHER_CONTRA:
            for account_id in entry_groups:
                if not VoucherService._group_is_cash_bank(entry_groups[account_id]):
                    raise VoucherValidationError(
                        f"CONTRA allows only Cash or Bank ledgers — "
                        f"'{account_names[account_id]}' belongs to "
                        f"'{entry_groups[account_id]}'.")

        elif voucher_type == VOUCHER_JOURNAL:
            for account_id in entry_groups:
                if VoucherService._group_is_cash_bank(entry_groups[account_id]):
                    raise VoucherValidationError(
                        f"JOURNAL cannot use Cash or Bank ledgers — "
                        f"'{account_names[account_id]}' is a "
                        f"'{entry_groups[account_id]}' ledger.")

        elif voucher_type == VOUCHER_PAYMENT:
            if not any(VoucherService._group_is_cash_bank(e['group']) for e in credit_entries):
                raise VoucherValidationError(
                    "PAYMENT requires at least one Credit entry on a Cash or Bank ledger.")
            if not any(not VoucherService._group_is_cash_bank(e['group']) for e in debit_entries):
                raise VoucherValidationError(
                    "PAYMENT requires at least one Debit entry on an "
                    "expense / party / asset ledger.")

        elif voucher_type == VOUCHER_RECEIPT:
            if not any(VoucherService._group_is_cash_bank(e['group']) for e in debit_entries):
                raise VoucherValidationError(
                    "RECEIPT requires at least one Debit entry on a Cash or Bank ledger.")
            if not any(not VoucherService._group_is_cash_bank(e['group']) for e in credit_entries):
                raise VoucherValidationError(
                    "RECEIPT requires at least one Credit entry on an "
                    "income / party / capital ledger.")

        elif voucher_type == VOUCHER_SALES:
            if not any(VoucherService._group_is_income(e['group']) for e in credit_entries):
                raise VoucherValidationError(
                    "SALES requires at least one Credit entry on a Sales/Income ledger.")
            if not any(VoucherService._group_is_cash_bank(e['group'])
                       or VoucherService._group_is_party(e['group'])
                       for e in debit_entries):
                raise VoucherValidationError(
                    "SALES requires at least one Debit entry on a party "
                    "(Sundry Debtor) or Cash/Bank ledger.")

        elif voucher_type == VOUCHER_PURCHASE:
            if not any(VoucherService._group_is_expense_or_asset(e['group'])
                       for e in debit_entries):
                raise VoucherValidationError(
                    "PURCHASE requires at least one Debit entry on a "
                    "purchase / expense / asset ledger.")
            if not any(VoucherService._group_is_cash_bank(e['group'])
                       or VoucherService._group_is_party(e['group'])
                       for e in credit_entries):
                raise VoucherValidationError(
                    "PURCHASE requires at least one Credit entry on a party "
                    "(Sundry Creditor) or Cash/Bank ledger.")

    @staticmethod
    def save_voucher(
        company_id: int,
        voucher_type: str,
        voucher_date: date,
        entries: List[Dict[str, Any]],
        reference_number: str = "",
        narration: str = "",
        due_date: Optional[date] = None,
        voucher_number: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[int]]:
        """Atomically save a balanced voucher. Returns (ok, message, id)."""
        if voucher_type not in VOUCHER_TYPES:
            return False, f"Invalid voucher type: {voucher_type}", None
        if not isinstance(voucher_date, date):
            return False, "Invalid voucher date.", None

        try:
            VoucherService._validate_entries(company_id, entries, voucher_type=voucher_type)
        except VoucherValidationError as exc:
            return False, exc.message, None

        if voucher_number is None or not str(voucher_number).strip():
            voucher_number = VoucherService.next_voucher_number(company_id, voucher_type)
        else:
            existing = db.fetch_one(
                "SELECT id FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, voucher_number),
            )
            if existing:
                return False, f"Voucher number {voucher_number} already exists.", None

        try:
            with db.transaction() as cursor:
                cursor.execute(
                    """
                    INSERT INTO vouchers (
                        company_id, voucher_type, voucher_date, voucher_number,
                        reference_number, narration, due_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        voucher_type,
                        voucher_date.isoformat(),
                        voucher_number,
                        reference_number,
                        narration,
                        due_date.isoformat() if due_date else None,
                        STATUS_POSTED,
                    ),
                )
                voucher_id = cursor.lastrowid
                for entry in entries:
                    cursor.execute(
                        """
                        INSERT INTO voucher_details (
                            voucher_id, account_id, debit_amount, credit_amount,
                            narration, contra_account_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            voucher_id,
                            entry.get('account_id'),
                            float(entry.get('debit_amount', 0.0) or 0.0),
                            float(entry.get('credit_amount', 0.0) or 0.0),
                            str(entry.get('narration', '') or ''),
                            entry.get('contra_account_id'),
                        ),
                    )
            return True, f"{voucher_type} voucher {voucher_number} saved.", voucher_id
        except Exception as exc:
            logger.error(f"Error saving voucher: {exc}")
            return False, f"Failed to save voucher: {str(exc)}", None

    @staticmethod
    def update_voucher(
        voucher_id: int,
        company_id: int,
        voucher_type: str,
        voucher_date: date,
        entries: List[Dict[str, Any]],
        reference_number: str = "",
        narration: str = "",
        due_date: Optional[date] = None,
    ) -> Tuple[bool, str]:
        """Replace an existing voucher's header + detail lines atomically."""
        existing = VoucherService.get_voucher(voucher_id)
        if not existing:
            return False, "Voucher not found."
        if existing['status'] == STATUS_CANCELLED:
            return False, "A cancelled voucher cannot be edited. Create a new voucher instead."
        if int(existing['company_id']) != int(company_id):
            return False, "Voucher belongs to a different company."

        if voucher_type not in VOUCHER_TYPES:
            return False, f"Invalid voucher type: {voucher_type}"

        try:
            VoucherService._validate_entries(company_id, entries, voucher_type=voucher_type)
        except VoucherValidationError as exc:
            return False, exc.message

        try:
            with db.transaction() as cursor:
                cursor.execute(
                    """
                    UPDATE vouchers
                    SET voucher_type = ?, voucher_date = ?, reference_number = ?,
                        narration = ?, due_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        voucher_type,
                        voucher_date.isoformat(),
                        reference_number,
                        narration,
                        due_date.isoformat() if due_date else None,
                        voucher_id,
                    ),
                )
                cursor.execute("DELETE FROM voucher_details WHERE voucher_id = ?", (voucher_id,))
                for entry in entries:
                    cursor.execute(
                        """
                        INSERT INTO voucher_details (
                            voucher_id, account_id, debit_amount, credit_amount,
                            narration, contra_account_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            voucher_id,
                            entry.get('account_id'),
                            float(entry.get('debit_amount', 0.0) or 0.0),
                            float(entry.get('credit_amount', 0.0) or 0.0),
                            str(entry.get('narration', '') or ''),
                            entry.get('contra_account_id'),
                        ),
                    )
            return True, f"{voucher_type} voucher {existing['voucher_number']} updated."
        except Exception as exc:
            logger.error(f"Error updating voucher: {exc}")
            return False, f"Failed to update voucher: {str(exc)}"

    @staticmethod
    def cancel_voucher(voucher_id: int, company_id: int) -> Tuple[bool, str]:
        """Soft-cancel a voucher. Reports exclude cancelled vouchers."""
        existing = VoucherService.get_voucher(voucher_id)
        if not existing:
            return False, "Voucher not found."
        if int(existing['company_id']) != int(company_id):
            return False, "Voucher belongs to a different company."
        if existing['status'] == STATUS_CANCELLED:
            return False, "Voucher is already cancelled."
        db.execute(
            "UPDATE vouchers SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (STATUS_CANCELLED, voucher_id),
        )
        return True, f"Voucher {existing['voucher_number']} cancelled."

    @staticmethod
    def get_voucher(voucher_id: int) -> Optional[dict]:
        row = db.fetch_one("SELECT * FROM vouchers WHERE id = ?", (voucher_id,))
        return dict(row) if row else None

    @staticmethod
    def get_voucher_details(voucher_id: int) -> list:
        rows = db.fetch_all(
            "SELECT * FROM voucher_details WHERE voucher_id = ? ORDER BY id",
            (voucher_id,),
        )
        return [dict(row) for row in rows]

    @staticmethod
    def get_voucher_with_details(voucher_id: int) -> Optional[Dict[str, Any]]:
        voucher = VoucherService.get_voucher(voucher_id)
        if not voucher:
            return None
        details = VoucherService.get_voucher_details(voucher_id)
        # Resolve account names for display/edit.
        for detail in details:
            account = db.fetch_one(
                "SELECT name, code, is_active FROM accounts WHERE id = ?",
                (detail.get('account_id'),),
            )
            detail['account_name'] = VoucherService._row_value(account, 'name', '')
            detail['account_code'] = VoucherService._row_value(account, 'code', '')
        voucher['details'] = details
        return voucher

    @staticmethod
    def list_vouchers(
        company_id: int,
        search_term: str = "",
        voucher_type: str = "",
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        include_cancelled: bool = True,
    ) -> List[Dict[str, Any]]:
        """List vouchers for a company with filters."""
        try:
            where = ["company_id = ?"]
            params: List[Any] = [company_id]
            if search_term:
                term = f"%{search_term.lower()}%"
                where.append(
                    "(LOWER(voucher_number) LIKE ? OR LOWER(reference_number) LIKE ? "
                    "OR LOWER(narration) LIKE ?)"
                )
                params.extend([term, term, term])
            if voucher_type:
                where.append("voucher_type = ?")
                params.append(voucher_type)
            if from_date:
                where.append("voucher_date >= ?")
                params.append(from_date.isoformat())
            if to_date:
                where.append("voucher_date <= ?")
                params.append(to_date.isoformat())
            if not include_cancelled:
                where.append("status != ?")
                params.append(STATUS_CANCELLED)

            rows = db.fetch_all(
                f"""
                SELECT id, company_id, voucher_number, voucher_type, voucher_date,
                       reference_number, narration, due_date, status, created_at, updated_at
                FROM vouchers
                WHERE {' AND '.join(where)}
                ORDER BY voucher_date DESC, id DESC
                """,
                tuple(params),
            )
            vouchers: List[Dict[str, Any]] = []
            for row in rows:
                voucher_id = VoucherService._row_value(row, 'id')
                vouchers.append({
                    'id': voucher_id,
                    'company_id': VoucherService._row_value(row, 'company_id'),
                    'voucher_number': VoucherService._row_value(row, 'voucher_number', ''),
                    'voucher_type': VoucherService._row_value(row, 'voucher_type', ''),
                    'voucher_date': VoucherService._row_value(row, 'voucher_date', ''),
                    'reference_number': VoucherService._row_value(row, 'reference_number', ''),
                    'narration': VoucherService._row_value(row, 'narration', ''),
                    'due_date': VoucherService._row_value(row, 'due_date'),
                    'status': VoucherService._row_value(row, 'status', ''),
                    'created_at': VoucherService._row_value(row, 'created_at', ''),
                    'updated_at': VoucherService._row_value(row, 'updated_at', ''),
                    'total_debit': 0.0,
                    'total_credit': 0.0,
                    'detail_count': 0,
                })
            return vouchers
        except Exception as exc:
            logger.error(f"Error listing vouchers: {exc}")
            return []

    @staticmethod
    def get_voucher_totals(voucher_id: int) -> Dict[str, float]:
        """Debit/credit totals for a voucher (used for list display)."""
        rows = db.fetch_all(
            """
            SELECT COALESCE(SUM(debit_amount), 0) AS debit_total,
                   COALESCE(SUM(credit_amount), 0) AS credit_total,
                   COUNT(*) AS detail_count
            FROM voucher_details
            WHERE voucher_id = ?
            """,
            (voucher_id,),
        )
        row = rows[0] if rows else None
        return {
            'debit_total': round(float(VoucherService._row_value(row, 'debit_total', 0.0) or 0.0), 2),
            'credit_total': round(float(VoucherService._row_value(row, 'credit_total', 0.0) or 0.0), 2),
            'detail_count': int(VoucherService._row_value(row, 'detail_count', 0) or 0),
        }

    @staticmethod
    def enrich_vouchers_with_totals(vouchers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Attach debit/credit totals and detail counts to a voucher list."""
        for voucher in vouchers:
            totals = VoucherService.get_voucher_totals(voucher['id'])
            voucher['total_debit'] = totals['debit_total']
            voucher['total_credit'] = totals['credit_total']
            voucher['detail_count'] = totals['detail_count']
        return vouchers

    @staticmethod
    def delete_voucher(voucher_id: int, company_id: int) -> Tuple[bool, str]:
        """Hard-delete a voucher. Only allowed when never posted, or as a
        destructive fallback — the UI prefers cancel_voucher."""
        existing = VoucherService.get_voucher(voucher_id)
        if not existing:
            return False, "Voucher not found."
        if int(existing['company_id']) != int(company_id):
            return False, "Voucher belongs to a different company."
        db.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
        return True, f"Voucher {existing['voucher_number']} deleted."

    # ------------------------------------------------------------------ #
    # Tally-style API alias
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_voucher_by_id(voucher_id: int) -> Optional[dict]:
        """Alias for ``get_voucher`` (fetch a voucher by id)."""
        return VoucherService.get_voucher(voucher_id)


voucher_service = VoucherService()
