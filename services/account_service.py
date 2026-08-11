"""
Account Service
Thin CRUD helpers over the Expenzo ``accounts`` schema used by the
party-ledger / outstanding / ageing report services and their tests.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AccountService:
    """Service for account master CRUD."""

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
    def create_account(
        company_id: int,
        name: str,
        code: str = "",
        account_group: str = "",
        opening_balance: float = 0.0,
        opening_balance_type: str = "Debit",
        alias: str = "",
        address: str = "",
        state: str = "",
        country: str = "",
        pincode: str = "",
        contact_person: str = "",
        mobile: str = "",
        email: str = "",
        credit_limit: float = 0.0,
        credit_days: int = 0,
    ) -> int:
        return db.execute(
            """
            INSERT INTO accounts (
                company_id, name, code, alias, account_group,
                opening_balance, opening_balance_type,
                address, state, country, pincode,
                contact_person, mobile, email,
                credit_limit, credit_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id, name, code, alias, account_group,
                opening_balance, opening_balance_type,
                address, state, country, pincode,
                contact_person, mobile, email,
                credit_limit, credit_days,
            ),
        )

    @staticmethod
    def get_account(account_id: int) -> Optional[Dict[str, Any]]:
        row = db.fetch_one(
            """
            SELECT id, company_id, name, code, alias, account_group,
                   opening_balance, opening_balance_type, is_active,
                   address, state, country, pincode,
                   contact_person, mobile, email,
                   credit_limit, credit_days
            FROM accounts
            WHERE id = ?
            """,
            (account_id,),
        )
        if not row:
            return None
        return AccountService._account_from_row(row)

    @staticmethod
    def _account_from_row(row: Any) -> Dict[str, Any]:
        return {
            'id': AccountService._row_value(row, 'id'),
            'company_id': AccountService._row_value(row, 'company_id'),
            'name': AccountService._row_value(row, 'name', ''),
            'code': AccountService._row_value(row, 'code', ''),
            'alias': AccountService._row_value(row, 'alias', ''),
            'account_group': AccountService._row_value(row, 'account_group', ''),
            'opening_balance': float(AccountService._row_value(row, 'opening_balance', 0.0) or 0.0),
            'opening_balance_type': AccountService._row_value(row, 'opening_balance_type', 'Debit'),
            'address': AccountService._row_value(row, 'address', ''),
            'state': AccountService._row_value(row, 'state', ''),
            'country': AccountService._row_value(row, 'country', ''),
            'pincode': AccountService._row_value(row, 'pincode', ''),
            'contact_person': AccountService._row_value(row, 'contact_person', ''),
            'mobile': AccountService._row_value(row, 'mobile', ''),
            'email': AccountService._row_value(row, 'email', ''),
            'credit_limit': float(AccountService._row_value(row, 'credit_limit', 0.0) or 0.0),
            'credit_days': int(AccountService._row_value(row, 'credit_days', 0) or 0),
            'is_active': bool(AccountService._row_value(row, 'is_active', 1)),
        }

    @staticmethod
    def list_accounts(company_id: int) -> List[Dict[str, Any]]:
        rows = db.fetch_all(
            """
            SELECT id, company_id, name, code, alias, account_group,
                   opening_balance, opening_balance_type, is_active,
                   address, state, country, pincode,
                   contact_person, mobile, email,
                   credit_limit, credit_days
            FROM accounts
            WHERE company_id = ?
            ORDER BY name
            """,
            (company_id,),
        )
        return [AccountService._account_from_row(row) for row in rows]

    @staticmethod
    def update_account(
        account_id: int,
        name: Optional[str] = None,
        code: Optional[str] = None,
        account_group: Optional[str] = None,
        opening_balance: Optional[float] = None,
        opening_balance_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        alias: Optional[str] = None,
        address: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        pincode: Optional[str] = None,
        contact_person: Optional[str] = None,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        credit_limit: Optional[float] = None,
        credit_days: Optional[int] = None,
    ) -> bool:
        current = AccountService.get_account(account_id)
        if not current:
            return False
        fields = {
            'name': name if name is not None else current['name'],
            'code': code if code is not None else current['code'],
            'alias': alias if alias is not None else current['alias'],
            'account_group': account_group if account_group is not None else current['account_group'],
            'opening_balance': opening_balance if opening_balance is not None else current['opening_balance'],
            'opening_balance_type': opening_balance_type if opening_balance_type is not None else current['opening_balance_type'],
            'address': address if address is not None else current['address'],
            'state': state if state is not None else current['state'],
            'country': country if country is not None else current['country'],
            'pincode': pincode if pincode is not None else current['pincode'],
            'contact_person': contact_person if contact_person is not None else current['contact_person'],
            'mobile': mobile if mobile is not None else current['mobile'],
            'email': email if email is not None else current['email'],
            'credit_limit': credit_limit if credit_limit is not None else current['credit_limit'],
            'credit_days': credit_days if credit_days is not None else current['credit_days'],
            'is_active': int(is_active) if is_active is not None else int(current['is_active']),
        }
        db.execute(
            """
            UPDATE accounts
            SET name = ?, code = ?, alias = ?, account_group = ?,
                opening_balance = ?, opening_balance_type = ?,
                address = ?, state = ?, country = ?, pincode = ?,
                contact_person = ?, mobile = ?, email = ?,
                credit_limit = ?, credit_days = ?,
                is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (fields['name'], fields['code'], fields['alias'], fields['account_group'],
             fields['opening_balance'], fields['opening_balance_type'],
             fields['address'], fields['state'], fields['country'], fields['pincode'],
             fields['contact_person'], fields['mobile'], fields['email'],
             fields['credit_limit'], fields['credit_days'],
             fields['is_active'], account_id),
        )
        return True

    @staticmethod
    def set_account_active(account_id: int, is_active: bool) -> bool:
        db.execute(
            "UPDATE accounts SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if is_active else 0, account_id),
        )
        return True

    @staticmethod
    def delete_account(account_id: int) -> bool:
        db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return True

    @staticmethod
    def is_account_referenced(account_id: int) -> bool:
        """True when the account appears in any voucher detail line."""
        row = db.fetch_one(
            "SELECT COUNT(*) AS count FROM voucher_details WHERE account_id = ?",
            (account_id,),
        )
        count = int(AccountService._row_value(row, 'count', 0) or 0) if row else 0
        return count > 0

    @staticmethod
    def list_groups(company_id: int) -> List[Dict[str, Any]]:
        """Distinct account groups currently in use by a company's ledgers."""
        rows = db.fetch_all(
            """
            SELECT DISTINCT account_group
            FROM accounts
            WHERE company_id = ? AND account_group != ''
            ORDER BY account_group
            """,
            (company_id,),
        )
        return [
            {'account_group': str(AccountService._row_value(row, 'account_group', ''))}
            for row in rows
        ]

    @staticmethod
    def search_accounts(company_id: int, search_term: str = "", include_inactive: bool = False) -> List[Dict[str, Any]]:
        """List ledgers for a company, filtered by name/code/group."""
        try:
            where = ["company_id = ?"]
            params: List[Any] = [company_id]
            if search_term:
                term = f"%{search_term.lower()}%"
                where.append("(LOWER(name) LIKE ? OR LOWER(code) LIKE ? OR LOWER(alias) LIKE ? OR LOWER(account_group) LIKE ?)")
                params.extend([term, term, term, term])
            if not include_inactive:
                where.append("is_active = 1")
            rows = db.fetch_all(
                f"""
                SELECT id, company_id, name, code, alias, account_group,
                       opening_balance, opening_balance_type, is_active,
                       address, state, country, pincode,
                       contact_person, mobile, email,
                       credit_limit, credit_days
                FROM accounts
                WHERE {' AND '.join(where)}
                ORDER BY name
                """,
                tuple(params),
            )
            return [AccountService._account_from_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Error searching accounts: {e}")
            return []


account_service = AccountService()
