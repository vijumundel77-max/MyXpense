"""Round-trip tests for the offline company backup / restore service."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from services.company_backup_service import BackupError, CompanyBackupService
from services.company_service import CompanyService


class CompanyBackupRoundTripTests(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmpdir.name, "test.db")
        self.db = Database(db_path=self._db_path)
        self.db.create_tables()
        # Remove the legacy seeded default bank account (company_id defaults to
        # 1) so it does not get captured in the backup of the first company.
        self.db.execute("DELETE FROM bank_accounts WHERE bank_name = 'Main Savings Account'")
        self.service = CompanyBackupService(self.db)
        self.company_service = CompanyService(self.db)
        self._export_dir = Path(self._tmpdir.name) / "backups"
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        try:
            self.db.close()
        finally:
            self._tmpdir.cleanup()

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _seed_company(self, name="Acme Traders") -> int:
        company = self.company_service.create_company(
            name, address="42 Main Road", mobile="9876543210",
            email="acme@example.com", financial_year_start="01-04",
            financial_year_end="31-03", books_begin_date="01-04-2025",
            state="Maharashtra", country="India", pincode="400001",
        )
        cid = company.id
        self.db.execute(
            "INSERT INTO groups (company_id, name, group_type, is_active) "
            "VALUES (?, 'Assets', 'Assets', 1)",
            (cid,),
        )
        cash = self.db.execute(
            "INSERT INTO accounts (company_id, name, code, account_group, "
            "opening_balance, opening_balance_type, is_active) "
            "VALUES (?, 'Cash', 'CASH', 'Cash-in-Hand', 5000.0, 'Debit', 1)",
            (cid,),
        )
        bank = self.db.execute(
            "INSERT INTO accounts (company_id, name, code, account_group, "
            "opening_balance, opening_balance_type, is_active) "
            "VALUES (?, 'Bank', 'BANK', 'Bank Accounts', 10000.0, 'Debit', 1)",
            (cid,),
        )
        creditor = self.db.execute(
            "INSERT INTO accounts (company_id, name, code, account_group, "
            "opening_balance, opening_balance_type, is_active) "
            "VALUES (?, 'ABC Traders', 'ABC', 'Sundry Creditors', 0.0, 'Credit', 1)",
            (cid,),
        )
        self.db.execute(
            "INSERT INTO bank_accounts (company_id, bank_name, account_name, "
            "account_number, account_type, opening_balance, current_balance) "
            "VALUES (?, 'HDFC', 'Main Account', '1234', 'Savings', 10000.0, 12500.0)",
            (cid,),
        )
        self.db.execute(
            "INSERT INTO financial_years (company_id, name, start_date, end_date) "
            "VALUES (?, 'FY 2025-26', '01-04-2025', '31-03-2026')",
            (cid,),
        )
        # voucher 1: Payment PV-0001 (Bank -> ABC Traders)
        v1 = self.db.execute(
            "INSERT INTO vouchers (company_id, voucher_number, voucher_type, "
            "voucher_date, narration, status) "
            "VALUES (?, 'PV-0001', 'Payment', '2026-08-10', 'Payment to ABC', 'Posted')",
            (cid,),
        )
        self.db.execute(
            "INSERT INTO voucher_details (voucher_id, account_id, debit_amount, "
            "credit_amount, narration) VALUES (?, ?, 3000.0, 0.0, 'ABC Traders')",
            (v1, creditor),
        )
        self.db.execute(
            "INSERT INTO voucher_details (voucher_id, account_id, debit_amount, "
            "credit_amount, narration) VALUES (?, ?, 0.0, 3000.0, 'Bank')",
            (v1, bank),
        )
        # voucher 2: Receipt RV-0001 (ABC Traders -> Cash)
        v2 = self.db.execute(
            "INSERT INTO vouchers (company_id, voucher_number, voucher_type, "
            "voucher_date, narration, status) "
            "VALUES (?, 'RV-0001', 'Receipt', '2026-08-11', 'Receipt from ABC', 'Posted')",
            (cid,),
        )
        self.db.execute(
            "INSERT INTO voucher_details (voucher_id, account_id, debit_amount, "
            "credit_amount, narration) VALUES (?, ?, 5000.0, 0.0, 'Cash')",
            (v2, cash),
        )
        self.db.execute(
            "INSERT INTO voucher_details (voucher_id, account_id, debit_amount, "
            "credit_amount, narration) VALUES (?, ?, 0.0, 5000.0, 'ABC Traders')",
            (v2, creditor),
        )
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES ('cash_balance', '1500.50') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        return cid

    def _counts(self, cid) -> dict:
        def count(table):
            row = self.db.fetch_one(
                f"SELECT COUNT(*) FROM {table} WHERE company_id = ?", (cid,))
            return int(row[0]) if row else 0
        counts = {
            "groups": count("groups"),
            "accounts": count("accounts"),
            "bank_accounts": count("bank_accounts"),
            "vouchers": count("vouchers"),
            "financial_years": count("financial_years"),
        }
        detail = self.db.fetch_one(
            "SELECT COUNT(*) FROM voucher_details "
            "WHERE voucher_id IN (SELECT id FROM vouchers WHERE company_id = ?)",
            (cid,))
        counts["voucher_details"] = int(detail[0]) if detail else 0
        return counts

    # ------------------------------------------------------------------ #
    # export
    # ------------------------------------------------------------------ #
    def test_export_creates_portable_file(self):
        cid = self._seed_company()
        path = self.service.export_company(cid, self._export_dir)
        self.assertTrue(path.is_file())
        self.assertEqual(path.suffix, ".expbackup")
        self.assertIn("Expenzo_Backup_Acme_Traders_", path.name)
        archive = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(archive["format"], "expenzo-company-backup")
        self.assertEqual(archive["version"], 1)
        self.assertEqual(archive["company_name"], "Acme Traders")
        data = archive["data"]
        self.assertEqual(len(data["accounts"]), 3)
        self.assertEqual(len(data["vouchers"]), 2)
        self.assertEqual(len(data["voucher_details"]), 4)
        self.assertEqual(data["settings"]["cash_balance"], "1500.50")
        self.assertTrue(all("_backup_id" in r for r in data["accounts"]))

    def test_export_missing_company_raises(self):
        with self.assertRaises(BackupError):
            self.service.export_company(999, self._export_dir)

    # ------------------------------------------------------------------ #
    # import: new company
    # ------------------------------------------------------------------ #
    def test_import_into_clean_database_restores_company(self):
        cid = self._seed_company("Alpha Ltd")
        path = self.service.export_company(cid, self._export_dir)

        # wipe and start a fresh DB (simulates a fresh installation)
        self.db.close()
        os.remove(self._db_path)
        self.db = Database(db_path=self._db_path)
        self.db.create_tables()
        self.db.execute("DELETE FROM bank_accounts WHERE bank_name = 'Main Savings Account'")
        self.service = CompanyBackupService(self.db)
        self.company_service = CompanyService(self.db)

        result = self.service.import_backup(path, mode="new")
        self.assertEqual(result["company_name"], "Alpha Ltd")
        new_cid = result["company_id"]
        counts = self._counts(new_cid)
        self.assertEqual(counts["groups"], 1)
        self.assertEqual(counts["accounts"], 3)
        self.assertEqual(counts["bank_accounts"], 1)
        self.assertEqual(counts["vouchers"], 2)
        self.assertEqual(counts["voucher_details"], 4)
        self.assertEqual(counts["financial_years"], 1)
        # opening balances preserved
        row = self.db.fetch_one(
            "SELECT opening_balance, opening_balance_type FROM accounts "
            "WHERE company_id = ? AND name = 'Cash'", (new_cid,))
        self.assertEqual(float(row["opening_balance"]), 5000.0)
        self.assertEqual(row["opening_balance_type"], "Debit")
        # voucher detail amounts preserved and FKs remapped
        detail = self.db.fetch_one(
            "SELECT debit_amount, credit_amount FROM voucher_details "
            "WHERE voucher_id IN (SELECT id FROM vouchers WHERE company_id = ?)",
            (new_cid,))
        self.assertIsNotNone(detail)
        self.assertEqual(float(detail["debit_amount"]), 3000.0)
        # settings restored
        setting = self.db.fetch_one(
            "SELECT value FROM settings WHERE key = 'cash_balance'")
        self.assertEqual(setting["value"], "1500.50")

    def test_import_duplicate_name_gets_suffix(self):
        self._seed_company("Beta Co")
        cid2 = self._seed_company("Gamma Co")
        path = self.service.export_company(cid2, self._export_dir)
        result = self.service.import_backup(path, mode="new")
        self.assertEqual(result["company_name"], "Gamma Co (2)")
        names = {c["name"] for c in self.company_service.list_companies()}
        self.assertIn("Beta Co", names)
        self.assertIn("Gamma Co", names)

    def test_import_replace_preserves_backup_data(self):
        cid = self._seed_company("Delta Ltd")
        path = self.service.export_company(cid, self._export_dir)
        result = self.service.import_backup(path, mode="replace", replace_company_id=cid)
        counts = self._counts(result["company_id"])
        self.assertEqual(counts["vouchers"], 2)
        self.assertEqual(counts["accounts"], 3)

    def test_replace_requires_target(self):
        cid = self._seed_company("Echo Co")
        path = self.service.export_company(cid, self._export_dir)
        with self.assertRaises(BackupError):
            self.service.import_backup(path, mode="replace", replace_company_id=None)

    # ------------------------------------------------------------------ #
    # validation / corruption
    # ------------------------------------------------------------------ #
    def test_validate_rejects_non_backup(self):
        bad = self._export_dir / "notes.txt"
        bad.write_text("hello", encoding="utf-8")
        with self.assertRaises(BackupError):
            self.service.validate_backup_file(bad)

    def test_validate_rejects_corrupted_json(self):
        bad = self._export_dir / "broken.expbackup"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(BackupError):
            self.service.validate_backup_file(bad)

    def test_validate_rejects_wrong_format(self):
        bad = self._export_dir / "other.expbackup"
        bad.write_text(json.dumps({"format": "something-else", "version": 1}),
                       encoding="utf-8")
        with self.assertRaises(BackupError):
            self.service.validate_backup_file(bad)

    def test_validate_rejects_future_version(self):
        bad = self._export_dir / "future.expbackup"
        bad.write_text(
            json.dumps({"format": "expenzo-company-backup", "version": 99,
                        "data": {"companies": [{"name": "X"}]}}),
            encoding="utf-8")
        with self.assertRaises(BackupError):
            self.service.validate_backup_file(bad)

    def test_validate_rejects_missing_company(self):
        bad = self._export_dir / "empty.expbackup"
        bad.write_text(
            json.dumps({"format": "expenzo-company-backup", "version": 1,
                        "data": {"companies": []}}),
            encoding="utf-8")
        with self.assertRaises(BackupError):
            self.service.validate_backup_file(bad)


if __name__ == "__main__":
    unittest.main()
