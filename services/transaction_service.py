"""
Transaction Service
CRUD helpers for the MyXpense transaction entry module.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from database.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TransactionService:
    """Service for transaction entry CRUD."""

    TRANSACTION_TYPES = ("Income", "Expense")
    PAYMENT_METHODS = ("Cash", "Bank", "UPI", "Card", "Transfer", "Other")

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
    def _table_columns(table_name: str) -> List[str]:
        try:
            rows = db.fetch_all(f"PRAGMA table_info({table_name})")
            return [str(TransactionService._row_value(row, "name", "")) for row in rows]
        except Exception:
            return []

    @staticmethod
    def _parse_transaction_date(value: str) -> date:
        return datetime.strptime(value, "%d-%m-%Y").date()

    @staticmethod
    def _parse_transaction_time(value: str) -> str:
        try:
            datetime.strptime(value, "%H:%M")
            return value
        except Exception:
            return datetime.now().strftime("%H:%M")

    @staticmethod
    def _normalize_type(value: str) -> str:
        return value if value in TransactionService.TRANSACTION_TYPES else "Expense"

    @staticmethod
    def _normalize_payment_method(value: str) -> str:
        return value if value in TransactionService.PAYMENT_METHODS else "Other"

    @staticmethod
    def list_transactions(limit: int = 200) -> List[Dict[str, Any]]:
        try:
            rows = db.fetch_all(
                """
                SELECT
                    id, title, amount, type, category_id, account_mode,
                    bank_account_id, party_id, payment_method,
                    transaction_date, transaction_time, notes, created_at
                FROM transactions
                ORDER BY transaction_date DESC, transaction_time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            transactions: List[Dict[str, Any]] = []
            for row in rows:
                transactions.append({
                    "id": TransactionService._row_value(row, "id"),
                    "title": TransactionService._row_value(row, "title", ""),
                    "amount": float(TransactionService._row_value(row, "amount", 0.0) or 0.0),
                    "type": TransactionService._row_value(row, "type", "Expense"),
                    "category_id": TransactionService._row_value(row, "category_id"),
                    "account_mode": TransactionService._row_value(row, "account_mode", ""),
                    "bank_account_id": TransactionService._row_value(row, "bank_account_id"),
                    "party_id": TransactionService._row_value(row, "party_id"),
                    "payment_method": TransactionService._row_value(row, "payment_method", ""),
                    "transaction_date": TransactionService._row_value(row, "transaction_date", ""),
                    "transaction_time": TransactionService._row_value(row, "transaction_time", ""),
                    "notes": TransactionService._row_value(row, "notes", ""),
                    "created_at": TransactionService._row_value(row, "created_at", ""),
                })
            return transactions
        except Exception as e:
            logger.error(f"Error listing transactions: {e}")
            return []

    @staticmethod
    def list_categories() -> List[Dict[str, Any]]:
        try:
            rows = db.fetch_all(
                """
                SELECT id, name, type
                FROM categories
                ORDER BY name
                """
            )
            return [
                {
                    "id": TransactionService._row_value(row, "id"),
                    "name": TransactionService._row_value(row, "name", ""),
                    "type": TransactionService._row_value(row, "type", ""),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error listing categories: {e}")
            return []

    @staticmethod
    def list_parties() -> List[Dict[str, Any]]:
        try:
            rows = db.fetch_all(
                """
                SELECT id, name, opening_balance, current_balance
                FROM parties
                ORDER BY name
                """
            )
            return [
                {
                    "id": TransactionService._row_value(row, "id"),
                    "name": TransactionService._row_value(row, "name", ""),
                    "opening_balance": float(TransactionService._row_value(row, "opening_balance", 0.0) or 0.0),
                    "current_balance": float(TransactionService._row_value(row, "current_balance", 0.0) or 0.0),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error listing parties: {e}")
            return []

    @staticmethod
    def list_bank_accounts() -> List[Dict[str, Any]]:
        try:
            rows = db.fetch_all(
                """
                SELECT id, bank_name, account_number, account_type, opening_balance, current_balance
                FROM bank_accounts
                ORDER BY bank_name
                """
            )
            return [
                {
                    "id": TransactionService._row_value(row, "id"),
                    "bank_name": TransactionService._row_value(row, "bank_name", ""),
                    "account_number": TransactionService._row_value(row, "account_number", ""),
                    "account_type": TransactionService._row_value(row, "account_type", ""),
                    "opening_balance": float(TransactionService._row_value(row, "opening_balance", 0.0) or 0.0),
                    "current_balance": float(TransactionService._row_value(row, "current_balance", 0.0) or 0.0),
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error listing bank accounts: {e}")
            return []

    @staticmethod
    def get_transaction(transaction_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = db.fetch_one(
                """
                SELECT
                    id, title, amount, type, category_id, account_mode,
                    bank_account_id, party_id, payment_method,
                    transaction_date, transaction_time, notes, created_at
                FROM transactions
                WHERE id = ?
                """,
                (transaction_id,),
            )
            if not row:
                return None
            return {
                "id": TransactionService._row_value(row, "id"),
                "title": TransactionService._row_value(row, "title", ""),
                "amount": float(TransactionService._row_value(row, "amount", 0.0) or 0.0),
                "type": TransactionService._row_value(row, "type", "Expense"),
                "category_id": TransactionService._row_value(row, "category_id"),
                "account_mode": TransactionService._row_value(row, "account_mode", ""),
                "bank_account_id": TransactionService._row_value(row, "bank_account_id"),
                "party_id": TransactionService._row_value(row, "party_id"),
                "payment_method": TransactionService._row_value(row, "payment_method", ""),
                "transaction_date": TransactionService._row_value(row, "transaction_date", ""),
                "transaction_time": TransactionService._row_value(row, "transaction_time", ""),
                "notes": TransactionService._row_value(row, "notes", ""),
                "created_at": TransactionService._row_value(row, "created_at", ""),
            }
        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            return None

    @staticmethod
    def create_transaction(data: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            title = str(data.get("title", "")).strip()
            amount = float(data.get("amount", 0.0) or 0.0)
            txn_type = TransactionService._normalize_type(str(data.get("type", "")))
            category_id = data.get("category_id")
            account_mode = str(data.get("account_mode", "")).strip()
            bank_account_id = data.get("bank_account_id")
            party_id = data.get("party_id")
            payment_method = TransactionService._normalize_payment_method(str(data.get("payment_method", "")))
            transaction_date = str(data.get("transaction_date", "")).strip()
            transaction_time = TransactionService._parse_transaction_time(str(data.get("transaction_time", "")).strip() or datetime.now().strftime("%H:%M"))
            notes = str(data.get("notes", "")).strip()

            if not title:
                return False, "Title is required"
            if amount <= 0:
                return False, "Amount must be greater than zero"
            if not category_id:
                return False, "Category is required"
            if not transaction_date:
                return False, "Transaction date is required"

            db.execute(
                """
                INSERT INTO transactions (
                    title, amount, type, category_id, account_mode,
                    bank_account_id, party_id, payment_method,
                    transaction_date, transaction_time, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    amount,
                    txn_type,
                    category_id,
                    account_mode,
                    bank_account_id,
                    party_id,
                    payment_method,
                    transaction_date,
                    transaction_time,
                    notes,
                ),
            )
            return True, "Transaction saved successfully"
        except Exception as e:
            logger.error(f"Error creating transaction: {e}")
            return False, f"Failed to save transaction: {str(e)}"

    @staticmethod
    def update_transaction(transaction_id: int, data: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            title = str(data.get("title", "")).strip()
            amount = float(data.get("amount", 0.0) or 0.0)
            txn_type = TransactionService._normalize_type(str(data.get("type", "")))
            category_id = data.get("category_id")
            account_mode = str(data.get("account_mode", "")).strip()
            bank_account_id = data.get("bank_account_id")
            party_id = data.get("party_id")
            payment_method = TransactionService._normalize_payment_method(str(data.get("payment_method", "")))
            transaction_date = str(data.get("transaction_date", "")).strip()
            transaction_time = TransactionService._parse_transaction_time(str(data.get("transaction_time", "")).strip() or datetime.now().strftime("%H:%M"))
            notes = str(data.get("notes", "")).strip()

            if not title:
                return False, "Title is required"
            if amount <= 0:
                return False, "Amount must be greater than zero"
            if not category_id:
                return False, "Category is required"
            if not transaction_date:
                return False, "Transaction date is required"

            db.execute(
                """
                UPDATE transactions
                SET title = ?, amount = ?, type = ?, category_id = ?, account_mode = ?,
                    bank_account_id = ?, party_id = ?, payment_method = ?,
                    transaction_date = ?, transaction_time = ?, notes = ?
                WHERE id = ?
                """,
                (
                    title,
                    amount,
                    txn_type,
                    category_id,
                    account_mode,
                    bank_account_id,
                    party_id,
                    payment_method,
                    transaction_date,
                    transaction_time,
                    notes,
                    transaction_id,
                ),
            )
            return True, "Transaction updated successfully"
        except Exception as e:
            logger.error(f"Error updating transaction: {e}")
            return False, f"Failed to update transaction: {str(e)}"

    @staticmethod
    def delete_transaction(transaction_id: int) -> Tuple[bool, str]:
        try:
            db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            return True, "Transaction deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting transaction: {e}")
            return False, f"Failed to delete transaction: {str(e)}"


transaction_service = TransactionService()
