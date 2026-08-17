"""
Expenzo — Top bar component.

Premium header: company selector, financial-year chip, global search (opens
the command palette), notifications bell with a panel, profile avatar, and a
theme toggle.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

import customtkinter as ctk

import config
from ui.components.icons import ACTION_ICONS


class TopBar(ctk.CTkFrame):
    def __init__(self, master, company_name: str, fy_text: str = "",
                 on_company_change: Optional[Callable[[int], None]] = None,
                 on_search: Optional[Callable[[], None]] = None,
                 on_toggle_theme: Optional[Callable[[], None]] = None,
                 companies: Optional[List[Dict]] = None,
                 on_open_company: Optional[Callable[[], None]] = None,
                 **kwargs):
        super().__init__(master, corner_radius=0,
                         fg_color=config.COLOR_BG_SECONDARY, **kwargs)
        self._on_company_change = on_company_change
        self._on_search = on_search
        self._companies = companies or []

        # App chip (left).
        self.chip = ctk.CTkLabel(
            self, text="Expenzo Accounting", font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=config.COLOR_BG_TERTIARY, corner_radius=config.CHIP_RADIUS,
            text_color=config.COLOR_TEXT_PRIMARY, padx=10, pady=3,
        )
        self.chip.pack(side="left", padx=(20, 12))

        # Center spacer.
        ctk.CTkFrame(self, fg_color="transparent").pack(side="left", fill="x", expand=True)

        # FY chip.
        if fy_text:
            self.fy_chip = ctk.CTkLabel(
                self, text=f"FY  {fy_text}", font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=config.COLOR_BG_TERTIARY, corner_radius=config.CHIP_RADIUS,
                text_color=config.COLOR_TEXT_SECONDARY, padx=10, pady=3,
            )
            self.fy_chip.pack(side="right", padx=(0, 12))

        # Company selector.
        company_names = [c.get("name", "?") for c in self._companies]
        self.company_var = ctk.StringVar(value=company_name)
        self.company_combo = ctk.CTkComboBox(
            self, values=company_names, variable=self.company_var, width=220,
            height=32, state="readonly", command=self._on_company_pick,
        )
        self.company_combo.pack(side="right", padx=(0, 12))

        # Notifications bell.
        self.bell = ctk.CTkButton(
            self, text=ACTION_ICONS.get("bell", "🔔"), width=36, height=32,
            corner_radius=8, fg_color="transparent", hover_color=config.COLOR_BG_TERTIARY,
            text_color=config.COLOR_TEXT_SECONDARY, command=self._toggle_notifications,
        )
        self.bell.pack(side="right", padx=(0, 8))
        self._notif_open = False

        # Profile avatar.
        avatar_text = self._initials(company_name)
        self.profile = ctk.CTkLabel(
            self, text=avatar_text, width=32, height=32, corner_radius=16,
            fg_color=config.COLOR_PRIMARY, text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.profile.pack(side="right", padx=(0, 8))

        # Theme toggle.
        self.theme_toggle = ctk.CTkButton(
            self, text=ACTION_ICONS.get("theme", "◐"), width=36, height=32,
            corner_radius=8, fg_color="transparent", hover_color=config.COLOR_BG_TERTIARY,
            text_color=config.COLOR_TEXT_SECONDARY, command=on_toggle_theme,
        )
        self.theme_toggle.pack(side="right", padx=(0, 12))

        # Global search.
        if on_search is not None:
            self.search_btn = ctk.CTkButton(
                self, text=f"  {ACTION_ICONS.get('search', '⌕')}  Search…   Ctrl K",
                width=220, height=32, corner_radius=8,
                fg_color=config.COLOR_BG_TERTIARY, hover_color=config.COLOR_HOVER_SURFACE,
                text_color=config.COLOR_TEXT_SECONDARY, command=on_search,
            )
            self.search_btn.pack(side="right", padx=(0, 12))

    @staticmethod
    def _initials(name: str) -> str:
        parts = [p for p in str(name).split() if p]
        if not parts:
            return "?"
        return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

    def _on_company_pick(self, selected: str) -> None:
        for company in self._companies:
            if company.get("name") == selected and self._on_company_change is not None:
                self._on_company_change(company.get("id"))
                return

    def _toggle_notifications(self) -> None:
        self._notif_open = not self._notif_open
        # A real notification panel is wired by the shell; this is a stub
        # that keeps the bell behavior inert.
        self.bell.configure(fg_color=config.COLOR_BG_TERTIARY if self._notif_open
                            else "transparent")

    def set_company(self, name: str, companies: Optional[List[Dict]] = None) -> None:
        if companies is not None:
            self._companies = companies
            self.company_combo.configure(
                values=[c.get("name", "?") for c in companies])
        self.company_var.set(name)
        self.profile.configure(text=self._initials(name))
