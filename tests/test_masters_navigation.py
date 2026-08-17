"""
Regression tests for the Masters Hub navigation wiring.

These exercise the real MastersFrame logic against a virtual (stubbed)
tkinter so they run headless: cards must be hidden while a master screen
is open, restored on Esc, never duplicated across repeated Open/Esc
cycles, and every screen must receive the selected company explicitly
(no silent fallback to company 1).
"""
import unittest

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.company_service import CompanyService  # noqa: E402
from ui.masters import MastersFrame  # noqa: E402

try:
    import tests.test_masters_navigation_stubs as _stubs  # noqa: F401
except ImportError:
    # Real tkinter available (Windows): nothing extra needed.
    pass


def _is_packed(widget) -> bool:
    """True when a widget is currently managed by the packer."""
    try:
        return widget.winfo_manager() == "pack"
    except Exception:
        return False


def _find_open_buttons(widget):
    """Return every Open button under a widget (depth-first)."""
    buttons = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton):
            try:
                if child.cget("text") == "Open":
                    buttons.append(child)
            except Exception:
                pass
        buttons.extend(_find_open_buttons(child))
    return buttons


class MastersNavigationTestCase(unittest.TestCase):
    """Hub show/hide, Esc ownership, company context, no duplicates."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute(
            """
            INSERT INTO companies (id, name, financial_year_start, financial_year_end)
            VALUES (?, ?, ?, ?)
            """,
            (1, "Masters Nav Co", "01-04", "31-03"),
        )
        db.execute(
            """
            INSERT INTO companies (id, name, financial_year_start, financial_year_end)
            VALUES (?, ?, ?, ?)
            """,
            (2, "Masters Nav Co B", "01-04", "31-03"),
        )
        from services.group_service import group_service
        group_service.seed_default_groups(1)
        group_service.seed_default_groups(2)
        # A single shared Tk root for the whole class: creating a fresh root
        # per test exhausts Tk resources on Windows (tcl_findLibrary errors).
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        # Reuse the shared root; build a fresh hub each test.
        self.hub = MastersFrame(
            self.root,
            db=db,
            company_id=2,
            company_service=CompanyService(db),
            on_company_switched=None,
        )

    def tearDown(self):
        try:
            self.hub.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # cards visibility
    # ------------------------------------------------------------------ #
    def test_cards_visible_on_hub(self):
        self.assertTrue(_is_packed(self.hub.cards_frame))
        self.assertEqual(len(_find_open_buttons(self.hub)), 4)

    def test_cards_hidden_while_screen_open_and_restored_on_esc(self):
        for label, opener in [
            ("Company", self.hub._open_company),
            ("Groups", self.hub._open_groups),
            ("Ledgers", self.hub._open_ledgers),
            ("Parties", self.hub._open_parties),
        ]:
            opener()
            self.assertIsNotNone(self.hub.current_ui, f"{label}: screen did not open")
            self.assertFalse(
                _is_packed(self.hub.cards_frame),
                f"{label}: cards still visible while screen open",
            )
            self.assertTrue(_is_packed(self.hub.current_frame))
            self.hub.on_keyboard_back()
            self.assertIsNone(self.hub.current_ui, f"{label}: Esc did not close screen")
            self.assertTrue(
                _is_packed(self.hub.cards_frame),
                f"{label}: cards not restored after Esc",
            )

    def test_no_duplicate_cards_after_repeated_open_esc(self):
        for _ in range(5):
            self.hub._open_groups()
            self.assertFalse(_is_packed(self.hub.cards_frame))
            self.hub.on_keyboard_back()
            self.assertTrue(_is_packed(self.hub.cards_frame))
            self.assertEqual(
                len(_find_open_buttons(self.hub)), 4,
                "duplicate Open buttons after repeated open/Esc",
            )

    # ------------------------------------------------------------------ #
    # correct screen object per button
    # ------------------------------------------------------------------ #
    def test_each_button_opens_correct_screen(self):
        expectations = {
            "Company": "CompanyManagementUI",
            "Groups": "GroupMasterUI",
            "Ledgers": "LedgerMasterUI",
            "Parties": "PartyMasterUI",
        }
        buttons = _find_open_buttons(self.hub)
        self.assertEqual(len(buttons), 4)
        # Order matches the card definitions: Company, Groups, Ledgers,
        # Parties.
        ordered = ["Company", "Groups", "Ledgers", "Parties"]
        for label, button in zip(ordered, buttons):
            button.invoke()
            self.assertIsNotNone(self.hub.current_ui)
            self.assertEqual(
                self.hub.current_ui.__class__.__name__,
                expectations[label],
                f"{label} opened wrong screen",
            )
            self.hub.on_keyboard_back()

    # ------------------------------------------------------------------ #
    # Esc ownership: child back routes to the hub, not the app
    # ------------------------------------------------------------------ #
    def test_child_screen_esc_owned_by_hub(self):
        self.hub._open_groups()
        child = self.hub.current_ui
        self.assertIsNotNone(getattr(child, "on_keyboard_back", None))
        # The hub reassigned the child's back handler to its own; calling it
        # must return to the hub (not jump to the top-level app).
        child.on_keyboard_back()
        self.assertIsNone(self.hub.current_ui)
        self.assertTrue(_is_packed(self.hub.cards_frame))

    def test_esc_does_not_exit(self):
        # Esc on the hub with no screen open must not raise or destroy.
        self.hub.on_keyboard_back()

    # ------------------------------------------------------------------ #
    # company context: no fallback to company 1
    # ------------------------------------------------------------------ #
    def test_company_id_passed_explicitly(self):
        for label, opener, attr in [
            ("Groups", self.hub._open_groups, "company_id"),
            ("Ledgers", self.hub._open_ledgers, "company_id"),
            ("Parties", self.hub._open_parties, "company_id"),
        ]:
            opener()
            ui = self.hub.current_ui
            self.assertEqual(
                getattr(ui, attr, None), 2,
                f"{label}: expected company_id=2, got {getattr(ui, attr, None)}",
            )
            self.hub.on_keyboard_back()

    def test_missing_company_id_fails_safely(self):
        self.hub.company_id = None
        for opener in (self.hub._open_groups, self.hub._open_ledgers,
                       self.hub._open_parties):
            with self.assertRaises(ValueError):
                opener()
            self.assertIsNone(self.hub.current_ui)

    # ------------------------------------------------------------------ #
    # theme toggle
    # ------------------------------------------------------------------ #
    def test_navigation_works_after_theme_toggle(self):
        ctk.set_appearance_mode("light")
        self.hub._open_groups()
        self.assertFalse(_is_packed(self.hub.cards_frame))
        self.hub.on_keyboard_back()
        self.assertTrue(_is_packed(self.hub.cards_frame))
        ctk.set_appearance_mode("dark")


if __name__ == "__main__":
    unittest.main()
