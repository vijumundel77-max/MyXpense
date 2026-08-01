"""
Outstanding Report UI
Provides interface for generating and viewing outstanding reports with ageing
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from typing import Optional, Dict, Any, List
import config
from services.outstanding_report_service import outstanding_report_service
from utils.report_exporter import report_exporter


class OutstandingReportUI:
    """UI for Outstanding Report"""
    
    def __init__(self, parent: tk.Widget, company_id: int):
        """
        Initialize Outstanding Report UI
        
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
    
    def _create_header(self):
        """Create header section"""
        header_frame = ttk.Frame(self.main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame,
            text="Outstanding Report",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(side=tk.LEFT)
        
        # Report type selection
        type_frame = ttk.Frame(header_frame)
        type_frame.pack(side=tk.RIGHT)
        
        ttk.Label(type_frame, text="Report Type:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.report_type_var = tk.StringVar(value="Outstanding")
        report_type_combo = ttk.Combobox(
            type_frame,
            textvariable=self.report_type_var,
            values=["Outstanding", "Ageing Summary", "Overdue Invoices"],
            state="readonly",
            width=20
        )
        report_type_combo.pack(side=tk.LEFT)
        report_type_combo.bind("<<ComboboxSelected>>", self._on_report_type_changed)
    
    def _create_filters(self):
        """Create filter section"""
        filter_frame = ttk.LabelFrame(self.main_frame, text="Filters", padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 1: Outstanding Type
        row1 = ttk.Frame(filter_frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row1, text="Outstanding Type:", width=18).pack(side=tk.LEFT)
        
        self.outstanding_type_var = tk.StringVar(value="Receivable")
        outstanding_type_combo = ttk.Combobox(
            row1,
            textvariable=self.outstanding_type_var,
            values=["Receivable", "Payable", "All"],
            state="readonly",
            width=20
        )
        outstanding_type_combo.pack(side=tk.LEFT, padx=(0, 20))
        
        # Row 2: As On Date
        row2 = ttk.Frame(filter_frame)
        row2.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row2, text="As On Date:", width=18).pack(side=tk.LEFT)
        
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        as_on_date_entry = ttk.Entry(row2, textvariable=self.as_on_date_var, width=15)
        as_on_date_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(row2, text="(DD-MM-YYYY)", font=('Arial', 8, 'italic')).pack(side=tk.LEFT)
        
        # Row 3: Options
        row3 = ttk.Frame(filter_frame)
        row3.pack(fill=tk.X, pady=(0, 5))
        
        self.include_zero_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            row3,
            text="Include Zero Balance Parties",
            variable=self.include_zero_var
        ).pack(side=tk.LEFT)
        
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
        
        ttk.Button(
            button_frame,
            text="Refresh",
            command=self._refresh
        ).pack(side=tk.LEFT)
        
        # Search frame
        search_frame = ttk.Frame(button_frame)
        search_frame.pack(side=tk.RIGHT)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self._on_search_changed)
        
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT)
    
    def _create_report_area(self):
        """Create report display area"""
        # Create notebook for tabbed interface
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Outstanding tab
        self.outstanding_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.outstanding_frame, text="Outstanding")
        
        # Ageing Summary tab
        self.ageing_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ageing_frame, text="Ageing Summary")
        
        # Overdue tab
        self.overdue_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.overdue_frame, text="Overdue Invoices")
        
        # Create views
        self._create_outstanding_view()
        self._create_ageing_view()
        self._create_overdue_view()
    
    def _create_outstanding_view(self):
        """Create outstanding parties view"""
        # Tree frame
        tree_frame = ttk.Frame(self.outstanding_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = ('code', 'name', 'group', 'outstanding', 'type', 'invoices')
        
        self.outstanding_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.outstanding_tree.yview)
        hsb.config(command=self.outstanding_tree.xview)
        
        # Column headings
        self.outstanding_tree.heading('code', text='Code')
        self.outstanding_tree.heading('name', text='Party Name')
        self.outstanding_tree.heading('group', text='Group')
        self.outstanding_tree.heading('outstanding', text='Outstanding Amount')
        self.outstanding_tree.heading('type', text='Type')
        self.outstanding_tree.heading('invoices', text='Invoices')
        
        # Column widths
        self.outstanding_tree.column('code', width=100)
        self.outstanding_tree.column('name', width=250)
        self.outstanding_tree.column('group', width=150)
        self.outstanding_tree.column('outstanding', width=150, anchor='e')
        self.outstanding_tree.column('type', width=80, anchor='center')
        self.outstanding_tree.column('invoices', width=80, anchor='center')
        
        self.outstanding_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind double-click
        self.outstanding_tree.bind('<Double-1>', self._on_party_double_click)
        
        # Totals frame
        self.outstanding_totals_frame = ttk.Frame(self.outstanding_frame)
        self.outstanding_totals_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _create_ageing_view(self):
        """Create ageing summary view"""
        # Info frame
        info_frame = ttk.Frame(self.ageing_frame)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(
            info_frame,
            text="Outstanding by Ageing Buckets",
            font=('Arial', 12, 'bold')
        ).pack(anchor=tk.W)
        
        # Buckets frame
        self.ageing_buckets_frame = ttk.Frame(self.ageing_frame)
        self.ageing_buckets_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
    
    def _create_overdue_view(self):
        """Create overdue invoices view"""
        # Tree frame
        tree_frame = ttk.Frame(self.overdue_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = ('party_code', 'party_name', 'voucher_no', 'invoice_date', 
                   'due_date', 'amount', 'overdue_days')
        
        self.overdue_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.overdue_tree.yview)
        hsb.config(command=self.overdue_tree.xview)
        
        # Column headings
        self.overdue_tree.heading('party_code', text='Party Code')
        self.overdue_tree.heading('party_name', text='Party Name')
        self.overdue_tree.heading('voucher_no', text='Voucher No.')
        self.overdue_tree.heading('invoice_date', text='Invoice Date')
        self.overdue_tree.heading('due_date', text='Due Date')
        self.overdue_tree.heading('amount', text='Amount')
        self.overdue_tree.heading('overdue_days', text='Overdue Days')
        
        # Column widths
        self.overdue_tree.column('party_code', width=100)
        self.overdue_tree.column('party_name', width=200)
        self.overdue_tree.column('voucher_no', width=120)
        self.overdue_tree.column('invoice_date', width=100)
        self.overdue_tree.column('due_date', width=100)
        self.overdue_tree.column('amount', width=120, anchor='e')
        self.overdue_tree.column('overdue_days', width=100, anchor='center')
        
        self.overdue_tree.pack(fill=tk.BOTH, expand=True)
        
        # Totals frame
        self.overdue_totals_frame = ttk.Frame(self.overdue_frame)
        self.overdue_totals_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
    
    def _create_status_bar(self):
        """Create status bar"""
        self.status_bar = ttk.Label(
            self.main_frame,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def _on_report_type_changed(self, event=None):
        """Handle report type change"""
        report_type = self.report_type_var.get()
        
        if report_type == "Outstanding":
            self.notebook.select(self.outstanding_frame)
        elif report_type == "Ageing Summary":
            self.notebook.select(self.ageing_frame)
        else:
            self.notebook.select(self.overdue_frame)
    
    def _generate_report(self):
        """Generate report based on selections"""
        report_type = self.report_type_var.get()
        
        if report_type == "Outstanding":
            self._generate_outstanding_report()
        elif report_type == "Ageing Summary":
            self._generate_ageing_summary()
        else:
            self._generate_overdue_report()
    
    def _generate_outstanding_report(self):
        """Generate outstanding report"""
        try:
            # Parse date
            try:
                as_on_date = datetime.strptime(
                    self.as_on_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use DD-MM-YYYY")
                return
            
            # Generate report
            self._set_status("Generating outstanding report...")
            
            outstanding_type = self.outstanding_type_var.get()
            include_zero = self.include_zero_var.get()
            
            report = outstanding_report_service.generate_outstanding_report(
                self.company_id,
                outstanding_type,
                as_on_date,
                include_zero
            )
            
            if not report['success']:
                messagebox.showerror("Error", report.get('error', 'Failed to generate report'))
                self._set_status("Error generating report")
                return
            
            self.current_report_data = report
            self._display_outstanding_report(report)
            self._set_status(f"Outstanding report generated: {report['party_count']} parties")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")
            self._set_status("Error")
    
    def _generate_ageing_summary(self):
        """Generate ageing summary"""
        try:
            # Parse date
            try:
                as_on_date = datetime.strptime(
                    self.as_on_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use DD-MM-YYYY")
                return
            
            # Generate report
            self._set_status("Generating ageing summary...")
            
            outstanding_type = self.outstanding_type_var.get()
            
            report = outstanding_report_service.generate_ageing_summary(
                self.company_id,
                outstanding_type,
                as_on_date
            )
            
            if not report['success']:
                messagebox.showerror("Error", report.get('error', 'Failed to generate report'))
                self._set_status("Error generating report")
                return
            
            self.current_report_data = report
            self._display_ageing_summary(report)
            self._set_status("Ageing summary generated")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")
            self._set_status("Error")
    
    def _generate_overdue_report(self):
        """Generate overdue invoices report"""
        try:
            # Parse date
            try:
                as_on_date = datetime.strptime(
                    self.as_on_date_var.get(),
                    config.DISPLAY_DATE_FORMAT
                ).date()
            except ValueError:
                messagebox.showerror("Error", "Invalid date format. Use DD-MM-YYYY")
                return
            
            # Generate report
            self._set_status("Generating overdue report...")
            
            outstanding_type = self.outstanding_type_var.get()
            
            report = outstanding_report_service.get_overdue_invoices(
                self.company_id,
                outstanding_type,
                as_on_date
            )
            
            if not report['success']:
                messagebox.showerror("Error", report.get('error', 'Failed to generate report'))
                self._set_status("Error generating report")
                return
            
            self.current_report_data = report
            self._display_overdue_report(report)
            self._set_status(f"Overdue report generated: {report['invoice_count']} invoices")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")
            self._set_status("Error")
    
    def _display_outstanding_report(self, report: Dict[str, Any]):
        """Display outstanding report"""
        # Clear existing data
        for item in self.outstanding_tree.get_children():
            self.outstanding_tree.delete(item)
        
        # Clear totals
        for widget in self.outstanding_totals_frame.winfo_children():
            widget.destroy()
        
        # Display parties
        for party in report['parties']:
            values = (
                party['account_code'],
                party['account_name'],
                party['account_group'],
                self._format_amount(party['outstanding_balance']),
                party['balance_type'],
                party['invoice_count']
            )
            
            item = self.outstanding_tree.insert('', tk.END, values=values)
            
            # Store party data
            self.outstanding_tree.set(item, '#0', party['account_id'])
            
            # Color code
            if party['is_receivable']:
                self.outstanding_tree.item(item, tags=('receivable',))
            elif party['is_payable']:
                self.outstanding_tree.item(item, tags=('payable',))
        
        # Configure tags
        self.outstanding_tree.tag_configure('receivable', foreground='blue')
        self.outstanding_tree.tag_configure('payable', foreground='red')
        
        # Display totals
        totals = report['totals']
        
        totals_text = f"Total Outstanding: {self._format_amount(totals['total_outstanding'])}  |  "
        totals_text += f"Receivable: {self._format_amount(totals['total_receivable'])}  |  "
        totals_text += f"Payable: {self._format_amount(totals['total_payable'])}  |  "
        totals_text += f"Parties: {report['party_count']}"
        
        ttk.Label(
            self.outstanding_totals_frame,
            text=totals_text,
            font=('Arial', 10, 'bold')
        ).pack(anchor=tk.W)
    
    def _display_ageing_summary(self, report: Dict[str, Any]):
        """Display ageing summary"""
        # Clear existing data
        for widget in self.ageing_buckets_frame.winfo_children():
            widget.destroy()
        
        # Create buckets display
        buckets = report['ageing_buckets']
        
        # Header
        ttk.Label(
            self.ageing_buckets_frame,
            text=f"As on: {report['as_on_date']}",
            font=('Arial', 10)
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # Buckets
        for bucket_name, amount in buckets.items():
            bucket_frame = ttk.Frame(self.ageing_buckets_frame)
            bucket_frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(
                bucket_frame,
                text=f"{bucket_name}:",
                font=('Arial', 11),
                width=20
            ).pack(side=tk.LEFT)
            
            amount_label = ttk.Label(
                bucket_frame,
                text=self._format_amount(amount),
                font=('Arial', 11, 'bold')
            )
            amount_label.pack(side=tk.LEFT)
            
            # Color code based on age
            if 'Above 180' in bucket_name:
                amount_label.config(foreground='red')
            elif '91-180' in bucket_name:
                amount_label.config(foreground='orange')
            elif '61-90' in bucket_name:
                amount_label.config(foreground='darkorange')
        
        # Separator
        ttk.Separator(self.ageing_buckets_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # Total
        total_frame = ttk.Frame(self.ageing_buckets_frame)
        total_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(
            total_frame,
            text="Total Outstanding:",
            font=('Arial', 12, 'bold'),
            width=20
        ).pack(side=tk.LEFT)
        
        ttk.Label(
            total_frame,
            text=self._format_amount(report['total_outstanding']),
            font=('Arial', 12, 'bold'),
            foreground='blue'
        ).pack(side=tk.LEFT)
    
    def _display_overdue_report(self, report: Dict[str, Any]):
        """Display overdue report"""
        # Clear existing data
        for item in self.overdue_tree.get_children():
            self.overdue_tree.delete(item)
        
        # Clear totals
        for widget in self.overdue_totals_frame.winfo_children():
            widget.destroy()
        
        # Display invoices
        for party in report['parties']:
            for invoice in party['invoices']:
                values = (
                    party['account_code'],
                    party['account_name'],
                    invoice['voucher_number'],
                    invoice['voucher_date'],
                    invoice.get('due_date', 'N/A'),
                    self._format_amount(invoice['outstanding_amount']),
                    invoice['overdue_days']
                )
                
                item = self.overdue_tree.insert('', tk.END, values=values)
                
                # Color code by overdue days
                if invoice['overdue_days'] > 90:
                    self.overdue_tree.item(item, tags=('critical',))
                elif invoice['overdue_days'] > 60:
                    self.overdue_tree.item(item, tags=('high',))
                elif invoice['overdue_days'] > 30:
                    self.overdue_tree.item(item, tags=('medium',))
        
        # Configure tags
        self.overdue_tree.tag_configure('critical', foreground='red')
        self.overdue_tree.tag_configure('high', foreground='orange')
        self.overdue_tree.tag_configure('medium', foreground='darkorange')
        
        # Display totals
        totals_text = f"Total Overdue: {self._format_amount(report['total_overdue'])}  |  "
        totals_text += f"Overdue Invoices: {report['invoice_count']}"
        
        ttk.Label(
            self.overdue_totals_frame,
            text=totals_text,
            font=('Arial', 10, 'bold'),
            foreground='red'
        ).pack(anchor=tk.W)
    
    def _on_party_double_click(self, event):
        """Handle double-click on party"""
        selection = self.outstanding_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        
        # Find party in report data
        if not self.current_report_data:
            return
        
        party_code = self.outstanding_tree.item(item)['values'][0]
        party = next(
            (p for p in self.current_report_data['parties'] if p['account_code'] == party_code),
            None
        )
        
        if not party:
            return
        
        # Show invoice details popup
        self._show_invoice_details(party)
    
    def _show_invoice_details(self, party: Dict[str, Any]):
        """Show invoice details in popup"""
        # Create popup window
        popup = tk.Toplevel(self.parent)
        popup.title(f"Invoice Details - {party['account_name']}")
        popup.geometry("900x500")
        
        # Header
        header_frame = ttk.Frame(popup, padding=10)
        header_frame.pack(fill=tk.X)
        
        header_text = f"Party: {party['account_name']} ({party['account_code']})\n"
        header_text += f"Outstanding: {self._format_amount(party['outstanding_balance'])} {party['balance_type']}"
        
        ttk.Label(
            header_frame,
            text=header_text,
            font=('Arial', 11, 'bold')
        ).pack(anchor=tk.W)
        
        # Tree frame
        tree_frame = ttk.Frame(popup)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = ('voucher_no', 'date', 'due_date', 'amount', 'ageing_days', 'ageing_category')
        
        tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        
        # Column headings
        tree.heading('voucher_no', text='Voucher No.')
        tree.heading('date', text='Date')
        tree.heading('due_date', text='Due Date')
        tree.heading('amount', text='Amount')
        tree.heading('ageing_days', text='Ageing Days')
        tree.heading('ageing_category', text='Ageing Category')
        
        # Column widths
        tree.column('voucher_no', width=120)
        tree.column('date', width=100)
        tree.column('due_date', width=100)
        tree.column('amount', width=120, anchor='e')
        tree.column('ageing_days', width=100, anchor='center')
        tree.column('ageing_category', width=150)
        
        tree.pack(fill=tk.BOTH, expand=True)
        
        # Display invoices
        for invoice in party.get('invoices', []):
            values = (
                invoice['voucher_number'],
                invoice['voucher_date'],
                invoice.get('due_date', 'N/A'),
                self._format_amount(invoice['outstanding_amount']),
                invoice['ageing_days'],
                invoice['ageing_category']
            )
            
            tree.insert('', tk.END, values=values)
        
        # Close button
        ttk.Button(
            popup,
            text="Close",
            command=popup.destroy
        ).pack(pady=10)
    
    def _on_search_changed(self, *args):
        """Handle search text change"""
        if not self.current_report_data:
            return
        
        search_term = self.search_var.get()
        
        if not search_term:
            # Restore full report
            self._display_current_report()
            return
        
        try:
            # Filter report
            filtered = outstanding_report_service.search_parties(
                self.current_report_data,
                search_term
            )
            
            if filtered['success']:
                self._display_current_report(filtered)
                self._set_status(f"Found {filtered['party_count']} parties")
            
        except Exception as e:
            self._set_status(f"Search error: {str(e)}")
    
    def _display_current_report(self, report_data=None):
        """Display current report"""
        if report_data is None:
            report_data = self.current_report_data
        
        if not report_data:
            return
        
        report_type = report_data.get('report_type', '')
        
        if 'Outstanding Report' in report_type:
            self._display_outstanding_report(report_data)
        elif 'Ageing Summary' in report_type:
            self._display_ageing_summary(report_data)
        elif 'Overdue' in report_type:
            self._display_overdue_report(report_data)
    
    def _export_to_csv(self):
        """Export report to CSV"""
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Please generate a report first")
            return
        
        try:
            report_type = self.current_report_data.get('report_type', 'outstanding')
            filename = f"{report_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            success, file_path = outstanding_report_service.export_outstanding_report_to_csv(
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
    
    def _export_to_json(self):
        """Export report to JSON"""
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Please generate a report first")
            return
        
        try:
            report_type = self.current_report_data.get('report_type', 'outstanding')
            filename = f"{report_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
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


def show_outstanding_report(parent: tk.Widget, company_id: int) -> OutstandingReportUI:
    """
    Show Outstanding Report UI
    
    Args:
        parent: Parent widget
        company_id: Company ID
        
    Returns:
        OutstandingReportUI instance
    """
    return OutstandingReportUI(parent, company_id)
