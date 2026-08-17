"""
Expenzo — Offline Company Backup / Restore Service

Exports the COMPLETE selected company (company details, groups, ledgers,
parties, bank accounts, opening balances, vouchers/transactions and the
company-scoped settings) into one portable ``.expbackup`` file (JSON), and
imports such a file back into the database — fully offline.

Import rules:
  * Never overwrites an existing company automatically.
  * If the company name already exists, the caller decides between
    "import as new company" (a ``(2)`` suffix is appended) or
    "replace existing company" (explicit, destructive, caller confirms).
  * Corrupted / incompatible / tampered files are rejected safely.

The archive carries a version header so future schema changes stay
compatible.  No accounting logic is changed: data is read and written
through plain row inserts inside one transaction per company.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from database.database import Database

# --------------------------------------------------------------------------- #
# Format contract
# --------------------------------------------------------------------------- #
BACKUP_FORMAT = "expenzo-company-backup"
BACKUP_VERSION = 1

# Tables whose rows are fully owned by a company and restored as-is.
# Column lists are explicit (not SELECT *) so the archive is stable across
# schema migrations; restoring only inserts the listed columns.
_COMPANY_TABLES: Dict[str, List[str]] = {
    "companies": [
        "name", "financial_year_start", "financial_year_end", "address",
        "state", "country", "pincode", "mobile", "email", "books_begin_date",
        "created_at", "updated_at",
    ],
    "groups": [
        "name", "group_type", "parent_id",
        "behaves_like_sub_ledger", "net_balance_for_reporting",
        "used_for_calculation", "allocation_method", "is_active",
        "created_at", "updated_at",
    ],
    "accounts": [
        "name", "code", "alias", "account_group",
        "opening_balance", "opening_balance_type", "address", "state",
        "country", "pincode", "contact_person", "mobile", "email",
        "credit_limit", "credit_days", "is_active", "created_at", "updated_at",
    ],
    "financial_years": [
        "name", "start_date", "end_date", "status",
        "created_at", "updated_at",
    ],
    "bank_accounts": [
        "bank_name", "account_name", "account_number",
        "account_type", "opening_balance", "opening_balance_type",
        "current_balance", "color_code", "ifsc_code", "branch", "notes",
        "created_at",
    ],
    "vouchers": [
        "voucher_number", "voucher_type", "voucher_date",
        "reference_number", "narration", "due_date", "status",
        "created_at", "updated_at",
    ],
    "voucher_details": [
        "voucher_id", "account_id", "debit_amount", "credit_amount",
        "narration", "contra_account_id", "created_at",
    ],
    "recent_reports": [
        "report_name", "opened_by", "opened_at",
    ],
}

# Non-company-scoped rows referenced by company data (restored idempotently).
# ``settings`` holds the legacy app-level cash balance / user name; a backup
# restores the keys it actually owns so the target app keeps its own defaults
# for anything the backup never touched.
_SETTINGS_KEYS = ("cash_balance", "user_name")


class BackupError(Exception):
    """Raised when a backup cannot be created or restored."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _safe_company_filename(name: str) -> str:
    """Sanitize a company name for use inside a file name."""
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in (" ", "-", "_"))
    cleaned = cleaned.strip().replace(" ", "_") or "Company"
    return cleaned[:60]


class CompanyBackupService:
    """Create and restore portable company backup files."""

    def __init__(self, database: Database):
        self._db = database

    # ------------------------------------------------------------------ #
    # export
    # ------------------------------------------------------------------ #
    def export_company(self, company_id: int, export_dir: Path | str | None = None) -> Path:
        """Back up the complete company into one portable .expbackup file.

        Returns the created file path.  Works fully offline.
        """
        company = self._db.fetch_one(
            "SELECT * FROM companies WHERE id = ?", (company_id,))
        if company is None:
            raise BackupError("Company not found; nothing to back up.")

        export_root = Path(export_dir or self._default_export_dir())
        export_root.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "company_name": company["name"],
            "company_id": company_id,
            "data": self._collect_company_data(company_id),
        }

        file_name = "Expenzo_Backup_{}_{}.expbackup".format(
            _safe_company_filename(company["name"]),
            datetime.now().strftime("%Y-%m-%d"),
        )
        output_path = export_root / file_name
        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path

    def _collect_company_data(self, company_id: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"settings": {}}

        # Company row itself (no company_id column).
        company_rows = self._db.fetch_all(
            "SELECT * FROM companies WHERE id = ?", (company_id,))
        payload["companies"] = []
        for row in company_rows:
            item = {col: row[col] for col in _COMPANY_TABLES["companies"]}
            item["_backup_id"] = row["id"]
            payload["companies"].append(item)

        # Child tables keyed by company_id, carrying original row ids so
        # foreign keys can be remapped on restore.
        child_tables = (
            "groups", "accounts", "financial_years", "bank_accounts",
            "vouchers", "recent_reports",
        )
        for table in child_tables:
            rows = self._db.fetch_all(
                f"SELECT * FROM {table} WHERE company_id = ?", (company_id,))
            payload[table] = []
            for row in rows:
                item = {col: row[col] for col in _COMPANY_TABLES[table]}
                item["_backup_id"] = row["id"]
                payload[table].append(item)

        # Voucher details (owned via the voucher, not the company).
        details = self._db.fetch_all(
            """
            SELECT vd.* FROM voucher_details vd
            JOIN vouchers v ON v.id = vd.voucher_id
            WHERE v.company_id = ?
            """,
            (company_id,),
        )
        payload["voucher_details"] = []
        for row in details:
            item = {col: row[col] for col in _COMPANY_TABLES["voucher_details"]}
            item["_backup_id"] = row["id"]
            payload["voucher_details"].append(item)

        for key in _SETTINGS_KEYS:
            row = self._db.fetch_one(
                "SELECT value FROM settings WHERE key = ?", (key,))
            if row:
                payload["settings"][key] = row["value"]
        return payload

    # ------------------------------------------------------------------ #
    # import
    # ------------------------------------------------------------------ #
    @staticmethod
    def validate_backup_file(path: Path | str) -> Dict[str, Any]:
        """Load and validate a backup file; raise BackupError on any problem.

        Returns the parsed archive (dict) on success.
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise BackupError("Backup file not found.")
        if file_path.suffix.lower() != ".expbackup":
            raise BackupError(
                "Not an Expenzo backup file (.expbackup expected).")
        try:
            raw = file_path.read_text(encoding="utf-8")
            archive = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BackupError(
                "The file is corrupted or is not a valid backup file.")
        if not isinstance(archive, dict):
            raise BackupError("The backup file has an invalid structure.")
        if archive.get("format") != BACKUP_FORMAT:
            raise BackupError(
                "This file is not an Expenzo company backup "
                "(unknown format marker).")
        try:
            version = int(archive.get("version", 0))
        except (TypeError, ValueError):
            raise BackupError("The backup version is invalid.")
        if version < 1 or version > BACKUP_VERSION:
            raise BackupError(
                f"This backup was created by an incompatible Expenzo version "
                f"(backup version {version}; this app supports "
                f"{BACKUP_VERSION}).")
        data = archive.get("data")
        if not isinstance(data, dict):
            raise BackupError("The backup contains no company data.")
        company_rows = data.get("companies")
        if not isinstance(company_rows, list) or not company_rows:
            raise BackupError("The backup contains no company record.")
        if not isinstance(company_rows[0], dict) or not company_rows[0].get("name"):
            raise BackupError("The backup company record is invalid.")
        return archive

    def import_backup(
        self,
        path: Path | str,
        mode: str = "new",
        replace_company_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Restore a backup into the database.

        mode:
          "new"      — import as a new company.  If the name already exists a
                       unique "(2)"/"(3)" suffix is appended (never overwrites).
          "replace"  — replace the existing company identified by
                       ``replace_company_id`` (explicit, destructive).

        Returns a summary dict: {company_id, company_name, counts}.
        """
        archive = self.validate_backup_file(path)
        data = archive["data"]

        if mode not in ("new", "replace"):
            raise BackupError("Unknown import mode.")

        with self._db.transaction() as cursor:
            if mode == "replace":
                if replace_company_id is None:
                    raise BackupError(
                        "Replace mode requires the company to replace.")
                self._delete_company_rows(cursor, int(replace_company_id))
                company_name = str(archive["company_name"])
            else:
                company_name = self._unique_name(
                    cursor, str(archive["company_name"]))

            company_id = self._insert_company(cursor, data, company_name)
            self._insert_children(cursor, data, company_id)
            self._restore_settings(cursor, data)

        counts = self._count_company_data(company_id)
        return {
            "company_id": company_id,
            "company_name": company_name,
            "counts": counts,
        }

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _default_export_dir() -> Path:
        import config
        return config.EXPORTS_DIR

    @staticmethod
    def _unique_name(cursor, base_name: str) -> str:
        taken = {
            row["name"]
            for row in cursor.execute(
                "SELECT name FROM companies WHERE LOWER(name) LIKE LOWER(?)",
                (f"{base_name}%",),
            ).fetchall()
        }
        candidate = base_name
        counter = 2
        while candidate in taken:
            candidate = f"{base_name} ({counter})"
            counter += 1
        return candidate

    @staticmethod
    def _insert_company(cursor, data: Dict[str, Any], company_name: str) -> int:
        source = data["companies"][0]
        cursor.execute(
            """
            INSERT INTO companies (
                name, financial_year_start, financial_year_end,
                address, state, country, pincode, mobile, email,
                books_begin_date, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_name,
                source.get("financial_year_start", "01-04"),
                source.get("financial_year_end", "31-03"),
                source.get("address", ""),
                source.get("state", ""),
                source.get("country", ""),
                source.get("pincode", ""),
                source.get("mobile", ""),
                source.get("email", ""),
                source.get("books_begin_date", ""),
                source.get("created_at") or datetime.now().isoformat(
                    timespec="seconds"),
                source.get("updated_at") or datetime.now().isoformat(
                    timespec="seconds"),
            ),
        )
        return cursor.lastrowid

    def _insert_children(self, cursor, data: Dict[str, Any], company_id: int) -> None:
        # id mapping: old id -> new id (per table), for FK preservation.
        account_map: Dict[int, int] = {}
        group_map: Dict[int, int] = {}
        voucher_map: Dict[int, int] = {}

        # --- groups (parents re-linked after all group rows exist) ---
        pending_parents: List[tuple] = []
        for row in data.get("groups", []):
            cursor.execute(
                """
                INSERT INTO groups (
                    company_id, name, group_type, parent_id,
                    behaves_like_sub_ledger, net_balance_for_reporting,
                    used_for_calculation, allocation_method, is_active,
                    created_at, updated_at
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, row.get("name", ""),
                    row.get("group_type", "Assets"),
                    row.get("behaves_like_sub_ledger", 0),
                    row.get("net_balance_for_reporting", 0),
                    row.get("used_for_calculation", 0),
                    row.get("allocation_method", ""),
                    row.get("is_active", 1),
                    row.get("created_at") or datetime.now().isoformat(
                        timespec="seconds"),
                    row.get("updated_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )
            new_id = cursor.lastrowid
            group_map[self._legacy_id(row)] = new_id
            pending_parents.append((new_id, row.get("parent_id")))

        for new_id, old_parent in pending_parents:
            new_parent = group_map.get(old_parent) if old_parent else None
            cursor.execute(
                "UPDATE groups SET parent_id = ? WHERE id = ?",
                (new_parent, new_id),
            )

        # --- accounts ---
        for row in data.get("accounts", []):
            cursor.execute(
                """
                INSERT INTO accounts (
                    company_id, name, code, alias, account_group,
                    opening_balance, opening_balance_type, address, state,
                    country, pincode, contact_person, mobile, email,
                    credit_limit, credit_days, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, row.get("name", ""), row.get("code", ""),
                    row.get("alias", ""), row.get("account_group", ""),
                    row.get("opening_balance", 0.0),
                    row.get("opening_balance_type", "Debit"),
                    row.get("address", ""), row.get("state", ""),
                    row.get("country", ""), row.get("pincode", ""),
                    row.get("contact_person", ""), row.get("mobile", ""),
                    row.get("email", ""), row.get("credit_limit", 0.0),
                    row.get("credit_days", 0), row.get("is_active", 1),
                    row.get("created_at") or datetime.now().isoformat(
                        timespec="seconds"),
                    row.get("updated_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )
            account_map[self._legacy_id(row)] = cursor.lastrowid

        # --- financial years ---
        for row in data.get("financial_years", []):
            cursor.execute(
                """
                INSERT INTO financial_years (
                    company_id, name, start_date, end_date, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, row.get("name", ""), row.get("start_date", ""),
                    row.get("end_date", ""), row.get("status", "Active"),
                    row.get("created_at") or datetime.now().isoformat(
                        timespec="seconds"),
                    row.get("updated_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )

        # --- bank accounts ---
        for row in data.get("bank_accounts", []):
            cursor.execute(
                """
                INSERT INTO bank_accounts (
                    company_id, bank_name, account_name, account_number,
                    account_type, opening_balance, opening_balance_type,
                    current_balance, color_code, ifsc_code, branch, notes,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, row.get("bank_name", ""),
                    row.get("account_name", ""),
                    row.get("account_number", ""),
                    row.get("account_type", "Savings"),
                    row.get("opening_balance", 0.0),
                    row.get("opening_balance_type", "Debit"),
                    row.get("current_balance", 0.0),
                    row.get("color_code", "#3B82F6"),
                    row.get("ifsc_code", ""), row.get("branch", ""),
                    row.get("notes", ""),
                    row.get("created_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )

        # --- vouchers ---
        for row in data.get("vouchers", []):
            cursor.execute(
                """
                INSERT INTO vouchers (
                    company_id, voucher_number, voucher_type, voucher_date,
                    reference_number, narration, due_date, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, row.get("voucher_number", ""),
                    row.get("voucher_type", ""), row.get("voucher_date", ""),
                    row.get("reference_number", ""), row.get("narration", ""),
                    row.get("due_date"), row.get("status", "Draft"),
                    row.get("created_at") or datetime.now().isoformat(
                        timespec="seconds"),
                    row.get("updated_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )
            voucher_map[self._legacy_id(row)] = cursor.lastrowid

        # --- voucher details (FK remapped via voucher + account maps) ---
        for row in data.get("voucher_details", []):
            old_voucher = int(row.get("voucher_id", 0))
            old_account = int(row.get("account_id", 0))
            old_contra = row.get("contra_account_id")
            cursor.execute(
                """
                INSERT INTO voucher_details (
                    voucher_id, account_id, debit_amount, credit_amount,
                    narration, contra_account_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    voucher_map.get(old_voucher, 0),
                    account_map.get(old_account, 0),
                    row.get("debit_amount", 0.0),
                    row.get("credit_amount", 0.0),
                    row.get("narration", ""),
                    account_map.get(int(old_contra)) if old_contra else None,
                    row.get("created_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )

        # --- recent reports ---
        for row in data.get("recent_reports", []):
            cursor.execute(
                """
                INSERT INTO recent_reports (company_id, report_name, opened_by, opened_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    company_id, row.get("report_name", ""),
                    row.get("opened_by", "Admin"),
                    row.get("opened_at") or datetime.now().isoformat(
                        timespec="seconds"),
                ),
            )

    @staticmethod
    def _legacy_id(row: Dict[str, Any]) -> int:
        """The original row id captured in the backup."""
        return int(row.get("_backup_id", 0))

    @staticmethod
    def _restore_settings(cursor, data: Dict[str, Any]) -> None:
        settings = data.get("settings") or {}
        for key in _SETTINGS_KEYS:
            if key in settings:
                cursor.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, settings[key]),
                )

    @staticmethod
    def _delete_company_rows(cursor, company_id: int) -> None:
        """Delete all rows owned by a company before replace-import.

        Foreign keys with ON DELETE CASCADE handle children, but older
        databases may predate those constraints, so delete explicitly.
        """
        cursor.execute(
            """
            DELETE FROM voucher_details
            WHERE voucher_id IN (SELECT id FROM vouchers WHERE company_id = ?)
            """,
            (company_id,),
        )
        for table in ("recent_reports", "vouchers",
                      "financial_years", "bank_accounts", "accounts",
                      "groups"):
            cursor.execute(f"DELETE FROM {table} WHERE company_id = ?",
                           (company_id,))
        cursor.execute("DELETE FROM companies WHERE id = ?", (company_id,))

    def _count_company_data(self, company_id: int) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for table in ("groups", "accounts", "bank_accounts", "vouchers",
                      "financial_years", "recent_reports"):
            row = self._db.fetch_one(
                f"SELECT COUNT(*) FROM {table} WHERE company_id = ?",
                (company_id,),
            )
            counts[table] = int(row[0]) if row else 0
        detail_row = self._db.fetch_one(
            """
            SELECT COUNT(*) FROM voucher_details
            WHERE voucher_id IN (SELECT id FROM vouchers WHERE company_id = ?)
            """,
            (company_id,),
        )
        counts["voucher_details"] = int(detail_row[0]) if detail_row else 0
        return counts
