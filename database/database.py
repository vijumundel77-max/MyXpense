"""
Database access layer for MyXpense / Expenzo V1 migration.

This module keeps the existing company-master APIs alive while adding the
accounting schema needed by the new report services.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional, Sequence

from config import DATABASE_PATH


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path or DATABASE_PATH)
        self.initialize_database()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize_database(self) -> None:
        self.create_tables()
        self.seed_default_data()

    def create_tables(self) -> None:
        with self.transaction() as cursor:
            self._create_legacy_tables(cursor)
            self._create_expenzo_tables(cursor)

    def _create_legacy_tables(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                address TEXT,
                mobile TEXT,
                email TEXT
            )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_company_name
            ON company(company_name)
        """)

    def _create_expenzo_tables(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                financial_year_start TEXT DEFAULT '01-04',
                financial_year_end TEXT DEFAULT '31-03',
                address TEXT DEFAULT '',
                mobile TEXT DEFAULT '',
                email TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                code TEXT DEFAULT '',
                account_group TEXT NOT NULL,
                opening_balance REAL DEFAULT 0.0,
                opening_balance_type TEXT DEFAULT 'Debit',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                voucher_number TEXT NOT NULL,
                voucher_type TEXT NOT NULL,
                voucher_date TEXT NOT NULL,
                reference_number TEXT DEFAULT '',
                narration TEXT DEFAULT '',
                due_date TEXT DEFAULT NULL,
                status TEXT DEFAULT 'Draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voucher_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                debit_amount REAL DEFAULT 0.0,
                credit_amount REAL DEFAULT 0.0,
                narration TEXT DEFAULT '',
                contra_account_id INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (contra_account_id) REFERENCES accounts(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financial_years (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT DEFAULT 'Active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

    def seed_default_data(self) -> None:
        with self.transaction() as cursor:
            self._seed_legacy_defaults(cursor)
            self._seed_expenzo_defaults(cursor)

    def _seed_legacy_defaults(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("SELECT value FROM settings WHERE key = 'cash_balance'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO settings (key, value) VALUES ('cash_balance', '0.0')")

        cursor.execute("SELECT value FROM settings WHERE key = 'user_name'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO settings (key, value) VALUES ('user_name', 'Personal User')")

        default_categories = [
            ("Salary", "Income", "dollar-sign", "#10B981", 1),
            ("Investments", "Income", "trending-up", "#3B82F6", 1),
            ("Freelnance / Side Business", "Income", "briefcase", "#8B5CF6", 1),
            ("Other Income", "Income", "plus-circle", "#06B6D4", 1),
            ("Food & Dining", "Expense", "coffee", "#EF4444", 1),
            ("Shopping & Apparel", "Expense", "shopping-bag", "#F59E0B", 1),
            ("Groceries", "Expense", "shopping-cart", "#10B981", 1),
            ("Rent & Housing", "Expense", "home", "#6366F1", 1),
            ("Utilities & Bills", "Expense", "zap", "#EC4899", 1),
            ("Transportation & Fuel", "Expense", "truck", "#14B8A6", 1),
            ("Entertainment & Movies", "Expense", "film", "#8B5CF6", 1),
            ("Health & Medical", "Expense", "heart", "#E11D48", 1),
            ("Education & Learning", "Expense", "book", "#0284C7", 1),
            ("General Expense", "Expense", "grid", "#64748B", 1),
        ]
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK(type IN ('Income', 'Expense')),
                    icon TEXT DEFAULT 'folder',
                    color TEXT DEFAULT '#3B82F6',
                    is_system INTEGER DEFAULT 0
                )
            """)

        for name, type_, icon, color, is_sys in default_categories:
            cursor.execute("""
                INSERT INTO categories (name, type, icon, color, is_system)
                SELECT ?, ?, ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = ?)
            """, (name, type_, icon, color, is_sys, name))

        cursor.execute("SELECT COUNT(*) FROM bank_accounts")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bank_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bank_name TEXT NOT NULL,
                    account_number TEXT DEFAULT '',
                    account_type TEXT DEFAULT 'Savings',
                    opening_balance REAL DEFAULT 0.0,
                    current_balance REAL DEFAULT 0.0,
                    color_code TEXT DEFAULT '#3B82F6',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO bank_accounts (
                    bank_name, account_number, account_type,
                    opening_balance, current_balance, color_code
                ) VALUES ('Main Savings Account', 'XXXX-1234', 'Savings', 0.0, 0.0, '#3B82F6')
            """)

    def _seed_expenzo_defaults(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute("SELECT COUNT(*) FROM companies")
        if cursor.fetchone()[0] == 0:
            return

    def execute(self, query: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as cursor:
            cursor.execute(query, params)
            return cursor.lastrowid or cursor.rowcount

    def fetch_all(self, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            conn.close()

    def fetch_one(self, query: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            conn.close()

    def execute_query(self, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.fetch_all(query, params)

    def execute_single(self, query: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        return self.fetch_one(query, params)

    def execute_non_query(self, query: str, params: Sequence[Any] = ()) -> int:
        return self.execute(query, params)

    # Legacy company-master API
    def company_exists(self) -> bool:
        row = self.fetch_one("SELECT COUNT(*) FROM company")
        return bool(row[0]) if row else False

    def company_name_exists(self, company_name: str, exclude_id: int | None = None) -> bool:
        if exclude_id is None:
            row = self.fetch_one(
                "SELECT COUNT(*) FROM company WHERE LOWER(company_name) = LOWER(?)",
                (company_name,),
            )
        else:
            row = self.fetch_one(
                "SELECT COUNT(*) FROM company WHERE LOWER(company_name) = LOWER(?) AND id != ?",
                (company_name, exclude_id),
            )
        return bool(row[0]) if row else False

    def get_company(self) -> tuple | None:
        row = self.fetch_one(
            """
            SELECT id, company_name, address, mobile, email
            FROM company
            ORDER BY id
            LIMIT 1
            """
        )
        return tuple(row) if row is not None else None

    def get_company_by_id(self, company_id: int) -> tuple | None:
        row = self.fetch_one(
            """
            SELECT id, company_name, address, mobile, email
            FROM company
            WHERE id = ?
            """,
            (company_id,),
        )
        return tuple(row) if row is not None else None

    def insert_company(self, company_name: str, address: str, mobile: str, email: str) -> int:
        return self.execute(
            """
            INSERT INTO company (company_name, address, mobile, email)
            VALUES (?, ?, ?, ?)
            """,
            (company_name, address, mobile, email),
        )

    def update_company(self, company_id: int, company_name: str, address: str, mobile: str, email: str) -> None:
        self.execute(
            """
            UPDATE company
            SET company_name = ?, address = ?, mobile = ?, email = ?
            WHERE id = ?
            """,
            (company_name, address, mobile, email, company_id),
        )
        if not self.get_company_by_id(company_id):
            raise ValueError("Company record not found.")

    def delete_company(self, company_id: int) -> None:
        self.execute("DELETE FROM company WHERE id = ?", (company_id,))
        if not self.fetch_one("SELECT 1 FROM company WHERE id = ?", (company_id,)):
            return
        raise ValueError("Company record not found.")

    def close(self) -> None:
        return


db = Database()
