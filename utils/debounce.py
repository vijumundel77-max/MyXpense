"""Debounce utility for search inputs and other delayed operations."""
import tkinter as tk
from typing import Callable, Optional


class Debouncer:
    """Generic debounce helper for Tkinter after callbacks."""

    def __init__(self, widget: tk.Misc, delay_ms: int = 250):
        self.widget = widget
        self.delay_ms = delay_ms
        self._timer_id: Optional[str] = None

    def schedule(self, callback: Callable[[], None]) -> None:
        """Schedule callback to run after delay_ms. Cancels any pending callback."""
        if self._timer_id:
            self.widget.after_cancel(self._timer_id)
        self._timer_id = self.widget.after(self.delay_ms, callback)

    def cancel(self) -> None:
        """Cancel any pending callback."""
        if self._timer_id:
            self.widget.after_cancel(self._timer_id)
            self._timer_id = None


def debounce(delay_ms: int = 250):
    """Decorator to debounce a method call on a widget.

    Usage:
        @debounce(250)
        def _on_search_changed(self):
            self._apply_search_filter()
    """
    def decorator(func: Callable):
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, '_debounce_timers'):
                self._debounce_timers = {}
            key = func.__name__
            if key in self._debounce_timers and self._debounce_timers[key]:
                self.after_cancel(self._debounce_timers[key])
            self._debounce_timers[key] = self.after(delay_ms, lambda: func(self, *args, **kwargs))
        return wrapper
    return decorator