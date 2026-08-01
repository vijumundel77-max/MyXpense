import customtkinter as ctk
from tkinter import messagebox


class DashboardFrame(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent)

        self.pack(fill="both", expand=True)

        # Title
        self.lbl_title = ctk.CTkLabel(
            self,
            text="Dashboard",
            font=("Arial", 26, "bold")
        )
        self.lbl_title.pack(pady=(30, 10))

        # Welcome
        self.lbl_welcome = ctk.CTkLabel(
            self,
            text="Welcome to MyXpense",
            font=("Arial", 18)
        )
        self.lbl_welcome.pack()

        # Statistics Frame
        self.stats_frame = ctk.CTkFrame(self)
        self.stats_frame.pack(fill="x", padx=20, pady=30)

        self.lbl_cash = ctk.CTkLabel(
            self.stats_frame,
            text="Cash Balance\n₹0.00",
            font=("Arial", 18)
        )
        self.lbl_cash.pack(side="left", expand=True, padx=20, pady=20)

        self.lbl_bank = ctk.CTkLabel(
            self.stats_frame,
            text="Bank Balance\n₹0.00",
            font=("Arial", 18)
        )
        self.lbl_bank.pack(side="left", expand=True, padx=20, pady=20)

        self.lbl_ledgers = ctk.CTkLabel(
            self.stats_frame,
            text="Ledgers\n0",
            font=("Arial", 18)
        )
        self.lbl_ledgers.pack(side="left", expand=True, padx=20, pady=20)

        # Reports shortcut
        self.reports_card = ctk.CTkFrame(self, corner_radius=12)
        self.reports_card.pack(fill="x", padx=20, pady=(0, 20))

        self.reports_title = ctk.CTkLabel(
            self.reports_card,
            text="Reports Hub",
            font=("Arial", 20, "bold")
        )
        self.reports_title.pack(pady=(16, 4))

        self.reports_desc = ctk.CTkLabel(
            self.reports_card,
            text="Open Party Ledger, Outstanding, Ageing, Cash Book, and Account Book.",
            font=("Arial", 14)
        )
        self.reports_desc.pack(pady=(0, 12))

        self.btn_reports = ctk.CTkButton(
            self.reports_card,
            text="Open Reports",
            command=self._open_reports
        )
        self.btn_reports.pack(pady=(0, 16))

    def _open_reports(self):
        """Open the Reports Hub via the main window navigation."""
        app = self.winfo_toplevel()
        if hasattr(app, "show_reports"):
            app.show_reports()
        else:
            messagebox.showinfo("Reports", "Reports hub is unavailable in this view.")
