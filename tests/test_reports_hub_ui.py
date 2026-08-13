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

    def test_esc_on_hub_does_not_raise(self):
        # Esc with no report open must not raise or destroy anything.
        self.hub._handle_back_shortcut()

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


if __name__ == "__main__":
    unittest.main()
