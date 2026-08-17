"""
Expenzo — Command palette.

Ctrl+K opens a searchable command/navigation palette styled like a premium
IDE. It filters a registry of (title, subtitle, action) commands and runs the
selected action on Enter.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

import config


class CommandPalette(ctk.CTkToplevel):
    def __init__(self, parent, commands: List[Tuple[str, str, Callable[[], None]]],
                 title: str = "Commands"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self._commands = commands
        self._selected = 0
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        self.configure(fg_color=config.COLOR_BG_SECONDARY)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=12)

        self.search = ctk.CTkEntry(
            body, placeholder_text="Type a command…", height=36,
            corner_radius=config.INPUT_CORNER_RADIUS,
        )
        self.search.pack(fill="x")
        self.search.bind("<KeyRelease>", self._on_key)
        self.search.bind("<Down>", self._down)
        self.search.bind("<Up>", self._up)
        self.search.bind("<Return>", self._enter)
        self.search.bind("<Escape>", lambda _e: self.destroy())

        self.listbox = ctk.CTkScrollableFrame(body, height=280,
                                              fg_color="transparent")
        self.listbox.pack(fill="both", expand=True, pady=(8, 0))
        self._render()

        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(10, self._center)
        self.after(20, self.search.focus_set)

    def _center(self) -> None:
        try:
            self.update_idletasks()
            w = 460
            h = min(self.winfo_reqheight(), 420)
            x = self.winfo_screenwidth() // 2 - w // 2
            y = self.winfo_screenheight() // 3 - h // 2
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _filtered(self) -> List[Tuple[str, str, Callable[[], None]]]:
        term = self.search.get().lower()
        if not term:
            return self._commands
        return [c for c in self._commands if term in c[0].lower() or term in c[1].lower()]

    def _render(self) -> None:
        for child in self.listbox.winfo_children():
            child.destroy()
        items = self._filtered()
        if not items:
            ctk.CTkLabel(self.listbox, text="No matching commands",
                         text_color=config.COLOR_TEXT_MUTED).pack(pady=20)
            return
        self._selected = min(self._selected, len(items) - 1)
        for i, (title, sub, _action) in enumerate(items):
            row = ctk.CTkFrame(self.listbox, fg_color="transparent")
            row.pack(fill="x", pady=1)
            selected = i == self._selected
            label = ctk.CTkLabel(
                row, text=f"  {title}", anchor="w", height=30,
                font=ctk.CTkFont(size=13, weight="bold" if selected else "normal"),
                fg_color=config.COLOR_PRIMARY if selected else "transparent",
                text_color="#FFFFFF" if selected else config.COLOR_TEXT_PRIMARY,
                corner_radius=6,
            )
            label.pack(fill="x", side="left")
            if sub:
                ctk.CTkLabel(
                    row, text=sub, anchor="e",
                    font=ctk.CTkFont(size=11),
                    text_color="#FFFFFF" if selected else config.COLOR_TEXT_MUTED,
                ).pack(side="right", padx=(0, 8))

    def _on_key(self, _event) -> None:
        self._selected = 0
        self._render()

    def _down(self, _event):
        self._selected = min(self._selected + 1, len(self._filtered()) - 1)
        self._render()
        return "break"

    def _up(self, _event):
        self._selected = max(self._selected - 1, 0)
        self._render()
        return "break"

    def _enter(self, _event):
        items = self._filtered()
        if items and 0 <= self._selected < len(items):
            action = items[self._selected][2]
            self.destroy()
            action()
        return "break"
