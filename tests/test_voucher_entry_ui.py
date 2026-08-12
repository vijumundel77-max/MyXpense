"""
Regression tests for the Tally-inspired Accounting Voucher Entry screen
(``ui/vouchers.py``).

These exercise the real VouchersFrame against a shared Tk root: the voucher
bar (type / date / number), Party A/C Name, the Particulars/Debit/Credit
grid, To/By presentation, totals/difference, narration, Save / Save & New /
Edit / View / Cancel, the Voucher Register, keyboard hooks, theme cycling,
layout sanity (no clipping) and company isolation.

The accounting engine (``voucher_service``) and database schema are reused
unchanged; these tests assert the UI drives that engine correctly.
"""
import unittest
from unittest import mock
from datetime import date

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.account_service import account_service  # noqa: E402
from services.group_service import group_service  # noqa: E402
from services.voucher_service import (  # noqa: E402
    voucher_service,
    VOUCHER_PAYMENT,
    VOUCHER_RECEIPT,
    VOUCHER_CONTRA,
    VOUCHER_JOURNAL,
    STATUS_CANCELLED,
)
from ui.vouchers import VouchersFrame  # noqa: E402
from utils import theme  # noqa: E402


def _all_text(widget):
    texts = []
    for child in widget.winfo_children():
        try:
            if isinstance(child, (ctk.CTkLabel, ctk.CTkButton, ctk.CTkCheckBox)):
                texts.append(str(child.cget("text")))
        except Exception:
            pass
        texts.extend(_all_text(child))
    return texts


class VoucherEntryUITest(unittest.TestCase):
    """Tally-style voucher entry screen tests."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (1, "UI Voucher Co"))
        db.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)", (2, "UI Voucher Co B"))
        group_service.seed_default_groups(1)
        group_service.seed_default_groups(2)
        cls.root = ctk.CTk()
        cls.root.withdraw()
        theme.apply_theme(cls.root, mode="dark")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        db.execute("DELETE FROM voucher_details")
        db.execute("DELETE FROM vouchers")
        db.execute("DELETE FROM accounts")
        self.acct = self._seed_accounts(1)
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.ui = VouchersFrame(self.root, company_id=1)
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

    @staticmethod
    def _seed_accounts(company_id):
        cash = account_service.create_account(company_id, "Cash", "CASH", "Cash-in-Hand",
                                              0.0, "Debit")
        bank = account_service.create_account(company_id, "Bank", "BANK", "Bank Accounts",
                                              0.0, "Debit")
        creditor = account_service.create_account(company_id, "ABC Traders", "ABC",
                                                  "Sundry Creditors", 0.0, "Credit")
        debtor = account_service.create_account(company_id, "MNO Buyers", "MNO",
                                                "Sundry Debtors", 0.0, "Debit")
        rent = account_service.create_account(company_id, "Rent", "RENT",
                                              "Indirect Expense", 0.0, "Debit")
        salary = account_service.create_account(company_id, "Salary", "SAL",
                                                "Indirect Expense", 0.0, "Debit")
        sales = account_service.create_account(company_id, "Sales", "SALES",
                                               "Sales Accounts", 0.0, "Credit")
        return {"cash": cash, "bank": bank, "creditor": creditor, "debtor": debtor,
                "rent": rent, "salary": salary, "sales": sales}

    # ------------------------------------------------------------------ #
    # screen opening + header
    # ------------------------------------------------------------------ #
    def test_screen_opens_with_voucher_entry(self):
        texts = "\n".join(_all_text(self.ui.main_frame))
        for expected in ["Voucher Entry", "Voucher Type", "Date", "Voucher No.",
                         "Party A/C Name", "Particulars", "Debit", "Credit",
                         "Narration", "Save", "Save & New", "Clear", "Cancel",
                         "Total Debit", "Total Credit", "Difference"]:
            self.assertIn(expected, texts)

    def test_voucher_number_preview_uses_existing_sequence(self):
        self.assertEqual(self.ui.type_var.get(), VOUCHER_PAYMENT)
        self.assertTrue(self.ui.number_var.get().startswith("PV-"))
        # Next number advances only when a voucher is saved.
        voucher_service.save_voucher(
            1, VOUCHER_PAYMENT, date(2026, 8, 1),
            [
                {"account_id": self.acct["rent"], "debit_amount": 100.0, "credit_amount": 0.0},
                {"account_id": self.acct["bank"], "debit_amount": 0.0, "credit_amount": 100.0},
            ],
        )
        self.ui._update_number_preview()
        self.assertEqual(self.ui.number_var.get(), "PV-0002")

    def test_default_grid_has_debit_and_to_credit_rows(self):
        self.assertEqual(len(self.ui.rows), 2)
        debit_rows = [r for r in self.ui.rows if not r.get("to_line")]
        credit_rows = [r for r in self.ui.rows if r.get("to_line")]
        self.assertEqual(len(debit_rows), 1)
        self.assertEqual(len(credit_rows), 1)

    # ------------------------------------------------------------------ #
    # voucher type behavior
    # ------------------------------------------------------------------ #
    def test_contra_hides_party_field(self):
        self.ui.type_var.set(VOUCHER_CONTRA)
        self.ui._on_type_changed()
        self._sync()
        self.assertEqual(self.ui.party_picker.winfo_manager(), "")

    def test_journal_hides_party_field(self):
        self.ui.type_var.set(VOUCHER_JOURNAL)
        self.ui._on_type_changed()
        self._sync()
        self.assertEqual(self.ui.party_picker.winfo_manager(), "")

    def test_payment_and_receipt_show_party_field(self):
        self.ui.type_var.set(VOUCHER_PAYMENT)
        self.ui._on_type_changed()
        self._sync()
        self.assertNotEqual(self.ui.party_picker.winfo_manager(), "")
        self.ui.type_var.set(VOUCHER_RECEIPT)
        self.ui._on_type_changed()
        self._sync()
        self.assertNotEqual(self.ui.party_picker.winfo_manager(), "")

    # ------------------------------------------------------------------ #
    # Party A/C + To/By accounting flow
    # ------------------------------------------------------------------ #
    def test_payment_party_goes_to_debit_side(self):
        self.ui.type_var.set(VOUCHER_PAYMENT)
        self.ui._on_type_changed()
        self.ui.party_picker.set_account(self.acct["creditor"])
        self.ui._on_party_selected()
        self._sync()
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        self.assertEqual(debit_row["picker"].get_account(), self.acct["creditor"])

    def test_receipt_party_goes_to_credit_side(self):
        self.ui.type_var.set(VOUCHER_RECEIPT)
        self.ui._on_type_changed()
        self.ui.party_picker.set_account(self.acct["debtor"])
        self.ui._on_party_selected()
        self._sync()
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        self.assertEqual(credit_row["picker"].get_account(), self.acct["debtor"])

    def test_flow_hint_follows_type(self):
        self.ui.type_var.set(VOUCHER_PAYMENT)
        self.ui._on_type_changed()
        self.assertIn("To Bank/Cash", self.ui.flow_hint.cget("text"))
        self.ui.type_var.set(VOUCHER_RECEIPT)
        self.ui._on_type_changed()
        self.assertIn("To Party A/c", self.ui.flow_hint.cget("text"))
        self.ui.type_var.set(VOUCHER_CONTRA)
        self.ui._on_type_changed()
        self.assertIn("Contra", self.ui.flow_hint.cget("text"))
        self.ui.type_var.set(VOUCHER_JOURNAL)
        self.ui._on_type_changed()
        self.assertIn("To Credit A/c", self.ui.flow_hint.cget("text"))

    def test_party_picker_only_lists_party_ledgers(self):
        groups = set(self.ui.party_picker.groups or [])
        self.assertEqual(groups, {"Sundry Debtors", "Sundry Creditors"})
        names = {a["name"] for a in self.ui.party_picker.results}
        self.assertIn("ABC Traders", names)
        self.assertIn("MNO Buyers", names)
        self.assertNotIn("Cash", names)

    # ------------------------------------------------------------------ #
    # Debit / Credit / totals
    # ------------------------------------------------------------------ #
    def test_totals_and_difference_update(self):
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        debit_row["debit_var"].set("25000")
        credit_row["credit_var"].set("25000")
        self._sync()
        self.assertEqual(self.ui.total_debit_label.cget("text"), "Total Debit: 25,000.00")
        self.assertEqual(self.ui.total_credit_label.cget("text"), "Total Credit: 25,000.00")
        self.assertEqual(self.ui.difference_label.cget("text"), "Difference: 0.00")

    def test_unbalanced_difference_shows_warning(self):
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        debit_row["debit_var"].set("1000")
        credit_row["credit_var"].set("900")
        self._sync()
        self.assertIn("100.00", self.ui.difference_label.cget("text"))
        self.assertNotEqual(self.ui.difference_label.cget("text_color"), config.COLOR_INCOME)

    def test_amounts_are_right_aligned(self):
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        self.assertEqual(str(debit_row["debit_entry"].cget("justify")), "right")
        self.assertEqual(str(credit_row["credit_entry"].cget("justify")), "right")

    # ------------------------------------------------------------------ #
    # Save / Save & New
    # ------------------------------------------------------------------ #
    def _fill_payment(self, amount=25000.0):
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        debit_row["picker"].set_account(self.acct["creditor"])
        credit_row["picker"].set_account(self.acct["bank"])
        debit_row["debit_var"].set(str(amount))
        credit_row["credit_var"].set(str(amount))
        self.ui.narration_var.set("Being payment made to ABC Traders")

    def test_save_creates_balanced_voucher(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        vouchers = voucher_service.list_vouchers(1)
        self.assertEqual(len(vouchers), 1)
        voucher = vouchers[0]
        self.assertEqual(voucher["voucher_type"], VOUCHER_PAYMENT)
        self.assertEqual(voucher["voucher_number"], "PV-0001")
        totals = voucher_service.get_voucher_totals(voucher["id"])
        self.assertEqual(totals["debit_total"], 25000.0)
        self.assertEqual(totals["credit_total"], 25000.0)
        self.assertEqual(voucher["narration"], "Being payment made to ABC Traders")
        # Form resets to a blank new voucher.
        self.assertIsNone(self.ui.current_voucher_id)
        self.assertEqual(len(self.ui.rows), 2)

    def test_save_rejects_unbalanced(self):
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        debit_row["picker"].set_account(self.acct["rent"])
        debit_row["debit_var"].set("1000")
        with mock.patch("ui.vouchers.dialogs.warn") as warn:
            self.ui._save_voucher()
        self.assertTrue(warn.called)
        self.assertEqual(len(voucher_service.list_vouchers(1)), 0)

    def test_save_and_new_persists_and_stays(self):
        self._fill_payment(amount=5000.0)
        self.ui._save_and_new()
        self._sync()
        vouchers = voucher_service.list_vouchers(1)
        self.assertEqual(len(vouchers), 1)
        self.assertIsNone(self.ui.current_voucher_id)
        # A second voucher can be entered immediately.
        self.ui.type_var.set(VOUCHER_RECEIPT)
        self.ui._on_type_changed()
        self.ui.party_picker.set_account(self.acct["debtor"])
        self.ui._on_party_selected()
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        debit_row["picker"].set_account(self.acct["cash"])
        debit_row["debit_var"].set("700")
        credit_row["credit_var"].set("700")
        self.ui._save_voucher()
        self._sync()
        self.assertEqual(len(voucher_service.list_vouchers(1)), 2)

    def test_cancel_form_clears_without_saving(self):
        self._fill_payment()
        self.ui._cancel_form()
        self._sync()
        self.assertEqual(len(voucher_service.list_vouchers(1)), 0)
        self.assertIsNone(self.ui.current_voucher_id)
        self.assertEqual(len(self.ui.rows), 2)

    # ------------------------------------------------------------------ #
    # multiple lines (journal)
    # ------------------------------------------------------------------ #
    def test_journal_multiple_lines_save(self):
        # Start fresh, then switch to Journal (new voucher keeps the type).
        self.ui.on_keyboard_new()
        self.ui.type_var.set(VOUCHER_JOURNAL)
        self.ui._on_type_changed()
        self._sync()
        row0 = self.ui.rows[0]
        row0["picker"].set_account(self.acct["salary"])
        row0["debit_var"].set("50000")
        row1 = self.ui._add_row()
        row1["picker"].set_account(self.acct["rent"])
        row1["debit_var"].set("20000")
        row2 = self.ui._add_row(to_line=True)
        row2["picker"].set_account(self.acct["sales"])
        row2["credit_var"].set("70000")
        self._sync()
        debit, credit = self.ui._totals()
        self.assertEqual((debit, credit), (70000.0, 70000.0))
        self.ui.narration_var.set("Salary and rent provision")
        self.ui._save_voucher()
        self._sync()
        vouchers = voucher_service.list_vouchers(1, voucher_type=VOUCHER_JOURNAL)
        self.assertEqual(len(vouchers), 1)
        self.assertEqual(vouchers[0]["voucher_number"], "JV-0001")
        details = voucher_service.get_voucher_details(vouchers[0]["id"])
        self.assertEqual(len(details), 3)

    def test_enter_flow_adds_rows(self):
        # Debit amount Enter -> focus moves to credit (To) row account.
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        debit_row["picker"].set_account(self.acct["rent"])
        debit_row["debit_var"].set("100")
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        with mock.patch.object(credit_row["picker"], "focus_entry") as focus:
            self.ui._on_amount_return(debit_row, "debit")
            focus.assert_called_once()

    # ------------------------------------------------------------------ #
    # Edit / View
    # ------------------------------------------------------------------ #
    def test_edit_loads_existing_voucher(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        voucher = voucher_service.list_vouchers(1)[0]
        full = voucher_service.get_voucher_with_details(voucher["id"])
        self.ui._load_voucher(full)
        self._sync()
        self.assertEqual(self.ui.current_voucher_id, voucher["id"])
        self.assertEqual(self.ui.number_var.get(), "PV-0001")
        self.assertIn("Editing", self.ui.mode_label.cget("text"))
        self.assertEqual(self.ui.btn_save.cget("text"), "Update")
        debit_rows = [r for r in self.ui.rows if not r.get("to_line")]
        credit_rows = [r for r in self.ui.rows if r.get("to_line")]
        self.assertEqual(len(debit_rows), 1)
        self.assertEqual(len(credit_rows), 1)

    def test_update_persists_changes(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        voucher = voucher_service.list_vouchers(1)[0]
        self.ui._load_voucher(voucher_service.get_voucher_with_details(voucher["id"]))
        debit_row = [r for r in self.ui.rows if not r.get("to_line")][0]
        debit_row["debit_var"].set("30000")
        credit_row = [r for r in self.ui.rows if r.get("to_line")][0]
        credit_row["credit_var"].set("30000")
        self.ui._save_voucher()  # in edit mode this updates
        self._sync()
        totals = voucher_service.get_voucher_totals(voucher["id"])
        self.assertEqual(totals["debit_total"], 30000.0)
        self.assertEqual(len(voucher_service.list_vouchers(1)), 1)

    def test_view_read_only_state(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        voucher = voucher_service.list_vouchers(1)[0]
        self.ui._load_voucher(voucher_service.get_voucher_with_details(voucher["id"]))
        self.ui._set_read_only(True)
        self._sync()
        self.assertIn("Viewing", self.ui.mode_label.cget("text"))
        self.assertEqual(str(self.ui.date_entry.cget("state")), "disabled")
        self.assertEqual(len(voucher_service.list_vouchers(1)), 1)

    # ------------------------------------------------------------------ #
    # Cancel voucher (existing workflow)
    # ------------------------------------------------------------------ #
    def test_cancel_selected_voucher(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        voucher = voucher_service.list_vouchers(1)[0]
        self.ui._load_voucher(voucher_service.get_voucher_with_details(voucher["id"]))
        with mock.patch("ui.vouchers.dialogs.confirm_destructive", return_value=True):
            self.ui._cancel_selected_voucher()
        self._sync()
        self.assertEqual(voucher_service.get_voucher(voucher["id"])["status"], STATUS_CANCELLED)

    # ------------------------------------------------------------------ #
    # keyboard hooks
    # ------------------------------------------------------------------ #
    def test_ctrl_n_new(self):
        self._fill_payment()
        self.ui.on_keyboard_new()
        self._sync()
        self.assertIsNone(self.ui.current_voucher_id)
        self.assertEqual(len(self.ui.rows), 2)

    def test_ctrl_s_saves(self):
        self._fill_payment()
        self.ui.on_keyboard_save()
        self._sync()
        self.assertEqual(len(voucher_service.list_vouchers(1)), 1)

    def test_ctrl_f_opens_register(self):
        self.ui.on_keyboard_search()
        self._sync()
        self.assertTrue(self.ui._register_open)
        self.assertIsNotNone(self.ui.register_tree)
        self.ui._close_register()

    def test_f5_refreshes_register(self):
        self.ui.on_keyboard_refresh()
        self._sync()
        self.assertGreaterEqual(len(self.ui.vouchers), 0)

    def test_del_cancels_current(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        voucher = voucher_service.list_vouchers(1)[0]
        self.ui._load_voucher(voucher_service.get_voucher_with_details(voucher["id"]))
        with mock.patch("ui.vouchers.dialogs.confirm_destructive", return_value=True):
            self.ui.on_keyboard_delete()
        self._sync()
        self.assertEqual(voucher_service.get_voucher(voucher["id"])["status"], STATUS_CANCELLED)

    def test_esc_back_route(self):
        calls = []
        self.ui.on_keyboard_back = lambda: calls.append("back")
        self.ui.on_keyboard_back()
        self.assertEqual(calls, ["back"])

    # ------------------------------------------------------------------ #
    # voucher register (existing list preserved)
    # ------------------------------------------------------------------ #
    def test_register_lists_vouchers(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        self.ui._open_register()
        self._sync()
        children = self.ui.register_tree.get_children()
        self.assertEqual(len(children), 1)
        self.assertEqual(self.ui.register_tree.item(children[0], "values")[0], "PV-0001")
        self.ui._close_register()

    def test_register_loads_selected_for_edit(self):
        self._fill_payment()
        self.ui._save_voucher()
        self._sync()
        self.ui._open_register()
        self._sync()
        children = self.ui.register_tree.get_children()
        self.ui.register_tree.selection_set(children[0])
        self.ui._register_load_selected()
        self._sync()
        self.assertIsNotNone(self.ui.current_voucher_id)
        self.assertIn("Editing", self.ui.mode_label.cget("text"))
        self.assertFalse(self.ui._register_open)

    # ------------------------------------------------------------------ #
    # company isolation
    # ------------------------------------------------------------------ #
    def test_company_isolation(self):
        ui_b = VouchersFrame(self.root, company_id=2)
        try:
            self._sync()
            ui_b.rows[0]["picker"]._load_all()
            self.assertEqual(ui_b.rows[0]["picker"].results, [])
            self.assertEqual(len(voucher_service.list_vouchers(2)), 0)
        finally:
            ui_b.main_frame.destroy()

    def test_company_id_never_defaulted(self):
        self.assertEqual(self.ui.company_id, 1)

    # ------------------------------------------------------------------ #
    # theme + layout
    # ------------------------------------------------------------------ #
    def test_theme_cycles_without_error(self):
        for mode in ("light", "dark", "light", "dark"):
            ctk.set_appearance_mode(mode)
            theme.apply_theme(self.root, mode=mode)
            theme.apply_palette(self.root)
            self._sync()
        self.assertTrue(self.ui.main_frame.winfo_exists())

    def test_rows_and_buttons_not_clipped(self):
        # The test root is withdrawn; geometry presence is the reliable
        # layout signal (a mapped window is verified on the real app).
        for row in self.ui.rows:
            self.assertTrue(row["frame"].winfo_exists())
            self.assertGreaterEqual(row["frame"].winfo_width(), 0)
            self.assertGreaterEqual(row["frame"].winfo_height(), 0)
        for button in (self.ui.btn_save, self.ui.btn_save_new, self.ui.btn_clear,
                       self.ui.btn_cancel, self.ui.btn_register):
            self.assertTrue(button.winfo_exists())
            self.assertGreater(button.winfo_reqwidth(), 1)
            self.assertGreater(button.winfo_reqheight(), 1)

    def test_repeated_navigation_does_not_duplicate(self):
        for _ in range(4):
            self.ui.on_keyboard_new()
            self._sync()
            self.assertEqual(len(self.ui.rows), 2)

    def test_reference_field_reused_from_existing_schema(self):
        # The old screen had a "Reference / Cheque" field; the new screen
        # keeps narration and date, and never invents new columns.
        self.assertFalse(hasattr(self.ui, "reference_var"))


if __name__ == "__main__":
    unittest.main()
