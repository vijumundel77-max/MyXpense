import customtkinter as ctk

from config import APP_NAME, FONT_FAMILY, FONT_TITLE_SIZE
from database import Database
from ui.company import CompanyFrame


class MastersFrame(ctk.CTkFrame):

    def __init__(self, parent, db: Database):
        super().__init__(parent)

        self.parent = parent
        self.db = db

        self.pack(fill="both", expand=True)

        self.lbl_title = ctk.CTkLabel(
            self,
            text="Masters",
            font=(FONT_FAMILY, FONT_TITLE_SIZE, "bold"),
        )
        self.lbl_title.pack(pady=(20, 20))

        self.btn_frame = ctk.CTkFrame(self)
        self.btn_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.btn_company = ctk.CTkButton(
            self.btn_frame,
            text="Company",
            width=180,
            height=50,
            command=self.open_company,
        )
        self.btn_company.grid(row=0, column=0, padx=15, pady=15)

        self.btn_group = ctk.CTkButton(
            self.btn_frame,
            text="Group",
            width=180,
            height=50,
        )
        self.btn_group.grid(row=0, column=1, padx=15, pady=15)

        self.btn_ledger = ctk.CTkButton(
            self.btn_frame,
            text="Ledger",
            width=180,
            height=50,
        )
        self.btn_ledger.grid(row=0, column=2, padx=15, pady=15)

        self.btn_category = ctk.CTkButton(
            self.btn_frame,
            text="Category",
            width=180,
            height=50,
        )
        self.btn_category.grid(row=1, column=0, padx=15, pady=15)

        self.btn_item = ctk.CTkButton(
            self.btn_frame,
            text="Item",
            width=180,
            height=50,
        )
        self.btn_item.grid(row=1, column=1, padx=15, pady=15)

        self.btn_unit = ctk.CTkButton(
            self.btn_frame,
            text="Unit",
            width=180,
            height=50,
        )
        self.btn_unit.grid(row=1, column=2, padx=15, pady=15)

        self.btn_bank = ctk.CTkButton(
            self.btn_frame,
            text="Bank",
            width=180,
            height=50,
        )
        self.btn_bank.grid(row=2, column=0, padx=15, pady=15)

        self.btn_user = ctk.CTkButton(
            self.btn_frame,
            text="User",
            width=180,
            height=50,
        )
        self.btn_user.grid(row=2, column=1, padx=15, pady=15)

    def open_company(self):
        self.destroy()
        CompanyFrame(
            self.parent,
            db=self.db,
            on_back=self._show_masters,
        )

    def _show_masters(self):
        for widget in self.parent.winfo_children():
            widget.destroy()
        MastersFrame(self.parent, db=self.db)
