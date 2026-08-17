"""
Expenzo — Card components.

Premium rounded panels with soft borders, hover elevation, KPI stat cards,
and section cards. All colors come from config tokens so the theme walker
(theme.apply_palette) keeps them correct in both light and dark modes.
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

import config


class Card(ctk.CTkFrame):
    """A rounded, bordered surface panel."""

    def __init__(self, master, corner_radius: Optional[int] = None,
                 border_width: int = 1, hover_lift: bool = False,
                 command: Optional[Callable[[], None]] = None, **kwargs):
        kwargs.setdefault("corner_radius", corner_radius or config.CARD_CORNER_RADIUS)
        kwargs.setdefault("fg_color", config.COLOR_BG_SECONDARY)
        kwargs.setdefault("border_width", border_width)
        kwargs.setdefault("border_color", config.COLOR_CARD_BORDER)
        super().__init__(master, **kwargs)
        self._hover_lift = hover_lift
        self._command = command
        if command is not None or hover_lift:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _event) -> None:
        if self._hover_lift or self._command:
            try:
                self.configure(border_color=config.COLOR_PRIMARY,
                               border_width=2)
            except Exception:
                pass

    def _on_leave(self, _event) -> None:
        try:
            self.configure(border_color=config.COLOR_CARD_BORDER,
                           border_width=1)
        except Exception:
            pass

    def _on_click(self, _event) -> None:
        if self._command is not None:
            try:
                self._command()
            except Exception:
                pass


class SectionCard(Card):
    """A card with a title header and a body area."""

    def __init__(self, master, title: str, subtitle: str = "", **kwargs):
        super().__init__(master, **kwargs)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, 0))
        ctk.CTkLabel(
            header, text=title, anchor="w",
            font=ctk.CTkFont(size=config.FONT_SUBTITLE_SIZE, weight="bold"),
        ).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                header, text=subtitle, anchor="w",
                font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(side="left", padx=(config.SPACING_SM, 0))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True,
                       padx=config.SPACING_LG, pady=config.SPACING_LG)


class StatCard(Card):
    """A KPI card: icon chip, label, large value, optional delta hint.

    The value label is stored as ``self.value_label`` so screens can update
    the figure without rebuilding the card.
    """

    def __init__(self, master, label: str, value: str, icon: str,
                 accent: str, delta: str = "", **kwargs):
        super().__init__(master, border_width=1, **kwargs)
        self._label = label
        self._icon = icon
        self._accent = accent
        self._delta = delta

        self.configure(height=110)
        self.pack_propagate(False)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=config.SPACING_LG, pady=config.SPACING_MD)

        chip = ctk.CTkLabel(
            row, text=icon, width=38, height=38, corner_radius=10,
            fg_color=accent, text_color="#FFFFFF",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        chip.pack(side="left")

        text_col = ctk.CTkFrame(row, fg_color="transparent")
        text_col.pack(side="left", padx=(config.SPACING_MD, 0), fill="x", expand=True)
        ctk.CTkLabel(
            text_col, text=label, anchor="w",
            font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(fill="x")
        self.value_label = ctk.CTkLabel(
            text_col, text=value, anchor="w",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY,
        )
        self.value_label.pack(fill="x")

        if delta:
            ctk.CTkLabel(
                self, text=delta, anchor="w",
                font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
                text_color=config.COLOR_TEXT_MUTED,
            ).pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_MD))

    def set_value(self, text: str) -> None:
        self.value_label.configure(text=text)
