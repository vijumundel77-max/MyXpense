"""
Bank Account Service
CRUD helpers for managing bank accounts using the existing schema.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from database.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BankAccountService:
    """Service for bank account CRUD."""

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
    def list_bank_accounts(search_term: str = "", company_id: int | None = None) -> List[Dict[str, Any]]:
        try:
            where = ["1 = 1"]
            params: List[Any] = []
            if company_id is not None:
                where.append("company_id = ?")
                params.append(company_id)
            if search_term:
                where.append("(LOWER(bank_name) LIKE ? OR LOWER(account_number) LIKE ? OR LOWER(account_type) LIKE ?)")
                params.extend([f"%{search_term.lower()}%", f"%{search_term.lower()}%", f"%{search_term.lower()}%"])
            query = f"""
                SELECT id, company_id, bank_name, account_name, account_number, account_type,
                       opening_balance, opening_balance_type, current_balance, color_code,
                       ifsc_code, branch, notes, created_at
                FROM bank_accounts
                WHERE {' AND '.join(where)}
                ORDER BY bank_name
            """
            rows = db.fetch_all(query, tuple(params))
            return [BankAccountService._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error listing bank accounts: {e}")
            return []

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": BankAccountService._row_value(row, "id"),
            "company_id": BankAccountService._row_value(row, "company_id", 1),
            "bank_name": BankAccountService._row_value(row, "bank_name", ""),
            "account_name": BankAccountService._row_value(row, "account_name", ""),
            "account_number": BankAccountService._row_value(row, "account_number", ""),
            "account_type": BankAccountService._row_value(row, "account_type", ""),
            "opening_balance": float(BankAccountService._row_value(row, "opening_balance", 0.0) or 0.0),
            "opening_balance_type": BankAccountService._row_value(row, "opening_balance_type", "Debit"),
            "current_balance": float(BankAccountService._row_value(row, "current_balance", 0.0) or 0.0),
            "color_code": BankAccountService._row_value(row, "color_code", ""),
            "ifsc_code": BankAccountService._row_value(row, "ifsc_code", ""),
            "branch": BankAccountService._row_value(row, "branch", ""),
            "notes": BankAccountService._row_value(row, "notes", ""),
            "created_at": BankAccountService._row_value(row, "created_at", ""),
        }

    @staticmethod
    def get_bank_account(bank_account_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = db.fetch_one(
                """
                SELECT id, company_id, bank_name, account_name, account_number, account_type,
                       opening_balance, opening_balance_type, current_balance, color_code,
                       ifsc_code, branch, notes, created_at
                FROM bank_accounts
                WHERE id = ?
                """,
                (bank_account_id,),
            )
            if not row:
                return None
            return BankAccountService._row_to_dict(row)
        except Exception as e:
            logger.error(f"Error getting bank account: {e}")
            return None

    @staticmethod
    def create_bank_account(data: Dict[str, Any], company_id: int | None = None) -> Tuple[bool, str]:
        try:
            bank_name = str(data.get("bank_name", "")).strip()
            account_name = str(data.get("account_name", "")).strip()
            account_number = str(data.get("account_number", "")).strip()
            account_type = str(data.get("account_type", "")).strip()
            opening_balance = float(data.get("opening_balance", 0.0) or 0.0)
            opening_balance_type = str(data.get("opening_balance_type", "Debit")).strip() or "Debit"
            current_balance = float(data.get("current_balance", opening_balance) or opening_balance)
            color_code = str(data.get("color_code", "")).strip()
            ifsc_code = str(data.get("ifsc_code", "")).strip()
            branch = str(data.get("branch", "")).strip()
            notes = str(data.get("notes", "")).strip()
            company_id = int(company_id or data.get("company_id") or 1)

            if not bank_name:
                return False, "Bank name is required"
            if not account_type:
                return False, "Account type is required"

            db.execute(
                """
                INSERT INTO bank_accounts (
                    company_id, bank_name, account_name, account_number, account_type,
                    opening_balance, opening_balance_type, current_balance, color_code,
                    ifsc_code, branch, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (company_id, bank_name, account_name, account_number, account_type,
                 opening_balance, opening_balance_type, current_balance, color_code,
                 ifsc_code, branch, notes),
            )
            return True, "Bank account saved successfully"
        except Exception as e:
            logger.error(f"Error creating bank account: {e}")
            return False, f"Failed to save bank account: {str(e)}"

    @staticmethod
    def update_bank_account(bank_account_id: int, data: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            bank_name = str(data.get("bank_name", "")).strip()
            account_name = str(data.get("account_name", "")).strip()
            account_number = str(data.get("account_number", "")).strip()
            account_type = str(data.get("account_type", "")).strip()
            opening_balance = float(data.get("opening_balance", 0.0) or 0.0)
            opening_balance_type = str(data.get("opening_balance_type", "Debit")).strip() or "Debit"
            current_balance = float(data.get("current_balance", opening_balance) or opening_balance)
            color_code = str(data.get("color_code", "")).strip()
            ifsc_code = str(data.get("ifsc_code", "")).strip()
            branch = str(data.get("branch", "")).strip()
            notes = str(data.get("notes", "")).strip()

            if not bank_name:
                return False, "Bank name is required"
            if not account_type:
                return False, "Account type is required"

            db.execute(
                """
                UPDATE bank_accounts
                SET bank_name = ?, account_name = ?, account_number = ?, account_type = ?,
                    opening_balance = ?, opening_balance_type = ?, current_balance = ?,
                    color_code = ?, ifsc_code = ?, branch = ?, notes = ?
                WHERE id = ?
                """,
                (bank_name, account_name, account_number, account_type,
                 opening_balance, opening_balance_type, current_balance,
                 color_code, ifsc_code, branch, notes, bank_account_id),
            )
            return True, "Bank account updated successfully"
        except Exception as e:
            logger.error(f"Error updating bank account: {e}")
            return False, f"Failed to update bank account: {str(e)}"

    @staticmethod
    def is_bank_account_referenced(bank_account_id: int) -> bool:
        try:
            tx_row = db.fetch_one(
                "SELECT COUNT(*) AS count FROM transactions WHERE bank_account_id = ?",
                (bank_account_id,),
            )
            transfer_row = db.fetch_one(
                """
                SELECT COUNT(*) AS count
                FROM transfers
                WHERE from_bank_id = ? OR to_bank_id = ?
                """,
                (bank_account_id, bank_account_id),
            )
            tx_count = int(BankAccountService._row_value(tx_row, "count", 0) or 0) if tx_row else 0
            transfer_count = int(BankAccountService._row_value(transfer_row, "count", 0) or 0) if transfer_row else 0
            return (tx_count + transfer_count) > 0
        except Exception as e:
            logger.error(f"Error checking bank account references: {e}")
            return True

    @staticmethod
    def delete_bank_account(bank_account_id: int) -> Tuple[bool, str]:
        try:
            if BankAccountService.is_bank_account_referenced(bank_account_id):
                return False, "Cannot delete bank account because it is referenced in transactions or transfers"
            db.execute("DELETE FROM bank_accounts WHERE id = ?", (bank_account_id,))
            return True, "Bank account deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting bank account: {e}")
            return False, f"Failed to delete bank account: {str(e)}"


bank_account_service = BankAccountService()
