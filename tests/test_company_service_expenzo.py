"""
Tests for the Expenzo multi-company master service (Phase 1).

Verifies multi-company create/list/switch, financial year, books-begin
date, and that the legacy single-row save behavior is preserved.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from services.company_service import CompanyService, CompanyServiceError


class TestCompanyServiceExpenzo(unittest.TestCase):
    """Multi-company CRUD against the Expenzo ``companies`` table."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmpdir.name, "test.db")
        self.db = Database(db_path=self._db_path)
        self.db.create_tables()
        self.service = CompanyService(self.db)

    def tearDown(self):
        self.db.close()
        self._tmpdir.cleanup()

    def test_create_multiple_companies(self):
        c1 = self.service.create_company("Acme Corp")
        c2 = self.service.create_company("Beta Ltd")
        companies = self.service.list_companies()
        self.assertEqual(len(companies), 2)
        names = {c["name"] for c in companies}
        self.assertEqual(names, {"Acme Corp", "Beta Ltd"})
        self.assertNotEqual(c1.id, c2.id)

    def test_create_duplicate_name_rejected(self):
        self.service.create_company("Acme Corp")
        with self.assertRaises(CompanyServiceError):
            self.service.create_company("acme corp")

    def test_get_company_by_id(self):
        created = self.service.create_company("Acme Corp")
        loaded = self.service.get_company(created.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.company_name, "Acme Corp")

    def test_financial_year_and_books_begin(self):
        created = self.service.create_company(
            "Acme Corp",
            financial_year_start="01-04",
            financial_year_end="31-03",
            books_begin_date="2026-04-01",
        )
        self.assertEqual(created.financial_year_start, "01-04")
        self.assertEqual(created.financial_year_end, "31-03")
        self.assertEqual(created.books_begin_date, "2026-04-01")

        loaded = self.service.get_company(created.id)
        self.assertEqual(loaded.books_begin_date, "2026-04-01")

    def test_update_company(self):
        created = self.service.create_company("Acme Corp")
        updated = self.service.update_company(
            created.id, "Acme Corp Ltd", books_begin_date="2026-05-01")
        self.assertEqual(updated.company_name, "Acme Corp Ltd")
        self.assertEqual(updated.books_begin_date, "2026-05-01")
        self.assertEqual(self.service.get_company(created.id).company_name, "Acme Corp Ltd")

    def test_delete_company(self):
        created = self.service.create_company("Acme Corp")
        self.service.delete_company(created.id)
        self.assertIsNone(self.service.get_company(created.id))
        with self.assertRaises(CompanyServiceError):
            self.service.delete_company(created.id)

    def test_legacy_save_single_row_behavior(self):
        # The legacy save refuses a second company (single-row semantics).
        self.service.save_company("First Co", "", "", "")
        with self.assertRaises(CompanyServiceError):
            self.service.save_company("Second Co", "", "", "")

    def test_legacy_load_first_company(self):
        self.service.save_company("First Co", "Addr", "9876543210", "a@b.co")
        loaded = self.service.load_company()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.company_name, "First Co")
        self.assertEqual(loaded.address, "Addr")

    def test_validation_still_applies(self):
        with self.assertRaises(CompanyServiceError):
            self.service.create_company("", "addr", "", "")
        with self.assertRaises(CompanyServiceError):
            self.service.create_company("Bad Co", "", "123", "not-an-email")

    def test_list_companies_search(self):
        self.service.create_company("Acme Corp")
        self.service.create_company("Beta Ltd")
        results = self.service.list_companies("acme")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Acme Corp")


if __name__ == "__main__":
    unittest.main()
