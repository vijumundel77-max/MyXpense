"""
Expenzo — central iconography.

A curated map of Unicode glyphs used consistently across the application.
Everything renders as text (no image assets needed), is theme-aware by using
the widget's text_color, and avoids emoji for a professional look.
"""
from __future__ import annotations

# Navigation & sections.
ICONS = {
    "dashboard": "▦",
    "vouchers": "▤",
    "masters": "▧",
    "bank_accounts": "▨",
    "reports": "▥",
    "settings": "⚙",
    "company": "▣",
    "inventory": "▤",
    "utilities": "⌘",
    "help": "?",
}

# Common actions.
ACTION_ICONS = {
    "search": "⌕",
    "refresh": "⟳",
    "add": "+",
    "edit": "✎",
    "delete": "✕",
    "view": "▸",
    "back": "←",
    "forward": "→",
    "close": "✕",
    "save": "💾",
    "export": "⤓",
    "import": "⤒",
    "print": "⎙",
    "filter": "⇧",
    "sort": "⇅",
    "menu": "☰",
    "chevron_right": "›",
    "chevron_down": "⌄",
    "star": "★",
    "star_outline": "☆",
    "calendar": "◷",
    "bell": "🔔",
    "profile": "◉",
    "theme": "◐",
    "collapse": "«",
    "expand": "»",
    "check": "✓",
    "warning": "⚠",
    "info": "ℹ",
    "money": "₹",
    "cash": "₹",
    "bank": "◫",
    "receivable": "◭",
    "payable": "◮",
    "profit": "▲",
    "expense": "▼",
    "income": "▲",
}

# Financial KPIs used by the dashboard.
KPI_ICONS = {
    "cash": "₹",
    "bank": "◫",
    "receivable": "◭",
    "payable": "◮",
    "income": "▲",
    "expense": "▼",
    "profit": "◆",
}
