"""
MyXpense Configuration Module
Centralized settings, constants, dark theme design tokens, and application metadata.
"""

from pathlib import Path

# ==========================================
# APP METADATA
# ==========================================
APP_NAME = "MyXpense"
APP_SUBTITLE = "Personal Finance & Expense Manager"
APP_VERSION = "1.0.0"

# ==========================================
# PATHS
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "database"
DATABASE_NAME = "myxpense.db"
DATABASE_PATH = DATABASE_DIR / DATABASE_NAME
ASSETS_DIR = BASE_DIR / "assets"

# Ensure directories exist
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# WINDOW & LAYOUT CONFIGURATION
# ==========================================
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 820
WINDOW_MIN_WIDTH = 1100
WINDOW_MIN_HEIGHT = 680

SIDEBAR_WIDTH = 240
HEADER_HEIGHT = 70

# ==========================================
# THEME & DESIGN TOKENS
# ==========================================
APPEARANCE_MODE = "dark"
COLOR_THEME = "blue"

# Dark Theme Color Palette (Modern Slate / Material Dark)
COLOR_BG_PRIMARY = "#0F172A"      # Main Window Dark Background (Slate 900)
COLOR_BG_SECONDARY = "#1E293B"    # Cards & Panels Background (Slate 800)
COLOR_BG_TERTIARY = "#334155"     # Inputs, Hover & Borders (Slate 700)
COLOR_CARD_BORDER = "#334155"     # Card Border Color

# Accent Colors
COLOR_PRIMARY = "#3B82F6"         # Vibrant Blue Accent (Blue 500)
COLOR_PRIMARY_HOVER = "#2563EB"   # Primary Hover (Blue 600)
COLOR_PRIMARY_LIGHT = "#1D4ED8"   # Pressed State

# Text Colors
COLOR_TEXT_PRIMARY = "#F8FAFC"    # Primary White Text (Slate 50)
COLOR_TEXT_SECONDARY = "#94A3B8"  # Muted Text (Slate 400)
COLOR_TEXT_MUTED = "#64748B"      # Dark Muted Text (Slate 500)

# Status & Financial Indicators
COLOR_INCOME = "#10B981"          # Emerald Green 500
COLOR_INCOME_HOVER = "#059669"
COLOR_EXPENSE = "#EF4444"         # Crimson Red 500
COLOR_EXPENSE_HOVER = "#DC2626"
COLOR_TRANSFER = "#8B5CF6"        # Purple Accent 500
COLOR_TRANSFER_HOVER = "#7C3AED"
COLOR_WARNING = "#F59E0B"         # Amber Warning 500

# Widget Radius Settings
CARD_CORNER_RADIUS = 14
BUTTON_CORNER_RADIUS = 10
INPUT_CORNER_RADIUS = 8

# ==========================================
# TYPOGRAPHY
# ==========================================
FONT_FAMILY = "Segoe UI"  # Windows Native Clean Font

FONT_HERO = (FONT_FAMILY, 24, "bold")
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 16, "bold")
FONT_BODY_BOLD = (FONT_FAMILY, 14, "bold")
FONT_BODY = (FONT_FAMILY, 14, "normal")
FONT_SMALL = (FONT_FAMILY, 12, "normal")
FONT_SMALL_BOLD = (FONT_FAMILY, 12, "bold")

# ==========================================
# FINANCIAL CONSTANTS
# ==========================================
CURRENCY_SYMBOL = "₹"
DATE_DISPLAY_FORMAT = "%d %b %Y"
TIME_DISPLAY_FORMAT = "%I:%M %p"
DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DB_DATE_FORMAT = "%Y-%m-%d"

