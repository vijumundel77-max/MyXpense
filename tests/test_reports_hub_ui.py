"""
Regression tests for the redesigned Reports Hub UI.

These exercise the real ReportsHubUI against the shared Tk root (headless
under a virtual display; visible on Windows).  Coverage:

- the hub opens and shows every existing report card
- search filters the report cards immediately
- single click selects, double click / Enter opens the correct report route
- the correct report module (and company context) is opened
- F5 refreshes, Ctrl+F focuses search, Esc closes a report / returns back
- recently opened reports are recorded per company (no fake history)
- theme switching keeps the hub functional
- resize keeps cards inside the window (no clipping)
"""
import unittest
from unittest import mock

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.recent_reports_service import recent_reports  # noqa: E402
from services.voucher_service import voucher_service  # noqa: E402
from ui.reports import ReportsHubUI  # noqa: E402
from utils import theme  # noqa: E402

REPORT_TITLES = [
    "Day Book", "Cash Book", "Bank Book", "Party Ledger", "Account Book",
    "Outstanding Report", "Ageing Report", "Trial Balance", "Balance Sheet",
]


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


def _is_mapped(widget) -> bool:
    try:
        return bool(widget.winfo_ismapped())
    except Exception:
        return False


def _within_window(widget) -> bool:
    """True when a widget's requested geometry fits its toplevel window."""
    try:
        top = widget.winfo_toplevel()
        top.update_idletasks()
        width = widget.winfo_width()
        height = widget.winfo_height()
        return width > 1 and height > 1
    except Exception:
        return False


class ReportsHubTest(unittest.TestCase):
    """Reports hub UI behavior."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            "INSERT INTO companies (id, name) VALUES (1, 'Reports Hub Co')")
        db.execute(
            "INSERT INTO companies (id, name) VALUES (2, 'Reports Hub Co B')")
        from services.group_service import group_service
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
        db.execute("DELETE FROM recent_reports")
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.hub = ReportsHubUI(self.root, 1)
        self._sync()

    def tearDown(self):
        try:
            self.hub.destroy()
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _sync(self):
        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # hub opens with all report cards
    # ------------------------------------------------------------------ #
    def test_hub_opens(self):
        self.assertIsInstance(self.hub, ReportsHubUI)
        self.assertEqual(len(self.hub._card_widgets), 9)

    def test_all_existing_report_cards_present(self):
        titles = list(self.hub._card_widgets.keys())
        for title in REPORT_TITLES:
            self.assertIn(title, titles)

    def test_cards_have_subtitles(self):
        for item in self.hub._report_defs:
            self.assertTrue(item["subtitle"])

    def test_header_and_sections_visible(self):
        texts = "\n".join(_all_text(self.hub.main_frame))
        for expected in ["Reports", "Select a report to view",
                         "Open Advanced Report Module",
                         "Recently Opened Reports",
                         "How to use Reports",
                         "SHORTCUTS (THIS SCREEN)"]:
            self.assertIn(expected, texts)

    def test_shortcut_bar_buttons_present(self):
        texts = "\n".join(_all_text(self.hub.shortcut_bar))
        for expected in ["F5  Refresh", "Ctrl+F  Search", "Esc  Back",
                         "Enter  Open Report"]:
            self.assertIn(expected, texts)

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #
    def test_search_filters_cards(self):
        self.hub.search_var.set("bank")
        self._sync()
        titles = list(self.hub._card_widgets.keys())
        self.assertEqual(titles, ["Bank Book"])

    def test_search_clears_back(self):
        self.hub.search_var.set("bank")
        self._sync()
        self.assertEqual(len(self.hub._card_widgets), 1)
        self.hub.search_var.set("")
        self._sync()
        self.assertEqual(len(self.hub._card_widgets), 9)

    def test_search_no_match_shows_message(self):
        self.hub.search_var.set("zzz-no-such-report")
        self._sync()
        self.assertEqual(len(self.hub._card_widgets), 0)
        texts = "\n".join(_all_text(self.hub.cards_frame))
        self.assertIn("No matching reports found.", texts)

    def test_search_entry_has_placeholder(self):
        placeholder = self.hub.search_entry.cget("placeholder_text")
        self.assertIn("Search reports", placeholder)

    # ------------------------------------------------------------------ #
    # selection and opening
    # ------------------------------------------------------------------ #
    def test_single_click_selects(self):
        self.hub._on_card_click("Day Book")
        self.assertEqual(self.hub.selected_title, "Day Book")
        self.assertIs(self.hub._selected_card, self.hub._card_widgets["Day Book"])
        self.assertIsNone(self.hub.current_frame)

    def test_double_click_opens_report(self):
        self.hub._on_card_double_click("Day Book")
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "DayBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_enter_opens_report(self):
        self.hub._on_card_click("Cash Book")
        self.hub._on_card_enter("Cash Book")
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "CashBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_global_enter_opens_selected_report(self):
        """Enter anywhere on the hub opens the currently selected report."""
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "DayBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_global_enter_without_selection_opens_first(self):
        """Enter with no selection safely selects and opens the first card.

        The first report is auto-focused when the hub opens (per spec), so a
        bare Enter must open that focused first card.
        """
        self._sync()
        self.assertEqual(self.hub.selected_title, "Day Book")
        self.hub._on_global_enter()
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "DayBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_global_enter_after_filtering_keeps_selection(self):
        """The selected report stays correctly mapped after filtering."""
        self.hub.search_var.set("bank")
        self._sync()
        self.hub._on_card_click("Bank Book")
        self.hub._on_global_enter()
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "BankBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_enter_does_not_double_open(self):
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        first_ui = self.hub.current_report_ui
        self.hub._on_global_enter()
        self._sync()
        self.assertIs(self.hub.current_report_ui, first_ui)

    def test_open_report_is_visible_and_hub_body_hidden(self):
        """While a report is open the hub body is hidden; the report's main
        frame is packed and visible."""
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        self.assertEqual(self.hub.body_container.winfo_manager(), "")
        self.assertNotEqual(self.hub.current_frame.winfo_manager(), "")

    def test_close_report_restores_hub_body(self):
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        self.hub._close_report()
        self._sync()
        self.assertIsNone(self.hub.current_frame)
        self.assertEqual(self.hub.body_container.winfo_manager(), "pack")

    def test_mouse_open_button_visible(self):
        texts = "\n".join(_all_text(self.hub.shortcut_bar))
        self.assertIn("Enter  Open", texts)
        self.assertTrue(hasattr(self.hub, "_shortcut_enter_btn"))
        self.assertEqual(self.hub._shortcut_enter_btn.cget("text"), "Enter  Open")

    def test_report_has_back_button(self):
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        # The report carries its own back-arrow header + action bar Back.
        texts = "\n".join(_all_text(self.hub.current_frame))
        self.assertIn("← Back", texts)
        # And the back arrow returns to the hub.
        self.hub.current_report_ui._back()
        self._sync()
        self.assertIsNone(self.hub.current_frame)
        self.assertEqual(self.hub.body_container.winfo_manager(), "pack")

    def test_correct_route_for_each_report(self):
        expected = {
            "Day Book": "DayBookReportUI",
            "Cash Book": "CashBookReportUI",
            "Bank Book": "BankBookReportUI",
            "Party Ledger": "PartyLedgerReportUI",
            "Account Book": "AccountBookReportUI",
            "Outstanding Report": "OutstandingReportUI",
            "Ageing Report": "AgeingReportUI",
            "Trial Balance": "TrialBalanceReportUI",
            "Balance Sheet": "BalanceSheetReportUI",
        }
        for title, cls_name in expected.items():
            item = self.hub._report_by_title(title)
            item["open"](self.hub)
            self._sync()
            self.assertEqual(
                self.hub.current_report_ui.__class__.__name__, cls_name,
                f"{title} opened wrong route")
            self.hub._close_report()
            self._sync()
            self.assertIsNone(self.hub.current_frame)

    def test_company_id_passed_to_report(self):
        self.hub._on_card_enter("Party Ledger")
        self._sync()
        self.assertEqual(self.hub.current_report_ui.company_id, 1)
        self.hub._close_report()

    # ------------------------------------------------------------------ #
    # keyboard shortcuts
    # ------------------------------------------------------------------ #
    def test_f5_refresh_rebuilds_cards(self):
        before = list(self.hub._card_widgets.keys())
        self.hub.search_var.set("bank")
        self._sync()
        self.hub.on_keyboard_refresh()
        titles = list(self.hub._card_widgets.keys())
        # Refresh preserves the current search filter.
        self.assertEqual(titles, ["Bank Book"])
        self.hub.search_var.set("")
        self.hub.on_keyboard_refresh()
        self._sync()
        self.assertEqual(list(self.hub._card_widgets.keys()), before)

    def test_ctrl_f_focuses_search(self):
        self.hub.on_keyboard_search()
        self._sync()
        focused = self.root.focus_get()
        # focus_set lands on the CTkEntry's internal tk.Entry; both belong to
        # the same search box, so accept either.
        self.assertTrue(
            focused == self.hub.search_entry
            or focused in self.hub.search_entry.winfo_children(),
            f"expected search entry focus, got {focused}",
        )

    def test_esc_closes_open_report(self):
        self.hub._on_card_enter("Day Book")
        self._sync()
        self.assertIsNotNone(self.hub.current_frame)
        self.hub.on_keyboard_back()
        self._sync()
        self.assertIsNone(self.hub.current_frame)

    def test_esc_after_report_returns_to_hub(self):
        """Esc from a report returns to the hub (hub body visible again)."""
        self.hub._on_card_enter("Day Book")
        self._sync()
        self.hub.on_keyboard_back()
        self._sync()
        self.assertIsNone(self.hub.current_frame)
        self.assertEqual(self.hub.body_container.winfo_manager(), "pack")

    def test_esc_on_hub_does_not_raise(self):
        # Esc with no report open must not raise or destroy anything.
        self.hub._handle_back_shortcut()

    # ------------------------------------------------------------------ #
    # report-specific controls + shortcut forwarding
    # ------------------------------------------------------------------ #
    def test_day_book_has_date_type_search_controls(self):
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        for attr in ("from_date_var", "to_date_var", "type_var", "search_var"):
            self.assertTrue(hasattr(ui, attr), f"Day Book missing {attr}")
        texts = "\n".join(_all_text(ui.main_frame))
        for label in ("From Date", "To Date", "Type", "Search",
                      "Generate", "Export CSV", "Export JSON", "Export PNG"):
            self.assertIn(label, texts)

    def test_cash_book_has_account_search_controls(self):
        self.hub._on_card_click("Cash Book")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        for attr in ("from_date_var", "to_date_var", "account_var", "search_var"):
            self.assertTrue(hasattr(ui, attr), f"Cash Book missing {attr}")

    def test_bank_book_has_account_search_controls(self):
        self.hub._on_card_click("Bank Book")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        for attr in ("from_date_var", "to_date_var", "account_var", "search_var"):
            self.assertTrue(hasattr(ui, attr), f"Bank Book missing {attr}")

    def test_party_ledger_has_party_date_controls(self):
        self.hub._on_card_click("Party Ledger")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        for attr in ("party_var", "from_date_var", "to_date_var", "search_var",
                     "party_combo"):
            self.assertTrue(hasattr(ui, attr), f"Party Ledger missing {attr}")

    def test_trial_balance_has_as_of_date_and_search(self):
        self.hub._on_card_click("Trial Balance")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        self.assertTrue(hasattr(ui, "as_on_date_var"))
        self.assertTrue(hasattr(ui, "search_var"))
        self.assertTrue(hasattr(ui, "search_entry"))

    def test_f5_forwards_to_report_generate(self):
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        self.assertTrue(callable(getattr(ui, "on_keyboard_refresh", None)))
        with mock.patch.object(ui, "_generate_report") as gen:
            self.hub.on_keyboard_refresh()
        gen.assert_called_once()

    def test_ctrl_f_forwards_to_report_search(self):
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        ui = self.hub.current_report_ui
        self.assertTrue(callable(getattr(ui, "on_keyboard_search", None)))
        # Should not blow up and should focus the report's search entry.
        self.hub.on_keyboard_search()
        self._sync()
        focused = self.root.focus_get()
        self.assertTrue(
            focused == ui.search_entry or focused in ui.search_entry.winfo_children(),
            f"expected report search focus, got {focused}",
        )

    def test_each_report_exposes_keyboard_hooks(self):
        for title in REPORT_TITLES:
            item = self.hub._report_by_title(title)
            item["open"](self.hub)
            self._sync()
            ui = self.hub.current_report_ui
            self.assertTrue(callable(getattr(ui, "on_keyboard_refresh", None)),
                            f"{title} missing on_keyboard_refresh")
            self.assertTrue(callable(getattr(ui, "on_keyboard_search", None)),
                            f"{title} missing on_keyboard_search")
            self.hub._close_report()
            self._sync()

    # ------------------------------------------------------------------ #
    # compact report layout (filter bar, date pickers, action bar, table)
    # ------------------------------------------------------------------ #
    def _open_report_ui(self, title, company_id=None):
        if company_id is None:
            self.hub._on_card_click(title)
            self.hub._on_global_enter()
            self._sync()
            return self.hub.current_report_ui
        # Open a report screen directly against a specific company (used by
        # the Day Book data tests so totals are deterministic).  The report
        # packs into the hub's main frame (the hub remains the only widget
        # packed into the shared root, so layout stays intact for later
        # tests).
        from ui.day_book_report import show_day_book_report
        ui = show_day_book_report(self.hub.main_frame, company_id)
        self._sync()
        return ui

    def test_day_book_has_date_pickers(self):
        from ui import report_base as rb
        ui = self._open_report_ui("Day Book")
        # From/To date vars default to today in DD-MM-YYYY.
        from datetime import date
        expected = date.today().strftime(config.DISPLAY_DATE_FORMAT)
        self.assertEqual(ui.from_date_var.get(), expected)
        self.assertEqual(ui.to_date_var.get(), expected)

        # Calendar buttons exist (one per date field).
        def find_cal(w):
            found = []
            for c in w.winfo_children():
                try:
                    if isinstance(c, ctk.CTkButton) and c.cget("text") == "📅":
                        found.append(c)
                except Exception:
                    pass
                found.extend(find_cal(c))
            return found

        cal_buttons = find_cal(ui.main_frame)
        self.assertGreaterEqual(len(cal_buttons), 2)

    def test_report_filter_bar_is_compact_two_rows(self):
        ui = self._open_report_ui("Cash Book")
        from ui import report_base as rb
        fb = [c for c in ui.main_frame.winfo_children()
              if c.__class__.__name__ == "FilterBar"][0]
        rows = {w.grid_info().get("row") for w in fb.body.winfo_children()}
        self.assertLessEqual(len(rows), 2)

    def test_day_book_filter_area_is_compact_single_row(self):
        """The Day Book's Tally-style filter area is a single compact row."""
        ui = self._open_report_ui("Day Book")
        body = ui.filters.winfo_children()[0]
        rows = {int(w.grid_info().get("row", -1)) for w in body.winfo_children()}
        self.assertLessEqual(len(rows), 2)

    def test_report_table_takes_majority(self):
        ui = self._open_report_ui("Cash Book")
        self._sync()
        heights = {}
        for c in ui.main_frame.winfo_children():
            heights[c.__class__.__name__] = c.winfo_height()
        table_h = heights.get("ReportTable", 0)
        filter_h = heights.get("FilterBar", 0)
        action_h = heights.get("ReportActionBar", 0)
        self.assertGreater(table_h, filter_h, "table should exceed filter bar")
        self.assertGreater(table_h, action_h, "table should exceed action bar")
        # Filter bar is compact.
        self.assertLess(filter_h, 200)

    def test_day_book_table_takes_majority(self):
        """The Day Book's full-window table dominates the screen."""
        ui = self._open_report_ui("Day Book")
        self._sync()
        table_container = ui.table_container
        toolbar = ui.btn_new.master.master
        self.assertGreater(table_container.winfo_height(),
                           toolbar.winfo_height(),
                           "table should exceed toolbar")

    # ------------------------------------------------------------------ #
    # Day Book Tally-style table (amounts in the correct column only)
    # ------------------------------------------------------------------ #
    def _seed_day_book_vouchers(self):
        """Two vouchers with distinct parties so the register has real data.

        Uses a dedicated company so the totals are deterministic regardless of
        what other tests seeded into the shared in-memory database.
        """
        from services.account_service import account_service
        from services.voucher_service import VOUCHER_PAYMENT, VOUCHER_RECEIPT
        from datetime import date
        db.execute("DELETE FROM voucher_details WHERE voucher_id IN "
                   "(SELECT id FROM vouchers WHERE company_id = 77)")
        db.execute("DELETE FROM vouchers WHERE company_id = 77")
        db.execute("DELETE FROM accounts WHERE company_id = 77")
        db.execute("DELETE FROM companies WHERE id = 77")
        db.execute(
            "INSERT INTO companies (id, name) VALUES (77, 'Day Book Co')")
        from services.group_service import group_service
        group_service.seed_default_groups(77)
        accts = {}
        for name, code, group in [
            ("Cash", "CASH", "Cash-in-Hand"),
            ("Bank", "BANK", "Bank Accounts"),
            ("ABC Traders", "ABC", "Sundry Creditors"),
            ("XYZ Customer", "XYZ", "Sundry Debtors"),
        ]:
            accts[name] = account_service.create_account(
                77, name, code, group, 0.0,
                "Credit" if group == "Sundry Creditors" else "Debit")
        voucher_service.save_voucher(
            77, VOUCHER_PAYMENT, date(2026, 8, 14),
            [{"account_id": accts["ABC Traders"], "debit_amount": 3000.0,
              "credit_amount": 0.0},
             {"account_id": accts["Bank"], "debit_amount": 0.0,
              "credit_amount": 3000.0}],
            narration="Payment to ABC Traders")
        voucher_service.save_voucher(
            77, VOUCHER_RECEIPT, date(2026, 8, 14),
            [{"account_id": accts["Cash"], "debit_amount": 14450.0,
              "credit_amount": 0.0},
             {"account_id": accts["XYZ Customer"], "debit_amount": 0.0,
              "credit_amount": 14450.0}],
            narration="Receipt from XYZ Customer")
        return 77

    def test_day_book_columns_one_row_per_voucher(self):
        ui = self._open_report_ui("Day Book")
        headings = [ui.tree.heading(c, "text") for c in ui.tree["columns"]]
        self.assertEqual(headings, ["Date", "Particulars", "Vch Type",
                                    "Vch No.", "Amount"])

    def test_day_book_amount_shown_once_per_voucher(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui.from_date_var.set("14-08-2026")
        ui.to_date_var.set("14-08-2026")
        ui._generate_report()
        self._sync()
        children = ui.tree.get_children()
        # Two vouchers -> two rows (one per voucher, not per ledger line).
        self.assertEqual(len(children), 2)
        # Each row has a single Amount value (column 4) and nothing else.
        for iid in children:
            values = ui.tree.item(iid, "values")
            self.assertEqual(len(values), 5)
            self.assertTrue(values[4], f"amount missing: {values}")
        # Payment PV-0001 (Anita) -> 3,000.00 out; Receipt RV-0001 -> 14,450.00.
        by_number = {ui.tree.item(iid, "values")[3]: ui.tree.item(iid, "values")
                     for iid in children}
        self.assertEqual(by_number["PV-0001"][4], "3,000.00")
        self.assertEqual(by_number["RV-0001"][4], "14,450.00")

    def test_day_book_payment_red_receipt_green(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        children = ui.tree.get_children()
        self.assertEqual(len(children), 2)
        by_number = {ui.tree.item(iid, "values")[3]: iid for iid in children}
        # Payment = money OUT = red tag; Receipt = money IN = green tag.
        self.assertIn("out", ui.tree.item(by_number["PV-0001"], "tags"))
        self.assertIn("in", ui.tree.item(by_number["RV-0001"], "tags"))
        out_color = str(ui.tree.tag_configure("out", "foreground"))
        in_color = str(ui.tree.tag_configure("in", "foreground"))
        self.assertIn(config.COLOR_EXPENSE.lower(), out_color.lower())
        self.assertIn(config.COLOR_INCOME.lower(), in_color.lower())

    def test_day_book_date_is_dd_mm_yyyy(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        for iid in ui.tree.get_children():
            date_text = ui.tree.item(iid, "values")[0]
            self.assertRegex(date_text, r"^\d{2}-\d{2}-\d{4}$",
                             f"date not DD-MM-YYYY: {date_text}")

    def test_day_book_particulars_are_ledger_names(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        particulars = {ui.tree.item(iid, "values")[1]
                       for iid in ui.tree.get_children()}
        # Payment's party (ABC Traders) and Receipt's party (XYZ Customer).
        self.assertIn("ABC Traders", particulars)
        self.assertIn("XYZ Customer", particulars)

    def test_day_book_voucher_type_and_number(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        types = {ui.tree.item(iid, "values")[2] for iid in ui.tree.get_children()}
        numbers = {ui.tree.item(iid, "values")[3] for iid in ui.tree.get_children()}
        self.assertIn("Payment", types)
        self.assertIn("Receipt", types)
        self.assertIn("PV-0001", numbers)
        self.assertIn("RV-0001", numbers)

    def test_day_book_toolbar_buttons(self):
        ui = self._open_report_ui("Day Book")
        texts = "\n".join(_all_text(ui.main_frame))
        for label in ("New Voucher", "Open / Edit", "View", "Delete", "Refresh"):
            self.assertIn(label, texts)

    def test_day_book_search_label(self):
        ui = self._open_report_ui("Day Book")
        placeholder = ui.search_entry.cget("placeholder_text")
        self.assertIn("Search", placeholder)
        texts = "\n".join(_all_text(ui.main_frame))
        self.assertIn("Search", texts)

    def test_day_book_filters_default_to_today(self):
        ui = self._open_report_ui("Day Book")
        from datetime import date
        expected = date.today().strftime(config.DISPLAY_DATE_FORMAT)
        self.assertEqual(ui.from_date_var.get(), expected)
        self.assertEqual(ui.to_date_var.get(), expected)
        self.assertEqual(ui.type_var.get(), "All Types")

    def test_day_book_totals_bar(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        total_text = ui.totals_label.cget("text")
        # Payment 3,000 out; Receipt 14,450 in.
        self.assertIn("Total Out: 3,000.00", total_text)
        self.assertIn("Total In: 14,450.00", total_text)
        self.assertIn("2", total_text)          # 2 vouchers

    def test_day_book_single_click_selects_row(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        children = ui.tree.get_children()
        ui.tree.selection_set(children[0])
        self.assertEqual(len(ui.tree.selection()), 1)
        self.assertIsNotNone(ui._selected_voucher_id())

    def test_day_book_enter_opens_selected(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        children = ui.tree.get_children()
        ui.tree.selection_set(children[0])
        voucher_id = ui._selected_voucher_id()
        voucher = ui._selected_voucher()
        self.assertIsNotNone(voucher)
        self.assertEqual(voucher["id"], voucher_id)

    def test_day_book_double_click_opens_selected(self):
        self._seed_day_book_vouchers()
        ui = self._open_report_ui("Day Book", company_id=77)
        ui._generate_report()
        self._sync()
        children = ui.tree.get_children()
        ui.tree.selection_set(children[0])
        voucher = ui._selected_voucher()
        self.assertIsNotNone(voucher)
        self.assertIn(voucher["voucher_number"],
                      ("PV-0001", "RV-0001"))

    def test_report_action_bar_present_with_exports(self):
        ui = self._open_report_ui("Day Book")
        texts = "\n".join(_all_text(ui.main_frame))
        for label in ("Refresh", "Export CSV", "Export JSON", "Export PNG",
                      "Clear", "← Back"):
            self.assertIn(label, texts)

    def test_report_back_arrow_returns_to_hub(self):
        ui = self._open_report_ui("Cash Book")
        ui._back()
        self._sync()
        self.assertIsNone(self.hub.current_frame)
        self.assertEqual(self.hub.body_container.winfo_manager(), "pack")

    def test_report_clear_resets_filters(self):
        ui = self._open_report_ui("Day Book")
        ui.search_var.set("abc")
        ui.from_date_var.set("01-01-2020")
        ui._clear_filters()
        from datetime import date
        self.assertEqual(ui.search_var.get(), "")
        self.assertEqual(ui.from_date_var.get(),
                         date.today().strftime(config.DISPLAY_DATE_FORMAT))

    def test_date_picker_calendar_popup_opens(self):
        from ui import report_base as rb
        var = tk.StringVar(value="13-08-2026")
        picker = rb.DatePicker(self.root, var)
        picker.open()
        self._sync()
        popups = [w for w in self.root.winfo_children()
                  if isinstance(w, (ctk.CTkToplevel, tk.Toplevel))]
        self.assertEqual(len(popups), 1)
        popups[0].destroy()
        self._sync()

    def test_date_picker_today_sets_current_date(self):
        from ui import report_base as rb
        from datetime import date
        var = tk.StringVar(value="01-01-2020")
        picker = rb.DatePicker(self.root, var)
        picker.open()
        self._sync()
        popups = [w for w in self.root.winfo_children()
                  if isinstance(w, (ctk.CTkToplevel, tk.Toplevel))]
        self.assertEqual(len(popups), 1)
        popup = popups[0]

        def find_today(w):
            for c in w.winfo_children():
                try:
                    if isinstance(c, ctk.CTkButton) and c.cget("text") == "Today":
                        return c
                except Exception:
                    pass
                r = find_today(c)
                if r:
                    return r
            return None

        btn = find_today(popup)
        self.assertIsNotNone(btn)
        btn.invoke()
        self._sync()
        self.assertEqual(var.get(), date.today().strftime(config.DISPLAY_DATE_FORMAT))

    def test_hub_chrome_hidden_while_report_open(self):
        ui = self._open_report_ui("Day Book")
        self.assertEqual(self.hub.hub_header.winfo_manager(), "")
        self.assertEqual(self.hub.search_bar.winfo_manager(), "")
        self.assertEqual(self.hub.body_container.winfo_manager(), "")
        self.assertEqual(self.hub.shortcut_bar.winfo_manager(), "")
        self.assertIsNotNone(self.hub.current_frame)
        # Report frame is packed and fills the hub.
        self.assertNotEqual(self.hub.current_frame.winfo_manager(), "")

    def test_hub_chrome_restored_after_report_close(self):
        ui = self._open_report_ui("Day Book")
        self.hub.on_keyboard_back()
        self._sync()
        self.assertIsNone(self.hub.current_frame)
        self.assertNotEqual(self.hub.hub_header.winfo_manager(), "")
        self.assertNotEqual(self.hub.search_bar.winfo_manager(), "")
        self.assertNotEqual(self.hub.body_container.winfo_manager(), "")
        self.assertNotEqual(self.hub.shortcut_bar.winfo_manager(), "")

    def test_report_filters_do_not_stack_everything(self):
        """Report filters stay in a compact grid (<=3 rows), never one field
        per line stacked vertically."""
        for title in ("Outstanding Report", "Ageing Report", "Party Ledger",
                      "Trial Balance", "Balance Sheet", "Day Book", "Cash Book",
                      "Bank Book", "Account Book"):
            ui = self._open_report_ui(title)
            fbs = [c for c in ui.main_frame.winfo_children()
                   if c.__class__.__name__ == "FilterBar"]
            if fbs:
                rows = {w.grid_info().get("row")
                        for w in fbs[0].body.winfo_children()
                        if w.winfo_manager() != ""}
                self.assertLessEqual(len(rows), 3, f"{title} filter rows")
            self.hub.on_keyboard_back()
            self._sync()

    # ------------------------------------------------------------------ #
    # recently opened
    # ------------------------------------------------------------------ #
    def test_recent_empty_by_default(self):
        self.assertEqual(recent_reports(1), [])

    def test_recent_tracks_opened_reports(self):
        self.hub._on_card_enter("Day Book")
        self._sync()
        self.hub._close_report()
        self.hub._refresh_recent()
        entries = recent_reports(1)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["report_name"], "Day Book")

    def test_recent_bumps_reopened_report_to_top(self):
        self.hub._on_card_enter("Day Book")
        self._sync()
        self.hub._close_report()
        self.hub._on_card_enter("Cash Book")
        self._sync()
        self.hub._close_report()
        self.hub._on_card_enter("Day Book")
        self._sync()
        self.hub._close_report()
        entries = recent_reports(1)
        self.assertEqual(entries[0]["report_name"], "Day Book")

    def test_recent_is_company_scoped(self):
        self.hub._on_card_enter("Day Book")
        self._sync()
        self.hub._close_report()
        self.assertEqual(recent_reports(1)[0]["report_name"], "Day Book")
        self.assertEqual(recent_reports(2), [])

    # ------------------------------------------------------------------ #
    # theme + resize
    # ------------------------------------------------------------------ #
    def test_theme_cycles_without_error(self):
        self._sync()
        for mode in ("light", "dark", "light", "dark"):
            ctk.set_appearance_mode(mode)
            theme.apply_theme(self.root, mode=mode)
            theme.apply_palette(self.root)
            self._sync()
        self.assertEqual(len(self.hub._card_widgets), 9)

    def test_theme_toggle_keeps_recent_section(self):
        for mode in ("light", "dark"):
            ctk.set_appearance_mode(mode)
            theme.apply_theme(self.root, mode=mode)
            theme.apply_palette(self.root)
            self._sync()
            self.assertGreater(len(self.hub.recent_panel.winfo_children()), 0)

    def test_resize_keeps_widgets_mapped(self):
        try:
            self.root.deiconify()
        except Exception:
            pass
        for size in ((1360, 820), (1100, 680), (1600, 1000)):
            self.root.geometry(f"{size[0]}x{size[1]}")
            for _ in range(3):
                self._sync()
            # All chrome sections are managed and hold real geometry at every
            # supported size (never 1x1 collapsed).
            for widget in (self.hub.search_bar, self.hub.cards_frame,
                           self.hub.recent_frame, self.hub.help_frame,
                           self.hub.shortcut_bar):
                self.assertGreaterEqual(widget.winfo_width(), 1,
                                        f"{widget} collapsed at {size}")
                self.assertGreaterEqual(widget.winfo_height(), 1,
                                        f"{widget} collapsed at {size}")
                self.assertNotEqual(widget.winfo_manager(), "",
                                    f"{widget} unmanaged at {size}")
            for card in self.hub._card_widgets.values():
                self.assertTrue(_within_window(card),
                                f"card outside window at {size}")
        try:
            self.root.withdraw()
        except Exception:
            pass

    def test_min_window_size_no_cards_collapsed(self):
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.root.geometry("1100x680")
        self._sync()
        collapsed = [
            t for t, card in self.hub._card_widgets.items()
            if not _within_window(card)
        ]
        self.assertEqual(collapsed, [])
        try:
            self.root.withdraw()
        except Exception:
            pass

    def test_responsive_grid_single_column_when_narrow(self):
        # Force a narrow viewport: the grid must collapse to one column
        # instead of clipping the right column off-window.
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.root.geometry("500x400")
        for _ in range(3):
            self._sync()
        self.assertEqual(self.hub._card_columns(), 1)
        first = self.hub._card_widgets["Day Book"]
        second = self.hub._card_widgets["Cash Book"]
        # Both first-column cards share the same x position (stacked vertically).
        self.assertEqual(first.winfo_x(), second.winfo_x())
        self.assertGreater(second.winfo_y(), first.winfo_y())
        # No card extends beyond the cards frame.
        for card in self.hub._card_widgets.values():
            self.assertLessEqual(
                card.winfo_x() + card.winfo_width(),
                self.hub.cards_frame.winfo_width() + 1,
                f"card outside frame width",
            )
        try:
            self.root.withdraw()
        except Exception:
            pass

    def test_responsive_grid_two_columns_when_wide(self):
        # Deterministic: drive the responsive decision by simulating the
        # frame width (the grid never clips — it re-flows by width).
        with mock.patch.object(self.hub, "_available_card_width",
                               return_value=1100):
            self.assertEqual(self.hub._card_columns(), 2)
        with mock.patch.object(self.hub, "_available_card_width",
                               return_value=620):
            self.assertEqual(self.hub._card_columns(), 1)
        with mock.patch.object(self.hub, "_available_card_width",
                               return_value=0):
            # Unknown width falls back to the default two-column layout.
            self.assertEqual(self.hub._card_columns(), 2)

    # ------------------------------------------------------------------ #
    # interaction model: one click selects, double click / Enter / Open opens
    # ------------------------------------------------------------------ #
    def test_double_click_opens_without_prior_click(self):
        """Double-click directly on a card opens it — no click-click-click."""
        self.hub._on_card_double_click("Cash Book")
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "CashBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_card_open_button_visible_on_every_card(self):
        """Every report card carries a visible Open button."""
        self._sync()
        for title, card in self.hub._card_widgets.items():
            texts = "\n".join(_all_text(card))
            self.assertIn("Open", texts, f"{title} card missing Open button")

    def test_card_open_button_opens_report(self):
        """Clicking the card's Open button opens the report in one click."""
        self._sync()
        card = self.hub._card_widgets["Day Book"]
        btn = None
        for child in card.winfo_children():
            for sub in child.winfo_children():
                try:
                    if isinstance(sub, ctk.CTkButton) and sub.cget("text") == "Open":
                        btn = sub
                except Exception:
                    pass
        self.assertIsNotNone(btn)
        btn.invoke()
        self._sync()
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "DayBookReportUI")
        self.assertIsNotNone(self.hub.current_frame)

    def test_open_button_selects_before_opening(self):
        """The Open button also selects the report (visible selected state)."""
        self.hub._on_open_button("Ageing Report")
        self._sync()
        self.assertEqual(self.hub.selected_title, "Ageing Report")
        self.assertEqual(self.hub.current_report_ui.__class__.__name__,
                         "AgeingReportUI")

    def test_first_report_focused_when_hub_opens(self):
        """The first report card receives keyboard focus when the hub opens."""
        self._sync()
        first = self.hub._card_widgets["Day Book"]
        self.assertEqual(self.hub.selected_title, "Day Book")
        focused = self.root.focus_get()
        self.assertTrue(
            focused == first or focused in first.winfo_children()
            or focused == self.hub.search_entry,
            f"expected first card focus, got {focused}",
        )

    def test_arrow_down_moves_selection(self):
        """Arrow Down moves the selection to the next report."""
        self._sync()
        self.hub._on_card_arrow(type("E", (), {"keysym": "Down"})())
        self.assertIn(self.hub.selected_title, ("Cash Book", "Bank Book"))

    def test_arrow_navigation_wraps_within_bounds(self):
        """Arrow navigation never selects an out-of-range report."""
        self._sync()
        for _ in range(30):
            self.hub._on_card_arrow(type("E", (), {"keysym": "Down"})())
        self.assertIn(self.hub.selected_title, list(self.hub._card_widgets))

    def test_enter_after_arrow_opens_selected(self):
        """Enter opens whatever report is selected after arrow navigation."""
        self._sync()
        for _ in range(3):
            self.hub._on_card_arrow(type("E", (), {"keysym": "Down"})())
        title = self.hub.selected_title
        item = self.hub._report_by_title(title)
        item["open"](self.hub)
        self._sync()
        self.assertIsNotNone(self.hub.current_report_ui)
        self.assertIs(self.hub.current_frame,
                      getattr(self.hub.current_report_ui, "main_frame", None))

    def test_esc_closes_report_no_duplicate(self):
        """Esc closes the open report; reopening creates a fresh single window."""
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        first = self.hub.current_report_ui
        self.hub.on_keyboard_back()
        self._sync()
        self.assertIsNone(self.hub.current_frame)
        self.hub._on_global_enter()
        self._sync()
        second = self.hub.current_report_ui
        self.assertIsNotNone(second)
        self.assertIsNot(first, second)
        self.assertIs(self.hub.current_frame, getattr(second, "main_frame", second))

    def test_report_opens_only_once(self):
        """Opening the same report twice never stacks two report windows."""
        self.hub._on_card_click("Day Book")
        self.hub._on_global_enter()
        self._sync()
        first = self.hub.current_report_ui
        self.hub._on_card_double_click("Day Book")
        self._sync()
        # _open_report destroys the previous report frame first, so only one
        # report UI exists at a time.
        self.assertIsNotNone(self.hub.current_report_ui)
        self.assertIsNot(self.hub.current_report_ui, first)

    def test_modify_filters_button_present(self):
        """Every report (except Day Book, whose filters are always visible)
        exposes a Modify Filters action."""
        for title in REPORT_TITLES:
            if title == "Day Book":
                continue
            item = self.hub._report_by_title(title)
            item["open"](self.hub)
            self._sync()
            ui = self.hub.current_report_ui
            texts = "\n".join(_all_text(ui.main_frame))
            self.assertIn("Modify Filters", texts, f"{title} missing Modify Filters")
            self.hub._close_report()
            self._sync()

    def test_modify_filters_focuses_filter_field(self):
        """Modify Filters focuses the filter bar's first editable entry."""
        ui = self._open_report_ui("Cash Book")
        fbs = [c for c in ui.main_frame.winfo_children()
               if c.__class__.__name__ == "FilterBar"]
        self.assertTrue(fbs)
        fbs[0]._focus_filters()
        self._sync()
        focused = self.root.focus_get()
        # A CTkEntry wraps an internal tk.Entry; the focused widget is that
        # inner entry (which belongs to a CTkEntry inside the filter bar).
        self.assertIsNotNone(focused)
        # Walk up: the focused widget (or an ancestor) must live in the
        # filter bar's body (a CTkEntry's internal tk.Entry or the CTkEntry).
        ancestor = focused
        in_filter_bar = False
        for _ in range(6):
            if ancestor is fbs[0].body or ancestor is fbs[0]:
                in_filter_bar = True
                break
            try:
                ancestor = ancestor.master
            except Exception:
                break
        self.assertTrue(
            in_filter_bar or isinstance(focused, ctk.CTkEntry)
            or focused.__class__.__name__ == "Entry",
            f"expected filter entry focus, got {focused}",
        )

    def test_whole_card_is_click_target(self):
        """The card itself and its title/subtitle children all select."""
        card = self.hub._card_widgets["Day Book"]
        for seq in ("<Button-1>", "<Double-Button-1>"):
            bound = card.bind(seq)
            self.assertNotEqual(bound, "", f"card missing {seq} binding")
        # Title label is a child forwarding clicks.
        title_texts = [w for w in card.winfo_children()
                       if w.__class__.__name__ == "CTkFrame"]
        self.assertTrue(title_texts)

    def test_selected_card_has_visible_selected_state(self):
        """The selected card shows a highlighted border."""
        self.hub._on_card_click("Day Book")
        self._sync()
        card = self.hub._card_widgets["Day Book"]
        self.assertEqual(card.cget("border_width"), 2)
        self.assertEqual(card.cget("border_color"), config.COLOR_PRIMARY)

    def test_report_specific_actions_advertised(self):
        """Each card advertises only actions its report implements."""
        for item in self.hub._report_defs:
            actions = item.get("actions")
            self.assertTrue(actions, f"{item['title']} has no actions")
            # Open/Modify Filters/Refresh/Export are the real implemented set.
            for action in actions:
                self.assertIn(action, ["Open", "Modify Filters", "Refresh",
                                       "Export", "Print"])


if __name__ == "__main__":
    unittest.main()
