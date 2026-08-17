"""
Expenzo — Settings
Theme, company selection, and application settings.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import config
from database.database import db
from services.company_backup_service import BackupError, CompanyBackupService
from services.company_service import CompanyService
from utils import dialogs


class SettingsFrame(ctk.CTkFrame):
    """Settings screen: theme toggle, active company, exports directory."""

    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=config.SPACING_XL, pady=config.SPACING_XL)

        ctk.CTkLabel(
            self,
            text="Settings",
            font=ctk.CTkFont(size=config.FONT_TITLE_SIZE, weight="bold"),
        ).pack(anchor="w", pady=(0, config.SPACING_LG))

        self._build_company_card()
        self._build_theme_card()
        self._build_general_card()

        from utils.keyboard import add_shortcut_bar
        add_shortcut_bar(self, [("F5", "Refresh companies"), ("Esc", "Back")])

    def _card(self, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self,
            fg_color=config.COLOR_BG_SECONDARY,
            corner_radius=config.CARD_CORNER_RADIUS,
        )
        card.pack(fill="x", pady=(0, config.SPACING_LG))
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(config.SPACING_LG, config.SPACING_SM))
        return card

    def _build_company_card(self) -> None:
        card = self._card("Company")
        companies = db.fetch_all("SELECT id, name FROM companies ORDER BY name")
        if not companies:
            ctk.CTkLabel(card, text="No companies yet.", text_color=config.COLOR_TEXT_MUTED).pack(
                anchor="w", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
            return

        self.company_id_map = {row["name"]: row["id"] for row in companies}
        values = list(self.company_id_map.keys())
        current_id = self._current_company_id()
        current_name = next(
            (name for name, cid in self.company_id_map.items() if cid == current_id),
            values[0] if values else "",
        )

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))

        ctk.CTkLabel(row, text="Active Company", width=110).pack(side="left")
        self.company_var = ctk.StringVar(value=current_name)
        self.company_combo = ctk.CTkComboBox(
            row,
            values=values,
            variable=self.company_var,
            width=280,
            state="readonly",
            command=self._on_company_change,
        )
        self.company_combo.pack(side="left")
        ctk.CTkLabel(
            row,
            text="Selecting a company switches the whole application.",
            font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_LG, 0))

        backup_row = ctk.CTkFrame(card, fg_color="transparent")
        backup_row.pack(fill="x", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
        self.btn_export_backup = ctk.CTkButton(
            backup_row, text="Export Company Backup", width=180, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._export_backup,
        )
        self.btn_export_backup.pack(side="left", padx=(0, config.SPACING_SM))
        self.btn_import_backup = ctk.CTkButton(
            backup_row, text="Import Existing Backup", width=180, height=32,
            corner_radius=config.BUTTON_CORNER_RADIUS,
            fg_color="transparent", border_width=1, command=self._import_backup,
        )
        self.btn_import_backup.pack(side="left")
        ctk.CTkLabel(
            backup_row,
            text="Back up / restore a complete company (works offline).",
            font=ctk.CTkFont(size=12),
            text_color=config.COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(config.SPACING_LG, 0))

    def _current_company_id(self) -> int:
        try:
            app = self.winfo_toplevel()
            return int(getattr(app, "current_company_id", 1))
        except Exception:
            return 1

    def _on_company_change(self, value: str) -> None:
        company_id = self.company_id_map.get(value)
        if not company_id:
            return
        app = self.winfo_toplevel()
        if hasattr(app, "switch_company"):
            app.switch_company(company_id)

    # ------------------------------------------------------------------ #
    # offline backup / restore
    # ------------------------------------------------------------------ #
    def _backup_service(self) -> CompanyBackupService:
        return CompanyBackupService(db)

    def _export_backup(self) -> None:
        company_id = self._current_company_id()
        company = CompanyService(db).get_company(company_id)
        if not company:
            dialogs.warn("Export Backup", "No company selected to back up.", parent=self)
            return
        default_name = "Expenzo_Backup_{}_{}.expbackup".format(
            company.company_name.strip().replace(" ", "_"),
            date.today().strftime("%Y-%m-%d"),
        )
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Company Backup",
            initialfile=default_name,
            defaultextension=".expbackup",
            filetypes=[("Expenzo Backup", "*.expbackup"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            created = self._backup_service().export_company(company_id, Path(path).parent)
        except BackupError as exc:
            dialogs.error("Export Backup", exc.message, parent=self)
            return
        except Exception as exc:
            dialogs.error("Export Backup", f"Backup failed: {exc}", parent=self)
            return
        dialogs.info(
            "Export Backup",
            f"Backup created successfully.\n\n{created}\n\n"
            "This file can be copied to any computer (USB / HDD) and imported "
            "into Expenzo.",
            parent=self,
        )

    def _import_backup(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Import Expenzo Backup",
            filetypes=[("Expenzo Backup", "*.expbackup"), ("All files", "*.*")],
        )
        if not path:
            return
        service = self._backup_service()
        try:
            archive = service.validate_backup_file(path)
        except BackupError as exc:
            dialogs.error("Import Backup", exc.message, parent=self)
            return
        backup_name = str(archive.get("company_name", "Company"))

        service_cs = CompanyService(db)
        exists = service_cs.list_companies(backup_name)
        if exists:
            replace_id = exists[0]["id"]
            choice = dialogs.confirm(
                "Import Backup",
                f"Company \"{backup_name}\" already exists.\n\n"
                "Choose OK to import as a NEW company (name gets a (2) suffix).\n"
                "Choose NO to Replace the existing company.",
                parent=self,
            )
            if choice:
                mode, target = "new", None
            else:
                if not dialogs.confirm(
                    "Replace Company",
                    f"Are you sure you want to REPLACE the existing company "
                    f"\"{backup_name}\"?\n\n"
                    "All of its current data will be deleted and replaced by "
                    "the backup. This cannot be undone.",
                    parent=self,
                ):
                    return
                mode, target = "replace", replace_id
        else:
            mode, target = "new", None

        try:
            result = service.import_backup(path, mode=mode, replace_company_id=target)
        except BackupError as exc:
            dialogs.error("Import Backup", exc.message, parent=self)
            return
        except Exception as exc:
            dialogs.error("Import Backup", f"Import failed: {exc}", parent=self)
            return

        counts = result["counts"]
        summary = (
            f"Company \"{result['company_name']}\" restored successfully.\n\n"
            f"  Groups:          {counts.get('groups', 0)}\n"
            f"  Ledgers:         {counts.get('accounts', 0)}\n"
            f"  Bank Accounts:   {counts.get('bank_accounts', 0)}\n"
            f"  Vouchers:        {counts.get('vouchers', 0)}\n"
            f"  Voucher Lines:   {counts.get('voucher_details', 0)}\n"
        )
        dialogs.info("Import Backup", summary, parent=self)
        try:
            self._refresh_company_card()
        except Exception:
            pass

    def on_keyboard_refresh(self) -> None:
        """F5: refresh the company list from the database."""
        self.company_var.set(self.company_var.get())  # no-op guard
        try:
            self._refresh_company_card()
        except Exception:
            pass

    def _refresh_company_card(self) -> None:
        companies = db.fetch_all("SELECT id, name FROM companies ORDER BY name")
        if not companies:
            return
        self.company_id_map = {row["name"]: row["id"] for row in companies}
        self.company_combo.configure(values=list(self.company_id_map.keys()))

    def on_keyboard_back(self) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, "on_keyboard_back"):
            app.on_keyboard_back()

    def _build_theme_card(self) -> None:
        card = self._card("Appearance")
        ctk.CTkLabel(card, text="Theme:", width=90).pack(side="left", padx=(config.SPACING_LG, 0))
        self.theme_var = ctk.StringVar(value="Dark" if ctk.get_appearance_mode() == "Dark" else "Light")
        ctk.CTkComboBox(
            card,
            values=["Dark", "Light"],
            variable=self.theme_var,
            width=160,
            command=self._on_theme_change,
        ).pack(side="left", pady=config.SPACING_LG)

    def _on_theme_change(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())
        app = self.winfo_toplevel()
        if hasattr(app, "_toggle_theme"):
            # Reflect the toggle button state without toggling.
            from utils import theme as theme_utils
            theme_utils.apply_theme(app, mode=value.lower())
            if hasattr(app, "_apply_chrome"):
                app._apply_chrome()
            if hasattr(app, "_refresh_theme_toggle"):
                app._refresh_theme_toggle(value.lower())

    def _build_general_card(self) -> None:
        card = self._card("General")
        ctk.CTkLabel(
            card,
            text=f"Exports directory:  {config.EXPORTS_DIR}",
            text_color=config.COLOR_TEXT_SECONDARY,
        ).pack(anchor="w", padx=config.SPACING_LG, pady=(0, config.SPACING_LG))
