"""
Expenzo — Keyboard shortcuts & focus helpers

Installs application-wide key bindings on the Tk root and dispatches to the
currently active view using conventional method names:

    Ctrl+S  -> view.on_keyboard_save()    (falls back to _save_* / refresh)
    Ctrl+N  -> view.on_keyboard_new()     (falls back to _clear_form)
    Ctrl+F  -> view.on_keyboard_search()  (focus search_entry / search_var screen)
    F5      -> view.on_keyboard_refresh() (falls back to refresh_* / _generate_report)
    Delete  -> view.on_keyboard_delete()  (only when a table row is selected)

Popups (Toplevel windows) get their own Esc-to-close binding; Esc on the main
window never quits the application.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Optional


def _focus_search(view: Any) -> None:
    """Focus the current view's search entry if it exposes one."""
    if view is None:
        return
    entry = getattr(view, "search_entry", None)
    if entry is not None and hasattr(entry, "focus_set"):
        try:
            entry.focus_set()
            return
        except Exception:
            pass
    # Fall back: find the widget bound to search_var.
    search_var = getattr(view, "search_var", None)
    if search_var is not None:
        try:
            search_var.get()
        except Exception:
            return
        # Search for a CTkEntry/Entry whose textvariable is this var.
        def _walk(widget):
            for child in widget.winfo_children():
                try:
                    if str(getattr(child, "cget", lambda *_: None)("textvariable", None)) == str(search_var):
                        child.focus_set()
                        return True
                except Exception:
                    pass
                if _walk(child):
                    return True
            return False
        _walk(getattr(view, "master", None) or view)


def _find_refresh_method(view: Any) -> Optional[Callable[[], Any]]:
    if view is None:
        return None
    for name in ("on_keyboard_refresh", "refresh", "_refresh"):
        method = getattr(view, name, None)
        if callable(method):
            return method
    # Screens expose refresh_<entity> (refresh_companies, refresh_vouchers, ...)
    for attr in dir(view):
        if attr.startswith("refresh_") and callable(getattr(view, attr)):
            return getattr(view, attr)
    # Report screens expose a _generate_report that acts as refresh.
    method = getattr(view, "_generate_report", None)
    if callable(method):
        return method
    return None


def _find_save_method(view: Any) -> Optional[Callable[[], Any]]:
    if view is None:
        return None
    for name in ("on_keyboard_save", "_save_voucher", "_save_company", "_save_group",
                 "_save_ledger", "_save_party", "_save_bank_account", "_save_transaction",
                 "_save"):
        method = getattr(view, name, None)
        if callable(method):
            return method
    return None


def _find_new_method(view: Any) -> Optional[Callable[[], Any]]:
    if view is None:
        return None
    for name in ("on_keyboard_new", "_clear_form", "clear_form"):
        method = getattr(view, name, None)
        if callable(method):
            return method
    return None


def _find_delete_method(view: Any) -> Optional[Callable[[], Any]]:
    if view is None:
        return None
    for name in ("on_keyboard_delete", "_delete_voucher", "_delete_company", "_delete_group",
                 "_delete_ledger", "_delete_party", "_delete_bank_account", "_delete_transaction",
                 "_delete"):
        method = getattr(view, name, None)
        if callable(method):
            return method
    return None


def _list_tree(view: Any) -> Optional[Any]:
    """Return the view's primary Treeview, wherever it lives.

    Master screens (Company/Ledger/Group/Party) keep their list in a
    ``list`` sub-state with a ``tree``; simple screens expose ``tree`` or a
    named variant directly.
    """
    if view is None:
        return None
    list_state = getattr(view, "list", None)
    if list_state is not None and hasattr(list_state, "tree"):
        try:
            return list_state.tree
        except Exception:
            pass
    for attr in ("tree", "voucher_tree", "ledger_tree", "outstanding_tree",
                 "ageing_tree", "summary_tree", "overdue_tree"):
        tree = getattr(view, attr, None)
        if tree is not None:
            return tree
    return None


def _table_has_selection(view: Any) -> bool:
    """True when the view's primary Treeview has a selected row."""
    tree = _list_tree(view)
    if tree is not None and hasattr(tree, "selection"):
        try:
            return bool(tree.selection())
        except Exception:
            pass
    return False


def install_shortcuts(root: tk.Misc, get_view: Callable[[], Any]) -> None:
    """Bind global shortcuts on the app root.

    Args:
        root: the Tk/CTk root window.
        get_view: callable returning the currently active view (or None).
    """
    def _on_ctrl_s(_event=None) -> str:
        save = _find_save_method(get_view())
        if save:
            save()
        return "break"

    def _on_ctrl_a(_event=None) -> str:
        # Ctrl+A: save (Tally-style "A" for Accept).  Falls back to the same
        # save dispatch as Ctrl+S.
        save = _find_save_method(get_view())
        if save:
            save()
        return "break"

    def _on_ctrl_n(_event=None) -> str:
        new = _find_new_method(get_view())
        if new:
            new()
        return "break"

    def _on_ctrl_f(_event=None) -> str:
        view = get_view()
        # Prefer the view's own search dispatch (screens/hubs forward this to
        # their active sub-state); fall back to a generic focus helper.
        search = getattr(view, "on_keyboard_search", None)
        if callable(search):
            search()
            return "break"
        _focus_search(view)
        return "break"

    def _on_f5(_event=None) -> str:
        refresh = _find_refresh_method(get_view())
        if refresh:
            refresh()
        return "break"

    def _on_delete(_event=None) -> str:
        view = get_view()
        # Prefer the view's own delete dispatch (screens/hubs route this to
        # their active sub-state, which knows whether a row is selected).
        delete = _find_delete_method(view)
        if delete is not None:
            # Only invoke when a table row is selected (when one is visible);
            # hubs dispatch further to their child screens.
            dispatch = getattr(view, "on_keyboard_delete", None)
            if callable(dispatch):
                dispatch()
                return "break"
            if _table_has_selection(view):
                delete()
                return "break"
        return "break"

    def _on_escape(_event=None) -> str:
        # Esc only navigates back / closes popups; never quits.
        view = get_view()
        if view is not None:
            back = getattr(view, "on_keyboard_back", None)
            if callable(back):
                back()
                return "break"
            # Report hub: closing an open report returns to the hub.
            close = getattr(view, "_close_report", None)
            if callable(close) and getattr(view, "current_frame", None) is not None:
                close()
                return "break"
        return "break"

    def _on_alt_f4(_event=None) -> str:
        # Alt+F4 closes the application (Windows native behavior; bound
        # explicitly so it works even when focus is inside a widget).
        try:
            root.destroy()
        except Exception:
            pass
        return "break"

    # Bind on the root AND on all-children via bind_all so the shortcut works
    # regardless of which widget currently has focus.
    for seq, handler in [
        ("<Control-s>", _on_ctrl_s),
        ("<Control-S>", _on_ctrl_s),
        ("<Control-a>", _on_ctrl_a),
        ("<Control-A>", _on_ctrl_a),
        ("<Control-n>", _on_ctrl_n),
        ("<Control-N>", _on_ctrl_n),
        ("<Control-f>", _on_ctrl_f),
        ("<Control-F>", _on_ctrl_f),
        ("<F5>", _on_f5),
        ("<Delete>", _on_delete),
        ("<Escape>", _on_escape),
        ("<Alt-F4>", _on_alt_f4),
    ]:
        try:
            root.bind_all(seq, handler)
        except Exception:
            pass


def install_popup_escape(popup: tk.Toplevel) -> None:
    """Esc closes a popup window."""
    popup.bind("<Escape>", lambda _e: popup.destroy())


def add_shortcut_bar(parent, shortcuts: list[tuple[str, str]]) -> None:
    """Add a compact 'Shortcuts' hint line (grey, small) to a screen.

    Args:
        parent: container widget.
        shortcuts: list of (key, description) pairs, e.g. ("Ctrl+S", "Save").
    """
    import customtkinter as ctk
    import config

    text = "   ".join(f"{key} {label}" for key, label in shortcuts)
    ctk.CTkLabel(
        parent,
        text=text,
        font=ctk.CTkFont(size=11),
        text_color=config.COLOR_TEXT_MUTED,
        anchor="w",
    ).pack(fill="x", padx=config.SPACING_XL, pady=(0, config.SPACING_SM))


def wire_back_to_toplevel(view: Any) -> None:
    """Give a view an ``on_keyboard_back`` that asks the app root to go back.

    Screens opened from another screen (masters sub-screens, reports, etc.)
    should call this in their ``__init__`` so Esc returns to the previous
    screen instead of doing nothing.
    """
    def _on_keyboard_back() -> None:
        try:
            app = view.winfo_toplevel()
            if hasattr(app, "on_keyboard_back"):
                app.on_keyboard_back()
        except Exception:
            pass
    view.on_keyboard_back = _on_keyboard_back  # type: ignore[attr-defined]


def wire_entry_screen(view: Any, parent, shortcuts: list[tuple[str, str]]) -> None:
    """Convenience for master/entry screens: back-on-Esc + shortcut hint bar.

    Args:
        view: the screen instance.
        parent: the main_frame container for the hint bar.
        shortcuts: list of (key, description) pairs.
    """
    wire_back_to_toplevel(view)
    add_shortcut_bar(parent, shortcuts)
