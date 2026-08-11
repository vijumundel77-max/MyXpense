"""
Transaction Entry UI
Create, edit, delete income and expense transactions.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date, datetime
from typing import Any, Dict, Optional

import customtkinter as ctk

import config
from services.transaction_service import transaction_service


class TransactionEntryUI:
    """UI for transaction entry."""

    def __init__(self, parent: tk.Widget, company_id: int):
        self.parent = parent
        self.company_id = company_id
        self.current_transaction_id: Optional[int] = None
        self.current_transactions: list[Dict[str, Any]] = []

        self.main_frame = ctk.CTkFrame(parent, corner_radius=0)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_header()
        self._build_form()
        self._build_table()
        self._build_status()
        self._load_lookups()
        self.refresh_transactions()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main_frame, corner_radius=0)
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(header, text="Transaction Entry", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkLabel(header, text="Income / Expense / Transfer style entry", font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 0))

    def _build_form(self) -> None:
        form = ctk.CTkFrame(self.main_frame)
        form.pack(fill="x", pady=(0, 12))

        self.title_var = tk.StringVar()
        self.type_var = tk.StringVar(value="Expense")
        self.amount_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.party_var = tk.StringVar()
        self.bank_var = tk.StringVar()
        self.payment_method_var = tk.StringVar(value="Cash")
        self.date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.time_var = tk.StringVar(value=datetime.now().strftime("%H:%M"))
        self.notes_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._apply_search)

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(row1, text="Title", width=90).pack(side="left")
        ctk.CTkEntry(row1, textvariable=self.title_var, width=220).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row1, text="Type", width=70).pack(side="left")
        self.type_combo = ctk.CTkComboBox(row1, values=list(transaction_service.TRANSACTION_TYPES), variable=self.type_var, width=140)
        self.type_combo.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row1, text="Amount", width=80).pack(side="left")
        ctk.CTkEntry(row1, textvariable=self.amount_var, width=140).pack(side="left")

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(row2, text="Category", width=90).pack(side="left")
        self.category_combo = ctk.CTkComboBox(row2, values=[], variable=self.category_var, width=220)
        self.category_combo.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row2, text="Party", width=70).pack(side="left")
        self.party_combo = ctk.CTkComboBox(row2, values=[], variable=self.party_var, width=220)
        self.party_combo.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row2, text="Bank/Cash", width=90).pack(side="left")
        self.bank_combo = ctk.CTkComboBox(row2, values=[], variable=self.bank_var, width=220)
        self.bank_combo.pack(side="left")

        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(row3, text="Payment Method", width=120).pack(side="left")
        self.payment_combo = ctk.CTkComboBox(row3, values=list(transaction_service.PAYMENT_METHODS), variable=self.payment_method_var, width=160)
        self.payment_combo.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row3, text="Date", width=60).pack(side="left")
        ctk.CTkEntry(row3, textvariable=self.date_var, width=130).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row3, text="Time", width=60).pack(side="left")
        ctk.CTkEntry(row3, textvariable=self.time_var, width=100).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(row3, text="Notes", width=70).pack(side="left")
        ctk.CTkEntry(row3, textvariable=self.notes_var, width=260).pack(side="left")

        row4 = ctk.CTkFrame(form, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(row4, text="Search", width=90).pack(side="left")
        ctk.CTkEntry(row4, textvariable=self.search_var, width=260).pack(side="left", padx=(0, 12))
        ctk.CTkButton(row4, text="Save", command=self._save_transaction).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row4, text="Delete", command=self._delete_transaction).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row4, text="Clear", command=self._clear_form).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row4, text="Refresh", command=self.refresh_transactions).pack(side="left")

    def _build_table(self) -> None:
        table_frame = ctk.CTkFrame(self.main_frame)
        table_frame.pack(fill="both", expand=True)

        columns = ("date", "time", "title", "type", "category", "party", "bank", "method", "amount")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("date", "Date", 100),
            ("time", "Time", 80),
            ("title", "Title", 200),
            ("type", "Type", 90),
            ("category", "Category", 160),
            ("party", "Party", 160),
            ("bank", "Bank/Cash", 160),
            ("method", "Method", 100),
            ("amount", "Amount", 100),
        ]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w" if col not in {"amount"} else "e")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _build_status(self) -> None:
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(self.main_frame, textvariable=self.status_var, anchor="w").pack(fill="x", pady=(8, 0))

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.parent.update_idletasks()

    def _load_lookups(self) -> None:
        self.categories = transaction_service.list_categories()
        self.parties = transaction_service.list_parties()
        self.bank_accounts = transaction_service.list_bank_accounts()

        self.category_map = {f"{item['name']} ({item['type']})": item["id"] for item in self.categories}
        self.party_map = {item["name"]: item["id"] for item in self.parties}
        self.bank_map = {f"{item['bank_name']} ({item['account_number']})": item["id"] for item in self.bank_accounts}

        self.category_combo.configure(values=list(self.category_map.keys()))
        self.party_combo.configure(values=[""] + list(self.party_map.keys()))
        self.bank_combo.configure(values=[""] + list(self.bank_map.keys()))

        if self.category_map:
            self.category_combo.set(next(iter(self.category_map.keys())))
        if self.party_map:
            self.party_combo.set(next(iter(self.party_map.keys())))
        if self.bank_map:
            self.bank_combo.set(next(iter(self.bank_map.keys())))

    def _clear_form(self) -> None:
        self.current_transaction_id = None
        self.title_var.set("")
        self.type_var.set("Expense")
        self.amount_var.set("")
        self.notes_var.set("")
        self.payment_method_var.set("Cash")
        self.date_var.set(date.today().strftime(config.DISPLAY_DATE_FORMAT))
        self.time_var.set(datetime.now().strftime("%H:%M"))
        if self.category_combo.cget("values"):
            self.category_combo.set(self.category_combo.cget("values")[0])
        if self.party_combo.cget("values"):
            self.party_combo.set("")
        if self.bank_combo.cget("values"):
            self.bank_combo.set("")
        self.tree.selection_remove(self.tree.selection())
        self._set_status("Form cleared")

    def _selected_lookup_id(self, mapping: Dict[str, int], value: str) -> Optional[int]:
        value = value.strip()
        return mapping.get(value)

    def _validate(self) -> Optional[str]:
        if not self.title_var.get().strip():
            return "Title is required"
        try:
            if float(self.amount_var.get() or 0) <= 0:
                return "Amount must be greater than zero"
        except Exception:
            return "Amount must be numeric"
        if not self.category_var.get().strip():
            return "Category is required"
        try:
            datetime.strptime(self.date_var.get().strip(), config.DISPLAY_DATE_FORMAT)
        except Exception:
            return f"Date must be in {config.DISPLAY_DATE_FORMAT} format"
        try:
            datetime.strptime(self.time_var.get().strip(), "%H:%M")
        except Exception:
            return "Time must be in HH:MM format"
        return None

    def _form_data(self) -> Dict[str, Any]:
        bank_value = self.bank_var.get().strip()
        # The combo displays "Bank Name (XXXX-1234)"; store the raw mode
        # ("Cash"/"Bank") that the schema CHECK constraint expects.
        account_mode = "Bank" if bank_value in self.bank_map else "Cash"
        return {
            "title": self.title_var.get().strip(),
            "amount": float(self.amount_var.get() or 0),
            "type": self.type_var.get().strip(),
            "category_id": self._selected_lookup_id(self.category_map, self.category_var.get()),
            "account_mode": account_mode,
            "bank_account_id": self._selected_lookup_id(self.bank_map, bank_value),
            "party_id": self._selected_lookup_id(self.party_map, self.party_var.get()),
            "payment_method": self.payment_method_var.get().strip(),
            "transaction_date": self.date_var.get().strip(),
            "transaction_time": self.time_var.get().strip(),
            "notes": self.notes_var.get().strip(),
        }

    def _save_transaction(self) -> None:
        error = self._validate()
        if error:
            messagebox.showwarning("Validation", error)
            return
        data = self._form_data()
        if self.current_transaction_id is None:
            success, message = transaction_service.create_transaction(data)
        else:
            success, message = transaction_service.update_transaction(self.current_transaction_id, data)
        if success:
            self._set_status(message)
            self.refresh_transactions()
            self._clear_form()
        else:
            messagebox.showerror("Error", message)

    def _delete_transaction(self) -> None:
        if self.current_transaction_id is None:
            messagebox.showwarning("Warning", "Select a transaction to delete")
            return
        if not messagebox.askyesno("Confirm", "Delete selected transaction?"):
            return
        success, message = transaction_service.delete_transaction(self.current_transaction_id)
        if success:
            self._set_status(message)
            self.refresh_transactions()
            self._clear_form()
        else:
            messagebox.showerror("Error", message)

    def refresh_transactions(self) -> None:
        self.current_transactions = transaction_service.list_transactions()
        self._apply_search()
        self._set_status(f"Loaded {len(self.current_transactions)} transactions")

    def _apply_search(self, *args) -> None:
        search = self.search_var.get().strip().lower()
        filtered = [
            txn for txn in self.current_transactions
            if search in txn.get("title", "").lower()
            or search in txn.get("notes", "").lower()
            or search in txn.get("transaction_date", "").lower()
        ] if search else list(self.current_transactions)

        for item in self.tree.get_children():
            self.tree.delete(item)
        for txn in filtered:
            category_name = next((c["name"] for c in self.categories if c["id"] == txn.get("category_id")), "")
            party_name = next((p["name"] for p in self.parties if p["id"] == txn.get("party_id")), "")
            bank_name = next((b["bank_name"] for b in self.bank_accounts if b["id"] == txn.get("bank_account_id")), "")
            self.tree.insert("", tk.END, iid=str(txn["id"]), values=(
                txn.get("transaction_date", ""),
                txn.get("transaction_time", ""),
                txn.get("title", ""),
                txn.get("type", ""),
                category_name,
                party_name,
                bank_name,
                txn.get("payment_method", ""),
                f"{txn.get('amount', 0):,.2f}",
            ))

    def _on_select(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        txn = transaction_service.get_transaction(int(selection[0]))
        if not txn:
            return
        self.current_transaction_id = txn["id"]
        self.title_var.set(txn.get("title", ""))
        self.type_var.set(txn.get("type", "Expense"))
        self.amount_var.set(str(txn.get("amount", 0.0)))
        self.notes_var.set(txn.get("notes", ""))
        self.payment_method_var.set(txn.get("payment_method", "Cash"))
        self.date_var.set(txn.get("transaction_date", ""))
        self.time_var.set(txn.get("transaction_time", ""))
        category_name = next((c["name"] for c in self.categories if c["id"] == txn.get("category_id")), "")
        if category_name:
            display = next((key for key, value in self.category_map.items() if value == txn.get("category_id")), "")
            self.category_combo.set(display)
        party_name = next((p["name"] for p in self.parties if p["id"] == txn.get("party_id")), "")
        if party_name:
            self.party_combo.set(party_name)
        bank_name = next((b["bank_name"] for b in self.bank_accounts if b["id"] == txn.get("bank_account_id")), "")
        if bank_name:
            display = next((key for key, value in self.bank_map.items() if value == txn.get("bank_account_id")), "")
            self.bank_combo.set(display)
        self._set_status(f"Editing transaction #{txn['id']}")


def show_transaction_entry(parent: tk.Widget, company_id: int) -> TransactionEntryUI:
    return TransactionEntryUI(parent, company_id)
