"""
Regression tests for the Bank Account Master stateful workflow.

The Bank Account List and the Create/Edit form are SEPARATE UI states — the
form is never cramped into the list screen.  These exercise the real
BankAccountManagementUI against the shared Tk root: List state rendering
(columns, rows, paging hint), header toolbar (visible buttons + search),
Create / Edit / View states, List → Create → List navigation, Esc routing
per state, Ctrl+N/S/F, F5, Del, Enter, CRUD persistence, referenced-account
delete protection, Save & New, no duplicate widgets across repeated
navigation, theme cycling, company isolation, and the explicit "form is a
separate state" contract.
"""
import unittest
from unittest import mock

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.bank_account_service import bank_account_service  # noqa: E402
from ui.bank_account_management import BankAccountManagementUI  # noqa: E402
from utils import theme  # noqa: E402


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


def _seed_bank(company_id, bank_name, account_number="", account_type="Savings",
               opening=0.0, dtype="Debit"):
    success, message = bank_account_service.create_bank_account(
        {
            "bank_name": bank_name,
            "account_name": bank_name + " A/c",
            "account_number": account_number,
            "account_type": account_type,
            "opening_balance": opening,
            "opening_balance_type": dtype,
            "current_balance": opening,
            "ifsc_code": "",
            "branch": "",
            "notes": "",
        },
        company_id=company_id,
    )
    if not success:
        raise AssertionError(message)
    row = db.fetch_one(
        "SELECT id FROM bank_accounts WHERE company_id = ? AND bank_name = ?",
        (company_id, bank_name),
    )
    return row["id"]


class BankAccountManagementUITest(unittest.TestCase):
    """Stateful Bank flow: List/Create/Edit/View."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (1, "UI Bank Co"))
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (2, "UI Bank Co B"))
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        db.execute("DELETE FROM bank_accounts")
        _seed_bank(1, "HDFC Bank", "123456", "Savings", 1000.00, "Debit")
        _seed_bank(1, "ICICI Bank", "654321", "Current", 500.00, "Credit")
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = BankAccountManagementUI(self.root, 1)
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

    def _row_by_bank(self, bank_name):
        for item in self.ui.list.tree.get_children():
            if self.ui.list.tree.item(item, "values")[1] == bank_name:
                return item
        return None

    # ------------------------------------------------------------------ #
    # default state: Bank Account List
    # ------------------------------------------------------------------ #
    def test_opens_in_list_state(self):
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_list_columns_and_rows_visible(self):
        columns = [self.ui.list.tree.heading(c)["text"]
                   for c in self.ui.list.tree["columns"]]
        self.assertEqual(columns, [
            "#", "Bank Name", "Account Name", "Account Number", "Account Type",
            "Opening Balance", "Dr/Cr", "Status"])
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 2)
        values = [self.ui.list.tree.item(i, "values") for i in rows]
        by_bank = {v[1]: v for v in values}
        self.assertEqual(by_bank["HDFC Bank"][3], "123456")
        self.assertEqual(by_bank["HDFC Bank"][4], "Savings")
        self.assertEqual(by_bank["HDFC Bank"][5], "1,000.00")
        self.assertEqual(by_bank["HDFC Bank"][6], "Debit")
        self.assertEqual(by_bank["ICICI Bank"][4], "Current")
        self.assertEqual(by_bank["ICICI Bank"][5], "500.00")
        self.assertEqual(by_bank["ICICI Bank"][6], "Credit")

    def test_list_count_and_paging_hint(self):
        self.assertEqual(self.ui.list.list_title.cget("text"), "Bank Accounts (2)")
        self.assertEqual(self.ui.list.page_label.cget("text"),
                         "Showing 1 to 2 of 2 bank accounts")

    def test_header_actions_present(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        for expected in ["Bank Accounts", "Bank account master",
                         "+ New Bank Account", "Edit", "Delete", "Open / View",
                         "Refresh", "Ctrl+F",
                         "Edit (Enter)", "Delete (Del)", "View"]:
            self.assertIn(expected, texts)
        self.assertEqual(self.ui.list.btn_new.cget("text"), "+ New Bank Account")
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
        header = self.ui.list.main.winfo_children()[0]
        self.assertGreater(header.winfo_height(), 30)
        self.assertTrue(header.winfo_ismapped())

    def test_search_box_in_header_is_mapped(self):
        self._sync()
        self.assertTrue(self.ui.list.search_entry.winfo_ismapped())
        self.assertGreater(self.ui.list.search_entry.winfo_width(), 100)

    def test_selection_enables_actions(self):
        self.assertEqual(self.ui.list.btn_edit.cget("state"), "disabled")
        self.assertEqual(self.ui.list.btn_delete.cget("state"), "disabled")
        self.assertEqual(self.ui.list.btn_view.cget("state"), "disabled")
        row = self.ui.list.tree.get_children()[0]
        self.ui.list.tree.selection_set(row)
        self.ui._on_select()
        self.assertEqual(self.ui.list.selected_id, int(row))
        self.assertEqual(self.ui.list.btn_edit.cget("state"), "normal")
        self.assertEqual(self.ui.list.btn_delete.cget("state"), "normal")
        self.assertEqual(self.ui.list.btn_view.cget("state"), "normal")

    # ------------------------------------------------------------------ #
    # separate-state contract
    # ------------------------------------------------------------------ #
    def test_form_is_separate_state_not_cramped_in_list(self):
        list_texts = "\n".join(_all_text(self.ui.list.main))
        for field in ("Bank Name *", "Account Number", "IFSC Code",
                      "Notes / Remarks"):
            self.assertNotIn(field, list_texts)
        self.assertFalse(hasattr(self.ui.list, "bank_name_var"))
        self._go_create()
        form_texts = "\n".join(_all_text(self.ui.form.main))
        self.assertIn("Create Bank Account", form_texts)
        self.assertIn("Bank Name *", form_texts)

    def test_list_and_form_are_distinct_widgets(self):
        self.assertIsNot(self.ui.list.main, self.ui.form.main)
        self.assertIsNot(self.ui.list.main, self.ui.view.main)
        visible = [s for s in (self.ui.list, self.ui.form, self.ui.view)
                   if s.is_visible()]
        self.assertEqual(len(visible), 1)

    # ------------------------------------------------------------------ #
    # navigation: List -> Create -> List
    # ------------------------------------------------------------------ #
    def test_new_bank_account_opens_create_state(self):
        self._go_create()
        self.assertTrue(self.ui.form.is_visible())
        self.assertFalse(self.ui.list.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Create Bank Account")
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["account_type"].get(), "Savings")
        self.assertEqual(self.ui.form.vars["opening_balance"].get(), "0.00")
        self.assertEqual(self.ui.form.vars["opening_balance_type"].get(), "Debit")

    def test_create_form_fields_present(self):
        self._go_create()
        texts = "\n".join(_all_text(self.ui.form.main))
        for expected in [
            "Bank Name *", "Account Name", "Account Number", "Account Type",
            "Opening Balance", "Dr / Cr", "IFSC Code", "Branch", "Notes / Remarks",
            "Bank Account Information", "Opening Balance", "Branch Details",
        ]:
            self.assertIn(expected, texts)
        for button in ("Save", "Save & New", "Clear", "Cancel"):
            self.assertIn(button, texts)
        self.assertEqual(self.ui.form.btn_update.winfo_manager(), "")
        self.assertNotEqual(self.ui.form.btn_save.winfo_manager(), "")

    def test_create_cancel_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["bank_name"].set("Should Not Exist")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        row = db.fetch_one(
            "SELECT id FROM bank_accounts WHERE company_id = 1 AND bank_name = ?",
            ("Should Not Exist",))
        self.assertIsNone(row)

    def test_create_save_persists_and_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["bank_name"].set("Axis Bank")
        self.ui.form.vars["account_number"].set("999999")
        self.ui.form.vars["account_type"].set("Current")
        self.ui.form.vars["opening_balance"].set("250.50")
        self.ui.form.vars["ifsc_code"].set("UTIB0000001")
        self.ui._save_bank_account()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row = db.fetch_one(
            "SELECT id FROM bank_accounts WHERE company_id = 1 AND bank_name = ?",
            ("Axis Bank",))
        self.assertIsNotNone(row)
        item = bank_account_service.get_bank_account(row["id"])
        self.assertEqual(item["account_number"], "999999")
        self.assertEqual(item["account_type"], "Current")
        self.assertEqual(item["opening_balance"], 250.5)
        self.assertEqual(item["ifsc_code"], "UTIB0000001")
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("Axis Bank", names)
        self.assertEqual(self.ui.list.list_title.cget("text"), "Bank Accounts (3)")

    def test_create_validation_errors(self):
        self._go_create()
        self.ui.form.vars["bank_name"].set("")
        with mock.patch("ui.bank_account_management.dialogs.warn") as warn:
            self.ui._save_bank_account()
        self.assertTrue(warn.called)
        self.assertTrue(self.ui.form.is_visible())
        self.assertIn("required", self.ui.form.message_label.cget("text").lower())
        # Non-numeric opening
        self.ui.form.vars["bank_name"].set("UI Bad Opening")
        self.ui.form.vars["opening_balance"].set("abc")
        with mock.patch("ui.bank_account_management.dialogs.warn") as warn:
            self.ui._save_bank_account()
        self.assertTrue(warn.called)
        self.assertIn("numeric", self.ui.form.message_label.cget("text").lower())
        # Nothing persisted.
        remaining = db.fetch_one(
            "SELECT COUNT(*) AS n FROM bank_accounts WHERE company_id = 1")["n"]
        self.assertEqual(remaining, 2)

    # ------------------------------------------------------------------ #
    # Save & New
    # ------------------------------------------------------------------ #
    def test_save_and_new_persists_and_stays_in_create(self):
        self._go_create()
        self.ui.form.vars["bank_name"].set("UI Save And New Bank")
        self.ui._save_and_new()
        self._sync()
        row = db.fetch_one(
            "SELECT id FROM bank_accounts WHERE company_id = 1 AND bank_name = ?",
            ("UI Save And New Bank",))
        self.assertIsNotNone(row)
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["bank_name"].get(), "")
        self.ui.form.vars["bank_name"].set("UI Save And New Bank 2")
        self.ui._save_bank_account()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row2 = db.fetch_one(
            "SELECT id FROM bank_accounts WHERE company_id = 1 AND bank_name = ?",
            ("UI Save And New Bank 2",))
        self.assertIsNotNone(row2)

    def test_save_and_new_not_shown_in_edit_mode(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertEqual(self.ui.form.mode, "edit")
        self.assertEqual(self.ui.form.btn_save_new.winfo_manager(), "")
        self.assertNotEqual(self.ui.form.btn_update.winfo_manager(), "")

    # ------------------------------------------------------------------ #
    # navigation: List -> Edit -> List
    # ------------------------------------------------------------------ #
    def test_edit_opens_same_form_state(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Bank Account")
        self.assertEqual(self.ui.form.subtitle_label.cget("text"),
                         "Edit Bank Account: HDFC Bank")
        self.assertEqual(self.ui.form.mode, "edit")
        self.assertEqual(self.ui.form.vars["bank_name"].get(), "HDFC Bank")
        self.assertEqual(self.ui.form.vars["account_number"].get(), "123456")
        self.assertEqual(self.ui.form.vars["account_type"].get(), "Savings")
        self.assertEqual(self.ui.form.vars["opening_balance"].get(), "1000.00")

    def test_edit_clear_resets_to_create_state(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui._clear_form()
        self.assertEqual(self.ui.form.mode, "create")
        self.assertIsNone(self.ui.form.bank_account_id)
        self.assertEqual(self.ui.form.vars["bank_name"].get(), "")

    def test_edit_cancel_returns_to_list(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["bank_name"].set("Unwanted Change")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        item = bank_account_service.get_bank_account(int(target))
        self.assertEqual(item["bank_name"], "HDFC Bank")

    def test_update_persists_and_returns_to_list(self):
        target = self._row_by_bank("ICICI Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["bank_name"].set("ICICI Bank Renamed")
        self.ui.form.vars["opening_balance"].set("777.75")
        self.ui._update_bank_account()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        updated = bank_account_service.get_bank_account(int(target))
        self.assertEqual(updated["bank_name"], "ICICI Bank Renamed")
        self.assertEqual(updated["opening_balance"], 777.75)

    def test_form_component_reused_between_create_and_edit(self):
        form_state = self.ui.form
        self._go_create()
        self.ui._go_list()
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.assertIs(self.ui.form, form_state)

    # ------------------------------------------------------------------ #
    # navigation: List -> View -> List
    # ------------------------------------------------------------------ #
    def test_view_opens_read_only_state(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self._sync()
        self.assertTrue(self.ui.view.is_visible())
        self.assertEqual(self.ui.view.value_labels["bank_name"].cget("text"),
                         "HDFC Bank")
        self.assertEqual(self.ui.view.value_labels["account_type"].cget("text"),
                         "Savings")

    def test_view_back_returns_to_list(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_view_does_not_modify_database(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self.ui.on_keyboard_back()
        item = bank_account_service.get_bank_account(int(target))
        self.assertEqual(item["bank_name"], "HDFC Bank")
        self.assertEqual(item["opening_balance"], 1000.0)

    # ------------------------------------------------------------------ #
    # Esc routing per state
    # ------------------------------------------------------------------ #
    def test_esc_from_create_returns_to_list(self):
        self._go_create()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    def test_esc_from_edit_returns_to_list(self):
        target = self._row_by_bank("HDFC Bank")
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
    # keyboard shortcuts (state-dependent dispatch)
    # ------------------------------------------------------------------ #
    def test_ctrl_n_opens_create_from_list(self):
        self.ui.on_keyboard_new()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())

    def test_ctrl_s_saves_in_create_state(self):
        self._go_create()
        self.ui.form.vars["bank_name"].set("UI Keyboard Bank")
        self.ui.on_keyboard_save()
        self._sync()
        row = db.fetch_one(
            "SELECT id FROM bank_accounts WHERE company_id = 1 AND bank_name = ?",
            ("UI Keyboard Bank",))
        self.assertIsNotNone(row)

    def test_ctrl_s_updates_in_edit_state(self):
        target = self._row_by_bank("ICICI Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["bank_name"].set("UI Keyboard Edit")
        self.ui.on_keyboard_save()
        self._sync()
        item = bank_account_service.get_bank_account(int(target))
        self.assertEqual(item["bank_name"], "UI Keyboard Edit")

    def test_ctrl_f_focuses_search(self):
        self.ui.on_keyboard_search()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())

    def test_f5_refreshes_list(self):
        _seed_bank(1, "UI F5 Bank")
        self.ui.on_keyboard_refresh()
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI F5 Bank", names)

    def test_del_deletes_selected(self):
        target = _seed_bank(1, "UI Del Me")
        self.ui.refresh_bank_accounts()
        self.ui.list.tree.selection_set(str(target))
        self.ui._on_select()
        with mock.patch("ui.bank_account_management.dialogs.confirm_destructive",
                        return_value=True):
            self.ui.on_keyboard_delete()
        self.assertIsNone(bank_account_service.get_bank_account(target))

    def test_del_blocked_when_referenced(self):
        target = _seed_bank(1, "UI Ref Bank")
        db.execute(
            "INSERT INTO transactions (title, amount, type, account_mode,"
            " bank_account_id, transaction_date, transaction_time)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("UI Ref Tx", 100.0, "Income", "Bank", target, "2026-01-01", "10:00:00"),
        )
        self.ui.refresh_bank_accounts()
        self.ui.list.tree.selection_set(str(target))
        self.ui._on_select()
        with mock.patch("ui.bank_account_management.dialogs.confirm_destructive") as confirm:
            with mock.patch("ui.bank_account_management.dialogs.error") as error:
                self.ui._delete_bank_account()
        confirm.assert_not_called()
        self.assertTrue(error.called)
        self.assertIsNotNone(bank_account_service.get_bank_account(target))

    def test_enter_edits_selected(self):
        target = self._row_by_bank("HDFC Bank")
        self.ui.list.tree.selection_set(target)
        self.ui._on_enter_pressed()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Bank Account")

    def test_refresh_in_form_state_is_inert(self):
        self._go_create()
        self.ui.on_keyboard_refresh()
        self.assertTrue(self.ui.form.is_visible())

    def test_search_filters_list(self):
        self.ui.list.search_var.set("HDFC")
        self.ui._apply_search()
        self._sync()
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.ui.list.tree.item(rows[0], "values")[1], "HDFC Bank")
        self.assertEqual(self.ui.list.list_title.cget("text"), "Bank Accounts (1)")

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
        self.assertEqual(len(self.ui.form.vars), 9)  # fields never duplicated

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
        ui_b = BankAccountManagementUI(self.root, 2)
        try:
            names = [ui_b.list.tree.item(i, "values")[1]
                     for i in ui_b.list.tree.get_children()]
            self.assertEqual(names, [])
        finally:
            ui_b.main_frame.destroy()

    def test_company_id_never_defaulted(self):
        self.assertEqual(self.ui.company_id, 1)
        # Saving through the screen persists with the explicit company id.
        self._go_create()
        self.ui.form.vars["bank_name"].set("UI Isolation Save")
        self.ui._save_bank_account()
        self._sync()
        row = db.fetch_one(
            "SELECT company_id FROM bank_accounts WHERE bank_name = ?",
            ("UI Isolation Save",))
        self.assertEqual(row["company_id"], 1)

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
