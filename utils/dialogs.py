"""
Expenzo dialog helpers
Consistent confirmation, error, and information dialogs across the app.
"""
from __future__ import annotations

from tkinter import messagebox

import config


def info(title: str, message: str, parent=None) -> None:
    messagebox.showinfo(title, message, parent=parent)


def error(title: str, message: str, parent=None) -> None:
    messagebox.showerror(title, message, parent=parent)


def warn(title: str, message: str, parent=None) -> None:
    messagebox.showwarning(title, message, parent=parent)


def confirm(title: str, message: str, parent=None) -> bool:
    return messagebox.askyesno(title, message, parent=parent)


def confirm_destructive(title: str, item_type: str, item_name: str, parent=None) -> bool:
    """Confirm an irreversible delete with the item's name called out."""
    return confirm(
        title,
        f"Are you sure you want to delete this {item_type}?\n\n"
        f"\"{item_name}\"\n\n"
        "This action cannot be undone.",
        parent=parent,
    )


def format_amount(value: float) -> str:
    return f"{config.CURRENCY_SYMBOL}{float(value or 0.0):,.2f}"
