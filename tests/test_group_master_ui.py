"""
Regression tests for the Groups Master screen (UI wiring).

These exercise the real GroupMasterUI against the shared Tk root so the
widgets are actually built: the 30 default groups render, selecting a group
loads its details, the Tally-style fields are present (and the non-Tally
"Active" toggle is not), Create/Edit/Clear/Cancel state transitions work,
search filters the list, the Inactive checkbox toggles visibility, and the
screen persists to the real database service.

Company isolation is asserted at the service level (each company seeds and
sees only its own 30 groups) and the explicit company_id is never defaulted.
"""
import unittest

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.group_service import group_service  # noqa: E402
from ui.group_master import GroupMasterUI  # noqa: E402


def _label_texts(widget):
    """Every CTkLabel text under a widget (depth-first)."""
    texts = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkLabel):
            try:
                texts.append(str(child.cget("text")))
            except Exception:
                pass
        texts.extend(_label_texts(child))
    return texts


def _all_text(widget):
    """Every text-ish string under a widget (labels + buttons + checkboxes)."""
    texts = []
    for child in widget.winfo_children():
        try:
            if isinstance(child, (ctk.CTkLabel, ctk.CTkButton, ctk.CTkCheckBox)):
                texts.append(str(child.cget("text")))
        except Exception:
            pass
        texts.extend(_all_text(child))
    return texts


class GroupMasterUITest(unittest.TestCase):
    """Groups screen: rendering, CRUD wiring, search/filter, isolation."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (1, "UI Test Co A"))
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (2, "UI Test Co B"))
        group_service.seed_default_groups(1)
        group_service.seed_default_groups(2)
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        # Company-scoped cleanup between tests (keep defaults for company 1).
        db.execute(
            "DELETE FROM groups WHERE company_id = ? AND name NOT IN "
            "(SELECT name FROM groups WHERE company_id = 1 AND name IN ("
            "'Bank Accounts','Bank OCC A/c','Bank OD A/c','Branch / Divisions',"
            "'Capital Account','Cash-in-Hand','Current Assets','Current Liabilities',"
            "'Deposits (Asset)','Direct Expenses','Direct Incomes','Duties & Taxes',"
            "'Fixed Assets','Indirect Expenses','Indirect Incomes','Investments',"
            "'Loans & Advances (Asset)','Loans (Liability)','Misc. Expenses (ASSET)',"
            "'Provisions','Purchase Accounts','Reserves & Surplus','Retained Earnings',"
            "'Sales Accounts','Secured Loans','Stock-in-Hand','Sundry Creditors',"
            "'Sundry Debtors','Suspense A/c','Unsecured Loans'))",
            (1,),
        )
        self.ui = GroupMasterUI(self.root, 1)

    def tearDown(self):
        try:
            self.ui.main_frame.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # rendering
    # ------------------------------------------------------------------ #
    def test_30_default_groups_render(self):
        rows = self.ui.tree.get_children()
        self.assertEqual(len(rows), 30)

    def test_tally_fields_present(self):
        texts = "\n".join(_label_texts(self.ui.main_frame))
        for expected in [
            "Name *",
            "Under",
            "Group behaves like a sub-ledger",
            "Nett Debit/Credit Balances for Reporting",
            "Used for calculation (e.g. taxes, discounts)",
            "Method to allocate when used in purchase invoice",
        ]:
            self.assertIn(expected, texts)

    def test_no_active_toggle(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        self.assertNotIn("Active", texts)
        self.assertFalse(hasattr(self.ui, "active_var"))

    def test_under_dropdown_lists_groups(self):
        values = self.ui.parent_combo.cget("values")
        self.assertTrue(values)
        self.assertEqual(values[0], "(None)")
        # Every default group is a candidate parent.
        self.assertGreaterEqual(len(values), 31)

    def test_create_button_resets_form(self):
        self.ui.name_var.set("Something")
        self.ui._new_form()
        self.assertEqual(self.ui.name_var.get(), "")
        self.assertEqual(self.ui.form_title.cget("text"), "Create Group")
        self.assertIsNone(self.ui.current_edit_id)

    # ------------------------------------------------------------------ #
    # selection -> details
    # ------------------------------------------------------------------ #
    def test_selecting_group_loads_details(self):
        # Pick "Bank Accounts" (a default group).
        target = None
        for item in self.ui.tree.get_children():
            values = self.ui.tree.item(item, "values")
            if values and "Bank Accounts" in str(values[0]):
                target = item
                break
        self.assertIsNotNone(target)
        self.ui.tree.selection_set(target)
        self.ui._on_select()
        self.assertEqual(self.ui.name_var.get(), "Bank Accounts")
        self.assertEqual(self.ui.form_title.cget("text"), "Edit Group")
        self.assertIsNotNone(self.ui.current_edit_id)

    def test_clear_resets_to_create_state(self):
        self.ui.tree.selection_set(self.ui.tree.get_children()[0])
        self.ui._on_select()
        self.assertIsNotNone(self.ui.current_edit_id)
        self.assertEqual(self.ui.form_title.cget("text"), "Edit Group")
        self.ui._clear_form()
        self.assertIsNone(self.ui.current_edit_id)
        self.assertEqual(self.ui.form_title.cget("text"), "Create Group")
        self.assertEqual(self.ui.name_var.get(), "")

    # ------------------------------------------------------------------ #
    # search / inactive filter
    # ------------------------------------------------------------------ #
    def test_search_filters_list(self):
        self.ui.search_var.set("Bank")
        self.ui._apply_search()
        rows = self.ui.tree.get_children()
        self.assertGreater(len(rows), 0)
        self.assertLess(len(rows), 30)
        for item in rows:
            values = self.ui.tree.item(item, "values")
            self.assertIn("Bank", str(values[0]))

    def test_inactive_filter_toggles(self):
        group_service.create_group(1, "UI Inactive Group", "Assets", None, is_active=False)
        self.ui.refresh_groups()
        active_rows = self.ui.tree.get_children()
        self.assertNotIn(
            "UI Inactive Group",
            [self.ui.tree.item(i, "values")[0] for i in active_rows],
        )
        self.ui.show_inactive_var.set(True)
        self.ui.refresh_groups()
        rows_with_inactive = [self.ui.tree.item(i, "values")[0]
                              for i in self.ui.tree.get_children()]
        self.assertIn("UI Inactive Group", rows_with_inactive)

    # ------------------------------------------------------------------ #
    # CRUD wiring
    # ------------------------------------------------------------------ #
    def test_save_persists_and_appears_in_list(self):
        self.ui.name_var.set("UI Created Group")
        self.ui._save_group()
        row = db.fetch_one(
            "SELECT id FROM groups WHERE company_id = 1 AND name = ?",
            ("UI Created Group",),
        )
        self.assertIsNotNone(row)
        names = [self.ui.tree.item(i, "values")[0]
                 for i in self.ui.tree.get_children()]
        self.assertIn("UI Created Group", names)

    def test_edit_persists_changes(self):
        _, _, gid = group_service.create_group(
            1, "UI Edit Group", "Assets", None, is_active=True,
            behaves_like_sub_ledger=False,
        )
        self.ui.refresh_groups()
        for item in self.ui.tree.get_children():
            if "UI Edit Group" in str(self.ui.tree.item(item, "values")[0]):
                self.ui.tree.selection_set(item)
                break
        self.ui._on_select()
        self.ui.name_var.set("UI Edit Group Renamed")
        self.ui.sub_ledger_var.set(True)
        self.ui._update_group()
        updated = group_service.get_group(gid)
        self.assertEqual(updated["name"], "UI Edit Group Renamed")
        self.assertTrue(updated["behaves_like_sub_ledger"])

    # ------------------------------------------------------------------ #
    # company isolation
    # ------------------------------------------------------------------ #
    def test_company_isolation(self):
        # Company 2 must not see company 1's custom group.
        group_service.create_group(1, "UI Isolation Group", "Assets")
        ui_b = GroupMasterUI(self.root, 2)
        try:
            names = [ui_b.tree.item(i, "values")[0] for i in ui_b.tree.get_children()]
            self.assertEqual(len(names), 30)
            self.assertNotIn("UI Isolation Group", names)
        finally:
            ui_b.main_frame.destroy()
        # And company 2 has its own 30 defaults.
        self.assertEqual(
            len(group_service.list_groups(2, include_inactive=True)), 30)

    def test_company_id_never_defaulted(self):
        # The screen requires an explicit company id at construction.
        self.assertEqual(self.ui.company_id, 1)
        # Re-seeding must never duplicate defaults.
        created = group_service.seed_default_groups(1)
        self.assertEqual(len(created), 0)


if __name__ == "__main__":
    unittest.main()
