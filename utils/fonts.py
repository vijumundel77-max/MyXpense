"""
Expenzo — Inter font loader & cached CTkFont factory.

Loads the bundled Inter TTFs from assets/fonts so the app can use the Inter
typeface without it being installed on the system. On Windows the fonts are
registered privately into the process via GDI ``AddFontResourceExW``
(``FR_PRIVATE``), which makes the "Inter" family visible to Tk without
installing it system-wide. Falls back to the system font (Segoe UI) when the
font files are missing or registration fails, so the app never breaks.

Fonts are cached by (size, weight) so every CTkFont is created once.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Dict, Optional, Tuple

import customtkinter as ctk

import config

# Inter weights we bundle (SIL OFL licensed).
_WEIGHT_FILES = {
    "regular": "Inter-Regular.ttf",
    "medium": "Inter-Medium.ttf",
    "semibold": "Inter-SemiBold.ttf",
    "bold": "Inter-Bold.ttf",
}

_font_dir: Optional[Path] = None
_available: bool = False
_cache: Dict[Tuple[int, str], ctk.CTkFont] = {}

FR_PRIVATE = 0x10


def _fonts_dir() -> Path:
    global _font_dir
    if _font_dir is None:
        _font_dir = Path(config.ASSETS_DIR) / "fonts"
    return _font_dir


def _register_windows_gdi() -> int:
    """Register bundled TTFs privately into the process via GDI.

    Returns the number of fonts successfully registered. Uses
    ``AddFontResourceExW`` with ``FR_PRIVATE`` so Tk (and only this process)
    can use the Inter family without installing it system-wide.
    """
    try:
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        add = gdi32.AddFontResourceExW
        add.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
        add.restype = ctypes.c_int
    except Exception:
        return 0

    loaded = 0
    for filename in _WEIGHT_FILES.values():
        path = _fonts_dir() / filename
        if not path.exists():
            continue
        try:
            if add(str(path), FR_PRIVATE, None) > 0:
                loaded += 1
        except Exception:
            continue
    return loaded


def register_fonts() -> bool:
    """Register the bundled Inter faces so Tk can use the family.

    Returns True when Inter is available, False when falling back to the
    system font. On Windows uses GDI private registration; on other platforms
    (or if that fails) falls back gracefully.
    """
    global _available
    if _available:
        return True
    try:
        if _register_windows_gdi() >= 1:
            _available = True
            return True
    except Exception:
        pass
    return False


def font(size: int = config.FONT_BODY_SIZE, weight: str = "normal") -> ctk.CTkFont:
    """Return a cached CTkFont for the given size and weight.

    ``weight`` is one of "normal" (400), "medium" (500), "semibold" (600) or
    "bold" (700). Falls back to Segoe UI when Inter is unavailable.
    """
    norm = weight.lower()
    if norm not in ("normal", "medium", "semibold", "bold"):
        norm = "normal"
    key = (size, norm)
    if key in _cache:
        return _cache[key]
    family = "Inter" if _available else config.FONT_FAMILY
    bold = norm in ("semibold", "bold")
    f = ctk.CTkFont(family=family, size=size, weight="bold" if bold else "normal")
    _cache[key] = f
    return f
