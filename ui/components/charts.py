"""
Expenzo — Canvas charts.

Lightweight, dependency-free bar and trend charts drawn on tkinter Canvas,
fully themed through config tokens so the palette walker can re-tint them on
theme switch. Used by the dashboard.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import customtkinter as ctk

import config


class BarChart(ctk.CTkFrame):
    """A grouped bar chart (e.g. receipts vs payments per month)."""

    def __init__(self, master, title: str = "", height: int = 220,
                 height_px: Optional[int] = None, **kwargs):
        super().__init__(master, corner_radius=config.CARD_CORNER_RADIUS,
                         fg_color=config.COLOR_BG_SECONDARY,
                         border_width=1, border_color=config.COLOR_CARD_BORDER,
                         **kwargs)
        self._title = title
        if title:
            ctk.CTkLabel(
                self, text=title, anchor="w",
                font=ctk.CTkFont(size=config.FONT_SUBTITLE_SIZE, weight="bold"),
            ).pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, 0))
        self.canvas = ctk.CTkCanvas(self, height=height, highlightthickness=0,
                                    bg=config.COLOR_BG_SECONDARY)
        self.canvas.pack(fill="both", expand=True, padx=config.SPACING_LG,
                         pady=(config.SPACING_SM, config.SPACING_LG))
        self.canvas.bind("<Configure>", lambda _e: self._schedule_redraw())
        self._series: Dict[str, List[float]] = {}
        self._labels: List[str] = []
        self._colors: List[str] = [config.COLOR_PRIMARY, config.COLOR_SUCCESS]
        self._redraw_pending = False

    def _schedule_redraw(self) -> None:
        if self._redraw_pending:
            return
        self._redraw_pending = True
        self.after(20, self._redraw_now)

    def _redraw_now(self) -> None:
        self._redraw_pending = False
        self.redraw()

    def set_data(self, labels: List[str], series: Dict[str, List[float]]) -> None:
        self._labels = labels
        self._series = series
        self.redraw()

    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        if not self._series or not self._labels:
            canvas.create_text(canvas.winfo_width() // 2,
                               canvas.winfo_height() // 2,
                               text="No data", fill=config.COLOR_TEXT_MUTED,
                               font=("Inter", config.FONT_SMALL_SIZE))
            return
        try:
            width = max(canvas.winfo_width(), 100)
            height = max(canvas.winfo_height(), 60)
        except Exception:
            width, height = 400, 200

        pad_l, pad_r, pad_t, pad_b = 46, 12, 16, 28
        plot_w = width - pad_l - pad_r
        plot_h = height - pad_t - pad_b

        max_val = max((v for vals in self._series.values() for v in vals), default=0)
        max_val = max_val * 1.1 or 1

        # Horizontal gridlines + y labels.
        for i in range(5):
            y = pad_t + plot_h - (plot_h * i / 4)
            canvas.create_line(pad_l, y, width - pad_r, y,
                               fill=config.COLOR_CARD_BORDER, dash=(2, 4))
            val = max_val * i / 4
            canvas.create_text(pad_l - 6, y, text=f"{val:,.0f}",
                               anchor="e", fill=config.COLOR_TEXT_MUTED,
                               font=("Inter", 9))

        n = len(self._labels)
        n_series = len(self._series)
        group_w = plot_w / n
        bar_w = min(26, group_w / (n_series + 1.2))
        series_keys = list(self._series.keys())

        for i, label in enumerate(self._labels):
            x0 = pad_l + group_w * i
            cx = x0 + group_w / 2
            for s, key in enumerate(series_keys):
                val = self._series[key][i]
                bar_h = plot_h * (val / max_val)
                bx0 = cx - (bar_w * n_series) / 2 + bar_w * s
                by0 = pad_t + plot_h - bar_h
                color = self._colors[s % len(self._colors)]
                canvas.create_rectangle(bx0, by0, bx0 + bar_w - 3, pad_t + plot_h,
                                        fill=color, outline="")
            canvas.create_text(cx, pad_t + plot_h + 12, text=label, anchor="n",
                               fill=config.COLOR_TEXT_SECONDARY, font=("Inter", 9))

        # Legend.
        lx = pad_l
        ly = 8
        for s, key in enumerate(series_keys):
            canvas.create_rectangle(lx, ly, lx + 10, ly + 10,
                                    fill=self._colors[s % len(self._colors)], outline="")
            canvas.create_text(lx + 14, ly + 5, text=key, anchor="w",
                               fill=config.COLOR_TEXT_SECONDARY, font=("Inter", 9))
            lx += 14 + len(key) * 7 + 12


class DonutChart(ctk.CTkFrame):
    """A simple donut chart for proportions (e.g. receivables vs payables)."""

    def __init__(self, master, title: str = "", height: int = 180, **kwargs):
        super().__init__(master, corner_radius=config.CARD_CORNER_RADIUS,
                         fg_color=config.COLOR_BG_SECONDARY,
                         border_width=1, border_color=config.COLOR_CARD_BORDER,
                         **kwargs)
        if title:
            ctk.CTkLabel(
                self, text=title, anchor="w",
                font=ctk.CTkFont(size=config.FONT_SUBTITLE_SIZE, weight="bold"),
            ).pack(fill="x", padx=config.SPACING_LG, pady=(config.SPACING_LG, 0))
        self.canvas = ctk.CTkCanvas(self, height=height, highlightthickness=0,
                                    bg=config.COLOR_BG_SECONDARY)
        self.canvas.pack(fill="both", expand=True, padx=config.SPACING_LG,
                         pady=(config.SPACING_SM, config.SPACING_LG))
        self._data: List[tuple] = []  # (label, value, color)

    def set_data(self, data: List[tuple]) -> None:
        self._data = data
        self.redraw()

    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        try:
            width = max(canvas.winfo_width(), 100)
            height = max(canvas.winfo_height(), 60)
        except Exception:
            width, height = 300, 180
        cx, cy = width // 2, height // 2
        r = min(width, height) // 2 - 14
        if r < 10:
            return
        total = sum(v for _, v, _ in self._data) or 1
        start = 90.0
        for label, value, color in self._data:
            extent = -360.0 * value / total
            canvas.create_arc(cx - r, cy - r, cx + r, cy + r,
                              start=start, extent=extent, fill=color, outline="")
            start += extent
        # Center hole.
        canvas.create_oval(cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2,
                           fill=config.COLOR_BG_SECONDARY, outline="")
        canvas.create_text(cx, cy, text=f"{total:,.0f}", fill=config.COLOR_TEXT_PRIMARY,
                           font=("Inter", config.FONT_TITLE_SIZE, "bold"))
        # Legend.
        ly = 8
        for label, value, color in self._data:
            canvas.create_rectangle(10, ly, 20, ly + 10, fill=color, outline="")
            canvas.create_text(24, ly + 5, text=f"{label}  ·  {value:,.0f}",
                               anchor="w", fill=config.COLOR_TEXT_SECONDARY,
                               font=("Inter", 9))
            ly += 16
