"""
Tests for the Chart of Accounts Group master service (Phase 1).
"""
import unittest
from datetime import date

import config

config.DATABASE_PATH = ':memory:'

from database.database import db
from services.group_service import group_service, GroupService


class TestGroupService(unittest.TestCase):
    """Group CRUD, hierarchy, and seed integrity."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        cls.company_id = 1
        db.execute(
            """
            INSERT INTO companies (id, name, financial_year_start, financial_year_end)
            VALUES (?, ?, ?, ?)
            """,
            (cls.company_id, 'Group Test Co', '01-04', '31-03'),
        )

    def setUp(self):
        db.execute("DELETE FROM groups")
        db.execute("DELETE FROM accounts")

    def test_create_group(self):
        ok, message, group_id = group_service.create_group(self.company_id, 'Assets', 'Assets')
        self.assertTrue(ok)
        self.assertIsNotNone(group_id)
        group = group_service.get_group(group_id)
        self.assertEqual(group['name'], 'Assets')
        self.assertEqual(group['group_type'], 'Assets')
        self.assertTrue(group['is_active'])

    def test_create_group_requires_name(self):
        ok, message, _ = group_service.create_group(self.company_id, '', 'Assets')
        self.assertFalse(ok)
        self.assertIn('required', message.lower())

    def test_create_duplicate_group(self):
        group_service.create_group(self.company_id, 'Income', 'Income')
        ok, message, _ = group_service.create_group(self.company_id, 'income', 'Income')
        self.assertFalse(ok)
        self.assertIn('already exists', message.lower())

    def test_create_invalid_group_type(self):
        ok, message, _ = group_service.create_group(self.company_id, 'Whatever', 'NotAType')
        self.assertFalse(ok)

    def test_create_child_group(self):
        _, _, parent_id = group_service.create_group(self.company_id, 'Assets', 'Assets')
        ok, message, child_id = group_service.create_group(
            self.company_id, 'Bank Accounts', 'Assets', parent_id)
        self.assertTrue(ok)
        child = group_service.get_group(child_id)
        self.assertEqual(child['parent_id'], parent_id)

    def test_update_group(self):
        _, _, group_id = group_service.create_group(self.company_id, 'Income', 'Income')
        ok, message = group_service.update_group(group_id, 'Indirect Income', 'Income')
        self.assertTrue(ok)
        self.assertEqual(group_service.get_group(group_id)['name'], 'Indirect Income')

    def test_update_group_self_parent_rejected(self):
        _, _, group_id = group_service.create_group(self.company_id, 'Assets', 'Assets')
        ok, message = group_service.update_group(group_id, 'Assets', 'Assets', parent_id=group_id)
        self.assertFalse(ok)
        self.assertIn('own parent', message.lower())

    def test_group_tree_ordering(self):
        _, _, assets_id = group_service.create_group(self.company_id, 'Assets', 'Assets')
        group_service.create_group(self.company_id, 'Bank Accounts', 'Assets', assets_id)
        group_service.create_group(self.company_id, 'Cash-in-Hand', 'Assets', assets_id)
        tree = group_service.group_tree(self.company_id)
        self.assertEqual(len(tree), 3)
        root = next(g for g in tree if g['depth'] == 0)
        self.assertEqual(root['name'], 'Assets')
        children = [g for g in tree if g['depth'] == 1]
        self.assertEqual(len(children), 2)

    def test_delete_group_with_children_blocked(self):
        _, _, parent_id = group_service.create_group(self.company_id, 'Assets', 'Assets')
        group_service.create_group(self.company_id, 'Bank Accounts', 'Assets', parent_id)
        ok, message = group_service.delete_group(parent_id)
        self.assertFalse(ok)
        self.assertIn('sub-groups', message.lower())

    def test_delete_group_with_ledgers_blocked(self):
        _, _, group_id = group_service.create_group(self.company_id, 'Expense', 'Expense')
        from services.account_service import account_service
        account_service.create_account(self.company_id, 'Rent', 'RENT', 'Expense', 0.0, 'Debit')
        ok, message = group_service.delete_group(group_id)
        self.assertFalse(ok)
        self.assertIn('ledgers', message.lower())

    def test_delete_leaf_group(self):
        _, _, group_id = group_service.create_group(self.company_id, 'Misc', 'Expense')
        ok, message = group_service.delete_group(group_id)
        self.assertTrue(ok)
        self.assertIsNone(group_service.get_group(group_id))

    def test_search_groups(self):
        group_service.create_group(self.company_id, 'Sundry Debtors', 'Assets')
        group_service.create_group(self.company_id, 'Sundry Creditors', 'Liabilities')
        results = group_service.search_groups(self.company_id, 'sundry')
        self.assertEqual(len(results), 2)


if __name__ == '__main__':
    unittest.main()
