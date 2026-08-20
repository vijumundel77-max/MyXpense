"""
Expenzo Configuration Module
Centralized settings, constants, dark/light theme design tokens, and application metadata.
"""

import os
from pathlib import Path

# ==========================================
# APP METADATA
# ==========================================
APP_NAME = "Expenzo"
APP_SUBTITLE = "Accounting"

# Central version management: the canonical version string lives in
# version_service.py at the repo root (used by the installer/release scripts
# too).  The installed release (per-user %APPDATA%\\Expenzo\\version.json)
# wins over the compiled-in default so the app always knows which build it is.
from version_service import current_version  # noqa: E402

APP_VERSION = current_version()

# ==========================================
# PATHS
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

# Per-user data directory. User data (database, exports) always lives OUTSIDE
# the application installation folder so reinstalls/updates never touch it.
#   - override for tests/portable use: EXPENZO_DATA_DIR env var
#   - Windows: %APPDATA%\Expenzo
#   - other platforms: ~/.local/share/Expenzo
_ENV_DATA_DIR = os.environ.get("EXPENZO_DATA_DIR")
if _ENV_DATA_DIR:
    DATA_DIR = Path(_ENV_DATA_DIR)
elif os.name == "nt" and os.environ.get("APPDATA"):
    DATA_DIR = Path(os.environ["APPDATA"]) / "Expenzo"
else:
    DATA_DIR = Path.home() / ".local" / "share" / "Expenzo"

DATABASE_DIR = DATA_DIR / "database"
DATABASE_NAME = "myxpense.db"
DATABASE_PATH = DATABASE_DIR / DATABASE_NAME

EXPORTS_DIR = DATA_DIR / "exports"

# Ensure directories exist (now under the per-user data dir)
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# WINDOW & LAYOUT CONFIGURATION
# ==========================================
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 820
WINDOW_MIN_WIDTH = 1100
WINDOW_MIN_HEIGHT = 680

SIDEBAR_WIDTH = 240
HEADER_HEIGHT = 70

# Form widget sizing (used by masters/company screens)
FORM_ENTRY_WIDTH = 200
FORM_ADDRESS_HEIGHT = 4
FORM_MOBILE_WIDTH = 120

# Form typography sizes
FONT_TITLE_SIZE = 20
FONT_BODY_SIZE = 14

# ==========================================
# THEME & DESIGN TOKENS
# ==========================================
APPEARANCE_MODE = "dark"
COLOR_THEME = "blue"

# Dark Theme Color Palette (Modern Slate / Material Dark)
# These dark literals feed the theme token table; the dynamic COLOR_* names
# (resolved via __getattr__ below) return the ACTIVE theme's value so UI
# screens built in any mode use the correct colors immediately.
DARK_BG_PRIMARY = "#0F172A"        # Main Window Dark Background (Slate 900)
DARK_BG_SECONDARY = "#1E293B"      # Cards & Panels Background (Slate 800)
DARK_BG_TERTIARY = "#334155"       # Inputs, Hover & Borders (Slate 700)
DARK_CARD_BORDER = "#334155"       # Card Border Color
DARK_BG_MUTED = "#1B2435"          # Muted Card (subtle panels & table interiors)
DARK_TEXT_PRIMARY = "#F8FAFC"      # Primary White Text (Slate 50)
DARK_TEXT_SECONDARY = "#94A3B8"    # Muted Text (Slate 400)
DARK_TEXT_MUTED = "#64748B"        # Dark Muted Text (Slate 500)

# Voucher Entry Deep Dark Palette (for fully immersive dark screens)
VOUCHER_BG_PRIMARY = "#0B1329"      # Screen background - deepest navy
VOUCHER_CARD_BG = "#10192E"         # Card containers
VOUCHER_CARD_BORDER = "#1B2848"     # Card borders
VOUCHER_INPUT_BG = "#0B1329"        # Entry box backgrounds
VOUCHER_INPUT_BORDER = "#1B2848"    # Entry box borders
VOUCHER_INPUT_TEXT = "#FFFFFF"      # Entry box text

# Light Theme Color Palette (Modern Slate / Material Light)
LIGHT_BG_PRIMARY = "#F1F5F9"      # Main Window Light Background (Slate 100)
LIGHT_BG_SECONDARY = "#FFFFFF"    # Cards & Panels Background (White)
LIGHT_BG_TERTIARY = "#E2E8F0"     # Inputs, Hover & Borders (Slate 200)
LIGHT_CARD_BORDER = "#CBD5E1"     # Card Border Color (Slate 300)
LIGHT_TEXT_PRIMARY = "#0F172A"    # Primary Text (Slate 900)
LIGHT_TEXT_SECONDARY = "#475569"  # Muted Text (Slate 600)
LIGHT_TEXT_MUTED = "#94A3B8"      # Dark Muted Text (Slate 400)

# Sidebar & Header Accent (Light)
LIGHT_SIDEBAR_ACCENT = "#DBEAFE"       # Soft blue tint for the active nav item
LIGHT_SIDEBAR_ACCENT_HOVER = "#BFDBFE" # Slightly brighter hover for the active item
LIGHT_SIDEBAR_ACCENT_TEXT = "#1D4ED8"  # Blue-700 tint for active item text

# Muted Card (subtle, non-interactive panels & table interiors)
LIGHT_BG_MUTED = "#F8FAFC"        # Slightly lighter than the light background

# Accent Colors
COLOR_PRIMARY = "#3B82F6"         # Vibrant Blue Accent (Blue 500)
COLOR_PRIMARY_HOVER = "#2563EB"   # Primary Hover (Blue 600)
COLOR_PRIMARY_LIGHT = "#1D4ED8"   # Pressed State

# Sidebar & Header Accent (Dark)
DARK_SIDEBAR_ACCENT = "#1E3A5F"        # Soft blue tint for the active nav item
DARK_SIDEBAR_ACCENT_HOVER = "#274B77"  # Slightly brighter hover for the active item
DARK_SIDEBAR_ACCENT_TEXT = "#BFDBFE"   # Blue-200 tint for active item text

# Backward compatibility aliases
SIDEBAR_ACCENT = DARK_SIDEBAR_ACCENT
SIDEBAR_ACCENT_HOVER = DARK_SIDEBAR_ACCENT_HOVER
SIDEBAR_ACCENT_TEXT = DARK_SIDEBAR_ACCENT_TEXT

# Status & Financial Indicators
COLOR_INCOME = "#10B981"          # Emerald Green 500
COLOR_INCOME_HOVER = "#059669"
COLOR_SUCCESS = "#10B981"         # Same as COLOR_INCOME
COLOR_EXPENSE = "#EF4444"         # Crimson Red 500
COLOR_EXPENSE_HOVER = "#DC2626"
COLOR_HOVER_SURFACE = "#334155"   # Slate 700 (same as DARK_BG_TERTIARY)
COLOR_TRANSFER = "#8B5CF6"        # Purple Accent 500
COLOR_TRANSFER_HOVER = "#7C3AED"
COLOR_WARNING = "#F59E0B"         # Amber Warning 500

# Widget Radius Settings
CARD_CORNER_RADIUS = 14
BUTTON_CORNER_RADIUS = 10
INPUT_CORNER_RADIUS = 8

# ==========================================
# SPACING SCALE (px)
# ==========================================
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 12
SPACING_LG = 16
SPACING_XL = 24
SPACING_XXL = 32

# ==========================================
# TYPOGRAPHY
# ==========================================
FONT_FAMILY = "Segoe UI"  # Windows Native Clean Font

FONT_HERO = (FONT_FAMILY, 24, "bold")
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 16, "bold")
FONT_SUBTITLE_SIZE = 16
FONT_BODY_BOLD = (FONT_FAMILY, 14, "bold")
FONT_BODY = (FONT_FAMILY, 14, "normal")
FONT_SMALL = (FONT_FAMILY, 12, "normal")
FONT_SMALL_SIZE = 12
FONT_SMALL_BOLD = (FONT_FAMILY, 12, "bold")

# ==========================================
# FINANCIAL CONSTANTS
# ==========================================
CURRENCY_SYMBOL = "₹"
DATE_DISPLAY_FORMAT = "%d %b %Y"
DISPLAY_DATE_FORMAT = "%d-%m-%Y"
TIME_DISPLAY_FORMAT = "%I:%M %p"
DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DB_DATE_FORMAT = "%Y-%m-%d"

# ==========================================
# ACTIVE THEME PALETTE (dynamic)
# ==========================================
# UI screens resolve their colors through the COLOR_*/TEXT_* module names so
# that switching the appearance mode re-colors every already-built widget
# without rebuilding it.  These names are DYNAMIC: they resolve to the active
# theme's value, so a screen constructed in Light mode uses light colors from
# the start, and a toggle flips every existing widget in place.
#
# The literal dark tokens are COLOR_BG_* / COLOR_TEXT_* above; the light
# tokens are LIGHT_*.  A module-level __getattr__ (PEP 562) intercepts the
# COLOR_*/TEXT_* names and returns the active-theme hex.  theme.py keeps
# reading the literals it needs (the token table uses the raw constants).
_active_theme: str = "light" if str(APPEARANCE_MODE).lower() == "light" else "dark"


def set_active_theme(mode: str) -> None:
    """Point the dynamic palette at the given theme ('light' or 'dark')."""
    global _active_theme
    _active_theme = "light" if str(mode).lower() == "light" else "dark"


def is_dark() -> bool:
    return _active_theme != "light"


def current_palette() -> dict:
    """Return the full color dictionary for the active theme."""
    if _active_theme == "light":
        return {
            "BG_PRIMARY": LIGHT_BG_PRIMARY,
            "BG_SECONDARY": LIGHT_BG_SECONDARY,
            "BG_TERTIARY": LIGHT_BG_TERTIARY,
            "BG_MUTED": LIGHT_BG_MUTED,
            "CARD_BORDER": LIGHT_CARD_BORDER,
            "TEXT_PRIMARY": LIGHT_TEXT_PRIMARY,
            "TEXT_SECONDARY": LIGHT_TEXT_SECONDARY,
            "TEXT_MUTED": LIGHT_TEXT_MUTED,
            "SIDEBAR_ACCENT": LIGHT_SIDEBAR_ACCENT,
            "SIDEBAR_ACCENT_HOVER": LIGHT_SIDEBAR_ACCENT_HOVER,
            "SIDEBAR_ACCENT_TEXT": LIGHT_SIDEBAR_ACCENT_TEXT,
        }
    return {
        "BG_PRIMARY": DARK_BG_PRIMARY,
        "BG_SECONDARY": DARK_BG_SECONDARY,
        "BG_TERTIARY": DARK_BG_TERTIARY,
        "BG_MUTED": DARK_BG_MUTED,
        "CARD_BORDER": DARK_CARD_BORDER,
        "TEXT_PRIMARY": DARK_TEXT_PRIMARY,
        "TEXT_SECONDARY": DARK_TEXT_SECONDARY,
        "TEXT_MUTED": DARK_TEXT_MUTED,
        "SIDEBAR_ACCENT": DARK_SIDEBAR_ACCENT,
        "SIDEBAR_ACCENT_HOVER": DARK_SIDEBAR_ACCENT_HOVER,
        "SIDEBAR_ACCENT_TEXT": DARK_SIDEBAR_ACCENT_TEXT,
    }


# Map COLOR_*/TEXT_* module name -> (dark literal, light literal).  These names
# are NOT defined as module globals; __getattr__ resolves them dynamically.
_THEME_ATTRS = {
    "COLOR_BG_PRIMARY": (DARK_BG_PRIMARY, LIGHT_BG_PRIMARY),
    "COLOR_BG_SECONDARY": (DARK_BG_SECONDARY, LIGHT_BG_SECONDARY),
    "COLOR_BG_TERTIARY": (DARK_BG_TERTIARY, LIGHT_BG_TERTIARY),
    "COLOR_BG_MUTED": (DARK_BG_MUTED, LIGHT_BG_MUTED),
    "COLOR_CARD_BORDER": (DARK_CARD_BORDER, LIGHT_CARD_BORDER),
    "COLOR_TEXT_PRIMARY": (DARK_TEXT_PRIMARY, LIGHT_TEXT_PRIMARY),
    "COLOR_TEXT_SECONDARY": (DARK_TEXT_SECONDARY, LIGHT_TEXT_SECONDARY),
    "COLOR_TEXT_MUTED": (DARK_TEXT_MUTED, LIGHT_TEXT_MUTED),
    "COLOR_SIDEBAR_ACCENT": (DARK_SIDEBAR_ACCENT, LIGHT_SIDEBAR_ACCENT),
    "COLOR_SIDEBAR_ACCENT_HOVER": (DARK_SIDEBAR_ACCENT_HOVER, LIGHT_SIDEBAR_ACCENT_HOVER),
    "COLOR_SIDEBAR_ACCENT_TEXT": (DARK_SIDEBAR_ACCENT_TEXT, LIGHT_SIDEBAR_ACCENT_TEXT),
    "VOUCHER_BG_PRIMARY": (VOUCHER_BG_PRIMARY, VOUCHER_BG_PRIMARY),
    "VOUCHER_CARD_BG": (VOUCHER_CARD_BG, VOUCHER_CARD_BG),
    "VOUCHER_CARD_BORDER": (VOUCHER_CARD_BORDER, VOUCHER_CARD_BORDER),
    "VOUCHER_INPUT_BG": (VOUCHER_INPUT_BG, VOUCHER_INPUT_BG),
    "VOUCHER_INPUT_BORDER": (VOUCHER_INPUT_BORDER, VOUCHER_INPUT_BORDER),
    "VOUCHER_INPUT_TEXT": (VOUCHER_INPUT_TEXT, VOUCHER_INPUT_TEXT),
}


def __getattr__(name: str):
    """Resolve COLOR_*/TEXT_* module attributes to the active theme's hex.

    PEP 562 module __getattr__: only called when the name is not a real
    module global, so theme.py's token table (which reads the literals
    directly) is unaffected, while UI screens referencing
    ``config.COLOR_BG_SECONDARY`` get the active-theme value.
    """
    pair = _THEME_ATTRS.get(name)
    if pair is not None:
        dark_value, light_value = pair
        return dark_value if _active_theme != "light" else light_value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

