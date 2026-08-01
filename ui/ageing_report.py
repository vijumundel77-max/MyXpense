"""
Ageing Report UI
Provides interface for generating and viewing detailed ageing reports with FIFO allocation
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime
from typing import Optional, Dict, Any, List
import config
from services.ageing_report_service import ageing_report_service
from utils.report_exporter import report_exporter


class AgeingReportUI:
    """UI for Ageing Report"""
    
    def __init__(self, parent: tk.Widget, company_id: int):
        """
        Initialize Ageing Report UI
        
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
            text="Ageing Report (FIFO Allocation)",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(side=tk.LEFT)
        
        # Info button
        info_btn = ttk.Button(
            header_frame,
            text="â„¹ About FIFO",
            command=self._show_fifo_info,
            width=12
        )
        info_btn.pack(side=tk.RIGHT)
    
    def _create_filters(self):
        """Create filter section"""
        filter_frame = ttk.LabelFrame(self.main_frame, text="Filters", padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Row 1: Ageing Type
        row1 = ttk.Frame(filter_frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row1, text="Ageing Type:", width=18).pack(side=tk.LEFT)
        
        self.ageing_type_var = tk.StringVar(value="Receivable")
        ageing_type_combo = ttk.Combobox(
            row1,
            textvariable=self.ageing_type_var,
            values=["Receivable", "Payable"],
            state="readonly",
            width=20
        )
        ageing_type_combo.pack(side=tk.LEFT, padx=(0, 20))
        
        # Row 2: As On Date
        row2 = ttk.Frame(filter_frame)
        row2.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(row2, text="As On Date:", width=18).pack(side=tk.LEFT)
        
        self.as_on_date_var = tk.StringVar(value=date.today().strftime(config.DISPLAY_DATE_FORMAT))
        as_on_date_entry = ttk.Entry(row2, textvariable=self.as_on_date_var, width=15)
        as_on_date_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(row2, text="(DD-MM-YYYY)", font=('Arial', 8, 'italic')).pack(side=tk.LEFT)
        
        # Row 3: Custom Buckets
        row3 = ttk.Frame(filter_frame)
        row3.pack(fill=tk.X, pady=(0, 5))
        
        self.use_custom_buckets_var = tk.BooleanVar(value=False)
        custom_check = ttk.Checkbutton(
            row3,
            text="Use Custom Ageing Buckets",
            variable=self.use_custom_buckets_var,
            command=self._toggle_custom_buckets
        )
        custom_check.pack(side=tk.LEFT)
        
        # Row 4: Custom Buckets Entry
        self.custom_buckets_row = ttk.Frame(filter_frame)
        
        ttk.Label(self.custom_buckets_row, text="Buckets:", width=18).pack(side=tk.LEFT)
        
        self.custom_buckets_var = tk.StringVar(value="0-30, 31-60, 61-90, 91-180, 181-999")
        custom_buckets_entry = ttk.Entry(
            self.custom_buckets_row,
            textvariable=self.custom_buckets_var,
            width=50
        )
        custom_buckets_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(
            self.custom_buckets_row,
            text="(Format: min-max, separated by commas)",
            font=('Arial', 8, 'italic')
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
        # Summary frame
        self.summary_frame = ttk.LabelFrame(self.main_frame, text="Ageing Summary", padding=10)
        self.summary_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Tree frame
        tree_frame = ttk.Frame(self.main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview (dynamic columns based on buckets)
        self.ageing_tree = ttk.Treeview(
            tree_frame,
            show='headings',
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
        
        vsb.config(command=self.ageing_tree.yview)
        hsb.config(command=self.ageing_tree.xview)
        
        self.ageing_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind double-click
        self.ageing_tree.bind('<Double-1>', self._on_party_double_click)
        
        # Totals frame
        self.totals_frame = ttk.Frame(self.main_frame)
        self.totals_frame.pack(fill=tk.X, pady=(10, 0))
    
    def _create_status_bar(self):
        """Create status bar"""
        self.status_bar = ttk.Label(
            self.main_frame,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))
    
    def _toggle_custom_buckets(self):
        """Toggle custom buckets entry"""
        if self.use_custom_buckets_var.get():
            self.custom_buckets_row.pack(fill=tk.X, pady=(0, 5))
        else:
            self.custom_buckets_row.pack_forget()
    
    def _show_fifo_info(self):
        """Show FIFO allocation information"""
        info_text = """FIFO (First In First Out) Payment Allocation

This report uses FIFO method to allocate payments to invoices:

1. Invoices are sorted by date (oldest first)
2. Payments are sorted by date
3. Each payment is allocated to the oldest outstanding invoice first
4. Process continues until payment is fully allocated

Example:
• Invoice 1 (June 1): ₹10,000
• Invoice 2 (June 15): ₹8,000
• Payment (June 20): ₹7,000

Allocation:
• Payment of ₹7,000 goes to Invoice 1
• Invoice 1 outstanding: ₹3,000
• Invoice 2 outstanding: ₹8,000 (no payment allocated yet)

This ensures accurate ageing of each invoice based on actual payment behavior."""
        
        messagebox.showinfo("FIFO Allocation", info_text)
    
    def _parse_custom_buckets(self, bucket_string: str) -> List[tuple]:
        """Parse custom bucket string"""
        try:
            buckets = []
            parts = [p.strip() for p in bucket_string.split(',')]
            
            for part in parts:
                if '-' not in part:
                    raise ValueError(f"Invalid bucket format: {part}")
                
                min_val, max_val = part.split('-')
                min_val = int(min_val.strip())
                max_val = int(max_val.strip())
                
                if min_val >= max_val:
                    raise ValueError(f"Invalid range: {min_val}-{max_val}")
                
                bucket_name = f"{min_val}-{max_val} days" if max_val < 999 else f"Above {min_val} days"
                buckets.append((min_val, max_val, bucket_name))
            
            return buckets
            
        except Exception as e:
            raise ValueError(f"Invalid bucket format: {str(e)}")
    
    def _generate_report(self):
        """Generate ageing report"""
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
            
            # Parse custom buckets if enabled
            custom_buckets = None
            if self.use_custom_buckets_var.get():
                try:
                    custom_buckets = self._parse_custom_buckets(self.custom_buckets_var.get())
                except ValueError as e:
                    messagebox.showerror("Error", str(e))
                    return
            
            # Generate report
            self._set_status("Generating ageing report with FIFO allocation...")
            
            ageing_type = self.ageing_type_var.get()
            
            report = ageing_report_service.generate_ageing_report(
                self.company_id,
                ageing_type,
                as_on_date,
                custom_buckets
            )
            
            if not report['success']:
                messagebox.showerror("Error", report.get('error', 'Failed to generate report'))
                self._set_status("Error generating report")
                return
            
            self.current_report_data = report
            self._display_report(report)
            self._set_status(f"Ageing report generated: {report['party_count']} parties")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report: {str(e)}")
            self._set_status("Error")
    
    def _display_report(self, report: Dict[str, Any]):
        """Display ageing report"""
        # Clear existing data
        for item in self.ageing_tree.get_children():
            self.ageing_tree.delete(item)
        
        # Clear summary and totals
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        
        for widget in self.totals_frame.winfo_children():
            widget.destroy()
        
        # Setup columns
        buckets = report['buckets']
        columns = ['code', 'name'] + buckets + ['total']
        
        self.ageing_tree['columns'] = columns
        
        # Column headings
        self.ageing_tree.heading('code', text='Code')
        self.ageing_tree.heading('name', text='Party Name')
        
        for bucket in buckets:
            self.ageing_tree.heading(bucket, text=bucket)
        
        self.ageing_tree.heading('total', text='Total')
        
        # Column widths
        self.ageing_tree.column('code', width=100)
        self.ageing_tree.column('name', width=200)
        
        for bucket in buckets:
            self.ageing_tree.column(bucket, width=120, anchor='e')
        
        self.ageing_tree.column('total', width=120, anchor='e')
        
        # Display parties
        for party in report['parties']:
            values = [party['account_code'], party['account_name']]
            
            for bucket in buckets:
                values.append(self._format_amount(party['buckets'][bucket]))
            
            values.append(self._format_amount(party['total']))
            
            item = self.ageing_tree.insert('', tk.END, values=values)
            
            # Store party data
            self.ageing_tree.set(item, '#0', party['account_id'])
        
        # Add totals row
        total_values = ['', 'TOTAL']
        
        for bucket in buckets:
            total_values.append(self._format_amount(report['totals'][bucket]))
        
        total_values.append(self._format_amount(report['grand_total']))
        
        total_item = self.ageing_tree.insert('', tk.END, values=total_values)
        self.ageing_tree.item(total_item, tags=('total',))
        self.ageing_tree.tag_configure('total', font=('Arial', 10, 'bold'), background='lightgray')
        
        # Display summary
        summary_text = f"As on: {report['as_on_date']}  |  "
        summary_text += f"Ageing Type: {report['ageing_type']}  |  "
        summary_text += f"Parties: {report['party_count']}  |  "
        summary_text += f"Grand Total: {self._format_amount(report['grand_total'])}"
        
        ttk.Label(
            self.summary_frame,
            text=summary_text,
            font=('Arial', 10, 'bold')
        ).pack(anchor=tk.W)
        
        # Display bucket-wise breakdown
        breakdown_frame = ttk.Frame(self.summary_frame)
        breakdown_frame.pack(fill=tk.X, pady=(10, 0))
        
        for bucket in buckets:
            bucket_frame = ttk.Frame(breakdown_frame)
            bucket_frame.pack(side=tk.LEFT, padx=(0, 20))
            
            ttk.Label(
                bucket_frame,
                text=bucket,
                font=('Arial', 9)
            ).pack()
            
            amount_label = ttk.Label(
                bucket_frame,
                text=self._format_amount(report['totals'][bucket]),
                font=('Arial', 9, 'bold')
            )
            amount_label.pack()
            
            # Color code
            if 'Above 180' in bucket or 'Above 90' in bucket:
                amount_label.config(foreground='red')
            elif '91-180' in bucket or '61-90' in bucket:
                amount_label.config(foreground='orange')
        
        # Display totals info
        totals_text = "Double-click on any party to view invoice-level ageing details"
        
        ttk.Label(
            self.totals_frame,
            text=totals_text,
            font=('Arial', 9, 'italic'),
            foreground='gray'
        ).pack(anchor=tk.W)
    
    def _on_party_double_click(self, event):
        """Handle double-click on party"""
        selection = self.ageing_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        
        # Check if it's the total row
        if self.ageing_tree.item(item)['tags'] and 'total' in self.ageing_tree.item(item)['tags']:
            return
        
        # Find party in report data
        if not self.current_report_data:
            return
        
        party_code = self.ageing_tree.item(item)['values'][0]
        party = next(
            (p for p in self.current_report_data['parties'] if p['account_code'] == party_code),
            None
        )
        
        if not party:
            return
        
        # Show party ageing details
        self._show_party_ageing_details(party)
    
    def _show_party_ageing_details(self, party: Dict[str, Any]):
        """Show detailed ageing for a party"""
        try:
            # Parse date
            as_on_date = datetime.strptime(
                self.as_on_date_var.get(),
                config.DISPLAY_DATE_FORMAT
            ).date()
            
            # Get detailed ageing
            self._set_status(f"Loading details for {party['account_name']}...")
            
            ageing_type = self.ageing_type_var.get()
            
            details = ageing_report_service.get_party_ageing_details(
                self.company_id,
                party['account_id'],
                ageing_type,
                as_on_date
            )
            
            if not details['success']:
                messagebox.showerror("Error", details.get('error', 'Failed to get details'))
                self._set_status("Error loading details")
                return
            
            # Show in popup
            self._show_details_popup(details)
            self._set_status("Ready")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load details: {str(e)}")
            self._set_status("Error")
    
    def _show_details_popup(self, details: Dict[str, Any]):
        """Show party ageing details in popup"""
        # Create popup window
        popup = tk.Toplevel(self.parent)
        popup.title(f"Ageing Details - {details['account']['name']}")
        popup.geometry("1000x600")
        
        # Header frame
        header_frame = ttk.Frame(popup, padding=10)
        header_frame.pack(fill=tk.X)
        
        header_text = f"Party: {details['account']['name']} ({details['account']['code']})\n"
        header_text += f"Total Outstanding: {self._format_amount(details['total'])}"
        
        ttk.Label(
            header_frame,
            text=header_text,
            font=('Arial', 11, 'bold')
        ).pack(anchor=tk.W)
        
        # Buckets summary
        buckets_frame = ttk.LabelFrame(popup, text="Ageing Summary", padding=10)
        buckets_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        bucket_display = ttk.Frame(buckets_frame)
        bucket_display.pack(fill=tk.X)
        
        for bucket_name, amount in details['buckets'].items():
            bucket_frame = ttk.Frame(bucket_display)
            bucket_frame.pack(side=tk.LEFT, padx=(0, 20))
            
            ttk.Label(
                bucket_frame,
                text=bucket_name,
                font=('Arial', 9)
            ).pack()
            
            ttk.Label(
                bucket_frame,
                text=self._format_amount(amount),
                font=('Arial', 9, 'bold')
            ).pack()
        
        # Invoices frame
        invoices_frame = ttk.LabelFrame(popup, text="Outstanding Invoices", padding=10)
        invoices_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Tree frame
        tree_frame = ttk.Frame(invoices_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Treeview
        columns = ('voucher_no', 'type', 'date', 'due_date', 'amount', 'ageing_days', 'bucket')
        
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
        tree.heading('type', text='Type')
        tree.heading('date', text='Date')
        tree.heading('due_date', text='Due Date')
        tree.heading('amount', text='Outstanding')
        tree.heading('ageing_days', text='Ageing Days')
        tree.heading('bucket', text='Ageing Bucket')
        
        # Column widths
        tree.column('voucher_no', width=120)
        tree.column('type', width=120)
        tree.column('date', width=100)
        tree.column('due_date', width=100)
        tree.column('amount', width=120, anchor='e')
        tree.column('ageing_days', width=100, anchor='center')
        tree.column('bucket', width=150)
        
        tree.pack(fill=tk.BOTH, expand=True)
        
        # Display invoices
        for invoice in details['invoices']:
            values = (
                invoice['voucher_number'],
                invoice.get('voucher_type', 'Invoice'),
                invoice['voucher_date'],
                invoice.get('due_date', 'N/A'),
                self._format_amount(invoice['outstanding_amount']),
                invoice['ageing_days'],
                invoice['ageing_bucket']
            )
            
            item = tree.insert('', tk.END, values=values)
            
            # Color code by bucket
            if 'Above 180' in invoice['ageing_bucket'] or 'Above 90' in invoice['ageing_bucket']:
                tree.item(item, tags=('critical',))
            elif '91-180' in invoice['ageing_bucket'] or '61-90' in invoice['ageing_bucket']:
                tree.item(item, tags=('high',))
        
        # Configure tags
        tree.tag_configure('critical', foreground='red')
        tree.tag_configure('high', foreground='orange')
        
        # Footer
        footer_frame = ttk.Frame(popup, padding=10)
        footer_frame.pack(fill=tk.X)
        
        footer_text = f"Total Invoices: {details['invoice_count']}  |  "
        footer_text += f"Total Outstanding: {self._format_amount(details['total'])}"
        
        ttk.Label(
            footer_frame,
            text=footer_text,
            font=('Arial', 10, 'bold')
        ).pack(side=tk.LEFT)
        
        # Close button
        ttk.Button(
            footer_frame,
            text="Close",
            command=popup.destroy
        ).pack(side=tk.RIGHT)
    
    def _on_search_changed(self, *args):
        """Handle search text change"""
        if not self.current_report_data:
            return
        
        search_term = self.search_var.get()
        
        if not search_term:
            # Restore full report
            self._display_report(self.current_report_data)
            return
        
        try:
            # Filter report
            filtered = ageing_report_service.search_parties(
                self.current_report_data,
                search_term
            )
            
            if filtered['success']:
                self._display_report(filtered)
                self._set_status(f"Found {filtered['party_count']} parties")
            
        except Exception as e:
            self._set_status(f"Search error: {str(e)}")
    
    def _export_to_csv(self):
        """Export report to CSV"""
        if not self.current_report_data:
            messagebox.showwarning("Warning", "Please generate a report first")
            return
        
        try:
            filename = f"ageing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            success, file_path = ageing_report_service.export_ageing_report_to_csv(
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
            filename = f"ageing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
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


def show_ageing_report(parent: tk.Widget, company_id: int) -> AgeingReportUI:
    """
    Show Ageing Report UI
    
    Args:
        parent: Parent widget
        company_id: Company ID
        
    Returns:
        AgeingReportUI instance
    """
    return AgeingReportUI(parent, company_id)
