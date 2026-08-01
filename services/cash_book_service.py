"""
Cash Book Service
Generates cash book reports from the current MyXpense schema.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config
from database.database import db
from services.party_ledger_service import PartyLedgerService
from utils.report_exporter import report_exporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CashBookService:
    """Service for cash book reports."""

    CASH_KEYWORDS = ("cash", "bank")

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
    def _table_columns(table_name: str) -> List[str]:
        try:
            rows = db.fetch_all(f"PRAGMA table_info({table_name})")
            return [str(CashBookService._row_value(row, "name", "")) for row in rows]
        except Exception:
            return []

    @staticmethod
    def _pick_column(columns: List[str], candidates: List[str]) -> Optional[str]:
        lookup = {column.lower(): column for column in columns}
        for candidate in candidates:
            if candidate.lower() in lookup:
                return lookup[candidate.lower()]
        return None

    @staticmethod
    def _get_cash_sources(company_id: int) -> List[Dict[str, Any]]:
        try:
            columns = CashBookService._table_columns("bank_accounts")
            if not columns:
                return []

            id_col = CashBookService._pick_column(columns, ["id"])
            name_col = CashBookService._pick_column(columns, ["bank_name", "name"])
            number_col = CashBookService._pick_column(columns, ["account_number", "number"])
            type_col = CashBookService._pick_column(columns, ["account_type", "type"])
            opening_col = CashBookService._pick_column(columns, ["opening_balance"])
            current_col = CashBookService._pick_column(columns, ["current_balance"])
            color_col = CashBookService._pick_column(columns, ["color_code"])

            select_columns = [c for c in [id_col, name_col, number_col, type_col, opening_col, current_col, color_col] if c]
            rows = db.fetch_all(f"SELECT {', '.join(select_columns)} FROM bank_accounts ORDER BY {name_col or id_col}")
            bank_items: List[Dict[str, Any]] = []
            for row in rows:
                bank_items.append({
                    "id": CashBookService._row_value(row, id_col),
                    "name": CashBookService._row_value(row, name_col, ""),
                    "account_number": CashBookService._row_value(row, number_col, ""),
                    "account_type": CashBookService._row_value(row, type_col, ""),
                    "opening_balance": float(CashBookService._row_value(row, opening_col, 0.0) or 0.0),
                    "current_balance": float(CashBookService._row_value(row, current_col, 0.0) or 0.0),
                    "color_code": CashBookService._row_value(row, color_col, ""),
                })
            return bank_items
        except Exception as e:
            logger.error(f"Error getting cash sources: {e}")
            return []

    @staticmethod
    def _get_transactions(from_date: date, to_date: date, account_id: Optional[int] = None) -> List[Dict[str, Any]]:
        try:
            columns = CashBookService._table_columns("transactions")
            if not columns:
                return []

            id_col = CashBookService._pick_column(columns, ["id"])
            date_col = CashBookService._pick_column(columns, ["transaction_date", "date", "txn_date", "entry_date"])
            party_col = CashBookService._pick_column(columns, ["party_id", "account_id", "customer_id", "supplier_id"])
            category_col = CashBookService._pick_column(columns, ["category_id", "category"])
            transfer_col = CashBookService._pick_column(columns, ["transfer_id"])
            ref_col = CashBookService._pick_column(columns, ["reference_number", "reference", "ref_no", "voucher_number"])
            narration_col = CashBookService._pick_column(columns, ["narration", "description", "remarks", "note"])
            debit_col = CashBookService._pick_column(columns, ["debit_amount", "debit"])
            credit_col = CashBookService._pick_column(columns, ["credit_amount", "credit"])
            amount_col = CashBookService._pick_column(columns, ["amount", "transaction_amount", "net_amount"])
            direction_col = CashBookService._pick_column(columns, ["direction", "entry_side", "dr_cr"])
            status_col = CashBookService._pick_column(columns, ["status", "is_posted", "posted"])
            account_col = CashBookService._pick_column(columns, ["bank_account_id", "cash_account_id", "account_id"])

            if not date_col:
                return []

            select_columns = [c for c in [id_col, date_col, party_col, category_col, transfer_col, ref_col, narration_col, debit_col, credit_col, amount_col, direction_col, status_col, account_col] if c]
            where_clauses = [f"{date_col} BETWEEN ? AND ?"]
            params: List[Any] = [from_date.isoformat(), to_date.isoformat()]
            if account_id is not None and account_col:
                where_clauses.append(f"{account_col} = ?")
                params.append(account_id)
            query = f"""
                SELECT {', '.join(select_columns)}
                FROM transactions
                WHERE {' AND '.join(where_clauses)}
                ORDER BY {date_col}, {id_col or date_col}
            """
            rows = db.fetch_all(query, tuple(params))
            transactions: List[Dict[str, Any]] = []
            for row in rows:
                debit_value = float(CashBookService._row_value(row, debit_col, 0.0) or 0.0) if debit_col else 0.0
                credit_value = float(CashBookService._row_value(row, credit_col, 0.0) or 0.0) if credit_col else 0.0
                amount_value = float(CashBookService._row_value(row, amount_col, 0.0) or 0.0) if amount_col else debit_value - credit_value
                if debit_col is None and credit_col is None:
                    direction = str(CashBookService._row_value(row, direction_col, "debit")).lower() if direction_col else "debit"
                    if direction in ("credit", "cr", "out", "payment"):
                        credit_value = abs(amount_value)
                        debit_value = 0.0
                    else:
                        debit_value = abs(amount_value)
                        credit_value = 0.0
                tx_date_raw = CashBookService._row_value(row, date_col)
                transactions.append({
                    "id": CashBookService._row_value(row, id_col),
                    "transaction_date": tx_date_raw if isinstance(tx_date_raw, str) else (tx_date_raw.isoformat() if hasattr(tx_date_raw, "isoformat") else tx_date_raw),
                    "party_id": CashBookService._row_value(row, party_col),
                    "category_id": CashBookService._row_value(row, category_col),
                    "transfer_id": CashBookService._row_value(row, transfer_col),
                    "reference_number": CashBookService._row_value(row, ref_col, ""),
                    "narration": CashBookService._row_value(row, narration_col, ""),
                    "debit_amount": debit_value,
                    "credit_amount": credit_value,
                    "amount": amount_value,
                    "account_id": CashBookService._row_value(row, account_col),
                    "status": CashBookService._row_value(row, status_col, ""),
                })
            return transactions
        except Exception as e:
            logger.error(f"Error getting transactions: {e}")
            return []

    @staticmethod
    def _is_cash_related(transaction: Dict[str, Any]) -> bool:
        text = " ".join(
            str(transaction.get(field, "") or "").lower()
            for field in ("reference_number", "narration", "status")
        )
        return any(keyword in text for keyword in CashBookService.CASH_KEYWORDS)

    @staticmethod
    def _classify_transaction(transaction: Dict[str, Any]) -> str:
        debit = float(transaction.get("debit_amount", 0.0) or 0.0)
        credit = float(transaction.get("credit_amount", 0.0) or 0.0)
        if credit > debit:
            return "Receipt"
        if debit > credit:
            return "Payment"
        return "Transfer"

    @staticmethod
    def generate_cash_book(company_id: int, from_date: date, to_date: date, account_id: Optional[int] = None) -> Dict[str, Any]:
        try:
            cash_sources = CashBookService._get_cash_sources(company_id)
            if account_id is not None and account_id != 0:
                cash_sources = [item for item in cash_sources if item.get("id") == account_id]
            transactions = CashBookService._get_transactions(from_date, to_date, account_id if account_id not in (None, 0) else None)

            cash_transactions: List[Dict[str, Any]] = []
            opening_balance = 0.0

            for item in cash_sources:
                opening_balance += float(item.get("opening_balance", 0.0) or 0.0)
                opening_balance += float(item.get("current_balance", 0.0) or 0.0)

            running_balance = opening_balance
            total_receipts = 0.0
            total_payments = 0.0

            for transaction in transactions:
                if not CashBookService._is_cash_related(transaction):
                    continue

                txn_type = CashBookService._classify_transaction(transaction)
                debit = float(transaction.get("debit_amount", 0.0) or 0.0)
                credit = float(transaction.get("credit_amount", 0.0) or 0.0)
                if txn_type == "Receipt":
                    running_balance += abs(credit - debit)
                    total_receipts += abs(credit - debit)
                elif txn_type == "Payment":
                    running_balance -= abs(debit - credit)
                    total_payments += abs(debit - credit)

                cash_transactions.append({
                    **transaction,
                    "transaction_type": txn_type,
                    "running_balance": CashBookService._round_amount(running_balance),
                    "balance_type": "Debit" if running_balance >= 0 else "Credit",
                })

            closing_balance = running_balance
            report = {
                "success": True,
                "report_type": "Cash Book",
                "company_id": company_id,
                "account_id": account_id if account_id not in (None, 0) else None,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "opening_balance": CashBookService._round_amount(opening_balance),
                "receipts": CashBookService._round_amount(total_receipts),
                "payments": CashBookService._round_amount(total_payments),
                "transactions": cash_transactions,
                "closing_balance": {
                    "amount": CashBookService._round_amount(abs(closing_balance)),
                    "type": "Debit" if closing_balance >= 0 else "Credit",
                },
                "transaction_count": len(cash_transactions),
                "generated_at": datetime.now().isoformat(),
            }
            return report
        except Exception as e:
            logger.error(f"Error generating cash book: {e}")
            return {"success": False, "error": f"Failed to generate cash book: {str(e)}"}

    @staticmethod
    def search_transactions(cash_book_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        try:
            if not cash_book_data.get("success"):
                return cash_book_data

            search_lower = search_term.lower()
            filtered_transactions = [
                txn for txn in cash_book_data.get("transactions", [])
                if search_lower in str(txn.get("reference_number", "")).lower()
                or search_lower in str(txn.get("narration", "")).lower()
                or search_lower in str(txn.get("transaction_type", "")).lower()
            ]

            running_balance = float(cash_book_data.get("opening_balance", 0.0) or 0.0)
            for transaction in filtered_transactions:
                txn_type = transaction.get("transaction_type")
                if txn_type == "Receipt":
                    running_balance += abs(float(transaction.get("credit_amount", 0.0) or 0.0) - float(transaction.get("debit_amount", 0.0) or 0.0))
                elif txn_type == "Payment":
                    running_balance -= abs(float(transaction.get("debit_amount", 0.0) or 0.0) - float(transaction.get("credit_amount", 0.0) or 0.0))
                transaction["running_balance"] = CashBookService._round_amount(running_balance)
                transaction["balance_type"] = "Debit" if running_balance >= 0 else "Credit"

            filtered_data = cash_book_data.copy()
            filtered_data["transactions"] = filtered_transactions
            filtered_data["transaction_count"] = len(filtered_transactions)
            return filtered_data
        except Exception as e:
            logger.error(f"Error searching transactions: {e}")
            return cash_book_data

    @staticmethod
    def export_cash_book_to_csv(report_data: Dict[str, Any], filename: str = "cash_book") -> Tuple[bool, str]:
        try:
            if not report_data.get("success"):
                return False, "Invalid report data"

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = config.EXPORTS_DIR / f"{filename}_{timestamp}.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Cash Book"])
                writer.writerow(["Period:", f"{report_data.get('from_date', '')} to {report_data.get('to_date', '')}"])
                writer.writerow(["Opening Balance:", report_data.get("opening_balance", 0.0)])
                writer.writerow(["Receipts:", report_data.get("receipts", 0.0)])
                writer.writerow(["Payments:", report_data.get("payments", 0.0)])
                writer.writerow(["Closing Balance:", report_data.get("closing_balance", {}).get("amount", 0.0), report_data.get("closing_balance", {}).get("type", "")])
                writer.writerow([])
                writer.writerow(["Date", "Reference", "Type", "Narration", "Debit", "Credit", "Running Balance", "Dr/Cr"])
                for txn in report_data.get("transactions", []):
                    writer.writerow([
                        txn.get("transaction_date", ""),
                        txn.get("reference_number", ""),
                        txn.get("transaction_type", ""),
                        txn.get("narration", ""),
                        f"{txn.get('debit_amount', 0):,.2f}",
                        f"{txn.get('credit_amount', 0):,.2f}",
                        f"{txn.get('running_balance', 0):,.2f}",
                        txn.get("balance_type", ""),
                    ])

            return True, str(file_path)
        except Exception as e:
            logger.error(f"Error exporting cash book to CSV: {e}")
            return False, f"Export failed: {str(e)}"

    @staticmethod
    def export_to_json(data: Dict[str, Any], filename: str) -> Tuple[bool, str]:
        return report_exporter.export_to_json(data, filename)


cash_book_service = CashBookService()
