"""
Expenzo — Accounting Application Shell
Modern sidebar navigation, company-aware header, theme toggle, view routing.
"""
from __future__ import annotations

import sys
from pathlib import Path
import tkinter as tk

import customtkinter as ctk

import config
from config import (
    APP_NAME,
    APP_SUBTITLE,
    APPEARANCE_MODE,
    COLOR_BG_PRIMARY,
    COLOR_BG_SECONDARY,
    COLOR_BG_TERTIARY,
    COLOR_PRIMARY,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    SIDEBAR_WIDTH,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
)
from database.database import db
from services.company_service import CompanyService
from ui.dashboard import DashboardFrame
from ui.reports import show_reports
from ui.masters import MastersFrame
from ui.vouchers import VouchersFrame
from ui.settings import SettingsFrame
from utils import keyboard, theme


def _sidebar_accent(dark_value: str, light_value: str) -> str:
    """Resolve a sidebar accent token to the active theme's value."""
    return dark_value if ctk.get_appearance_mode() != "Light" else light_value


def _application_icon() -> str | None:
    """Resolve the bundled application icon (packaged build or dev tree).

    Returns the path to the .ico when present, else None so a dev run without
    the icon asset still launches normally.
    """
    candidates = []
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: runtime data is next to the executable.
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "expenzo.ico")
        # PyInstaller onefile: data is unpacked under sys._MEIPASS.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / "expenzo.ico")
    else:
        candidates.append(config.BASE_DIR / "assets" / "expenzo.ico")
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


class SidebarButton(ctk.CTkButton):
    """Icon + label sidebar button with hover/active states.

    The active item uses the theme-aware sidebar accent tokens so its
    background/text/icon always contrast properly in both Light and Dark.
    """

    def __init__(self, master, text: str, icon: str, command=None, active: bool = False):
        self.is_active = active
        accent = _sidebar_accent(config.SIDEBAR_ACCENT, config.LIGHT_SIDEBAR_ACCENT)
        accent_hover = _sidebar_accent(config.SIDEBAR_ACCENT_HOVER, config.LIGHT_SIDEBAR_ACCENT_HOVER)
        accent_text = _sidebar_accent(config.SIDEBAR_ACCENT_TEXT, config.LIGHT_SIDEBAR_ACCENT_TEXT)
        super().__init__(
            master,
            text=f"  {icon}  {text}",
            command=command,
            anchor="w",
            height=36,
            corner_radius=8,
            fg_color=accent if active else "transparent",
            hover_color=accent_hover if active else config.COLOR_BG_TERTIARY,
            text_color=accent_text if active else config.COLOR_TEXT_PRIMARY,
            text_color_disabled=config.COLOR_TEXT_SECONDARY,
            font=ctk.CTkFont(size=13, weight="bold" if active else "normal"),
        )


class ExpenzoApp(ctk.CTk):
    """Main Expenzo application window."""

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode(APPEARANCE_MODE)
        ctk.set_default_color_theme(config.COLOR_THEME)

        self.title(f"{APP_NAME} — {APP_SUBTITLE}")
        icon_path = _application_icon()
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                # Icon is cosmetic; never block startup if it cannot load.
                pass
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.configure(fg_color=COLOR_BG_PRIMARY)

        # Company context (threaded to every view).
        self.company_service = CompanyService(db)
        db.seed_expenzo_defaults()
        self.current_company_id = self._resolve_company_id()
        # Load available companies for quick switcher
        self._load_available_companies()
        # Ensure the 30 default Chart-of-Accounts groups exist for this company
        # (idempotent; existing groups are preserved).
        from services.group_service import group_service
        group_service.seed_default_groups(self.current_company_id)

        self._build_shell()
        self._sidebar_section_labels: list[ctk.CTkLabel] = []
        self._build_sidebar()
        self._build_header()
        self._build_navigation()
        theme.apply_theme(self, mode=APPEARANCE_MODE)
        self._apply_chrome()

        # Keyboard-first support: global shortcuts + maximize to work area.
        keyboard.install_shortcuts(self, lambda: self.current_view)
        self._maximize_to_work_area()
        self.show_dashboard()

    # ------------------------------------------------------------------ #
    # window behavior
    # ------------------------------------------------------------------ #
    def _maximize_to_work_area(self) -> None:
        """Maximize the window to the available desktop work area on launch
        (never larger than the usable screen)."""
        try:
            self.update_idletasks()
            if self.tk.call("tk", "windowingsystem") == "win32":
                # 'zoomed' is the Windows-native maximized state; it respects
                # the taskbar work area and keeps the standard controls.
                self.state("zoomed")
            else:
                # Fallback for other platforms: fill the screen work area.
                w = self.winfo_screenwidth()
                h = self.winfo_screenheight()
                self.geometry(f"{w}x{h}+0+0")
                self.state("zoomed")
        except Exception:
            # Never let a maximization hiccup prevent the app from starting.
            self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

    # ------------------------------------------------------------------ #
    # company context
    # ------------------------------------------------------------------ #
    def _resolve_company_id(self) -> int:
        """Pick the active company: the first Expenzo company row, else 1."""
        row = db.fetch_one("SELECT id FROM companies ORDER BY id LIMIT 1")
        return row["id"] if row else 1

    def _company_name(self) -> str:
        row = db.fetch_one("SELECT name FROM companies WHERE id = ?", (self.current_company_id,))
        return row["name"] if row else "No Company"

    def _load_available_companies(self) -> None:
        """Fetch companies safely (handles missing is_active column or different table name)."""
        from database.database import db
        rows = []
        # Try preferred query with is_active on 'companies'
        try:
            rows = db.fetch_all("SELECT id, name FROM companies WHERE is_active = 1 ORDER BY name ASC")
        except Exception:
            # Fallback 1: same table without is_active
            try:
                rows = db.fetch_all("SELECT id, name FROM companies ORDER BY name ASC")
            except Exception:
                # Fallback 2: alternate table name 'company'
                try:
                    rows = db.fetch_all("SELECT id, name FROM company ORDER BY name ASC")
                except Exception:
                    rows = []

        self.company_map = {}
        self.company_names = []
        for r in rows:
            display = f"🏢  {r['name']}"
            self.company_map[display] = r['id']
            self.company_names.append(display)

        # Ensure current company is in list (it should be)
        current_display = f"🏢  {self._company_name()}"
        if current_display not in self.company_names:
            self.company_names.insert(0, current_display)
            self.company_map[current_display] = self.current_company_id

        # set variable default
        self.company_var = tk.StringVar(value=current_display)

    def _on_quick_company_change(self, selected_display: str) -> None:
        new_company_id = self.company_map.get(selected_display)
        if new_company_id and new_company_id != self.current_company_id:
            # 1. Update global date control
            from services.date_control_service import date_control
            date_control.set_company(new_company_id)

            # 2. Switch company context and refresh view
            self.switch_company(new_company_id)
            # Title update
            self.title(f"{APP_NAME} — {selected_display}")

    def switch_company(self, company_id: int) -> None:
        self.current_company_id = int(company_id)
        # Re-open the current view so it reflects the new company.
        if self.current_view_name:
            getattr(self, f"show_{self.current_view_name}")()
        else:
            self.show_dashboard()

    # ------------------------------------------------------------------ #
    # shell layout
    # ------------------------------------------------------------------ #
    def _build_shell(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.container = ctk.CTkFrame(self, fg_color=COLOR_BG_PRIMARY, corner_radius=0)
        self.container.grid(row=0, column=0, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkFrame(self.container, width=SIDEBAR_WIDTH, corner_radius=0,
                                    fg_color=COLOR_BG_SECONDARY)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        self.right_column = ctk.CTkFrame(self.container, fg_color=COLOR_BG_PRIMARY, corner_radius=0)
        self.right_column.grid(row=0, column=1, sticky="nsew")
        self.right_column.grid_rowconfigure(1, weight=1)
        self.right_column.grid_columnconfigure(0, weight=1)

        self.header = ctk.CTkFrame(self.right_column, fg_color=COLOR_BG_SECONDARY, corner_radius=0,
                                   height=config.HEADER_HEIGHT)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_propagate(False)
        self.header.grid_columnconfigure(1, weight=1)

        self.content_frame = ctk.CTkFrame(self.right_column, corner_radius=0, fg_color=COLOR_BG_PRIMARY)
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

    def _sidebar_section(self, title: str) -> None:
        label = ctk.CTkLabel(
            self.sidebar,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        label.pack(padx=16, pady=(14, 4), anchor="w")
        self._sidebar_section_labels.append(label)

    def _build_sidebar(self) -> None:
        brand_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_row.pack(fill="x", padx=16, pady=(20, 2), anchor="w")

        logo = ctk.CTkLabel(
            brand_row,
            text="E",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#FFFFFF",
            fg_color=COLOR_PRIMARY,
            corner_radius=8,
            width=38,
            height=38,
        )
        logo.pack(side="left")

        brand_text = ctk.CTkFrame(brand_row, fg_color="transparent")
        brand_text.pack(side="left", padx=(12, 0))
        self._brand_name = ctk.CTkLabel(
            brand_text,
            text=APP_NAME,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self._brand_name.pack(anchor="w")
        self._brand_subtitle = ctk.CTkLabel(
            brand_text,
            text=APP_SUBTITLE,
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self._brand_subtitle.pack(anchor="w")

        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLOR_BG_TERTIARY).pack(
            fill="x", padx=16, pady=(14, 6)
        )

        self._sidebar_buttons: list[SidebarButton] = []

        self._sidebar_section("OVERVIEW")
        self._add_sidebar_button("Dashboard", "▦", self.show_dashboard, active=True)

        self._sidebar_section("TRANSACTIONS")
        self._add_sidebar_button("Vouchers", "▤", self.show_vouchers)

        self._sidebar_section("MASTERS")
        self._add_sidebar_button("Masters", "▧", self.show_masters)

        self._sidebar_section("REPORTS")
        self._add_sidebar_button("Reports", "▥", self.show_reports)

        self._sidebar_section("TOOLS")
        self._add_sidebar_button("Settings", "⚙", self.show_settings)

        self._wire_sidebar_keyboard()

    def _add_sidebar_button(self, text: str, icon: str, command, active: bool = False) -> None:
        button = SidebarButton(self.sidebar, text, icon, command, active=active)
        button.pack(fill="x", padx=12, pady=2)
        self._sidebar_buttons.append(button)

    def _set_active_nav(self, name: str) -> None:
        """Highlight the nav item matching the current view name."""
        mapping = {
            "dashboard": 0,
            "vouchers": 1,
            "masters": 2,
            "reports": 3,
            "settings": 4,
        }
        active_index = mapping.get(name, -1)
        accent = _sidebar_accent(config.SIDEBAR_ACCENT, config.LIGHT_SIDEBAR_ACCENT)
        accent_hover = _sidebar_accent(config.SIDEBAR_ACCENT_HOVER, config.LIGHT_SIDEBAR_ACCENT_HOVER)
        accent_text = _sidebar_accent(config.SIDEBAR_ACCENT_TEXT, config.LIGHT_SIDEBAR_ACCENT_TEXT)
        for index, button in enumerate(self._sidebar_buttons):
            is_active = index == active_index
            if button.is_active != is_active:
                button.is_active = is_active
                button.configure(
                    fg_color=accent if is_active else "transparent",
                    text_color=accent_text if is_active else config.COLOR_TEXT_PRIMARY,
                    hover_color=accent_hover if is_active else config.COLOR_BG_TERTIARY,
                    font=ctk.CTkFont(size=13, weight="bold" if is_active else "normal"),
                )

    def _wire_sidebar_keyboard(self) -> None:
        """Arrow-key navigation across sidebar buttons (Up/Down move focus,
        Enter activates the focused button)."""
        buttons = self._sidebar_buttons

        def _move(delta: int) -> None:
            if not buttons:
                return
            try:
                current = self.focus_get()
                index = next((i for i, b in enumerate(buttons) if b == current), -1)
            except Exception:
                index = -1
            next_index = (index + delta) % len(buttons) if index >= 0 else 0
            buttons[next_index].focus_set()

        def _focus_next(_event=None):
            _move(1)
            return "break"

        def _focus_prev(_event=None):
            _move(-1)
            return "break"

        # Arrow keys move between sidebar buttons only when a sidebar button
        # currently has focus (so we never steal arrow keys from tables).
        def _on_down(_event=None):
            if self.focus_get() in buttons:
                _move(1)
                return "break"
            return None

        def _on_up(_event=None):
            if self.focus_get() in buttons:
                _move(-1)
                return "break"
            return None

        for button in buttons:
            button.bind("<Down>", _on_down)
            button.bind("<Up>", _on_up)
            button.bind("<Return>", lambda _e, b=button: (b.invoke(), "break")[1])

    def _build_header(self) -> None:
        self._header_chip = ctk.CTkLabel(
            self.header,
            text="Expenzo Accounting",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_BG_TERTIARY,
            corner_radius=6,
            text_color=COLOR_TEXT_PRIMARY,
            padx=10,
            pady=3,
        )
        self._header_chip.pack(side="left", padx=(20, 12))

        # Quick company switcher dropdown (self.company_var already created in _load_available_companies)
        self.company_dropdown = ctk.CTkOptionMenu(
            self.header,
            values=self.company_names,
            variable=self.company_var,
            command=self._on_quick_company_change,
            width=180,
            height=32,
            corner_radius=8,
            fg_color=("#E2E8F0", "#16223E"),
            button_color=("#CBD5E1", "#1E3A8A"),
            button_hover_color=("#94A3B8", "#1E3A8A"),
            text_color=("#0F172A", "#60A5FA"),
            font=ctk.CTkFont(size=13, weight="bold"),
            dropdown_fg_color=("#F8FAFC", "#0F172A"),
            dropdown_text_color=("#0F172A", "#E2E8F0"),
            dropdown_hover_color=("#E2E8F0", "#1E3A8A"),
        )
        self.company_dropdown.pack(side="right", padx=(0, 20))

        self.theme_toggle = ctk.CTkButton(
            self.header,
            text="☀ Light" if ctk.get_appearance_mode() == "Light" else "🌙 Dark",
            width=92,
            height=32,
            corner_radius=8,
            command=self._toggle_theme,
        )
        self.theme_toggle.pack(side="right", padx=(0, 12))

    def _toggle_theme(self) -> None:
        current = ctk.get_appearance_mode()
        new_mode = "light" if current == "Dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        theme.apply_theme(self, mode="light" if new_mode == "light" else "dark")
        self._apply_chrome()
        self._refresh_theme_toggle(new_mode)

    def _refresh_theme_toggle(self, mode: str) -> None:
        # Always reflect the ACTIVE theme (the one now in effect), not the
        # theme that would be activated next.
        active = "light" if str(mode).lower() == "light" else "dark"
        self.theme_toggle.configure(text="☀ Light" if active == "light" else "🌙 Dark")

    def _apply_chrome(self) -> None:
        """Refresh theme-dependent colors across the whole widget tree.

        Runs the shared palette walker (re-colors every existing ctk widget
        on every screen), then re-applies the shell chrome that uses
        non-palette markers (transparent fills, accent text) explicitly.
        """
        # Re-tint every existing widget (all open screens) to the active theme.
        theme.apply_palette(self)

        # If the current view has a refresh_theme method, call it (e.g., Dashboard).
        if self.current_view and hasattr(self.current_view, "refresh_theme"):
            try:
                self.current_view.refresh_theme()
            except Exception:
                pass

        dark = ctk.get_appearance_mode() != "Light"
        text_primary = config.COLOR_TEXT_PRIMARY if dark else config.LIGHT_TEXT_PRIMARY
        text_secondary = config.COLOR_TEXT_SECONDARY if dark else config.LIGHT_TEXT_SECONDARY
        bg_tertiary = config.COLOR_BG_TERTIARY if dark else config.LIGHT_BG_TERTIARY

        self.configure(fg_color=config.COLOR_BG_PRIMARY if dark else config.LIGHT_BG_PRIMARY)
        self.sidebar.configure(fg_color=config.COLOR_BG_SECONDARY if dark else config.LIGHT_BG_SECONDARY)
        self.header.configure(fg_color=config.COLOR_BG_SECONDARY if dark else config.LIGHT_BG_SECONDARY)

        # Sidebar section labels (cached in _build_sidebar).
        for label in self._sidebar_section_labels:
            label.configure(text_color=text_secondary)

        # Sidebar buttons (text color + active fill adapt to the theme).
        accent = _sidebar_accent(config.SIDEBAR_ACCENT, config.LIGHT_SIDEBAR_ACCENT)
        accent_hover = _sidebar_accent(config.SIDEBAR_ACCENT_HOVER, config.LIGHT_SIDEBAR_ACCENT_HOVER)
        accent_text = _sidebar_accent(config.SIDEBAR_ACCENT_TEXT, config.LIGHT_SIDEBAR_ACCENT_TEXT)
        for button in self._sidebar_buttons:
            button.configure(
                text_color=accent_text if button.is_active else text_primary,
                text_color_disabled=text_secondary,
                fg_color=accent if button.is_active else "transparent",
                hover_color=accent_hover if button.is_active else bg_tertiary,
            )

        # Brand block labels (cached in _build_sidebar).
        self._brand_name.configure(text_color=text_primary)
        self._brand_subtitle.configure(text_color=text_secondary)

        # Header chrome.
        self._header_chip.configure(text_color=text_primary, fg_color=bg_tertiary)
        # Dropdown uses its own fg/button colors; ensure text color matches theme
        try:
            self.company_dropdown.configure(text_color=("#0F172A", "#60A5FA"))
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # navigation
    # ------------------------------------------------------------------ #
    def _build_navigation(self) -> None:
        self.current_view = None
        self.current_view_name: str | None = None
        self._nav_history: list[str] = []

    def _clear_content(self) -> None:
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _set_view(self, widget, name: str, view_object=None) -> None:
        # Callers clear the content frame before constructing (the view
        # classes pack themselves in __init__), so no clear here.
        self.current_view = view_object or widget
        self.current_view_name = name
        if not self._nav_history or self._nav_history[-1] != name:
            self._nav_history.append(name)
            if len(self._nav_history) > 20:
                self._nav_history.pop(0)
        widget.pack(fill="both", expand=True)

    def on_keyboard_back(self) -> None:
        """Esc: return to the previous top-level screen (never quits)."""
        if len(self._nav_history) >= 2:
            previous = self._nav_history[-2]
            self._nav_history = self._nav_history[:-2] + [previous]
            method = getattr(self, f"show_{previous}", None)
            if callable(method):
                method()

    def show_dashboard(self) -> None:
        self._clear_content()
        self._set_view(
            DashboardFrame(self.content_frame, company_id=self.current_company_id),
            "dashboard",
        )
        self._set_active_nav("dashboard")

    def show_vouchers(self) -> None:
        self._clear_content()
        self._set_view(
            VouchersFrame(self.content_frame, company_id=self.current_company_id),
            "vouchers",
        )
        self._set_active_nav("vouchers")

    def show_masters(self) -> None:
        self._clear_content()
        self._set_view(
            MastersFrame(
                self.content_frame,
                db=db,
                company_id=self.current_company_id,
                company_service=self.company_service,
                on_company_switched=self.switch_company,
            ),
            "masters",
        )
        self._set_active_nav("masters")

    def show_reports(self) -> None:
        self._clear_content()
        reports_view = show_reports(self.content_frame, self.current_company_id)
        self.current_view = reports_view
        self.current_view_name = "reports"
        reports_view.main_frame.pack(fill="both", expand=True)
        self._set_active_nav("reports")

    def show_settings(self) -> None:
        self._clear_content()
        self._set_view(SettingsFrame(self.content_frame), "settings")
        self._set_active_nav("settings")


def main() -> None:
    """Application launch entry point."""
    app = ExpenzoApp()
    theme.apply_theme(app)
    app.mainloop()


if __name__ == "__main__":
    main()
