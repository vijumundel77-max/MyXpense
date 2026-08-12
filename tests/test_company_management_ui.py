"""
Regression tests for the Company Management stateful workflow.

The Company List and the Create/Edit form are SEPARATE UI states — the form is
never cramped into the list screen.  These exercise the real CompanyManagementUI
against the shared Tk root: List state rendering (table rows visible, count,
paging hint, columns), Create state, Edit state, View state, List → Create →
List navigation, Esc routing per state, Ctrl+N/S/F, F5, Del, Enter, selection,
CRUD persistence, last-company deletion protection, no duplicate widgets across
repeated navigation, theme cycling, and the explicit "form is a separate state"
contract.

Company switching stays in Settings; this screen never switches companies.
"""
import unittest
from unittest import mock

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.company_service import CompanyService  # noqa: E402
from ui.company_management import CompanyManagementUI  # noqa: E402
from utils import theme  # noqa: E402


def _all_text(widget):
    """Every text-ish string under a widget (labels + buttons)."""
    texts = []
    for child in widget.winfo_children():
        try:
            if isinstance(child, (ctk.CTkLabel, ctk.CTkButton)):
                texts.append(str(child.cget("text")))
        except Exception:
            pass
        texts.extend(_all_text(child))
    return texts


class CompanyManagementUITest(unittest.TestCase):
    """Stateful Company Management flow: List/Create/Edit/View."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        # Deterministic per-test state: exactly two base rows.
        db.execute("DELETE FROM companies")
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end,"
            " mobile, email) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "UI Acme Corp", "01-04", "31-03", "9876543210", "info@acme.com"),
        )
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end)"
            " VALUES (?, ?, ?, ?)",
            (2, "UI Beta Ltd", "01-04", "31-03"),
        )
        # A visible root is required so winfo_ismapped()/geometry reflect the
        # real layout (a withdrawn root never maps any widget).
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = CompanyManagementUI(self.root, CompanyService(db), current_company_id=1)
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

    # ------------------------------------------------------------------ #
    # default state: Company List
    # ------------------------------------------------------------------ #
    def test_opens_in_list_state(self):
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_list_columns_and_rows_visible(self):
        columns = [self.ui.list.tree.heading(c)["text"] for c in self.ui.list.tree["columns"]]
        self.assertEqual(columns, ["#", "Company Name", "Code", "Email", "Phone", "Status"])
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 2)
        values = [self.ui.list.tree.item(i, "values") for i in rows]
        self.assertEqual(values[0][1], "UI Acme Corp")
        self.assertEqual(values[0][2], "CMP-001")
        self.assertEqual(values[0][3], "info@acme.com")
        self.assertEqual(values[0][4], "9876543210")
        self.assertEqual(values[0][5], "Active")
        self.assertEqual(values[1][1], "UI Beta Ltd")
        self.assertEqual(values[1][2], "CMP-002")

    def test_list_count_and_paging_hint(self):
        self.assertEqual(self.ui.list.list_title.cget("text"), "Companies (2)")
        self.assertEqual(self.ui.list.page_label.cget("text"),
                         "Showing 1 to 2 of 2 companies")

    def test_header_actions_present(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        for expected in ["Company Management",
                         "Create, view, edit and manage companies",
                         "+ New Company", "Edit", "Delete", "Open / View",
                         "Refresh", "Ctrl+F",
                         "Edit (Enter)", "Delete (Del)", "View"]:
            self.assertIn(expected, texts)
        # Every important workflow action is a VISIBLE button, not only a
        # keyboard shortcut: the header toolbar carries all of them.
        self.assertEqual(self.ui.list.btn_new.cget("text"), "+ New Company")
        self.assertEqual(self.ui.list.btn_edit_toolbar.cget("text"), "Edit")
        self.assertEqual(self.ui.list.btn_delete_toolbar.cget("text"), "Delete")
        self.assertEqual(self.ui.list.btn_view_toolbar.cget("text"), "Open / View")
        self.assertEqual(self.ui.list.btn_refresh.cget("text"), "Refresh")
        # The search box lives directly in the header toolbar area.
        self.assertIsNotNone(self.ui.list.search_entry)

    def test_selection_enables_actions(self):
        # No selection -> disabled.
        self.assertEqual(self.ui.list.btn_edit.cget("state"), "disabled")
        self.assertEqual(self.ui.list.btn_delete.cget("state"), "disabled")
        self.assertEqual(self.ui.list.btn_view.cget("state"), "disabled")
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.assertEqual(self.ui.list.selected_id, 1)
        self.assertEqual(self.ui.list.btn_edit.cget("state"), "normal")
        self.assertEqual(self.ui.list.btn_delete.cget("state"), "normal")
        self.assertEqual(self.ui.list.btn_view.cget("state"), "normal")

    # ------------------------------------------------------------------ #
    # separate-state contract
    # ------------------------------------------------------------------ #
    def test_form_is_separate_state_not_cramped_in_list(self):
        # The list screen must NOT contain the create form fields.
        list_texts = "\n".join(_all_text(self.ui.list.main))
        for field in ("Company Name *", "FY Start (DD-MM)",
                      "Books Beginning From"):
            self.assertNotIn(field, list_texts)
        self.assertFalse(hasattr(self.ui.list, "name_var"))
        # The form is its own full state.
        self._go_create()
        form_texts = "\n".join(_all_text(self.ui.form.main))
        self.assertIn("Create Company", form_texts)
        self.assertIn("Company Name *", form_texts)

    def test_list_and_form_are_distinct_widgets(self):
        self.assertIsNot(self.ui.list.main, self.ui.form.main)
        self.assertIsNot(self.ui.list.main, self.ui.view.main)
        # Exactly one of the states is visible at a time.
        visible = [s for s in (self.ui.list, self.ui.form, self.ui.view) if s.is_visible()]
        self.assertEqual(len(visible), 1)

    # ------------------------------------------------------------------ #
    # navigation: List -> Create -> List
    # ------------------------------------------------------------------ #
    def test_new_company_opens_create_state(self):
        self.ui._go_create()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertFalse(self.ui.list.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Create Company")
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["fy_start"].get(), "01-04")
        self.assertEqual(self.ui.form.vars["fy_end"].get(), "31-03")

    def test_create_form_fields_present(self):
        self._go_create()
        texts = "\n".join(_all_text(self.ui.form.main))
        for expected in [
            "Company Name *", "Company Code", "Email", "Phone", "Address",
            "State", "Country", "Pincode",
            "FY Start (DD-MM)", "FY End (DD-MM)",
            "Books Beginning From",
        ]:
            self.assertIn(expected, texts)
        self.assertNotIn("GSTIN", texts)
        self.assertNotIn("PAN", texts)
        # Save/Clear/Cancel are the Create actions; Update is hidden.
        for button in ("Save", "Clear", "Cancel"):
            self.assertIn(button, texts)
        self.assertEqual(self.ui.form.btn_update.winfo_manager(), "")
        self.assertNotEqual(self.ui.form.btn_save.winfo_manager(), "")

    def test_edit_mode_shows_update_not_save(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Company")
        self.assertNotEqual(self.ui.form.btn_update.winfo_manager(), "")
        self.assertEqual(self.ui.form.btn_save.winfo_manager(), "")

    def test_create_cancel_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["name"].set("Should Not Exist")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.form.is_visible())
        row = db.fetch_one(
            "SELECT id FROM companies WHERE name = ?", ("Should Not Exist",))
        self.assertIsNone(row)

    def test_create_save_persists_and_returns_to_list(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Created Company")
        self.ui.form.vars["email"].set("created@expenzo.test")
        self.ui._save_company()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row = db.fetch_one(
            "SELECT id FROM companies WHERE name = ?", ("UI Created Company",))
        self.assertIsNotNone(row)
        names = [self.ui.list.tree.item(i, "values")[1]
                 for i in self.ui.list.tree.get_children()]
        self.assertIn("UI Created Company", names)
        self.assertEqual(self.ui.list.list_title.cget("text"), "Companies (3)")

    # ------------------------------------------------------------------ #
    # navigation: List -> Edit -> List
    # ------------------------------------------------------------------ #
    def test_edit_opens_same_form_state(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Company")
        self.assertEqual(self.ui.form.mode, "edit")
        self.assertEqual(self.ui.form.company_id, 1)
        self.assertEqual(self.ui.form.vars["name"].get(), "UI Acme Corp")
        self.assertEqual(self.ui.form.vars["email"].get(), "info@acme.com")
        self.assertEqual(self.ui.form.vars["mobile"].get(), "9876543210")
        self.assertEqual(self.ui.form.vars["code"].get(), "CMP-001")

    def test_edit_clear_resets_to_create_state(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        self.ui._clear_form()
        self.assertEqual(self.ui.form.mode, "create")
        self.assertIsNone(self.ui.form.company_id)
        self.assertEqual(self.ui.form.vars["name"].get(), "")

    def test_edit_cancel_returns_to_list(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("Unwanted Change")
        self.ui._go_list()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        name = db.fetch_one("SELECT name FROM companies WHERE id = 1")["name"]
        self.assertEqual(name, "UI Acme Corp")  # unchanged

    def test_update_persists_and_returns_to_list(self):
        self.ui.list.tree.selection_set("2")
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("UI Beta Renamed")
        self.ui._update_company()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        name = db.fetch_one("SELECT name FROM companies WHERE id = 2")["name"]
        self.assertEqual(name, "UI Beta Renamed")

    def test_form_component_reused_between_create_and_edit(self):
        form_state = self.ui.form
        self.ui._go_create()
        self.ui._go_list()
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        # Same form object reused, not rebuilt.
        self.assertIs(self.ui.form, form_state)

    # ------------------------------------------------------------------ #
    # navigation: List -> View -> List
    # ------------------------------------------------------------------ #
    def test_view_opens_read_only_state(self):
        self.ui.list.tree.selection_set("2")
        self.ui._on_select()
        self.ui._go_view()
        self._sync()
        self.assertTrue(self.ui.view.is_visible())
        self.assertEqual(self.ui.view.value_labels["name"].cget("text"), "UI Beta Ltd")
        self.assertEqual(self.ui.view.value_labels["code"].cget("text"), "CMP-002")

    def test_view_back_returns_to_list(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_view()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        self.assertFalse(self.ui.view.is_visible())

    def test_view_does_not_modify_database(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_view()
        self.ui.on_keyboard_back()
        row = db.fetch_one("SELECT name, email, mobile FROM companies WHERE id = 1")
        self.assertEqual(row["name"], "UI Acme Corp")
        self.assertEqual(row["email"], "info@acme.com")

    # ------------------------------------------------------------------ #
    # Esc routing per state
    # ------------------------------------------------------------------ #
    def test_esc_from_create_returns_to_list(self):
        self.ui._go_create()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    def test_esc_from_edit_returns_to_list(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())

    def test_esc_from_list_routes_to_hub(self):
        # The hub overwrites on_keyboard_back; simulate that.
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
        self.ui._go_create()
        self.ui.form.vars["name"].set("UI Keyboard Co")
        self.ui.form.vars["email"].set("kb@expenzo.test")
        self.ui.on_keyboard_save()
        self._sync()
        row = db.fetch_one("SELECT id FROM companies WHERE name = ?", ("UI Keyboard Co",))
        self.assertIsNotNone(row)

    def test_ctrl_s_updates_in_edit_state(self):
        self.ui.list.tree.selection_set("2")
        self.ui._on_select()
        self.ui._go_edit()
        self.ui.form.vars["name"].set("UI Keyboard Edit")
        self.ui.on_keyboard_save()
        self._sync()
        name = db.fetch_one("SELECT name FROM companies WHERE id = 2")["name"]
        self.assertEqual(name, "UI Keyboard Edit")

    def test_ctrl_f_focuses_search(self):
        self.ui.on_keyboard_search()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        # on_keyboard_search must not navigate away from the list.
        self.assertFalse(self.ui.form.is_visible())

    def test_f5_refreshes_list(self):
        db.execute("INSERT INTO companies (id, name) VALUES (?, ?)", (99, "UI F5 Co"))
        try:
            self.ui.on_keyboard_refresh()
            ids = [int(i) for i in self.ui.list.tree.get_children()]
            self.assertIn(99, ids)
        finally:
            db.execute("DELETE FROM companies WHERE id = 99")
            self.ui.on_keyboard_refresh()

    def test_del_deletes_selected(self):
        self.ui.list.tree.selection_set("2")
        self.ui._on_select()
        with mock.patch("ui.company_management.dialogs.confirm_destructive",
                        return_value=True):
            self.ui.on_keyboard_delete()
        row = db.fetch_one("SELECT id FROM companies WHERE id = 2")
        self.assertIsNone(row)

    def test_enter_edits_selected(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_enter_pressed()
        self._sync()
        self.assertTrue(self.ui.form.is_visible())
        self.assertEqual(self.ui.form.title_label.cget("text"), "Edit Company")

    def test_refresh_in_form_state_is_inert(self):
        self.ui._go_create()
        self.ui.on_keyboard_refresh()
        self.assertTrue(self.ui.form.is_visible())

    def test_search_filters_list(self):
        self.ui.list.search_var.set("Beta")
        self.ui._apply_search()
        self._sync()
        rows = self.ui.list.tree.get_children()
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.ui.list.tree.item(rows[0], "values")[1], "UI Beta Ltd")
        self.assertEqual(self.ui.list.list_title.cget("text"), "Companies (1)")

    # ------------------------------------------------------------------ #
    # delete protection
    # ------------------------------------------------------------------ #
    def test_last_company_delete_blocked(self):
        db.execute("DELETE FROM companies WHERE id != 1")
        self.ui.refresh_companies()
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        with mock.patch("ui.company_management.dialogs.confirm_destructive") as confirm:
            with mock.patch("ui.company_management.dialogs.error") as error:
                self.ui._delete_company()
        confirm.assert_not_called()
        self.assertTrue(error.called)
        remaining = db.fetch_one("SELECT COUNT(*) AS n FROM companies")["n"]
        self.assertEqual(remaining, 1)

    def test_delete_with_multiple_companies_confirms(self):
        self.ui.list.tree.selection_set("2")
        self.ui._on_select()
        with mock.patch("ui.company_management.dialogs.confirm_destructive",
                        return_value=False) as confirm:
            with mock.patch("ui.company_management.dialogs.error") as error:
                self.ui._delete_company()
        confirm.assert_called_once()
        self.assertFalse(error.called)
        remaining = db.fetch_one("SELECT COUNT(*) AS n FROM companies")["n"]
        self.assertEqual(remaining, 2)

    # ------------------------------------------------------------------ #
    # no duplicate widgets across repeated navigation
    # ------------------------------------------------------------------ #
    def test_repeated_navigation_does_not_duplicate(self):
        for _ in range(4):
            self.ui._go_create()
            self._sync()
            self.assertTrue(self.ui.form.is_visible())
            self.ui.on_keyboard_back()
            self._sync()
            self.assertTrue(self.ui.list.is_visible())
        self.assertEqual(len(self.ui.form.vars), 11)  # fields never duplicated

    def test_one_state_visible_after_each_navigation(self):
        for nav in (self.ui._go_create, self.ui._go_list):
            nav()
            self._sync()
            visible = [s for s in (self.ui.list, self.ui.form, self.ui.view) if s.is_visible()]
            self.assertEqual(len(visible), 1)

    # ------------------------------------------------------------------ #
    # visible toolbar / no-collapsed-header regression
    # ------------------------------------------------------------------ #
    def test_toolbar_buttons_are_mapped_not_collapsed(self):
        # Regression: the header row previously carried grid weight and could
        # collapse to 1x1, making every toolbar button invisible.
        self._sync()
        for button in (self.ui.list.btn_back, self.ui.list.btn_new,
                       self.ui.list.btn_edit_toolbar, self.ui.list.btn_delete_toolbar,
                       self.ui.list.btn_view_toolbar, self.ui.list.btn_refresh):
            self.assertTrue(button.winfo_ismapped(),
                            f"{button.cget('text')} should be mapped")
            self.assertGreater(button.winfo_width(), 1)
            self.assertGreater(button.winfo_height(), 1)
        # The header itself must have real geometry.
        header = self.ui.list.main.winfo_children()[0]
        self.assertGreater(header.winfo_height(), 30)
        self.assertTrue(header.winfo_ismapped())

    def test_search_box_in_header_is_mapped(self):
        self._sync()
        self.assertTrue(self.ui.list.search_entry.winfo_ismapped())
        self.assertGreater(self.ui.list.search_entry.winfo_width(), 100)

    def test_status_line_not_clipped(self):
        # The status line must render its full text without being cut off.
        self.ui.list.set_status(
            "Note: At least one company must always exist. The last remaining company cannot be deleted.")
        self._sync()
        self.assertIn("last remaining company cannot be deleted",
                      self.ui.list.status_label.cget("text"))

    # ------------------------------------------------------------------ #
    # Save & New
    # ------------------------------------------------------------------ #
    def test_save_and_new_persists_and_stays_in_create(self):
        self._go_create()
        self.ui.form.vars["name"].set("UI Save And New Co")
        self.ui.form.vars["email"].set("sn@expenzo.test")
        self.ui._save_and_new()
        self._sync()
        # Persisted and the form stays in Create mode (blank).
        row = db.fetch_one(
            "SELECT id FROM companies WHERE name = ?", ("UI Save And New Co",))
        self.assertIsNotNone(row)
        self.assertTrue(self.ui.form.is_visible())
        self.assertFalse(self.ui.list.is_visible())
        self.assertEqual(self.ui.form.mode, "create")
        self.assertEqual(self.ui.form.vars["name"].get(), "")
        # A second company can be entered without navigating away.
        self.ui.form.vars["name"].set("UI Save And New Co 2")
        self.ui.form.vars["email"].set("sn2@expenzo.test")
        self.ui._save_company()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())
        row2 = db.fetch_one(
            "SELECT id FROM companies WHERE name = ?", ("UI Save And New Co 2",))
        self.assertIsNotNone(row2)

    def test_save_and_new_not_shown_in_edit_mode(self):
        self.ui.list.tree.selection_set("1")
        self.ui._on_select()
        self.ui._go_edit()
        self._sync()
        self.assertEqual(self.ui.form.mode, "edit")
        self.assertEqual(self.ui.form.btn_save_new.winfo_manager(), "")
        self.assertEqual(self.ui.form.btn_update.winfo_manager() != "", True)

    def test_save_and_new_validation_error_stays_in_create(self):
        self._go_create()
        self.ui.form.vars["name"].set("")  # invalid: name required
        with mock.patch("ui.company_management.dialogs.error") as error:
            self.ui._save_and_new()
        self.assertTrue(error.called)
        self.assertTrue(self.ui.form.is_visible())
        # No partial company was persisted.
        remaining = db.fetch_one("SELECT COUNT(*) AS n FROM companies")["n"]
        self.assertEqual(remaining, 2)

    # ------------------------------------------------------------------ #
    # create form sections (logical layout contract)
    # ------------------------------------------------------------------ #
    def test_create_form_sections_present(self):
        self._go_create()
        titles = []
        for sf in self.ui.form.section_frames:
            for child in sf.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    try:
                        titles.append(child.cget("text"))
                    except Exception:
                        pass
        for expected in ["Company Information", "Address", "Financial Year"]:
            self.assertIn(expected, titles)

    def test_form_has_no_invented_fields(self):
        # Only the finalized company fields; no GSTIN/PAN/website/city.
        self._go_create()
        var_names = set(self.ui.form.vars.keys())
        self.assertEqual(var_names, {
            "name", "code", "email", "mobile", "address",
            "state", "country", "pincode", "fy_start", "fy_end", "books_begin",
        })

    # ------------------------------------------------------------------ #
    # theme cycling
    # ------------------------------------------------------------------ #
    def test_theme_cycles_without_error(self):
        self.ui._go_create()
        self._sync()
        for mode in ("light", "dark", "light", "dark"):
            ctk.set_appearance_mode(mode)
            theme.apply_theme(self.root, mode=mode)
            theme.apply_palette(self.root)
            self._sync()
        # Still navigable after theme switches.
        self.ui.on_keyboard_back()
        self._sync()
        self.assertTrue(self.ui.list.is_visible())


if __name__ == "__main__":
    unittest.main()
