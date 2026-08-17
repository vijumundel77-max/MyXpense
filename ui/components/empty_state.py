"""
Expenzo — Empty state component.

A premium "nothing here yet" panel: icon, title, hint, and optional action
button. Used across list screens and tables.
"""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

import config


class EmptyState(ctk.CTkFrame):
    def __init__(self, master, icon: str = "◌", title: str = "No data",
                 hint: str = "", action_text: Optional[str] = None,
                 on_action: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(master, corner_radius=config.CARD_CORNER_RADIUS,
                         fg_color="transparent", **kwargs)

        ctk.CTkLabel(
            self, text=icon, font=ctk.CTkFont(size=36),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(pady=(config.SPACING_XXL, config.SPACING_SM))
        ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=config.FONT_SUBTITLE_SIZE, weight="bold"),
            text_color=config.COLOR_TEXT_PRIMARY,
        ).pack()
        if hint:
            ctk.CTkLabel(
                self, text=hint, font=ctk.CTkFont(size=config.FONT_SMALL_SIZE),
                text_color=config.COLOR_TEXT_SECONDARY,
            ).pack(pady=(config.SPACING_XS, 0))
        if action_text and on_action is not None:
            ctk.CTkButton(
                self, text=action_text, height=32, corner_radius=config.BUTTON_CORNER_RADIUS,
                fg_color=config.COLOR_PRIMARY, hover_color=config.COLOR_PRIMARY_HOVER,
                text_color="#FFFFFF", command=on_action,
            ).pack(pady=(config.SPACING_LG, config.SPACING_XXL))
