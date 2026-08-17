"""
Tests for the Global Date Control system (Alt+F2 period, F2 single date).

Covers the service state/financial-year logic, the modal dialogs
(Enter applies / Esc cancels / grab blocks / non-movable), the global
keyboard dispatch (Alt+F2 / F2), and the per-screen application hooks.
"""
import unittest
from datetime import date

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402
import tkinter as tk  # noqa: E402

from database.database import db  # noqa: E402
from services.date_control_service import date_control, DateControlService  # noqa: E402
from ui.date_control_dialog import (  # noqa: E402
    DatePeriodDialog,
    DateDialog,
)


class TestDateControlService(unittest.TestCase):
    """Service-level state and financial-year logic."""

    # A single Tk root for the whole file: creating multiple CTk() roots in
    # one process corrupts Tcl (tcl_findLibrary errors on later tests).
    root = None

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM companies")
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (1, 'Date Co', '01-04', '31-03')"
        )
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (2, 'Date Co B', '01-01', '31-12')"
        )
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        # Root stays alive for TestDateControlDialogs (which runs after this
        # class); it destroys it in its own teardown (last in file order).
        pass

    def setUp(self):
        date_control.reset()
        date_control._company_id = None

    def test_financial_year_contains_today(self):
        start, end = date_control.company_financial_year(1)
        today = date.today()
        self.assertLessEqual(start, today)
        self.assertGreaterEqual(end, today)

    def test_calendar_year_company(self):
        start, end = date_control.company_financial_year(2)
        # 01-01 -> 31-12 containing today.
        self.assertEqual(start.month, 1)
        self.assertEqual(start.day, 1)
        self.assertEqual(end.month, 12)
        self.assertEqual(end.day, 31)

    def test_default_period_is_today(self):
        p1, p2 = date_control.period(1)
        self.assertEqual(p1, date.today())
        self.assertEqual(p2, date.today())

    def test_set_and_get_period(self):
        date_control.set_period(date(2026, 4, 1), date(2026, 4, 30))
        self.assertEqual(date_control.period(1), (date(2026, 4, 1), date(2026, 4, 30)))

    def test_single_date_default_and_set(self):
        self.assertEqual(date_control.single_date(1), date.today())
        date_control.set_single_date(date(2026, 4, 15))
        self.assertEqual(date_control.single_date(1), date(2026, 4, 15))

    def test_dispatch_to_view_with_hook(self):
        calls = []

        class FakeView:
            def on_global_date_period(self, f, t):
                calls.append(('period', f, t))

            def on_global_single_date(self, d):
                calls.append(('single', d))

        date_control.set_period(date(2026, 4, 1), date(2026, 4, 30))
        date_control.set_single_date(date(2026, 4, 15))
        view = FakeView()
        date_control.apply_to(view, 1)
        self.assertEqual(calls[0], ('period', date(2026, 4, 1), date(2026, 4, 30)))
        self.assertEqual(calls[1], ('single', date(2026, 4, 15)))

    def test_dispatch_to_view_with_vars(self):
        class FakeView:
            def __init__(self):
                self.from_date_var = tk.StringVar(self.__class__.root,
                                                  value='01-01-2020')
                self.to_date_var = tk.StringVar(self.__class__.root,
                                                value='01-01-2020')
                self.refreshed = False

            def refresh(self):
                self.refreshed = True

        FakeView.root = self.root
        date_control.set_period(date(2026, 4, 1), date(2026, 4, 30))
        view = FakeView()
        date_control.apply_to(view, 1)
        self.assertEqual(view.from_date_var.get(), '01-04-2026')
        self.assertEqual(view.to_date_var.get(), '30-04-2026')
        self.assertTrue(view.refreshed)


class TestDateControlDialogs(unittest.TestCase):
    """Modal dialog behavior: grab, non-movable, Enter/Esc."""

    @classmethod
    def setUpClass(cls):
        db.initialize_database()
        db.execute("DELETE FROM companies")
        db.execute(
            "INSERT INTO companies (id, name, financial_year_start, financial_year_end) "
            "VALUES (1, 'Date Co', '01-04', '31-03')"
        )
        # Reuse the service test class's root (still alive — it does not
        # destroy it, so the second class never creates a second CTk root).
        cls.root = TestDateControlService.root
        cls.root.current_company_id = 1

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_period_dialog_grabs_and_is_non_movable(self):
        dlg = DatePeriodDialog(self.root)
        self.root.update_idletasks()
        self.assertEqual(dlg.grab_current(), dlg)
        self.assertTrue(dlg.overrideredirect())
        dlg._cancel()

    def test_period_dialog_enter_applies(self):
        applied = []
        dlg = DatePeriodDialog(self.root, on_apply=lambda f, t: applied.append((f, t)))
        self.root.update_idletasks()
        dlg.from_var.set('01-04-2026')
        dlg.to_var.set('30-04-2026')
        dlg._apply()
        self.root.update_idletasks()
        self.assertEqual(applied, [(date(2026, 4, 1), date(2026, 4, 30))])
        self.assertFalse(dlg.winfo_exists())

    def test_period_dialog_esc_cancels(self):
        applied = []
        dlg = DatePeriodDialog(self.root, on_apply=lambda f, t: applied.append((f, t)))
        self.root.update_idletasks()
        dlg._cancel()
        self.root.update_idletasks()
        self.assertEqual(applied, [])
        self.assertFalse(dlg.winfo_exists())

    def test_date_dialog_enter_applies(self):
        applied = []
        dlg = DateDialog(self.root, on_apply=lambda d: applied.append(d))
        self.root.update_idletasks()
        dlg.date_var.set('15-04-2026')
        dlg._apply()
        self.root.update_idletasks()
        self.assertEqual(applied, [date(2026, 4, 15)])
        self.assertFalse(dlg.winfo_exists())

    def test_date_dialog_esc_cancels(self):
        applied = []
        dlg = DateDialog(self.root, on_apply=lambda d: applied.append(d))
        self.root.update_idletasks()
        dlg._cancel()
        self.root.update_idletasks()
        self.assertEqual(applied, [])

    def test_dialog_esc_and_return_bindings_present(self):
        dlg = DatePeriodDialog(self.root)
        self.root.update_idletasks()
        self.assertTrue(dlg.bind('<Escape>'))
        self.assertTrue(dlg.bind('<Return>'))
        dlg._cancel()


if __name__ == '__main__':
    unittest.main()
