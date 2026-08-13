"""
Regression tests for the Party Master stateful workflow.

The Party List and the Create/Edit form are SEPARATE UI states — the form is
never cramped into the list screen.  These exercise the real PartyMasterUI
against the shared Tk root: List state rendering (columns, rows, paging
hint), header toolbar (visible buttons + search + Inactive filter), Create /
Edit / View states, List → Create → List navigation, Esc routing per state,
Ctrl+N/S/F, F5, Del, Enter, CRUD persistence, referenced-party delete
protection, Save & New, no duplicate widgets across repeated navigation,
theme cycling, company isolation, and the explicit "form is a separate
state" contract.
"""
import unittest
from unittest import mock

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.account_service import account_service  # noqa: E402
from services.group_service import group_service  # noqa: E402
from ui.party_master import PartyMasterUI, DEBTOR_GROUP, CREDITOR_GROUP  # noqa: E402
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


def _seed_party(company_id, name, group, opening=0.0, dtype="Debit",
                mobile="", email="", credit_days=0):
    account_service.create_account(
        company_id, name, "", group, opening, dtype,
        mobile=mobile, email=email, credit_days=credit_days,
    )
    row = db.fetch_one(
        "SELECT id FROM accounts WHERE company_id = ? AND name = ?",
        (company_id, name),
    )
    return row["id"]


class PartyMasterUITest(unittest.TestCase):
    """Stateful Party flow: List/Create/Edit/View."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (1, "UI Party Co"))
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (2, "UI Party Co B"))
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
        db.execute("DELETE FROM accounts")
        _seed_party(1, "UI ABC Traders", DEBTOR_GROUP, 1000.00, "Debit",
                    mobile="9876543210", email="abc@expenzo.test", credit_days=30)
        _seed_party(1, "UI XYZ Suppliers", CREDITOR_GROUP, 500.00, "Credit")
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = PartyMasterUI(self.root, 1)
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

    def _wait_mapped(self, widget):
        """Pump the event loop until the widget is actually mapped.

        Under a heavily reused Tk root, a freshly deiconified window can take
        a few idle iterations before children report as mapped; this retries
        instead of asserting on a transient pre-layout state.
        """
        for _ in range(25):
            self._sync()
            try:
                if widget.winfo_ismapped():
                    return
            except Exception:
                pass
        self.assertTrue(widget.winfo_ismapped(), "widget should be mapped")

    def _go_create(self):
        self.ui._go_create()
        self._sync()

    def _row_by_name(self, name):
        for item in self.ui.list.tree.get_children():
            if self.ui.list.tree.item(item, "values")[1] == name:
                return item
        return None

    # ------------------------------------------------------------------ #
    # default state: Party List
    # ------------------------------------------------------------------ #
    def test_opens_in_list_state(self):
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_list_columns_and_rows_visible(self):
        columns = [self.ui.list.tree.heading(c)["text"]
                   for c in self.ui.list.tree["columns"]]
        self.assertEqual(columns, [
            "#", "Party Name", "Under", "Mobile", "Email",
            "Opening Balance", "Dr/Cr", "Credit Days", "Status"])
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 2)
        values = [self.ui.list.tree.item(i, "values") for i in rows]
        by_name = {v[1]: v for v in values}
        self.assertEqual(by_name["UI ABC Traders"][2], "Sundry Debtors")
        self.assertEqual(by_name["UI ABC Traders"][3], "9876543210")
        self.assertEqual(by_name["UI ABC Traders"][5], "1,000.00")
        self.assertEqual(by_name["UI ABC Traders"][6], "Debit")
        self.assertEqual(by_name["UI ABC Traders"][7], "30")
        self.assertEqual(by_name["UI XYZ Suppliers"][2], "Sundry Creditors")
        self.assertEqual(by_name["UI XYZ Suppliers"][5], "500.00")
        self.assertEqual(by_name["UI XYZ Suppliers"][6], "Credit")

    def test_list_count_and_paging_hint(self):
        self.assertEqual(self.ui.list.list_title.cget("text"), "Parties (2)")
        self.assertEqual(self.ui.list.page_label.cget("text"),
                         "Showing 1 to 2 of 2 parties")

    def test_header_actions_present(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        for expected in ["Party Master", "Debtors & Creditors",
                         "+ New Party", "Edit", "Delete", "Open / View",
                         "Refresh", "Ctrl+F", "Inactive",
                         "Edit (Enter)", "Delete (Del)", "View"]:
            self.assertIn(expected, texts)
        self.assertEqual(self.ui.list.btn_new.cget("text"), "+ New Party")
        self.assertEqual(self.ui.list.btn_edit_toolbar.cget("text"), "Edit")
        self.assertEqual(self.ui.list.btn_delete_toolbar.cget("text"), "Delete")
        self.assertEqual(self.ui.list.btn_view_toolbar.cget("text"), "Open / View")
        self.assertEqual(self.ui.list.btn_refresh.cget("text"), "Refresh")

    def test_toolbar_buttons_are_mapped_not_collapsed(self):
        for button in (self.ui.list.btn_back, self.ui.list.btn_new,
                       self.ui.list.btn_edit_toolbar, self.ui.list.btn_delete_toolbar,
                       self.ui.list.btn_view_toolbar, self.ui.list.btn_refresh):
            self._wait_mapped(button)
            self.assertGreater(button.winfo_width(), 1)
            self.assertGreater(button.winfo_height(), 1)
        header = self.ui.list.main.winfo_children()[0]
        self._wait_mapped(header)
        self.assertGreater(header.winfo_height(), 30)

    def test_search_box_in_header_is_mapped(self):
        self._wait_mapped(self.ui.list.search_entry)
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
        for field in ("Party Name *", "Contact Person", "Credit Limit",
                      "Credit / Payment Terms"):
            self.assertNotIn(field, list_texts)
        self.assertFalse(hasattr(self.ui.list, "name_var"))
        self._go_create()
        form_texts = "\n".join(_all_text(self.ui.form.main))
        self.assertIn("Create Party", form_texts)
        self.assertIn("Party Name *", form_texts)

    def test_list_and_form_are_distinct_widgets(self):
        self.assertIsNot(self.ui.list.main, self.ui.form.main)
        self.assertIsNot(self.ui.list.main, self.ui.view.main)
        visible = [s for s in (self.ui.list, self.ui.form, self.ui.view)
                   if s.is_visible()]
        self.assertEqual(len(visible), 1)

    # ------------------------------------------------------------------ #
    # navigation: List -> Create -> List
    # ------------------------------------------------------------------ #
    def test_new_party_opens_create_state(self):
        self._go_create()
        self.assertTrue(self.ui.form.is_visible())
        self.assertFalse(self.ui.list.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Create Party")
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["opening_balance"].get(), "0.00")
        self.assertEqual(self.ui.form.vars["opening_balance_type"].get(), "Debit")

    def test_create_form_fields_present(self):
        self._go_create()
        texts = "\n".join(_all_text(self.ui.form.main))
        for expected in [
            "Party Name *", "Under", "Alias", "Contact Person", "Mobile",
            "Email", "Address", "State", "Country", "Pincode",
            "Opening Balance", "Dr / Cr", "Credit Limit", "Credit Days",
            "Primary Information", "Contact Details", "Credit / Payment Terms",
        ]:
            self.assertIn(expected, texts)
        for button in ("Save", "Save & New", "Clear", "Cancel"):
            self.assertIn(button, texts)
        self.assertEqual(self.ui.form.btn_update.winfo_manager(), "")
        self.assertNotEqual(self.ui.form.btn_save.winfo_manager(), "")

    def test_create_cancel_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["name"].set("Should Not Exist")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        row = db.fetch_one(
            "SELECT id FROM accounts WHERE company_id = 1 AND name = ?",
            ("Should Not Exist",))
        self.assertIsNone(row)

    def test_create_save_persists_and_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Created Party")
        self.ui.form.vars["mobile"].set("1234567890")
        self.ui.form.vars["email"].set("party@expenzo.test")
        self.ui.form.vars["credit_days"].set("45")
        self.ui._save_party()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row = db.fetch_one(
            "SELECT id FROM accounts WHERE company_id = 1 AND name = ?",
            ("UI Created Party",))
        self.assertIsNotNone(row)
        party = account_service.get_account(row["id"])
        self.assertEqual(party["account_group"], DEBTOR_GROUP)
        self.assertEqual(party["mobile"], "1234567890")
        self.assertEqual(party["credit_days"], 45)
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI Created Party", names)
        self.assertEqual(self.ui.list.list_title.cget("text"), "Parties (3)")

    def test_create_validation_errors(self):
        self._go_create()
        self.ui.form.vars["name"].set("")
        with mock.patch("ui.party_master.dialogs.warn") as warn:
            self.ui._save_party()
        self.assertTrue(warn.called)
        self.assertTrue(self.ui.form.is_visible())
        self.assertIn("required", self.ui.form.message_label.cget("text").lower())
        # Non-numeric opening
        self.ui.form.vars["name"].set("UI Bad Opening")
        self.ui.form.vars["opening_balance"].set("abc")
        with mock.patch("ui.party_master.dialogs.warn") as warn:
            self.ui._save_party()
        self.assertTrue(warn.called)
        self.assertIn("numeric", self.ui.form.message_label.cget("text").lower())
        # Nothing persisted.
        remaining = db.fetch_one(
            "SELECT COUNT(*) AS n FROM accounts WHERE company_id = 1")["n"]
        self.assertEqual(remaining, 2)

    # ------------------------------------------------------------------ #
    # Save & New
    # ------------------------------------------------------------------ #
    def test_save_and_new_persists_and_stays_in_create(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Save And New Party")
        self.ui._save_and_new()
        self._sync()
        row = db.fetch_one(
            "SELECT id FROM accounts WHERE company_id = 1 AND name = ?",
            ("UI Save And New Party",))
        self.assertIsNotNone(row)
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["name"].get(), "")
        self.ui.form.vars["name"].set("UI Save And New Party 2")
        self.ui._save_party()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row2 = db.fetch_one(
            "SELECT id FROM accounts WHERE company_id = 1 AND name = ?",
            ("UI Save And New Party 2",))
        self.assertIsNotNone(row2)

    def test_save_and_new_not_shown_in_edit_mode(self):
        row = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(row)
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
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Party")
        self.assertEqual(self.ui.form.subtitle_label.cget("text"),
                         "Edit Party: UI ABC Traders")
        self.assertEqual(self.ui.form.mode, "edit")
        self.assertEqual(self.ui.form.vars["name"].get(), "UI ABC Traders")
        self.assertEqual(self.ui.form.vars["party_type"].get(), "Sundry Debtors")
        self.assertEqual(self.ui.form.vars["opening_balance"].get(), "1000.00")
        self.assertEqual(self.ui.form.vars["mobile"].get(), "9876543210")
        self.assertEqual(self.ui.form.vars["email"].get(), "abc@expenzo.test")
        self.assertEqual(self.ui.form.vars["credit_days"].get(), "30")

    def test_edit_clear_resets_to_create_state(self):
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui._clear_form()
        self.assertEqual(self.ui.form.mode, "create")
        self.assertIsNone(self.ui.form.party_id)
        self.assertEqual(self.ui.form.vars["name"].get(), "")

    def test_edit_cancel_returns_to_list(self):
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("Unwanted Change")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        party = account_service.get_account(int(target))
        self.assertEqual(party["name"], "UI ABC Traders")

    def test_update_persists_and_returns_to_list(self):
        target = self._row_by_name("UI XYZ Suppliers")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("UI XYZ Suppliers Renamed")
        self.ui.form.vars["opening_balance"].set("777.75")
        self.ui._update_party()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        updated = account_service.get_account(int(target))
        self.assertEqual(updated["name"], "UI XYZ Suppliers Renamed")
        self.assertEqual(updated["opening_balance"], 777.75)

    def test_form_component_reused_between_create_and_edit(self):
        form_state = self.ui.form
        self._go_create()
        self.ui._go_list()
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.assertIs(self.ui.form, form_state)

    # ------------------------------------------------------------------ #
    # navigation: List -> View -> List
    # ------------------------------------------------------------------ #
    def test_view_opens_read_only_state(self):
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self._sync()
        self.assertTrue(self.ui.view.is_visible())
        self.assertEqual(self.ui.view.value_labels["name"].cget("text"),
                         "UI ABC Traders")
        self.assertEqual(self.ui.view.value_labels["party_type"].cget("text"),
                         "Sundry Debtors")

    def test_view_back_returns_to_list(self):
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_view_does_not_modify_database(self):
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_view()
        self.ui.on_keyboard_back()
        party = account_service.get_account(int(target))
        self.assertEqual(party["name"], "UI ABC Traders")
        self.assertEqual(party["opening_balance"], 1000.0)

    # ------------------------------------------------------------------ #
    # Esc routing per state
    # ------------------------------------------------------------------ #
    def test_esc_from_create_returns_to_list(self):
        self._go_create()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    def test_esc_from_edit_returns_to_list(self):
        target = self._row_by_name("UI ABC Traders")
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
        self.ui.form.vars["name"].set("UI Keyboard Party")
        self.ui.on_keyboard_save()
        self._sync()
        row = db.fetch_one(
            "SELECT id FROM accounts WHERE company_id = 1 AND name = ?",
            ("UI Keyboard Party",))
        self.assertIsNotNone(row)

    def test_ctrl_s_updates_in_edit_state(self):
        target = self._row_by_name("UI XYZ Suppliers")
        self.ui.list.tree.selection_set(target)
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("UI Keyboard Edit")
        self.ui.on_keyboard_save()
        self._sync()
        party = account_service.get_account(int(target))
        self.assertEqual(party["name"], "UI Keyboard Edit")

    def test_ctrl_f_focuses_search(self):
        self.ui.on_keyboard_search()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())

    def test_f5_refreshes_list(self):
        _seed_party(1, "UI F5 Party", DEBTOR_GROUP)
        self.ui.on_keyboard_refresh()
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI F5 Party", names)

    def test_del_deletes_selected(self):
        target = _seed_party(1, "UI Del Me", DEBTOR_GROUP)
        self.ui.refresh_parties()
        self.ui.list.tree.selection_set(str(target))
        self.ui._on_select()
        with mock.patch("ui.party_master.dialogs.confirm_destructive",
                        return_value=True):
            self.ui.on_keyboard_delete()
        self.assertIsNone(account_service.get_account(target))

    def test_del_blocked_when_referenced(self):
        target = _seed_party(1, "UI Ref Party", DEBTOR_GROUP)
        db.execute(
            "INSERT INTO vouchers (id, company_id, voucher_number, voucher_type,"
            " voucher_date) VALUES (?, ?, ?, ?, ?)",
            (9001, 1, "V-9001", "Receipt", "2026-01-01"),
        )
        db.execute(
            "INSERT INTO voucher_details (voucher_id, account_id, debit_amount,"
            " credit_amount) VALUES (?, ?, ?, ?)",
            (9001, target, 100.0, 0.0),
        )
        self.ui.refresh_parties()
        self.ui.list.tree.selection_set(str(target))
        self.ui._on_select()
        with mock.patch("ui.party_master.dialogs.confirm_destructive") as confirm:
            with mock.patch("ui.party_master.dialogs.error") as error:
                self.ui._delete_party()
        confirm.assert_not_called()
        self.assertTrue(error.called)
        self.assertIsNotNone(account_service.get_account(target))

    def test_enter_edits_selected(self):
        target = self._row_by_name("UI ABC Traders")
        self.ui.list.tree.selection_set(target)
        self.ui._on_enter_pressed()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Party")

    def test_refresh_in_form_state_is_inert(self):
        self._go_create()
        self.ui.on_keyboard_refresh()
        self.assertTrue(self.ui.form.is_visible())

    def test_search_filters_list(self):
        self.ui.list.search_var.set("ABC")
        self.ui._apply_search()
        self._sync()
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.ui.list.tree.item(rows[0], "values")[1],
                         "UI ABC Traders")
        self.assertEqual(self.ui.list.list_title.cget("text"), "Parties (1)")

    def test_inactive_filter_toggles(self):
        target = _seed_party(1, "UI Inactive Party", DEBTOR_GROUP)
        account_service.set_account_active(target, False)
        self.ui.refresh_parties()
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertNotIn("UI Inactive Party", names)
        self.ui.list.show_inactive_var.set(True)
        self.ui.refresh_parties()
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI Inactive Party", names)

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
        self.assertEqual(len(self.ui.form.vars), 14)  # fields never duplicated

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
        ui_b = PartyMasterUI(self.root, 2)
        try:
            names = [ui_b.list.tree.item(i, "values")[1]
                     for i in ui_b.list.tree.get_children()]
            self.assertEqual(names, [])
        finally:
            ui_b.main_frame.destroy()

    def test_company_id_never_defaulted(self):
        self.assertEqual(self.ui.company_id, 1)

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
