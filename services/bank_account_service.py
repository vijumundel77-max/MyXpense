"""
Bank Account Service
CRUD helpers for bank accounts in the Expenzo accounting schema.
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
                return row.get(key, default)
            except Exception:
                return default

    @staticmethod
    def list_bank_accounts(company_id: int = 1) -> List[Dict[str, Any]]:
        try:
            rows = db.fetch_all(
                """
                SELECT id, company_id, bank_name, account_name, account_number,
                       account_type, opening_balance, opening_balance_type,
                       current_balance, color_code, ifsc_code, branch, notes
                FROM bank_accounts
                WHERE company_id = ?
                ORDER BY bank_name
                """,
                (company_id,),
            )
            return [
                {
                    "id": BankAccountService._row_value(row, "id"),
                    "company_id": BankAccountService._row_value(row, "company_id"),
                    "bank_name": BankAccountService._row_value(row, "bank_name", ""),
                    "account_name": BankAccountService._row_value(row, "account_name", ""),
                    "account_number": BankAccountService._row_value(row, "account_number", ""),
                    "account_type": BankAccountService._row_value(row, "account_type", ""),
                    "opening_balance": float(BankAccountService._row_value(row, "opening_balance", 0.0) or 0.0),
                    "opening_balance_type": BankAccountService._row_value(row, "opening_balance_type", "Debit"),
                    "current_balance": float(BankAccountService._row_value(row, "current_balance", 0.0) or 0.0),
                    "color_code": BankAccountService._row_value(row, "color_code", "#3B82F6"),
                    "ifsc_code": BankAccountService._row_value(row, "ifsc_code", ""),
                    "branch": BankAccountService._row_value(row, "branch", ""),
                    "notes": BankAccountService._row_value(row, "notes", ""),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error listing bank accounts: {e}")
            return []

    @staticmethod
    def get_bank_account(bank_account_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = db.fetch_one(
                """
                SELECT id, company_id, bank_name, account_name, account_number,
                       account_type, opening_balance, opening_balance_type,
                       current_balance, color_code, ifsc_code, branch, notes
                FROM bank_accounts
                WHERE id = ?
                """,
                (bank_account_id,),
            )
            if not row:
                return None
            return {
                "id": BankAccountService._row_value(row, "id"),
                "company_id": BankAccountService._row_value(row, "company_id"),
                "bank_name": BankAccountService._row_value(row, "bank_name", ""),
                "account_name": BankAccountService._row_value(row, "account_name", ""),
                "account_number": BankAccountService._row_value(row, "account_number", ""),
                "account_type": BankAccountService._row_value(row, "account_type", ""),
                "opening_balance": float(BankAccountService._row_value(row, "opening_balance", 0.0) or 0.0),
                "opening_balance_type": BankAccountService._row_value(row, "opening_balance_type", "Debit"),
                "current_balance": float(BankAccountService._row_value(row, "current_balance", 0.0) or 0.0),
                "color_code": BankAccountService._row_value(row, "color_code", "#3B82F6"),
                "ifsc_code": BankAccountService._row_value(row, "ifsc_code", ""),
                "branch": BankAccountService._row_value(row, "branch", ""),
                "notes": BankAccountService._row_value(row, "notes", ""),
            }
        except Exception as e:
            logger.error(f"Error getting bank account: {e}")
            return None

    @staticmethod
    def create_bank_account(data: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            bank_name = str(data.get("bank_name", "")).strip()
            account_name = str(data.get("account_name", "")).strip()
            account_number = str(data.get("account_number", "")).strip()
            account_type = str(data.get("account_type", "Savings")).strip()
            opening_balance = float(data.get("opening_balance", 0.0) or 0.0)
            opening_balance_type = str(data.get("opening_balance_type", "Debit")).strip()
            color_code = str(data.get("color_code", "#3B82F6")).strip()
            ifsc_code = str(data.get("ifsc_code", "")).strip()
            branch = str(data.get("branch", "")).strip()
            notes = str(data.get("notes", "")).strip()
            company_id = int(data.get("company_id", 1) or 1)

            if not bank_name:
                return False, "Bank name is required"

            db.execute(
                """
                INSERT INTO bank_accounts (
                    company_id, bank_name, account_name, account_number,
                    account_type, opening_balance, opening_balance_type,
                    current_balance, color_code, ifsc_code, branch, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    bank_name,
                    account_name,
                    account_number,
                    account_type,
                    opening_balance,
                    opening_balance_type,
                    opening_balance,
                    color_code,
                    ifsc_code,
                    branch,
                    notes,
                ),
            )
            return True, "Bank account created successfully"
        except Exception as e:
            logger.error(f"Error creating bank account: {e}")
            return False, f"Failed to create bank account: {str(e)}"

    @staticmethod
    def update_bank_account(bank_account_id: int, data: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            bank_name = str(data.get("bank_name", "")).strip()
            account_name = str(data.get("account_name", "")).strip()
            account_number = str(data.get("account_number", "")).strip()
            account_type = str(data.get("account_type", "Savings")).strip()
            opening_balance = float(data.get("opening_balance", 0.0) or 0.0)
            opening_balance_type = str(data.get("opening_balance_type", "Debit")).strip()
            color_code = str(data.get("color_code", "#3B82F6")).strip()
            ifsc_code = str(data.get("ifsc_code", "")).strip()
            branch = str(data.get("branch", "")).strip()
            notes = str(data.get("notes", "")).strip()

            if not bank_name:
                return False, "Bank name is required"

            db.execute(
                """
                UPDATE bank_accounts
                SET bank_name = ?, account_name = ?, account_number = ?,
                    account_type = ?, opening_balance = ?, opening_balance_type = ?,
                    current_balance = ?, color_code = ?, ifsc_code = ?, branch = ?, notes = ?
                WHERE id = ?
                """,
                (
                    bank_name,
                    account_name,
                    account_number,
                    account_type,
                    opening_balance,
                    opening_balance_type,
                    opening_balance,
                    color_code,
                    ifsc_code,
                    branch,
                    notes,
                    bank_account_id,
                ),
            )
            return True, "Bank account updated successfully"
        except Exception as e:
            logger.error(f"Error updating bank account: {e}")
            return False, f"Failed to update bank account: {str(e)}"

    @staticmethod
    def delete_bank_account(bank_account_id: int) -> Tuple[bool, str]:
        try:
            db.execute("DELETE FROM bank_accounts WHERE id = ?", (bank_account_id,))
            return True, "Bank account deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting bank account: {e}")
            return False, f"Failed to delete bank account: {str(e)}"


bank_account_service = BankAccountService()