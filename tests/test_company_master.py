"""Automated tests for Company Master phase."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from services.company_service import CompanyService, CompanyServiceError
from utils.validators import ValidationError, validate_company_fields


class CompanyMasterTests(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmpdir.name, "test.db")
        self.db = Database(db_path=self._db_path)
        self.db.create_tables()
        self.service = CompanyService(self.db)

    def tearDown(self):
        self.db.close()
        self._tmpdir.cleanup()

    def test_save_and_load_company(self):
        saved = self.service.save_company(
            "Acme Corp",
            "123 Main St",
            "9876543210",
            "info@acme.com",
        )
        self.assertEqual(saved.company_name, "Acme Corp")

        loaded = self.service.load_company()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.company_name, "Acme Corp")
        self.assertEqual(loaded.email, "info@acme.com")

    def test_prevent_duplicate_company(self):
        self.service.save_company("Acme Corp", "", "", "")
        with self.assertRaises(CompanyServiceError):
            self.service.save_company("Other Corp", "", "", "")

    def test_update_company(self):
        saved = self.service.save_company("Acme Corp", "Old Address", "", "")
        updated = self.service.update_company(
            saved.id,
            "Acme Corp",
            "New Address",
            "9999999999",
            "new@acme.com",
        )
        self.assertEqual(updated.address, "New Address")
        self.assertEqual(updated.mobile, "9999999999")

    def test_delete_company(self):
        saved = self.service.save_company("Acme Corp", "", "", "")
        self.service.delete_company(saved.id)
        self.assertIsNone(self.service.load_company())

    def test_required_company_name(self):
        with self.assertRaises(CompanyServiceError):
            self.service.save_company("", "", "", "")

    def test_invalid_email(self):
        with self.assertRaises(CompanyServiceError):
            self.service.save_company("Acme Corp", "", "", "not-an-email")

    def test_validate_company_fields(self):
        with self.assertRaises(ValidationError):
            validate_company_fields("", "", "")


if __name__ == "__main__":
    unittest.main()
