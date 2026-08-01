"""
Party Ledger Report UI
Provides interface for generating and viewing party ledger reports
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from typing import Optional, Dict, Any
import config
from services.party_ledger_service import party_ledger_service
from utils.report_exporter import report_exporter


class PartyLedgerReportUI:
    """UI for Party Ledger Report"""
    
    def __init__(self, parent: tk.Widget, company_id: int):
        """
        Initialize Party Ledger Report UI
        
        Args:
            parent: Parent widget
            company_id: Company ID
        """
        self.parent = parent
        self.company_id = company_id
        self.current_report_data = None
        
        # Create main frame
        self.main_frame = ttk.Frame(parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create UI components
        self._create_header()
        self._create_filters()
        self._create_report_area()
        self._create_status_bar()
        
        # Load initial data
        self._load_party_types()
    
    def _create_header(self):
        """Create header section"""
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame,
            text="Party Ledger Report",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(side=tk.LEFT)
        
        # Report type selection
        type_frame = ttk.Frame(header_frame)
        type_frame.pack(side=tk.RIGHT)
        
        ttk.Label(type_frame, text="Report Type:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.report_type_var = tk.StringVar(value="Ledger")
        report_type_combo = ttk.Combobox(
            type_frame,
            textvariable=self.report_type_var,
            values=["Ledger", "Summary"],
            state="readonly",
            width=15
        )
        report_type_combo.pack(side=tk.LEFT)
        report_type_combo.bind("<<ComboboxSelected>>", self._on_report_type_changed)
    
    def _create_filters(self):
        """Create filter section"""
        filter_frame = ttk.LabelFrame(self.main_frame, text="Filters", padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 1: Party Type
        row1 = ttk.Frame(filter_frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row1, text="Party Type:", width=15).pack(side=tk.LEFT)
        
        self.party_type_var = tk.StringVar(value="Debtor")
        party_type_combo = ttk.Combobox(
            row1,
            textvariable=self.party_type_var,
            values=["Debtor", "Creditor", "All"],
            state="readonly",
            width=20
        )
        party_type_combo.pack(side=tk.LEFT, padx=(0, 20))
        party_type_combo.bind("<<ComboboxSelected>>", self._on_party_type_changed)
        
        # Row 2: Party Selection (for Ledger only)
        self.party_row = ttk.Frame(filter_frame)
        self.party_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(self.party_row, text="Select Party:", width=15).pack(side=tk.LEFT)
        
        # Search entry
        search_frame = ttk.Frame(self.party_row)
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self._on_search_changed)
        
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(search_frame, text="(Type to search)", font=('Arial', 8, 'italic')).pack(side=tk.LEFT)
        
        # Party dropdown
        self.party_var = tk.StringVar()
        self.party_combo = ttk.Combobox(
            self.party_row,
            textvariable=self.party_var,
            state="readonly",
            width=40
        )
        self.party_combo.pack(side=tk.LEFT, padx=(10, 0))
        
        # Row 3: Date Range
        row3 = ttk.Frame(filter_frame)
        row3.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row3, text="From Date:", width=15).pack(side=tk.LEFT)
        
        self.from_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        from_date_entry = ttk.Entry(row3, textvariable=self.from_date_var, width=15)
        from_date_entry.pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(row3, text="To Date:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.to_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        to_date_entry = ttk.Entry(row3, textvariable=self.to_date_var, width=15)
        to_date_entry.pack(side=tk.LEFT)
        
        ttk.Label(row3, text="(DD-MM-YYYY)", font=('Arial', 8, 'italic')).pack(side=tk.LEFT, padx=(5, 0))
        
        # Buttons
        button_frame = ttk.Frame(filter_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(
            button_frame,
            text="Generate Report",
            command=self._generate_report
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Export to CSV",
            command=self._export_to_csv
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Export to JSON",
            command=self._export_to_json
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.outstanding_btn = ttk.Button(
            button_frame,
            text="Check Outstanding",
            command=self._check_outstanding
        )
        self.outstanding_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Refresh",
            command=self._refresh
        ).pack(side=tk.LEFT)
    
    def _create_report_area(self):
        """Create report display area"""
        # Create notebook for tabbed interface
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Ledger tab
        self.ledger_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ledger_frame, text="Ledger")
        
        # Summary tab
        self.summary_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.summary_frame, text="Summary")
        
        # Create ledger view
        self._create_ledger_view()
        
        # Create summary view
        self._create_summary_view()
    
    def _create_ledger_view(self):
        """Create ledger transaction view"""
        # Header info frame
        self.ledger_header_frame = ttk.Frame(self.ledger_frame)
        self.ledger_header_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Tree frame
        tree_frame = ttk.Frame(self.ledger_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = (
            'date', 'voucher_no', 'type', 'reference', 'particulars',
            'debit', 'credit', 'balance', 'balance_type'
        )
        
        self.ledger_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.ledger_tree.yview)
        hsb.config(command=self.ledger_tree.xview)
        
        # Column headings
        self.ledger_tree.heading('date', text='Date')
        self.ledger_tree.heading('voucher_no', text='Voucher No.')
        self.ledger_tree.heading('type', text='Type')
        self.ledger_tree.heading('reference', text='Reference')
        self.ledger_tree.heading('particulars', text='Particulars')
        self.ledger_tree.heading('debit', text='Debit')
        self.ledger_tree.heading('credit', text='Credit')
        self.ledger_tree.heading('balance', text='Balance')
        self.ledger_tree.heading('balance_type', text='Dr/Cr')
        
        # Column widths
        self.ledger_tree.column('date', width=100)
        self.ledger_tree.column('voucher_no', width=120)
        self.ledger_tree.column('type', width=150)
        self.ledger_tree.column('reference', width=100)
        self.ledger_tree.column('particulars', width=200)
        self.ledger_tree.column('debit', width=120, anchor='e')
        self.ledger_tree.column('credit', width=120, anchor='e')
        self.ledger_tree.column('balance', width=120, anchor='e')
        self.ledger_tree.column('balance_type', width=60, anchor='center')
        
        self.ledger_tree.pack(fill=tk.BOTH, expand=True)
        
        # Footer frame
        self.ledger_footer_frame = ttk.Frame(self.ledger_frame)
        self.ledger_footer_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _create_summary_view(self):
        """Create summary view"""
        # Tree frame
        tree_frame = ttk.Frame(self.summary_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = (
            'code', 'name', 'group', 'opening', 'opening_type',
            'debit', 'credit', 'closing', 'closing_type', 'transactions'
        )
        
        self.summary_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.summary_tree.yview)
        hsb.config(command=self.summary_tree.xview)
        
        # Column headings
        self.summary_tree.heading('code', text='Code')
        self.summary_tree.heading('name', text='Party Name')
        self.summary_tree.heading('group', text='Group')
        self.summary_tree.heading('opening', text='Opening')
        self.summary_tree.heading('opening_type', text='Type')
        self.summary_tree.heading('debit', text='Debit')
        self.summary_tree.heading('credit', text='Credit')
        self.summary_tree.heading('closing', text='Closing')
        self.summary_tree.heading('closing_type', text='Type')
        self.summary_tree.heading('transactions', text='Txns')
        
        # Column widths
        self.summary_tree.column('code', width=100)
        self.summary_tree.column('name', width=200)
        self.summary_tree.column('group', width=150)
        self.summary_tree.column('opening', width=120, anchor='e')
        self.summary_tree.column('opening_type', width=60, anchor='center')
        self.summary_tree.column('debit', width=120, anchor='e')
        self.summary_tree.column('credit', width=120, anchor='e')
        self.summary_tree.column('closing', width=120, anchor='e')
        self.summary_tree.column('closing_type', width=60, anchor='center')
        self.summary_tree.column('transactions', width=80, anchor='center')
        
        self.summary_tree.pack(fill=tk.BOTH, expand=True)
        
        # Summary totals frame
        self.summary_totals_frame = ttk.Frame(self.summary_frame)
        self.summary_totals_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _create_status_bar(self):
        """Create status bar"""
        self.status_bar = ttk.Label(
            self.main_frame,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def _load_party_types(self):
        """Load party types and initial data"""
        self._on_party_type_changed()
    
    def _on_report_type_changed(self, event=None):
        """Handle report type change"""
        report_type = self.report_type_var.get()
        
        if report_type == "Ledger":
            self.party_row.pack(fill=tk.X, pady=(0, 5))
            self.outstanding_btn.pack(side=tk.LEFT, padx=(0, 5))
            self.notebook.select(self.ledger_frame)
        else:
            self.party_row.pack_forget()
            self.outstanding_btn.pack_forget()
            self.notebook.select(self.summary_frame)
    
    def _on_party_type_changed(self, event=None):
        """Handle party type change"""
        party_type = self.party_type_var.get()
        
        # Load parties
        self._load_parties(party_type)
    
    def _load_parties(self, party_type: str):
        """Load parties based on type"""
        try:
            results = party_ledger_service.search_parties(
                self.company_id,
                party_type,
                ""
            )
            
            self.all_parties = results
            self._update_party_combo(results)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load parties: {str(e)}")
    
    def _update_party_combo(self, parties):
        """Update party combobox"""
        values = [f"{p['code']} - {p['name']}" for p in parties]
        self.party_combo['values'] = values
        
        if values:
            self.party_combo.current(0)
    
    def _on_search_changed(self, *args):
        """Handle search text change"""
        search_term = self.search_var.get()
        party_type = self.party_type_var.get()
        
        if not search_term:
            self._update_party_combo(self.all_parties)
            return
        
        try:
            results = party_ledger_service.search_parties(
                self.company_id,
                party_type,
                search_term
            )
            
            self._update_party_combo(results)
            
        except Exception as e:
            self._set_status(f"Search error: {str(e)}")
    
    def _generate_report(self):
        """Generate report based on selections"""
        report_type = self.report_type_var.get()
        
        if report_type == "Ledger":
            self._generate_ledger_report()
        else:
            self._generate_summary_report()
    
    def _generate_ledger_report(self):
        """Generate party ledger report"""
        try:
            # Validate inputs
            if not self.party_var.get():
                messagebox.showwarning("Warning", "Please select a party")
                return
            
            # Get selected party ID
            party_text = self.party_var.get()
            party_code = party_text.split(' - ')[0]
            party = next((p for p in self.all_parties if p['code'] == party_code), None)
            
            if not party:
                messagebox.showerror("Error", "Invalid party selection")
                return
            
            # Parse dates
            try:
                from_date = datetime.strptime(
                    self.from_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
                
                to_date = datetime.strptime(
                    self.to_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use DD-MM-YYYY")
                return
            
            if from_date > to_date:
                messagebox.showerror("Error", "From Date cannot be after To Date")
                return
            
            # Generate report
            self._set_status("Generating ledger report...")
            
            report = party_ledger_service.generate_party_ledger(
                self.company_id,
                party['id'],
                from_date,
                to_date
            )
            
            if not report['success']:
                messagebox.showerror("Error", report.get('error', 'Failed to generate report'))
                self._set_status("Error generating report")
                return
            
            self.current_report_data = report
            self._display_ledger_report(report)
            self._set_status(f"Ledger generated: {report['transaction_count']} transactions")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")
            self._set_status("Error")
    
    def _generate_summary_report(self):
        """Generate party summary report"""
        try:
            # Parse dates
            try:
                to_date = datetime.strptime(
                    self.to_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
                
                from_date = datetime.strptime(
                    self.from_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use DD-MM-YYYY")
                return
            
            # Generate report
            self._set_status("Generating summary report...")
            
            party_type = self.party_type_var.get()
            
            report = party_ledger_service.generate_party_summary(
                self.company_id,
                party_type,
                to_date,
                from_date
            )
            
            if not report['success']:
                messagebox.showerror("Error", report.get('error', 'Failed to generate report'))
                self._set_status("Error generating report")
                return
            
            self.current_report_data = report
            self._display_summary_report(report)
            self._set_status(f"Summary generated: {report['party_count']} parties")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")
            self._set_status("Error")
    
    def _display_ledger_report(self, report: Dict[str, Any]):
        """Display ledger report"""
        # Clear existing data
        for item in self.ledger_tree.get_children():
            self.ledger_tree.delete(item)
        
        # Clear header and footer
        for widget in self.ledger_header_frame.winfo_children():
            widget.destroy()
        
        for widget in self.ledger_footer_frame.winfo_children():
            widget.destroy()
        
        # Display header
        account = report['account']
        header_text = f"Party: {account['name']} ({account['code']})\n"
        header_text += f"Period: {report['from_date']} to {report['to_date']}\n"
        header_text += f"Opening Balance: {self._format_amount(report['opening_balance']['amount'])} "
        header_text += f"{report['opening_balance']['type']}"
        
        ttk.Label(
            self.ledger_header_frame,
            text=header_text,
            font=('Arial', 10)
        ).pack(anchor=tk.W)
        
        ttk.Separator(self.ledger_header_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Display transactions
        for txn in report['transactions']:
            values = (
                txn['voucher_date'],
                txn['voucher_number'],
                txn['voucher_type'],
                txn.get('reference_number', ''),
                txn['contra_account_name'],
                self._format_amount(txn['debit_amount']),
                self._format_amount(txn['credit_amount']),
                self._format_amount(txn['running_balance']),
                txn['balance_type']
            )
            
            item = self.ledger_tree.insert('', tk.END, values=values)
            
            # Color code balance type
            if txn['balance_type'] == 'Debit':
                self.ledger_tree.item(item, tags=('debit',))
            else:
                self.ledger_tree.item(item, tags=('credit',))
        
        # Configure tags
        self.ledger_tree.tag_configure('debit', foreground='blue')
        self.ledger_tree.tag_configure('credit', foreground='red')
        
        # Display footer
        totals = report['totals']
        closing = report['closing_balance']
        
        footer_text = f"Total Debit: {self._format_amount(totals['debit'])}  |  "
        footer_text += f"Total Credit: {self._format_amount(totals['credit'])}  |  "
        footer_text += f"Closing Balance: {self._format_amount(closing['amount'])} {closing['type']}"
        
        footer_label = ttk.Label(
            self.ledger_footer_frame,
            text=footer_text,
            font=('Arial', 10, 'bold')
        )
        footer_label.pack(anchor=tk.W)
        
        # Color code closing balance
        if closing['type'] == 'Debit':
            footer_label.config(foreground='blue')
        else:
            footer_label.config(foreground='red')
    
    def _display_summary_report(self, report: Dict[str, Any]):
        """Display summary report"""
        # Clear existing data
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)
        
        # Clear totals
        for widget in self.summary_totals_frame.winfo_children():
            widget.destroy()
        
        # Display parties
        for party in report['parties']:
            values = (
                party['account_code'],
                party['account_name'],
                party['account_group'],
                self._format_amount(party['opening_balance']['amount']),
                party['opening_balance']['type'],
                self._format_amount(party['totals']['debit']),
                self._format_amount(party['totals']['credit']),
                self._format_amount(party['closing_balance']['amount']),
                party['closing_balance']['type'],
                party['transaction_count']
            )
            
            self.summary_tree.insert('', tk.END, values=values)
        
        # Display totals
        totals = report['totals']
        
        totals_text = f"Total Debit: {self._format_amount(totals['total_debit'])}  |  "
        totals_text += f"Total Credit: {self._format_amount(totals['total_credit'])}  |  "
        totals_text += f"Net Receivable: {self._format_amount(totals['net_receivable'])}  |  "
        totals_text += f"Net Payable: {self._format_amount(totals['net_payable'])}"
        
        ttk.Label(
            self.summary_totals_frame,
            text=totals_text,
            font=('Arial', 10, 'bold')
        ).pack(anchor=tk.W)
    
    def _check_outstanding(self):
        """Check outstanding balance for selected party"""
        try:
            # Validate inputs
            if not self.party_var.get():
                messagebox.showwarning("Warning", "Please select a party")
                return
            
            # Get selected party ID
            party_text = self.party_var.get()
            party_code = party_text.split(' - ')[0]
            party = next((p for p in self.all_parties if p['code'] == party_code), None)
            
            if not party:
                messagebox.showerror("Error", "Invalid party selection")
                return
            
            # Parse to date
            try:
                to_date = datetime.strptime(
                    self.to_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use DD-MM-YYYY")
                return
            
            # Get outstanding
            result = party_ledger_service.get_party_outstanding(
                self.company_id,
                party['id'],
                to_date
            )
            
            if not result['success']:
                messagebox.showerror("Error", result.get('error', 'Failed to get outstanding'))
                return
            
            # Display result
            amount = self._format_amount(result['outstanding_balance'])
            balance_type = result['balance_type']
            
            message = f"Party: {party['name']}\n"
            message += f"As on: {to_date.strftime(config.DISPLAY_DATE_FORMAT)}\n\n"
            message += f"Outstanding Balance: {amount} {balance_type}\n\n"
            
            if result['is_receivable']:
                message += "Status: Receivable (To be collected)"
            elif result['is_payable']:
                message += "Status: Payable (To be paid)"
            else:
                message += "Status: No outstanding"
            
            messagebox.showinfo("Outstanding Balance", message)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to check outstanding: {str(e)}")
    
    def _export_to_csv(self):
        """Export report to CSV"""
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Please generate a report first")
            return
        
        try:
            report_type = self.report_type_var.get()
            
            if report_type == "Ledger":
                success, file_path = party_ledger_service.export_party_ledger_to_csv(
                    self.current_report_data,
                    f"party_ledger_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
            else:
                success, file_path = party_ledger_service.export_party_summary_to_csv(
                    self.current_report_data,
                    f"party_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
            
            if success:
                messagebox.showinfo("Success", f"Report exported to:\n{file_path}")
                self._set_status(f"Exported to {file_path}")
            else:
                messagebox.showerror("Error", "Failed to export report")
                
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")
    
    def _export_to_json(self):
        """Export report to JSON"""
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Please generate a report first")
            return
        
        try:
            report_type = self.report_type_var.get()
            filename = f"party_{report_type.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            success, file_path = report_exporter.export_to_json(
                self.current_report_data,
                filename
            )
            
            if success:
                messagebox.showinfo("Success", f"Report exported to:\n{file_path}")
                self._set_status(f"Exported to {file_path}")
            else:
                messagebox.showerror("Error", "Failed to export report")
                
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {str(e)}")
    
    def _refresh(self):
        """Refresh the report"""
        self._generate_report()
    
    def _format_amount(self, amount: float) -> str:
        """Format amount for display"""
        return f"{amount:,.2f}"
    
    def _set_status(self, message: str):
        """Set status bar message"""
        self.status_bar.config(text=message)
        self.status_bar.update_idletasks()


def show_party_ledger_report(parent: tk.Widget, company_id: int) -> PartyLedgerReportUI:
    """
    Show Party Ledger Report UI
    
    Args:
        parent: Parent widget
        company_id: Company ID
        
    Returns:
        PartyLedgerReportUI instance
    """
    return PartyLedgerReportUI(parent, company_id)
