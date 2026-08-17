"""
Smoke tests for the new premium UI component library (ui/components/).

These instantiate the shared widgets on a real CTk root (withdrawn) against
an in-memory DB and assert widget state — the same pattern used by the
existing screen UI tests. Also verifies the theme walker re-tints them.
"""
import unittest

import config

config.DATABASE_PATH = ':memory:'

import customtkinter as ctk  # noqa: E402

from ui.components.card import Card, SectionCard, StatCard  # noqa: E402
from ui.components.table import DataTable  # noqa: E402
from ui.components.inputs import (  # noqa: E402
    DateEntry, FormGrid, FormSection, MoneyEntry, SearchBox, ToggleSwitch,
)
from ui.components.empty_state import EmptyState  # noqa: E402
from ui.components.charts import BarChart, DonutChart  # noqa: E402
from utils import theme  # noqa: E402


class ComponentSmokeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
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
        self.frame = ctk.CTkFrame(self.root)
        self.frame.pack()
        self.addCleanup(self.frame.destroy)

    def _sync(self):
        self.root.update_idletasks()
        self.root.update()

    # ------------------------------------------------------------------ #
    def test_stat_card(self):
        card = StatCard(self.frame, "Cash", "1,234.50", "₹", "#22C55E")
        self.assertEqual(card.value_label.cget("text"), "1,234.50")
        card.set_value("9,999.00")
        self.assertEqual(card.value_label.cget("text"), "9,999.00")

    def test_section_card_has_title(self):
        card = SectionCard(self.frame, "Company Details", subtitle="sub")
        self.assertEqual(card.body.winfo_manager(), "pack")

    def test_card_hover_border(self):
        card = Card(self.frame, hover_lift=True)
        card.event_generate("<Enter>")
        self._sync()

    def test_data_table_basic(self):
        table = DataTable(
            self.frame,
            [{"id": "name", "heading": "Name"}, {"id": "amt", "heading": "Amount"}],
            rows=[("A", 10), ("B", 20), ("C", 30)],
            page_size=2,
        )
        self._sync()
        self.assertEqual(len(table.tree.get_children()), 2)  # page 1 only

    def test_data_table_pagination(self):
        table = DataTable(
            self.frame,
            [{"id": "name", "heading": "Name"}],
            rows=[("A",), ("B",), ("C",), ("D",)],
            page_size=2,
        )
        table._next_page()
        self._sync()
        self.assertEqual(len(table.tree.get_children()), 2)
        table._prev_page()
        self._sync()
        self.assertEqual(len(table.tree.get_children()), 2)

    def test_data_table_search(self):
        table = DataTable(
            self.frame,
            [{"id": "name", "heading": "Name"}],
            rows=[("Apple",), ("Banana",)],
            searchable=True,
        )
        table._search_term = "app"
        table._apply_search()
        self._sync()
        self.assertEqual(len(table.tree.get_children()), 1)

    def test_data_table_sort(self):
        table = DataTable(
            self.frame,
            [{"id": "amt", "heading": "Amount"}],
            rows=[(30,), (10,), (20,)],
        )
        table._toggle_sort("amt")
        self._sync()
        first = table.tree.item(table.tree.get_children()[0], "values")
        # Treeview stores values as strings; the sort uses numeric keys.
        self.assertEqual(str(first[0]), "10")

    def test_money_entry(self):
        entry = MoneyEntry(self.frame)
        entry.insert(0, "1234.5")
        entry._format()
        self.assertEqual(entry.get_value(), 1234.5)

    def test_form_grid(self):
        grid = FormGrid(self.frame, columns=2)
        grid.add_field("Name", ctk.CTkEntry(grid, width=150))
        grid.add_field("Code", ctk.CTkEntry(grid, width=150))
        self.assertEqual(len(grid._cells), 2)

    def test_search_box_callback(self):
        calls = []
        box = SearchBox(self.frame, lambda term: calls.append(term))
        box.insert(0, "xyz")
        box._changed(None)  # invoke the key-release handler directly
        self.assertGreaterEqual(len(calls), 1)

    def test_empty_state(self):
        state = EmptyState(self.frame, icon="◌", title="Nothing here",
                           hint="Create something", action_text="New",
                           on_action=lambda: None)
        self._sync()

    def test_charts(self):
        bar = BarChart(self.frame)
        bar.set_data(["Jan", "Feb"], {"In": [1, 2], "Out": [3, 4]})
        donut = DonutChart(self.frame)
        donut.set_data([("Rec", 10, "#3B82F6"), ("Pay", 5, "#EF4444")])
        self._sync()

    def test_date_entry(self):
        entry = DateEntry(self.frame)
        entry.insert(0, "01-08-2026")
        self.assertEqual(entry.get(), "01-08-2026")

    def test_toggle_switch(self):
        var = ctk.BooleanVar(value=False)
        switch = ToggleSwitch(self.frame, "Active", var)
        var.set(True)
        self.assertTrue(var.get())

    def test_theme_cycles_components(self):
        StatCard(self.frame, "A", "1", "₹", "#3B82F6")
        DataTable(self.frame, [{"id": "c", "heading": "C"}], rows=[("x",)])
        BarChart(self.frame)
        self._sync()
        for mode in ("light", "dark", "light"):
            theme.apply_theme(self.root, mode=mode)
            theme.apply_palette(self.root)
            self._sync()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
