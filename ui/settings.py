"""
Expenzo — Settings
Theme, company selection, and application settings.
"""
from __future__ import annotations

import customtkinter as ctk

import config
from database.database import db


class SettingsFrame(ctk.CTkFrame):
    """Settings screen: theme toggle, active company, exports directory."""

    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ctk.CTkLabel(
            self,
            text="Settings",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w", pady=(0, config.SPACING_LG))

        self._build_company_card()
        self._build_theme_card()
        self._build_general_card()

        from utils.keyboard import add_shortcut_bar
        add_shortcut_bar(self, [("F5", "Refresh companies"), ("Esc", "Back")])

    def _card(self, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self,
            fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        card.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))
        return card

    def _build_company_card(self) -> None:
        card = self._card("Company")
        companies = db.fetch_all("SELECT id, name FROM companies ORDER BY name")
        if not companies:
            ctk.CTkLabel(card, text="No companies yet.", text_color=config.COLOR_TEXT_MUTED).pack(
                anchor="w", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
            return

        self.company_id_map = {row["name"]: row["id"] for row in companies}
        values = list(self.company_id_map.keys())
        current_id = self._current_company_id()
        current_name = next(
            (name for name, cid in self.company_id_map.items() if cid == current_id),
            values[0] if values else "",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))

        ctk.CTkLabel(row, text="Active Company", width=110).pack(side="left")
        self.company_var = ctk.StringVar(value=current_name)
        self.company_combo = ctk.CTkComboBox(
            row,
            values=values,
            variable=self.company_var,
            width=280,
            state="readonly",
            command=self._on_company_change,
        )
        self.company_combo.pack(side="left")
        ctk.CTkLabel(
            row,
            text="Selecting a company switches the whole application.",
            font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_LG, 0))

    def _current_company_id(self) -> int:
        try:
            app = self.winfo_toplevel()
            return int(getattr(app, "current_company_id", 1))
        except Exception:
            return 1

    def _on_company_change(self, value: str) -> None:
        company_id = self.company_id_map.get(value)
        if not company_id:
            return
        app = self.winfo_toplevel()
        if hasattr(app, "switch_company"):
            app.switch_company(company_id)

    def on_keyboard_refresh(self) -> None:
        """F5: refresh the company list from the database."""
        self.company_var.set(self.company_var.get())  # no-op guard
        try:
            self._refresh_company_card()
        except Exception:
            pass

    def _refresh_company_card(self) -> None:
        companies = db.fetch_all("SELECT id, name FROM companies ORDER BY name")
        if not companies:
            return
        self.company_id_map = {row["name"]: row["id"] for row in companies}
        self.company_combo.configure(values=list(self.company_id_map.keys()))

    def on_keyboard_back(self) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, "on_keyboard_back"):
            app.on_keyboard_back()

    def _build_theme_card(self) -> None:
        card = self._card("Appearance")
        ctk.CTkLabel(card, text="Theme:", width=90).pack(side="left", padx=(config.SPACING_LG, 0))
        self.theme_var = ctk.StringVar(value="Dark" if ctk.get_appearance_mode() == "Dark" else "Light")
        ctk.CTkComboBox(
            card,
            values=["Dark", "Light"],
            variable=self.theme_var,
            width=160,
            command=self._on_theme_change,
        ).pack(side="left", pady=config.SPACING_LG)

    def _on_theme_change(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())
        app = self.winfo_toplevel()
        if hasattr(app, "_toggle_theme"):
            # Reflect the toggle button state without toggling.
            from utils import theme as theme_utils
            theme_utils.apply_theme(app, mode=value.lower())
            if hasattr(app, "_apply_chrome"):
                app._apply_chrome()
            if hasattr(app, "_refresh_theme_toggle"):
                app._refresh_theme_toggle(value.lower())

    def _build_general_card(self) -> None:
        card = self._card("General")
        ctk.CTkLabel(
            card,
            text=f"Exports directory:  {config.EXPORTS_DIR}",
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
