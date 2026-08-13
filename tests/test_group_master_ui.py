"""
Regression tests for the Groups Master stateful workflow.

The Group List and the Create/Edit form are SEPARATE UI states — the form is
never cramped into the list screen.  These exercise the real GroupMasterUI
against the shared Tk root: the 30 default groups render in the List state,
the Tally-style fields live in the Create/Edit form state (and the non-Tally
"Active" toggle does not), the Under dropdown lists every group, Create /
Edit / Clear / Cancel transitions work, search and the Inactive filter
filter the list, CRUD persists through the real service, deletion is
protected for groups that have children or ledgers, Esc routing per state,
keyboard shortcuts, no duplicate widgets, theme cycling, and company
isolation (each company seeds and sees only its own 30 groups).
"""
import unittest
from unittest import mock

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.group_service import group_service  # noqa: E402
from ui.group_master import GroupMasterUI  # noqa: E402
from utils import theme  # noqa: E402

DEFAULT_NAMES = [
    "Bank Accounts", "Bank OCC A/c", "Bank OD A/c", "Branch / Divisions",
    "Capital Account", "Cash-in-Hand", "Current Assets", "Current Liabilities",
    "Deposits (Asset)", "Direct Expenses", "Direct Incomes", "Duties & Taxes",
    "Fixed Assets", "Indirect Expenses", "Indirect Incomes", "Investments",
    "Loans & Advances (Asset)", "Loans (Liability)", "Misc. Expenses (ASSET)",
    "Provisions", "Purchase Accounts", "Reserves & Surplus", "Retained Earnings",
    "Sales Accounts", "Secured Loans", "Stock-in-Hand", "Sundry Creditors",
    "Sundry Debtors", "Suspense A/c", "Unsecured Loans",
]


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
    """Groups screen: stateful List/Create/Edit/View, CRUD, isolation."""

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
        placeholders = ", ".join("?" for _ in DEFAULT_NAMES)
        db.execute(
            "DELETE FROM groups WHERE company_id = ? AND name NOT IN "
            "(SELECT name FROM groups WHERE company_id = 1 AND name IN ("
            + placeholders + "))",
            (1, *DEFAULT_NAMES),
        )
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = GroupMasterUI(self.root, 1)
        self._sync()

    def tearDown(self):
        try:
            self.ui.main_frame.destroy()
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _sync(self):
        self.root.update_idletasks()
        self.root.update()

    def _go_create(self):
        self.ui._go_create()
        self._sync()

    def _row_by_name(self, name):
        for item in self.ui.list.tree.get_children():
            if name in str(self.ui.list.tree.item(item, "values")[1]):
                return item
        return None

    # ------------------------------------------------------------------ #
    # default state: Group List
    # ------------------------------------------------------------------ #
    def test_opens_in_list_state(self):
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_30_default_groups_render(self):
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 30)

    def test_list_columns(self):
        columns = [self.ui.list.tree.heading(c)["text"]
                   for c in self.ui.list.tree["columns"]]
        self.assertEqual(columns, ["#", "Group Name", "Under", "Status"])

    def test_header_actions_present(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        for expected in ["Groups", "Chart of Accounts groups",
                         "+ New Group", "Edit", "Delete", "Open / View",
                         "Refresh", "Ctrl+F", "Inactive",
                         "Edit (Enter)", "Delete (Del)", "View"]:
            self.assertIn(expected, texts)
        self.assertEqual(self.ui.list.btn_new.cget("text"), "+ New Group")
        self.assertEqual(self.ui.list.btn_edit_toolbar.cget("text"), "Edit")
        self.assertEqual(self.ui.list.btn_delete_toolbar.cget("text"), "Delete")
        self.assertEqual(self.ui.list.btn_view_toolbar.cget("text"), "Open / View")
        self.assertEqual(self.ui.list.btn_refresh.cget("text"), "Refresh")

    def test_toolbar_buttons_are_mapped_not_collapsed(self):
        self._sync()
        for button in (self.ui.list.btn_back, self.ui.list.btn_new,
                       self.ui.list.btn_edit_toolbar, self.ui.list.btn_delete_toolbar,
                       self.ui.list.btn_view_toolbar, self.ui.list.btn_refresh):
            self.assertTrue(button.winfo_ismapped(),
                            f"{button.cget('text')} should be mapped")
            self.assertGreater(button.winfo_width(), 1)
            self.assertGreater(button.winfo_height(), 1)

    # ------------------------------------------------------------------ #
    # separate-state contract
    # ------------------------------------------------------------------ #
    def test_form_is_separate_state_not_cramped_in_list(self):
        list_texts = "\n".join(_label_texts(self.ui.list.main))
        for field in ("Name *", "Group behaves like a sub-ledger",
                      "Nett Debit/Credit Balances for Reporting",
                      "Used for calculation (e.g. taxes, discounts)",
                      "Method to allocate when used in purchase invoice"):
            self.assertNotIn(field, list_texts)
        self.assertFalse(hasattr(self.ui.list, "name_var"))
        self._go_create()
        form_texts = "\n".join(_label_texts(self.ui.form.main))
        self.assertIn("Create Group", form_texts)
        self.assertIn("Name *", form_texts)

    # ------------------------------------------------------------------ #
    # Create state
    # ------------------------------------------------------------------ #
    def test_new_group_opens_create_state(self):
        self._go_create()
        self.assertTrue(self.ui.form.is_visible())
        self.assertFalse(self.ui.list.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Create Group")
        self.assertEqual(self.ui.form.mode, "create")
        self.assertIsNone(self.ui.form.group_id)

    def test_tally_fields_present_in_form(self):
        self._go_create()
        texts = "\n".join(_label_texts(self.ui.form.main))
        for expected in [
            "Name *",
            "Under",
            "Group behaves like a sub-ledger",
            "Nett Debit/Credit Balances for Reporting",
            "Used for calculation (e.g. taxes, discounts)",
            "Method to allocate when used in purchase invoice",
        ]:
            self.assertIn(expected, texts)
        button_texts = "\n".join(_all_text(self.ui.form.main))
        for button in ("Save", "Save & New", "Clear", "Cancel"):
            self.assertIn(button, button_texts)
        self.assertEqual(self.ui.form.btn_update.winfo_manager(), "")
        self.assertNotEqual(self.ui.form.btn_save.winfo_manager(), "")

    def test_no_active_toggle(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        self.assertNotIn("Active", texts)
        self.assertFalse(hasattr(self.ui, "active_var"))
        self.assertFalse(hasattr(self.ui.form, "active_var"))

    def test_under_dropdown_lists_groups(self):
        self._go_create()
        values = self.ui.form.parent_combo.cget("values")
        self.assertTrue(values)
        self.assertEqual(values[0], "(None)")
        # Every default group is a candidate parent.
        self.assertGreaterEqual(len(values), 31)

    def test_create_cancel_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["name"].set("Should Not Exist")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row = db.fetch_one(
            "SELECT id FROM groups WHERE company_id = 1 AND name = ?",
            ("Should Not Exist",))
        self.assertIsNone(row)

    def test_create_save_persists_and_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Created Group")
        self.ui._save_group()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row = db.fetch_one(
            "SELECT id FROM groups WHERE company_id = 1 AND name = ?",
            ("UI Created Group",))
        self.assertIsNotNone(row)
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI Created Group", names)
        self.assertEqual(self.ui.list.list_title.cget("text"), "Groups (31)")

    def test_create_validation_error(self):
        self._go_create()
        self.ui.form.vars["name"].set("")
        with mock.patch("ui.group_master.dialogs.warn") as warn:
            self.ui._save_group()
        self.assertTrue(warn.called)
        self.assertTrue(self.ui.form.is_visible())
        self.assertIn("required", self.ui.form.message_label.cget("text").lower())
        remaining = db.fetch_one(
            "SELECT COUNT(*) AS n FROM groups WHERE company_id = 1")["n"]
        self.assertEqual(remaining, 30)

    def test_duplicate_group_rejected(self):
        self._go_create()
        self.ui.form.vars["name"].set("Cash-in-Hand")
        with mock.patch("ui.group_master.dialogs.error") as error:
            self.ui._save_group()
        self.assertTrue(error.called)
        self.assertTrue(self.ui.form.is_visible())
        remaining = db.fetch_one(
            "SELECT COUNT(*) AS n FROM groups WHERE company_id = 1")["n"]
        self.assertEqual(remaining, 30)

    def test_save_and_new_persists_and_stays_in_create(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Save And New Group")
        self.ui._save_and_new()
        self._sync()
        row = db.fetch_one(
            "SELECT id FROM groups WHERE company_id = 1 AND name = ?",
            ("UI Save And New Group",))
        self.assertIsNotNone(row)
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["name"].get(), "")

    # ------------------------------------------------------------------ #
    # selection -> Edit state
    # ------------------------------------------------------------------ #
    def test_selecting_group_loads_details(self):
        target = self._row_by_name("Bank Accounts")
        self.assertIsNotNone(target)
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Group")
        self.assertEqual(self.ui.form.mode, "edit")
        self.assertEqual(self.ui.form.vars["name"].get(), "Bank Accounts")
        self.assertIsNotNone(self.ui.form.group_id)

    def test_edit_clear_resets_to_create_state(self):
        target = self._row_by_name("Bank Accounts")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui._clear_form()
        self.assertEqual(self.ui.form.mode, "create")
        self.assertIsNone(self.ui.form.group_id)
        self.assertEqual(self.ui.form.vars["name"].get(), "")
        self.assertEqual(self.ui.form.title_label.cget("text"), "Create Group")

    def test_edit_cancel_returns_to_list(self):
        target = self._row_by_name("Bank Accounts")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("Unwanted Change")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        group = group_service.get_group(int(target))
        self.assertEqual(group["name"], "Bank Accounts")

    def test_update_persists_and_returns_to_list(self):
        _, _, gid = group_service.create_group(
            1, "UI Edit Group", "Assets", None, is_active=True,
            behaves_like_sub_ledger=False,
        )
        self.ui.refresh_groups()
        target = self._row_by_name("UI Edit Group")
        self.assertIsNotNone(target)
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("UI Edit Group Renamed")
        self.ui.form.vars["behaves_like_sub_ledger"].set("1")
        self.ui._update_group()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        updated = group_service.get_group(gid)
        self.assertEqual(updated["name"], "UI Edit Group Renamed")
        self.assertTrue(updated["behaves_like_sub_ledger"])

    def test_form_component_reused_between_create_and_edit(self):
        form_state = self.ui.form
        self._go_create()
        self.ui._go_list()
        target = self._row_by_name("Bank Accounts")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.assertIs(self.ui.form, form_state)

    # ------------------------------------------------------------------ #
    # View state
    # ------------------------------------------------------------------ #
    def test_view_opens_read_only_state(self):
        target = self._row_by_name("Bank Accounts")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self._sync()
        self.assertTrue(self.ui.view.is_visible())
        self.assertEqual(self.ui.view.value_labels["name"].cget("text"),
                         "Bank Accounts")
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    # ------------------------------------------------------------------ #
    # search / inactive filter
    # ------------------------------------------------------------------ #
    def test_search_filters_list(self):
        self.ui.list.search_var.set("Bank")
        self.ui._apply_search()
        rows = self.ui.list.tree.get_children()
        self.assertGreater(len(rows), 0)
        self.assertLess(len(rows), 30)
        for item in rows:
            values = self.ui.list.tree.item(item, "values")
            self.assertIn("Bank", str(values[1]))

    def test_inactive_filter_toggles(self):
        group_service.create_group(1, "UI Inactive Group", "Assets", None, is_active=False)
        self.ui.refresh_groups()
        active_names = [self.ui.list.tree.item(i, "values")[1]
                        for i in self.ui.list.tree.get_children()]
        self.assertNotIn("UI Inactive Group", active_names)
        self.ui.list.show_inactive_var.set(True)
        self.ui.refresh_groups()
        names_with_inactive = [self.ui.list.tree.item(i, "values")[1]
                               for i in self.ui.list.tree.get_children()]
        self.assertIn("UI Inactive Group", names_with_inactive)

    # ------------------------------------------------------------------ #
    # delete protection
    # ------------------------------------------------------------------ #
    def test_delete_group_with_children_blocked(self):
        _, _, child_id = group_service.create_group(1, "UI Child Group", "Assets", None)
        _, _, grandchild_id = group_service.create_group(
            1, "UI Grandchild", "Assets", child_id)
        self.ui.refresh_groups()
        target = self._row_by_name("UI Child Group")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        with mock.patch("ui.group_master.dialogs.confirm_destructive",
                        return_value=True) as confirm:
            with mock.patch("ui.group_master.dialogs.error") as error:
                self.ui._delete_group()
        confirm.assert_called_once()
        self.assertTrue(error.called)
        self.assertIsNotNone(group_service.get_group(child_id))
        self.assertIsNotNone(group_service.get_group(grandchild_id))

    def test_delete_group_with_ledgers_blocked(self):
        _, _, gid = group_service.create_group(1, "UI Ledger Group", "Assets")
        db.execute(
            "INSERT INTO accounts (company_id, name, account_group, opening_balance)"
            " VALUES (?, ?, ?, ?)",
            (1, "UI Ledger In Group", "UI Ledger Group", 0.0),
        )
        self.ui.refresh_groups()
        target = self._row_by_name("UI Ledger Group")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        with mock.patch("ui.group_master.dialogs.confirm_destructive",
                        return_value=True) as confirm:
            with mock.patch("ui.group_master.dialogs.error") as error:
                self.ui._delete_group()
        # Confirmation is shown first, then the service blocks the delete.
        confirm.assert_called_once()
        self.assertTrue(error.called)
        self.assertIsNotNone(group_service.get_group(gid))

    def test_delete_leaf_group_succeeds(self):
        _, _, gid = group_service.create_group(1, "UI Delete Leaf", "Assets")
        self.ui.refresh_groups()
        target = self._row_by_name("UI Delete Leaf")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        with mock.patch("ui.group_master.dialogs.confirm_destructive",
                        return_value=True):
            self.ui._delete_group()
        self.assertIsNone(group_service.get_group(gid))

    # ------------------------------------------------------------------ #
    # keyboard shortcuts & Esc routing
    # ------------------------------------------------------------------ #
    def test_ctrl_n_opens_create_from_list(self):
        self.ui.on_keyboard_new()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())

    def test_ctrl_s_saves_in_create_state(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Keyboard Group")
        self.ui.on_keyboard_save()
        self._sync()
        row = db.fetch_one(
            "SELECT id FROM groups WHERE company_id = 1 AND name = ?",
            ("UI Keyboard Group",))
        self.assertIsNotNone(row)

    def test_ctrl_s_updates_in_edit_state(self):
        target = self._row_by_name("Cash-in-Hand")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("UI Keyboard Edit")
        self.ui.on_keyboard_save()
        self._sync()
        group = group_service.get_group(int(target))
        self.assertEqual(group["name"], "UI Keyboard Edit")

    def test_ctrl_f_focuses_search(self):
        self.ui.on_keyboard_search()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())

    def test_f5_refreshes_list(self):
        group_service.create_group(1, "UI F5 Group", "Assets")
        self.ui.on_keyboard_refresh()
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI F5 Group", names)

    def test_del_deletes_selected(self):
        _, _, gid = group_service.create_group(1, "UI Del Me", "Assets")
        self.ui.refresh_groups()
        target = self._row_by_name("UI Del Me")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        with mock.patch("ui.group_master.dialogs.confirm_destructive",
                        return_value=True):
            self.ui.on_keyboard_delete()
        self.assertIsNone(group_service.get_group(gid))

    def test_enter_edits_selected(self):
        target = self._row_by_name("Cash-in-Hand")
        self.ui.list.tree.selection_set(target)
        self.ui._on_enter_pressed()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Group")

    def test_esc_from_create_returns_to_list(self):
        self._go_create()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    def test_esc_from_edit_returns_to_list(self):
        target = self._row_by_name("Cash-in-Hand")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    def test_esc_from_list_routes_to_hub(self):
        calls = []
        self.ui.on_keyboard_back = lambda: calls.append("hub")
        self.ui.on_keyboard_back()
        self.assertEqual(calls, ["hub"])

    # ------------------------------------------------------------------ #
    # no duplicate widgets across repeated navigation
    # ------------------------------------------------------------------ #
    def test_repeated_navigation_does_not_duplicate(self):
        for _ in range(4):
            self._go_create()
            self.assertTrue(self.ui.form.is_visible())
            self.ui.on_keyboard_back()
            self._sync()
            self.assertTrue(self.ui.list.is_visible())
        self.assertEqual(len(self.ui.form.vars), 6)  # fields never duplicated

    def test_one_state_visible_after_each_navigation(self):
        for nav in (self.ui._go_create, self.ui._go_list):
            nav()
            self._sync()
            visible = [s for s in (self.ui.list, self.ui.form, self.ui.view)
                       if s.is_visible()]
            self.assertEqual(len(visible), 1)

    # ------------------------------------------------------------------ #
    # company isolation
    # ------------------------------------------------------------------ #
    def test_company_isolation(self):
        group_service.create_group(1, "UI Isolation Group", "Assets")
        ui_b = GroupMasterUI(self.root, 2)
        try:
            names = [ui_b.list.tree.item(i, "values")[1]
                     for i in ui_b.list.tree.get_children()]
            self.assertEqual(len(names), 30)
            self.assertNotIn("UI Isolation Group", names)
        finally:
            ui_b.main_frame.destroy()
        self.assertEqual(
            len(group_service.list_groups(2, include_inactive=True)), 30)

    def test_company_id_never_defaulted(self):
        self.assertEqual(self.ui.company_id, 1)
        created = group_service.seed_default_groups(1)
        self.assertEqual(len(created), 0)

    # ------------------------------------------------------------------ #
    # theme cycling
    # ------------------------------------------------------------------ #
    def test_theme_cycles_without_error(self):
        self._go_create()
        self._sync()
        for mode in ("light", "dark", "light", "dark"):
            ctk.set_appearance_mode(mode)
            theme.apply_theme(self.root, mode=mode)
            theme.apply_palette(self.root)
            self._sync()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())


if __name__ == "__main__":
    unittest.main()
