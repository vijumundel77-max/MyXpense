import customtkinter as ctk
from tkinter import messagebox

from config import (
    APP_NAME,
    FONT_FAMILY,
    FONT_TITLE_SIZE,
    FONT_BODY_SIZE,
    FORM_ADDRESS_HEIGHT,
    FORM_ENTRY_WIDTH,
    FORM_MOBILE_WIDTH,
)
from database import Database
from models.company import Company
from services.company_service import CompanyService, CompanyServiceError


class CompanyFrame(ctk.CTkFrame):

    def __init__(self, parent, db: Database, on_back=None):
        super().__init__(parent)

        self.db = db
        self.on_back = on_back
        self.service = CompanyService(db)
        self.current_company: Company | None = None

        self.pack(fill="both", expand=True, padx=20, pady=20)

        self._build_header()
        self._build_form()
        self._build_status()
        self._build_buttons()
        self._load_company()
        self._update_button_states()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(10, 20))

        ctk.CTkLabel(
            header,
            text="Company Master",
            font=(FONT_FAMILY, FONT_TITLE_SIZE, "bold"),
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Back",
            width=100,
            command=self._handle_back,
        ).pack(side="right")

    def _build_form(self):
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(
            form,
            text="Company Name *",
            font=(FONT_FAMILY, FONT_BODY_SIZE),
        ).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.entry_name = ctk.CTkEntry(form, width=FORM_ENTRY_WIDTH)
        self.entry_name.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(
            form,
            text="Address",
            font=(FONT_FAMILY, FONT_BODY_SIZE),
        ).grid(row=1, column=0, padx=10, pady=10, sticky="nw")

        self.entry_address = ctk.CTkTextbox(
            form,
            width=FORM_ENTRY_WIDTH,
            height=FORM_ADDRESS_HEIGHT,
        )
        self.entry_address.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(
            form,
            text="Mobile",
            font=(FONT_FAMILY, FONT_BODY_SIZE),
        ).grid(row=2, column=0, padx=10, pady=10, sticky="w")

        self.entry_mobile = ctk.CTkEntry(form, width=FORM_MOBILE_WIDTH)
        self.entry_mobile.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(
            form,
            text="Email",
            font=(FONT_FAMILY, FONT_BODY_SIZE),
        ).grid(row=3, column=0, padx=10, pady=10, sticky="w")

        self.entry_email = ctk.CTkEntry(form, width=FORM_ENTRY_WIDTH)
        self.entry_email.grid(row=3, column=1, padx=10, pady=10, sticky="w")

    def _build_status(self):
        self.lbl_status = ctk.CTkLabel(
            self,
            text="",
            font=(FONT_FAMILY, FONT_BODY_SIZE),
            text_color="#4CAF50",
        )
        self.lbl_status.pack(pady=(5, 0))

    def _build_buttons(self):
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=20)

        self.btn_save = ctk.CTkButton(
            button_frame,
            text="Save",
            width=120,
            command=self._handle_save,
        )
        self.btn_save.pack(side="left", padx=10)

        self.btn_update = ctk.CTkButton(
            button_frame,
            text="Update",
            width=120,
            command=self._handle_update,
        )
        self.btn_update.pack(side="left", padx=10)

        self.btn_delete = ctk.CTkButton(
            button_frame,
            text="Delete",
            width=120,
            fg_color="#B71C1C",
            hover_color="#8E0000",
            command=self._handle_delete,
        )
        self.btn_delete.pack(side="left", padx=10)

        self.btn_clear = ctk.CTkButton(
            button_frame,
            text="Clear",
            width=120,
            fg_color="transparent",
            border_width=1,
            command=self._handle_clear,
        )
        self.btn_clear.pack(side="left", padx=10)

    def _get_form_data(self) -> tuple[str, str, str, str]:
        address = self.entry_address.get("1.0", "end-1c")
        return (
            self.entry_name.get(),
            address,
            self.entry_mobile.get(),
            self.entry_email.get(),
        )

    def _set_form_data(
        self,
        company_name: str = "",
        address: str = "",
        mobile: str = "",
        email: str = "",
    ):
        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, company_name)

        self.entry_address.delete("1.0", "end")
        if address:
            self.entry_address.insert("1.0", address)

        self.entry_mobile.delete(0, "end")
        self.entry_mobile.insert(0, mobile)

        self.entry_email.delete(0, "end")
        self.entry_email.insert(0, email)

    def _show_status(self, message: str, is_error: bool = False):
        color = "#F44336" if is_error else "#4CAF50"
        self.lbl_status.configure(text=message, text_color=color)

    def _load_company(self):
        try:
            self.current_company = self.service.load_company()
        except Exception as exc:
            self._show_status(f"Failed to load company: {exc}", is_error=True)
            return

        if self.current_company is None:
            self._set_form_data()
            self._show_status("No company record found. Enter details and save.")
            return

        self._populate_form(self.current_company)
        self._show_status("Company loaded successfully.")

    def _populate_form(self, company: Company):
        self._set_form_data(
            company.company_name,
            company.address,
            company.mobile,
            company.email,
        )

    def _update_button_states(self):
        has_record = self.current_company is not None
        self.btn_save.configure(state="disabled" if has_record else "normal")
        self.btn_update.configure(state="normal" if has_record else "disabled")
        self.btn_delete.configure(state="normal" if has_record else "disabled")

    def _handle_save(self):
        name, address, mobile, email = self._get_form_data()
        try:
            self.current_company = self.service.save_company(
                name, address, mobile, email
            )
        except CompanyServiceError as exc:
            messagebox.showerror(APP_NAME, exc.message, parent=self)
            self._show_status(exc.message, is_error=True)
            return
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                f"An unexpected error occurred: {exc}",
                parent=self,
            )
            self._show_status("Save failed.", is_error=True)
            return

        self._populate_form(self.current_company)
        self._update_button_states()
        messagebox.showinfo(APP_NAME, "Company saved successfully.", parent=self)
        self._show_status("Company saved successfully.")

    def _handle_update(self):
        if self.current_company is None or self.current_company.id is None:
            messagebox.showwarning(
                APP_NAME,
                "No company record to update. Save a new company first.",
                parent=self,
            )
            return

        name, address, mobile, email = self._get_form_data()
        try:
            self.current_company = self.service.update_company(
                self.current_company.id,
                name,
                address,
                mobile,
                email,
            )
        except CompanyServiceError as exc:
            messagebox.showerror(APP_NAME, exc.message, parent=self)
            self._show_status(exc.message, is_error=True)
            return
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                f"An unexpected error occurred: {exc}",
                parent=self,
            )
            self._show_status("Update failed.", is_error=True)
            return

        self._populate_form(self.current_company)
        messagebox.showinfo(APP_NAME, "Company updated successfully.", parent=self)
        self._show_status("Company updated successfully.")

    def _handle_delete(self):
        if self.current_company is None or self.current_company.id is None:
            messagebox.showwarning(
                APP_NAME,
                "No company record to delete.",
                parent=self,
            )
            return

        confirmed = messagebox.askyesno(
            APP_NAME,
            "Are you sure you want to delete this company record?",
            parent=self,
        )
        if not confirmed:
            return

        try:
            self.service.delete_company(self.current_company.id)
        except CompanyServiceError as exc:
            messagebox.showerror(APP_NAME, exc.message, parent=self)
            self._show_status(exc.message, is_error=True)
            return
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                f"An unexpected error occurred: {exc}",
                parent=self,
            )
            self._show_status("Delete failed.", is_error=True)
            return

        self.current_company = None
        self._set_form_data()
        self._update_button_states()
        messagebox.showinfo(APP_NAME, "Company deleted successfully.", parent=self)
        self._show_status("Company deleted successfully.")

    def _handle_clear(self):
        if self.current_company is not None:
            self._populate_form(self.current_company)
            self._show_status("Form reset to saved company data.")
            return

        self._set_form_data()
        self._show_status("Form cleared.")

    def _handle_back(self):
        if self.on_back:
            self.destroy()
            self.on_back()
