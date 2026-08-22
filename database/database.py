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
        self._db_path = str(db_path) if db_path is not None else None
        self.db_path = self._resolve_path()
        self._initialized = False

    def _resolve_path(self) -> str:
        if self._db_path is not None:
            return self._db_path
        # Re-read config so tests can point DATABASE_PATH before first use.
        from config import DATABASE_PATH as _DATABASE_PATH
        return str(_DATABASE_PATH)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            # Pick up a possibly-changed config.DATABASE_PATH before first init.
            self.db_path = self._resolve_path()
            self.initialize_database()

    def get_connection(self) -> sqlite3.Connection:
        self._ensure_initialized()
        if self.db_path == ':memory:':
            # Connection-per-operation would discard the in-memory DB between
            # calls; keep a single persistent connection instead.
            if getattr(self, '_memory_conn', None) is None:
                self._memory_conn = sqlite3.connect(self.db_path)
                self._memory_conn.row_factory = sqlite3.Row
                self._memory_conn.execute("PRAGMA foreign_keys = ON;")
                self._apply_pragmas(self._memory_conn)
            return self._memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        self._apply_pragmas(conn)
        return conn

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply SQLite PRAGMA settings for performance optimization."""
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = 10000;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA mmap_size = 268435456;")  # 256MB
        conn.execute("PRAGMA page_size = 4096;")

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
            if conn is not getattr(self, '_memory_conn', None):
                conn.close()

    def initialize_database(self) -> None:
        """(Re)initialize the database. Calling this explicitly resets any
        cached in-memory connection so tests get a clean schema."""
        if self._db_path is None:
            # Re-read config so tests can point DATABASE_PATH before init.
            self.db_path = self._resolve_path()
        self._memory_conn = None
        self._initialized = False
        self._initializing = True
        try:
            self.create_tables()
            self.seed_default_data()
            self._initialized = True
        finally:
            self._initializing = False

    def _ensure_initialized(self) -> None:
        if not self._initialized and not getattr(self, '_initializing', False):
            # Pick up a possibly-changed config.DATABASE_PATH before first init.
            self.db_path = self._resolve_path()
            self.initialize_database()

    SCHEMA_VERSION = 2

    def create_tables(self) -> None:
        with self.transaction() as cursor:
            self._create_legacy_tables(cursor)
            self._create_expenzo_tables(cursor)
            self._migrate_schema(cursor)
            # Migration hook: bump SCHEMA_VERSION and add ALTERs here when the
            # schema evolves in a future release.
            cursor.execute(f"PRAGMA user_version = {int(self.SCHEMA_VERSION)}")

    def _migrate_schema(self, cursor: sqlite3.Cursor) -> None:
        """Additive ALTERs for existing databases (idempotent)."""
        companies_columns = [
            str(r[1]) for r in cursor.execute("PRAGMA table_info(companies)").fetchall()
        ]
        if "books_begin_date" not in companies_columns:
            cursor.execute(
                "ALTER TABLE companies ADD COLUMN books_begin_date TEXT DEFAULT ''"
            )
        if "state" not in companies_columns:
            cursor.execute("ALTER TABLE companies ADD COLUMN state TEXT DEFAULT ''")
        if "country" not in companies_columns:
            cursor.execute("ALTER TABLE companies ADD COLUMN country TEXT DEFAULT ''")
        if "pincode" not in companies_columns:
            cursor.execute("ALTER TABLE companies ADD COLUMN pincode TEXT DEFAULT ''")

        accounts_columns = [
            str(r[1]) for r in cursor.execute("PRAGMA table_info(accounts)").fetchall()
        ]
        if "alias" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN alias TEXT DEFAULT ''")
        if "address" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN address TEXT DEFAULT ''")
        if "state" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN state TEXT DEFAULT ''")
        if "country" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN country TEXT DEFAULT ''")
        if "pincode" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN pincode TEXT DEFAULT ''")
        if "contact_person" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN contact_person TEXT DEFAULT ''")
        if "mobile" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN mobile TEXT DEFAULT ''")
        if "email" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN email TEXT DEFAULT ''")
        if "credit_limit" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN credit_limit REAL DEFAULT 0.0")
        if "credit_days" not in accounts_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN credit_days INTEGER DEFAULT 0")

        bank_columns = [
            str(r[1]) for r in cursor.execute("PRAGMA table_info(bank_accounts)").fetchall()
        ]
        if "company_id" not in bank_columns:
            cursor.execute(
                "ALTER TABLE bank_accounts ADD COLUMN company_id INTEGER DEFAULT 1"
            )
        if "account_name" not in bank_columns:
            cursor.execute("ALTER TABLE bank_accounts ADD COLUMN account_name TEXT DEFAULT ''")
        if "opening_balance_type" not in bank_columns:
            cursor.execute(
                "ALTER TABLE bank_accounts ADD COLUMN opening_balance_type TEXT DEFAULT 'Debit'"
            )
        if "ifsc_code" not in bank_columns:
            cursor.execute("ALTER TABLE bank_accounts ADD COLUMN ifsc_code TEXT DEFAULT ''")
        if "branch" not in bank_columns:
            cursor.execute("ALTER TABLE bank_accounts ADD COLUMN branch TEXT DEFAULT ''")
        if "notes" not in bank_columns:
            cursor.execute("ALTER TABLE bank_accounts ADD COLUMN notes TEXT DEFAULT ''")

        groups_columns = [
            str(r[1]) for r in cursor.execute("PRAGMA table_info(groups)").fetchall()
        ]
        if "behaves_like_sub_ledger" not in groups_columns:
            cursor.execute(
                "ALTER TABLE groups ADD COLUMN behaves_like_sub_ledger INTEGER DEFAULT 0"
            )
        if "net_balance_for_reporting" not in groups_columns:
            cursor.execute(
                "ALTER TABLE groups ADD COLUMN net_balance_for_reporting INTEGER DEFAULT 0"
            )
        if "used_for_calculation" not in groups_columns:
            cursor.execute(
                "ALTER TABLE groups ADD COLUMN used_for_calculation INTEGER DEFAULT 0"
            )
        if "allocation_method" not in groups_columns:
            cursor.execute(
                "ALTER TABLE groups ADD COLUMN allocation_method TEXT DEFAULT ''"
            )

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
                state TEXT DEFAULT '',
                country TEXT DEFAULT '',
                pincode TEXT DEFAULT '',
                mobile TEXT DEFAULT '',
                email TEXT DEFAULT '',
                books_begin_date TEXT DEFAULT '',
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
                alias TEXT DEFAULT '',
                account_group TEXT NOT NULL,
                opening_balance REAL DEFAULT 0.0,
                opening_balance_type TEXT DEFAULT 'Debit',
                address TEXT DEFAULT '',
                state TEXT DEFAULT '',
                country TEXT DEFAULT '',
                pincode TEXT DEFAULT '',
                contact_person TEXT DEFAULT '',
                mobile TEXT DEFAULT '',
                email TEXT DEFAULT '',
                credit_limit REAL DEFAULT 0.0,
                credit_days INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                group_type TEXT DEFAULT 'Assets',
                parent_id INTEGER DEFAULT NULL,
                behaves_like_sub_ledger INTEGER DEFAULT 0,
                net_balance_for_reporting INTEGER DEFAULT 0,
                used_for_calculation INTEGER DEFAULT 0,
                allocation_method TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES groups(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_company_name
            ON groups(company_id, name)
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bank_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER DEFAULT 1,
                bank_name TEXT NOT NULL,
                account_name TEXT DEFAULT '',
                account_number TEXT DEFAULT '',
                account_type TEXT DEFAULT 'Savings',
                opening_balance REAL DEFAULT 0.0,
                opening_balance_type TEXT DEFAULT 'Debit',
                current_balance REAL DEFAULT 0.0,
                color_code TEXT DEFAULT '#3B82F6',
                ifsc_code TEXT DEFAULT '',
                branch TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('Income', 'Expense')),
                category_id INTEGER,
                account_mode TEXT NOT NULL CHECK(account_mode IN ('Cash', 'Bank')),
                bank_account_id INTEGER,
                party_id INTEGER,
                payment_method TEXT DEFAULT 'Cash',
                transaction_date TEXT NOT NULL,
                transaction_time TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
                FOREIGN KEY (bank_account_id) REFERENCES bank_accounts(id) ON DELETE SET NULL,
                FOREIGN KEY (party_id) REFERENCES parties(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                opening_balance REAL DEFAULT 0.0,
                current_balance REAL DEFAULT 0.0,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                report_name TEXT NOT NULL,
                opened_by TEXT DEFAULT 'Admin',
                opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, report_name),
                FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_account_type TEXT NOT NULL CHECK(from_account_type IN ('Cash', 'Bank')),
                from_bank_id INTEGER,
                to_account_type TEXT NOT NULL CHECK(to_account_type IN ('Cash', 'Bank')),
                to_bank_id INTEGER,
                amount REAL NOT NULL,
                transfer_date TEXT NOT NULL,
                transfer_time TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (from_bank_id) REFERENCES bank_accounts(id) ON DELETE SET NULL,
                FOREIGN KEY (to_bank_id) REFERENCES bank_accounts(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vouchers_company_id
            ON vouchers(company_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vouchers_company_date
            ON vouchers(company_id, voucher_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vouchers_comp_type
            ON vouchers(company_id, voucher_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_vdetail_voucher_acc
            ON voucher_details(voucher_id, account_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_accounts_company
            ON accounts(company_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_voucher_details_account_id
            ON voucher_details(account_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_party_id
            ON transactions(party_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date
            ON transactions(transaction_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_bank_account_id
            ON transactions(bank_account_id)
        """)

    def seed_default_data(self) -> None:
        with self.transaction() as cursor:
            self._seed_legacy_defaults(cursor)

    def seed_expenzo_defaults(self) -> None:
        """Seed a default company + standard Chart of Accounts on first app
        run (when the Expenzo accounting tables are empty).

        Called explicitly by the application shell at startup; never run
        automatically by ``initialize_database`` so the test suite (which
        initializes empty in-memory/file databases) stays deterministic.
        """
        if self.db_path == ':memory:':
            return
        with self.transaction() as cursor:
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
        for name, type_, icon, color, is_sys in default_categories:
            cursor.execute("""
                INSERT INTO categories (name, type, icon, color, is_system)
                SELECT ?, ?, ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM categories WHERE name = ?)
            """, (name, type_, icon, color, is_sys, name))

        cursor.execute("SELECT COUNT(*) FROM bank_accounts")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO bank_accounts (
                    bank_name, account_number, account_type,
                    opening_balance, current_balance, color_code
                ) VALUES ('Main Savings Account', 'XXXX-1234', 'Savings', 0.0, 0.0, '#3B82F6')
            """)

    def _seed_expenzo_defaults(self, cursor: sqlite3.Cursor) -> None:
        """Seed a default company + standard Chart of Accounts when the
        Expenzo accounting tables are empty (first run only).
        """
        cursor.execute("SELECT COUNT(*) FROM companies")
        if cursor.fetchone()[0] > 0:
            return

        cursor.execute("""
            INSERT OR IGNORE INTO companies (
                name, financial_year_start, financial_year_end, address, mobile, email
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, ("My Business", "01-04", "31-03", "", "", ""))
        company_id = cursor.lastrowid

        default_groups = [
            # (name, group_type, parent_id)
            ("Assets", "Assets", None),
            ("Liabilities", "Liabilities", None),
            ("Capital", "Capital", None),
            ("Income", "Income", None),
            ("Expense", "Expense", None),
            ("Current Assets", "Assets", None),
            ("Current Liabilities", "Liabilities", None),
            ("Bank Accounts", "Assets", None),
            ("Cash-in-Hand", "Assets", None),
            ("Sundry Debtors", "Assets", None),
            ("Sundry Creditors", "Liabilities", None),
            ("Direct Income", "Income", None),
            ("Indirect Income", "Income", None),
            ("Direct Expense", "Expense", None),
            ("Indirect Expense", "Expense", None),
            ("Fixed Assets", "Assets", None),
            ("Investments", "Assets", None),
            ("Loans & Advances", "Assets", None),
            ("Duties & Taxes", "Liabilities", None),
            ("Provisions", "Liabilities", None),
            ("Reserves & Surplus", "Capital", None),
            ("Sales Accounts", "Income", None),
            ("Purchase Accounts", "Expense", None),
        ]
        group_ids: dict[str, int] = {}
        for name, group_type, _ in default_groups:
            cursor.execute(
                """
                INSERT INTO groups (company_id, name, group_type, parent_id, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (company_id, name, group_type, None),
            )
            group_ids[name] = cursor.lastrowid

        default_accounts = [
            # (name, code, group, opening, opening_type)
            ("Cash", "CASH", "Cash-in-Hand", 0.0, "Debit"),
            ("Bank", "BANK", "Bank Accounts", 0.0, "Debit"),
            ("Capital", "CAP", "Capital", 0.0, "Credit"),
            ("Sales", "SALES", "Sales Accounts", 0.0, "Credit"),
            ("Purchases", "PURCH", "Purchase Accounts", 0.0, "Debit"),
            ("Sundry Debtors", "DEBTORS", "Sundry Debtors", 0.0, "Debit"),
            ("Sundry Creditors", "CREDITORS", "Sundry Creditors", 0.0, "Credit"),
        ]
        for name, code, group_name, opening, opening_type in default_accounts:
            cursor.execute(
                """
                INSERT INTO accounts (
                    company_id, name, code, account_group,
                    opening_balance, opening_balance_type, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (company_id, name, code, group_name, opening, opening_type),
            )

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
            if conn is not getattr(self, '_memory_conn', None):
                conn.close()

    def fetch_one(self, query: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            if conn is not getattr(self, '_memory_conn', None):
                conn.close()

    def execute_query(self, query: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.fetch_all(query, params)

    def execute_single(self, query: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        return self.fetch_one(query, params)

    def execute_non_query(self, query: str, params: Sequence[Any] = ()) -> int:
        return self.execute(query, params)

    # Legacy company-master API (now backed by the Expenzo `companies` table)
    def company_exists(self) -> bool:
        row = self.fetch_one("SELECT COUNT(*) FROM companies")
        return bool(row[0]) if row else False

    def company_name_exists(self, company_name: str, exclude_id: int | None = None) -> bool:
        if exclude_id is None:
            row = self.fetch_one(
                "SELECT COUNT(*) FROM companies WHERE LOWER(name) = LOWER(?)",
                (company_name,),
            )
        else:
            row = self.fetch_one(
                "SELECT COUNT(*) FROM companies WHERE LOWER(name) = LOWER(?) AND id != ?",
                (company_name, exclude_id),
            )
        return bool(row[0]) if row else False

    def get_company(self) -> tuple | None:
        row = self.fetch_one(
            """
            SELECT id, name, address, mobile, email
            FROM companies
            ORDER BY id
            LIMIT 1
            """
        )
        return tuple(row) if row is not None else None

    def get_company_by_id(self, company_id: int) -> tuple | None:
        row = self.fetch_one(
            """
            SELECT id, name, address, mobile, email
            FROM companies
            WHERE id = ?
            """,
            (company_id,),
        )
        return tuple(row) if row is not None else None

    def insert_company(self, company_name: str, address: str, mobile: str, email: str) -> int:
        return self.execute(
            """
            INSERT INTO companies (name, address, mobile, email)
            VALUES (?, ?, ?, ?)
            """,
            (company_name, address, mobile, email),
        )

    def update_company(self, company_id: int, company_name: str, address: str, mobile: str, email: str) -> None:
        if not self.get_company_by_id(company_id):
            raise ValueError("Company record not found.")
        self.execute(
            """
            UPDATE companies
            SET name = ?, address = ?, mobile = ?, email = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (company_name, address, mobile, email, company_id),
        )

    def delete_company(self, company_id: int) -> None:
        self.execute("DELETE FROM companies WHERE id = ?", (company_id,))
        if not self.fetch_one("SELECT 1 FROM companies WHERE id = ?", (company_id,)):
            return
        raise ValueError("Company record not found.")

    def close(self) -> None:
        return


db = Database()
