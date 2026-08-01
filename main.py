"""
MyXpense Main Application Entry Point
Built with CustomTkinter and SQLite for modern Windows Desktop Personal Finance Management.
"""

import customtkinter as ctk

from config import (
    APP_NAME,
    APPEARANCE_MODE,
    COLOR_THEME,
    COLOR_BG_PRIMARY,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
)
from database.database import Database
from ui.reports import show_reports


class MyXpenseApp(ctk.CTk):
    """Main Application Window for MyXpense."""

    def __init__(self) -> None:
        super().__init__()

        # 1. Appearance & Theme Setup
        ctk.set_appearance_mode(APPEARANCE_MODE)
        ctk.set_default_color_theme(COLOR_THEME)

        # 2. Window Configuration
        self.title(APP_NAME)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.configure(fg_color=COLOR_BG_PRIMARY)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 3. Initialize Database
        self.db = Database()

        # 4. Configure Grid Layout for Main Window (Strict grid usage, no pack)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 5. Main Root Container Frame
        self.container = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_PRIMARY,
            corner_radius=0
        )
        self.container.grid(row=0, column=0, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkFrame(self.container, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        self.content_frame = ctk.CTkFrame(self.container, corner_radius=0, fg_color=COLOR_BG_PRIMARY)
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.current_view = None

        self._build_navigation()
        self.show_home()

    def _build_navigation(self) -> None:
        """Build main navigation."""
        title = ctk.CTkLabel(self.sidebar, text=APP_NAME, font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(padx=16, pady=(20, 8), anchor="w")

        subtitle = ctk.CTkLabel(self.sidebar, text="Navigation", font=ctk.CTkFont(size=12))
        subtitle.pack(padx=16, pady=(0, 14), anchor="w")

        ctk.CTkButton(self.sidebar, text="Dashboard", command=self.show_home).pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(self.sidebar, text="Reports", command=self.show_reports).pack(fill="x", padx=16, pady=(0, 8))

    def _clear_content(self) -> None:
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _set_view(self, widget) -> None:
        self._clear_content()
        self.current_view = widget
        widget.pack(fill="both", expand=True)

    def show_home(self) -> None:
        """Show the default home view."""
        self._clear_content()
        home = ctk.CTkFrame(self.content_frame, fg_color=COLOR_BG_PRIMARY)
        home.grid_rowconfigure(0, weight=1)
        home.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(home, text="Welcome to MyXpense", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(80, 12))
        ctk.CTkLabel(home, text="Select Reports from the navigation to open the report hub.").pack()
        self._set_view(home)

    def show_reports(self) -> None:
        """Open the Reports hub in the main content area."""
        self._clear_content()
        reports_view = show_reports(self.content_frame, 1)
        self.current_view = reports_view
        reports_view.main_frame.pack(fill="both", expand=True)

    def _on_close(self) -> None:
        """Gracefully handle window close."""
        self.destroy()


def main() -> None:
    """Application launch entry point."""
    app = MyXpenseApp()
    app.mainloop()


if __name__ == "__main__":
    main()

