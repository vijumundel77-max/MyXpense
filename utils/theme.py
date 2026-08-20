"""
Expenzo theme helper
Configures ttk.Style so ttk widgets (Treeview, Notebook, Combobox, buttons,
labels, entries) match the CustomTkinter palette in both light and dark modes.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config


def apply_theme(root: tk.Tk | None = None, mode: str | None = None) -> ttk.Style:
    """Apply the current Expenzo palette to ttk widgets.

    Args:
        root: optional Tk root used to build the Style (defaults to the
            active Tk root).
        mode: 'dark' or 'light'; when None, derives from
            ``ctk.get_appearance_mode()``.

    Returns:
        The configured ttk.Style instance.
    """
    if mode is None:
        try:
            import customtkinter as ctk
            appearance = ctk.get_appearance_mode()
            mode = "light" if appearance == "Light" else "dark"
        except Exception:
            mode = config.APPEARANCE_MODE

    config.set_active_theme(mode)
    dark = mode != "light"

    if dark:
        bg_primary = config.COLOR_BG_PRIMARY
        bg_secondary = config.COLOR_BG_SECONDARY
        bg_tertiary = config.COLOR_BG_TERTIARY
        bg_muted = config.COLOR_BG_MUTED
        border = config.COLOR_CARD_BORDER
        text_primary = config.COLOR_TEXT_PRIMARY
        text_secondary = config.COLOR_TEXT_SECONDARY
        text_muted = config.COLOR_TEXT_MUTED
        sidebar_accent = config.SIDEBAR_ACCENT
        sidebar_accent_hover = config.SIDEBAR_ACCENT_HOVER
        sidebar_accent_text = config.SIDEBAR_ACCENT_TEXT
    else:
        bg_primary = config.LIGHT_BG_PRIMARY
        bg_secondary = config.LIGHT_BG_SECONDARY
        bg_tertiary = config.LIGHT_BG_TERTIARY
        bg_muted = config.LIGHT_BG_MUTED
        border = config.LIGHT_CARD_BORDER
        text_primary = config.LIGHT_TEXT_PRIMARY
        text_secondary = config.LIGHT_TEXT_SECONDARY
        text_muted = config.LIGHT_TEXT_MUTED
        sidebar_accent = config.LIGHT_SIDEBAR_ACCENT
        sidebar_accent_hover = config.LIGHT_SIDEBAR_ACCENT_HOVER
        sidebar_accent_text = config.LIGHT_SIDEBAR_ACCENT_TEXT

    accent = config.COLOR_PRIMARY
    accent_hover = config.COLOR_PRIMARY_HOVER
    selected_bg = accent
    selected_fg = "#FFFFFF"

    style = ttk.Style(root) if root is not None else ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        ".",
        background=bg_primary,
        foreground=text_primary,
        fieldbackground=bg_tertiary,
        bordercolor=border,
        lightcolor=bg_tertiary,
        darkcolor=bg_tertiary,
        troughcolor=bg_tertiary,
        font=(config.FONT_FAMILY, config.FONT_BODY_SIZE),
    )
    style.map(
        ".",
        background=[("disabled", bg_secondary), ("active", bg_secondary)],
    )

    # Frames & panels
    style.configure("TFrame", background=bg_primary)
    style.configure("Card.TFrame", background=bg_secondary)
    style.configure("Muted.TFrame", background=bg_muted)
    style.configure("TLabelframe", background=bg_primary, bordercolor=border)
    style.configure("TLabelframe.Label", background=bg_primary, foreground=text_primary)

    # Labels
    style.configure("TLabel", background=bg_primary, foreground=text_primary)
    style.configure("Card.TLabel", background=bg_secondary, foreground=text_primary)
    style.configure("Muted.TLabel", background=bg_primary, foreground=text_muted)
    style.configure("Heading.TLabel", background=bg_primary, foreground=text_primary,
                    font=(config.FONT_FAMILY, config.FONT_TITLE_SIZE, "bold"))
    style.configure("Section.TLabel", background=bg_primary, foreground=text_secondary,
                    font=(config.FONT_FAMILY, 12, "bold"))
    style.configure("Amount.TLabel", background=bg_primary, foreground=text_primary,
                    font=(config.FONT_FAMILY, config.FONT_BODY_SIZE, "bold"))

    # Buttons
    style.configure("TButton", background=bg_tertiary, foreground=text_primary,
                    bordercolor=border, focusthickness=0, padding=(12, 6))
    style.map(
        "TButton",
        background=[("pressed", accent_hover), ("active", bg_secondary)],
        foreground=[("disabled", text_muted)],
    )
    style.configure("Accent.TButton", background=accent, foreground="#FFFFFF")
    style.map(
        "Accent.TButton",
        background=[("pressed", accent_hover), ("active", accent_hover)],
    )

    # Entry / combobox / spinbox
    style.configure("TEntry", fieldbackground=bg_secondary, foreground=text_primary,
                    bordercolor=border, insertcolor=text_primary, padding=(6, 4))
    style.configure("TCombobox", fieldbackground=bg_secondary, background=bg_secondary,
                    foreground=text_primary, bordercolor=border, arrowcolor=text_secondary,
                    padding=(6, 4))
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", bg_secondary)],
        foreground=[("readonly", text_primary)],
        selectbackground=[("readonly", bg_secondary)],
        selectforeground=[("readonly", text_primary)],
    )
    style.configure("TSpinbox", fieldbackground=bg_secondary, foreground=text_primary,
                    bordercolor=border, arrowcolor=text_secondary)

    # Checkbutton / radiobutton
    style.configure("TCheckbutton", background=bg_primary, foreground=text_primary)
    style.map("TCheckbutton", background=[("active", bg_primary)])
    style.configure("TRadiobutton", background=bg_primary, foreground=text_primary)
    style.map("TRadiobutton", background=[("active", bg_primary)])

    # Notebook
    style.configure("TNotebook", background=bg_primary, bordercolor=border, tabmargins=(4, 4, 4, 0))
    style.configure(
        "TNotebook.Tab",
        background=bg_secondary,
        foreground=text_secondary,
        padding=(16, 8),
        bordercolor=border,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", bg_tertiary)],
        foreground=[("selected", text_primary)],
    )

    # Treeview
    style.configure(
        "Treeview",
        background=bg_muted,
        fieldbackground=bg_muted,
        foreground=text_primary,
        bordercolor=border,
        rowheight=30,
    )
    style.map(
        "Treeview",
        background=[("selected", selected_bg)],
        foreground=[("selected", selected_fg)],
    )
    style.configure(
        "Treeview.Heading",
        background=bg_tertiary,
        foreground=text_primary,
        bordercolor=border,
        font=(config.FONT_FAMILY, config.FONT_BODY_SIZE, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", bg_secondary)])

    # Standard row tags used across screens (zebra, cancelled, totals).
    for tag, fg, bg in [
        ("even", text_primary, bg_muted),
        ("odd", text_primary, bg_secondary),
        ("cancelled", text_muted, bg_muted),
        ("total", text_primary, bg_tertiary),
        ("header", text_secondary, bg_muted),
    ]:
        try:
            style.configure(tag, foreground=fg, background=bg)
        except Exception:
            pass
    try:
        style.map("cancelled", background=[("selected", selected_bg)],
                  foreground=[("selected", selected_fg)])
        style.map("total", background=[("selected", selected_bg)],
                  foreground=[("selected", selected_fg)])
    except Exception:
        pass

    # Scrollbars
    style.configure("Vertical.TScrollbar", background=bg_tertiary, troughcolor=bg_primary,
                    bordercolor=bg_primary, arrowcolor=text_secondary)
    style.configure("Horizontal.TScrollbar", background=bg_tertiary, troughcolor=bg_primary,
                    bordercolor=bg_primary, arrowcolor=text_secondary)

    # Separator
    style.configure("TSeparator", background=border)

    return style


# ---------------------------------------------------------------------- #
# deterministic live re-coloring via semantic tokens
# ---------------------------------------------------------------------- #
# Instead of inferring a widget's semantic color from its current hex value
# (collision-prone: the same hex can mean different tokens across themes),
# each themed color option is classified ONCE against the token tables and the
# identified token is stored on the widget.  On every theme switch we resolve
# that stored token against the newly active palette, so a single toggle
# deterministically re-colors every existing widget in place.

# The token table: semantic name -> (dark hex, light hex).
_TOKEN_TABLE = {
    "BG_PRIMARY": (config.DARK_BG_PRIMARY, config.LIGHT_BG_PRIMARY),
    "BG_SECONDARY": (config.DARK_BG_SECONDARY, config.LIGHT_BG_SECONDARY),
    "BG_TERTIARY": (config.DARK_BG_TERTIARY, config.LIGHT_BG_TERTIARY),
    "BG_MUTED": (config.DARK_BG_MUTED, config.LIGHT_BG_MUTED),
    "CARD_BORDER": (config.DARK_CARD_BORDER, config.LIGHT_CARD_BORDER),
    "TEXT_PRIMARY": (config.DARK_TEXT_PRIMARY, config.LIGHT_TEXT_PRIMARY),
    "TEXT_SECONDARY": (config.DARK_TEXT_SECONDARY, config.LIGHT_TEXT_SECONDARY),
    "TEXT_MUTED": (config.DARK_TEXT_MUTED, config.LIGHT_TEXT_MUTED),
    "SIDEBAR_ACCENT": (config.DARK_SIDEBAR_ACCENT, config.LIGHT_SIDEBAR_ACCENT),
    "SIDEBAR_ACCENT_HOVER": (config.DARK_SIDEBAR_ACCENT_HOVER, config.LIGHT_SIDEBAR_ACCENT_HOVER),
    "SIDEBAR_ACCENT_TEXT": (config.DARK_SIDEBAR_ACCENT_TEXT, config.LIGHT_SIDEBAR_ACCENT_TEXT),
}

# Reverse lookup: exact hex (lowercased) -> token name.  Colliding hexes
# (e.g. #0F172A = light TEXT_PRIMARY AND dark BG_PRIMARY) are resolved to the
# MORE SPECIFIC token using the ordered _TOKEN_PRIORITY list; the classifier
# additionally uses the option's ROLE (text vs background) so the semantics
# are never ambiguous.
_TOKEN_FROM_HEX: dict[str, str] = {}
for _name, (_dark, _light) in _TOKEN_TABLE.items():
    _TOKEN_FROM_HEX.setdefault(_dark.lower(), _name)
    _TOKEN_FROM_HEX.setdefault(_light.lower(), _name)

# Roles (which option => which kind of token).
_TEXT_ROLE_TOKENS = {"TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED"}
_BG_ROLE_TOKENS = {"BG_PRIMARY", "BG_SECONDARY", "BG_TERTIARY", "BG_MUTED", "CARD_BORDER"}

# Ordered specificity for hex collisions (text wins over background; borders
# after backgrounds; sidebar accents last).
_TOKEN_PRIORITY = (
    "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_MUTED",
    "BG_PRIMARY", "BG_SECONDARY", "BG_TERTIARY", "BG_MUTED", "CARD_BORDER",
    "SIDEBAR_ACCENT", "SIDEBAR_ACCENT_HOVER", "SIDEBAR_ACCENT_TEXT",
)

# Colors that should never be re-mapped by the walker (accents & semantics).
_PRESERVE_COLORS = {
    c.lower() for c in (
        config.COLOR_PRIMARY, config.COLOR_PRIMARY_HOVER, config.COLOR_PRIMARY_LIGHT,
        config.COLOR_INCOME, config.COLOR_INCOME_HOVER,
        config.COLOR_EXPENSE, config.COLOR_EXPENSE_HOVER,
        config.COLOR_TRANSFER, config.COLOR_TRANSFER_HOVER,
        config.COLOR_WARNING,
    )
}


def _hex_matches_token(value: str, token: str) -> bool:
    dark_hex, light_hex = _TOKEN_TABLE[token]
    low = value.lower()
    return low == dark_hex.lower() or low == light_hex.lower()


def _resolve_token(token: str) -> str:
    """Return the active-theme hex for a semantic token."""
    if token not in _TOKEN_TABLE:
        return token
    dark_hex, light_hex = _TOKEN_TABLE[token]
    return dark_hex if config.is_dark() else light_hex


# Widget types whose text/foreground color should follow the palette.
_TEXT_OPTIONS = {
    "CTkLabel": "text_color",
    "CTkButton": "text_color",
    "CTkCheckBox": "text_color",
    "CTkRadioButton": "text_color",
    "CTkSwitch": "text_color",
    "CTkComboBox": "text_color",
    "CTkEntry": "text_color",
    "CTkTextbox": "text_color",
    "CTkOptionMenu": "text_color",
}

# Widget types whose background color should follow the palette.
_BG_OPTIONS = {
    "CTkLabel": "fg_color",
    "CTkButton": "fg_color",
    "CTkCheckBox": "fg_color",
    "CTkRadioButton": "fg_color",
    "CTkSwitch": "fg_color",
    "CTkFrame": "fg_color",
    "CTkScrollableFrame": "fg_color",
}

# Extra options that carry a themed color (borders, fields, toggles, etc.).
_EXTRA_OPTIONS = {
    "CTkButton": ("border_color", "hover_color", "text_color_disabled", "fg_color_disabled"),
    "CTkComboBox": ("border_color",),
    "CTkEntry": ("border_color",),
    "CTkCheckBox": ("border_color",),
    "CTkRadioButton": ("border_color",),
    "CTkSwitch": ("progress_color", "button_color"),
    "CTkScrollbar": ("button_color",),
    "CTkTextbox": ("border_color",),
}


def _remember_token(child, opt: str, token: str) -> None:
    """Store the semantic token for a widget option (first classification wins)."""
    if not hasattr(child, "_theme_tokens"):
        child._theme_tokens = {}
    if opt not in child._theme_tokens:
        child._theme_tokens[opt] = token


def _classify_option(child, opt: str, role: str, value: str) -> str | None:
    """Identify the semantic token for a color value given its role.

    Returns the token name, or None if the value is not a themed color
    (accent, transparent, custom).  Deterministic: the role narrows the token
    space (text vs background), and the hex look-up resolves within that role.

    Colliding hexes (e.g. #94A3B8 is both the dark TEXT_SECONDARY and the
    light TEXT_MUTED) are resolved by checking the current theme's tokens first.
    """
    if not value or not isinstance(value, str):
        return None
    low = value.lower()
    if low in _PRESERVE_COLORS or low == "transparent" or low == "#000000":
        return None
    
    # Use current theme to prioritize matching (light tokens first in light mode, etc.)
    is_dark_mode = config.is_dark()
    
    # Role-specific tokens in FIXED order.
    if role == "text":
        role_order = ("TEXT_MUTED", "TEXT_SECONDARY", "TEXT_PRIMARY")
    else:
        role_order = ("BG_SECONDARY", "BG_PRIMARY", "BG_TERTIARY", "BG_MUTED", "CARD_BORDER")
    
    # Check current theme's variant first to avoid cross-theme collisions
    for token in role_order:
        dark_hex, light_hex = _TOKEN_TABLE[token]
        if is_dark_mode:
            if low == dark_hex.lower():
                return token
        else:
            if low == light_hex.lower():
                return token
    
    # Fall back to checking the other theme's variant
    for token in role_order:
        if _hex_matches_token(value, token):
            return token
    
    # Fall back to the full table (for tokens without a role restriction).
    for token in _TOKEN_PRIORITY:
        if _hex_matches_token(value, token):
            return token
    return None


def _retint_child(child) -> None:
    """Re-apply the active palette to a single ctk widget in place."""
    cls = child.__class__.__name__

    # ---- background (fg_color) ----
    if cls in _BG_OPTIONS:
        opt = _BG_OPTIONS[cls]
        try:
            value = str(child.cget(opt) or "")
        except Exception:
            value = ""
        token = getattr(child, "_theme_tokens", {}).get(opt)
        if token is None:
            token = _classify_option(child, opt, "bg", value)
            if token:
                _remember_token(child, opt, token)
        if token and token in _TOKEN_TABLE:
            try:
                child.configure(**{opt: _resolve_token(token)})
            except Exception:
                pass
        elif value.lower() == "transparent":
            # Force refresh of transparent frames so they inherit updated parent background.
            try:
                child.configure(**{opt: "transparent"})
            except Exception:
                pass

    # ---- text (text_color) ----
    if cls in _TEXT_OPTIONS:
        opt = _TEXT_OPTIONS[cls]
        try:
            value = str(child.cget(opt) or "")
        except Exception:
            value = ""
        token = getattr(child, "_theme_tokens", {}).get(opt)
        if token is None:
            token = _classify_option(child, opt, "text", value)
            if token:
                _remember_token(child, opt, token)
        if token and token in _TOKEN_TABLE:
            try:
                child.configure(**{opt: _resolve_token(token)})
            except Exception:
                pass

    # ---- extra themed options (borders, fields, toggles, disabled states) ----
    for opt in _EXTRA_OPTIONS.get(cls, ()):
        try:
            value = str(child.cget(opt) or "")
        except Exception:
            continue
        if not value or value.lower() in ("transparent", ""):
            continue
        token = getattr(child, "_theme_tokens", {}).get(opt)
        if token is None:
            # Border color is a background-ish token (CARD_BORDER or BG_TERTIARY).
            # Disabled colors: map to muted/secondary tokens.
            if opt in ("text_color_disabled", "fg_color_disabled"):
                token = _classify_option(child, opt, "text" if "text" in opt else "bg", value)
            else:
                token = _classify_option(child, opt, "bg", value)
            if token:
                _remember_token(child, opt, token)
        if token and token in _TOKEN_TABLE:
            try:
                child.configure(**{opt: _resolve_token(token)})
            except Exception:
                pass

    # Entries/combos: keep the field background readable in both themes.
    if cls in ("CTkEntry", "CTkComboBox"):
        try:
            child.configure(fg_color=_resolve_token("BG_SECONDARY"))
        except Exception:
            pass


def _apply_palette(root) -> None:
    """Walk the widget tree and re-tint every ctk widget to the active palette."""
    def _walk(widget):
        try:
            _retint_child(widget)
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                _walk(child)
        except Exception:
            pass

    try:
        _walk(root)
    except Exception:
        pass


def apply_palette(root) -> None:
    """Public entry point: re-color every existing widget under ``root`` so it
    matches the active theme (light/dark). Deterministic: every widget's
    semantic token is resolved against the active palette, so a single call
    re-colors everything (repeated calls are idempotent)."""
    _apply_palette(root)
    # Also refresh ttk Treeview styles and widget colors
    refresh_treeview_styles(root)


def refresh_treeview_styles(root) -> None:
    """Re-apply the current theme's ttk.Style to all Treeview widgets under root.
    
    This ensures Treeview background, foreground, heading, and selection colors
    match the active theme immediately without needing to recreate the widgets.
    """
    try:
        import customtkinter as ctk
        mode = "light" if ctk.get_appearance_mode() == "Light" else "dark"
        apply_theme(root, mode=mode)
    except Exception:
        pass
    
    dark = config.is_dark()
    bg_muted = config.COLOR_BG_MUTED if dark else config.LIGHT_BG_MUTED
    bg_secondary = config.COLOR_BG_SECONDARY if dark else config.LIGHT_BG_SECONDARY
    bg_tertiary = config.COLOR_BG_TERTIARY if dark else config.LIGHT_BG_TERTIARY
    text_primary = config.COLOR_TEXT_PRIMARY if dark else config.LIGHT_TEXT_PRIMARY
    text_secondary = config.COLOR_TEXT_SECONDARY if dark else config.LIGHT_TEXT_SECONDARY
    text_muted = config.COLOR_TEXT_MUTED if dark else config.LIGHT_TEXT_MUTED
    selected_bg = config.COLOR_PRIMARY
    selected_fg = "#FFFFFF"
    hover_bg = config.COLOR_HOVER_SURFACE
    expense_color = config.COLOR_EXPENSE
    income_color = config.COLOR_INCOME
    
    def _walk(widget):
        try:
            if isinstance(widget, ttk.Treeview):
                widget.configure(style="Treeview")
                widget.tag_configure("even", foreground=text_primary, background=bg_muted)
                widget.tag_configure("odd", foreground=text_primary, background=bg_secondary)
                widget.tag_configure("cancelled", foreground=text_muted, background=bg_muted)
                widget.tag_configure("total", foreground=text_primary, background=bg_tertiary)
                widget.tag_configure("header", foreground=text_secondary, background=bg_muted)
                widget.tag_configure("hover", background=hover_bg)
                widget.tag_configure("in", foreground=income_color)
                widget.tag_configure("out", foreground=expense_color)
                widget.tag_configure("cancelled", background=[("selected", selected_bg)],
                                    foreground=[("selected", selected_fg)])
                widget.tag_configure("total", background=[("selected", selected_bg)],
                                    foreground=[("selected", selected_fg)])
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                _walk(child)
        except Exception:
            pass
    
    try:
        _walk(root)
    except Exception:
        pass
    
    # Also refresh custom picker style if it exists
    try:
        from ui.ledger_picker import configure_picker_style
        configure_picker_style(root)
    except Exception:
        pass
