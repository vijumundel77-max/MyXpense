"""
Report Exporter
Minimal export helper for report data (CSV / JSON) plus PNG screenshots
of report tables.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReportExporter:
    """Export report data to CSV and JSON."""

    @staticmethod
    def _ensure_exports_dir() -> Path:
        exports_dir = Path(config.EXPORTS_DIR)
        exports_dir.mkdir(parents=True, exist_ok=True)
        return exports_dir

    @staticmethod
    def export_table_to_png(widget: Any, filename: str) -> Tuple[bool, str]:
        """Capture the given widget (report table / treeview) as a PNG image.

        Works on Windows (PIL ImageGrab) and on X11/Linux (ImageMagick
        ``import``); returns a friendly message when no capture method is
        available.
        """
        try:
            from PIL import ImageGrab
            exports_dir = ReportExporter._ensure_exports_dir()
            output_path = exports_dir / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            width, height = widget.winfo_width(), widget.winfo_height()
            if width <= 1 or height <= 1:
                return False, "Report has not been rendered yet."
            image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
            image.save(output_path)
            return True, str(output_path)
        except ImportError:
            pass
        except Exception as exc:
            logger.error(f"Error exporting PNG: {exc}")
            return False, f"PNG export failed: {exc}"
        # Fallback for non-Windows platforms.
        try:
            import shutil
            import subprocess
            if shutil.which("import"):
                exports_dir = ReportExporter._ensure_exports_dir()
                output_path = exports_dir / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                result = subprocess.run(
                    ["import", "-window", str(widget.winfo_id()), str(output_path)],
                    capture_output=True, timeout=20,
                )
                if result.returncode == 0:
                    return True, str(output_path)
        except Exception as exc:
            logger.error(f"Error exporting PNG (fallback): {exc}")
        return False, "PNG export is only available on Windows (or with ImageMagick installed)."

    @staticmethod
    def export_to_json(data: Dict[str, Any], filename: str) -> Tuple[bool, str]:
        try:
            exports_dir = ReportExporter._ensure_exports_dir()
            output_path = exports_dir / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_path, "w", encoding="utf-8") as json_file:
                json.dump(data, json_file, indent=2, default=str)
            return True, str(output_path)
        except Exception as exc:
            logger.error(f"Error exporting JSON: {exc}")
            return False, f"Export failed: {exc}"

    @staticmethod
    def export_to_csv(data: Dict[str, Any], filename: str) -> Tuple[bool, str]:
        try:
            exports_dir = ReportExporter._ensure_exports_dir()
            output_path = exports_dir / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

            rows = ReportExporter._build_csv_rows(data)
            with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                for row in rows:
                    writer.writerow(row)

            return True, str(output_path)
        except Exception as exc:
            logger.error(f"Error exporting CSV: {exc}")
            return False, f"Export failed: {exc}"

    # Preferred column order for common report payloads; any key not listed
    # here is appended in sorted order so output stays deterministic.
    _PARTY_COLUMNS = [
        "account_code", "account_name", "account_group", "outstanding_balance",
        "balance_type", "is_receivable", "is_payable", "invoice_count",
        "buckets", "total", "opening_balance", "opening_type",
        "debit_total", "credit_total", "closing_balance", "closing_type",
        "transaction_count",
    ]
    _TRANSACTION_COLUMNS = [
        "voucher_date", "voucher_number", "voucher_type", "reference_number",
        "narration", "debit_amount", "credit_amount", "running_balance",
        "balance_type", "transaction_type", "transaction_date", "amount",
        "status", "account_mode", "payment_method",
    ]

    @staticmethod
    def _header_for(columns: List[str], items: List[Dict[str, Any]]) -> List[str]:
        known = [c for c in columns if any(c in item for item in items)]
        extra = sorted({c for item in items for c in item.keys() if c not in known})
        return known + extra

    @staticmethod
    def _build_csv_rows(data: Dict[str, Any]) -> List[List[Any]]:
        if not isinstance(data, dict):
            return [[str(data)]]

        rows: List[List[Any]] = []
        title = data.get("report_type") or data.get("title") or "Report"
        rows.append([title])

        for key in ("company", "account", "party_type", "outstanding_type", "ageing_type", "from_date", "to_date", "as_on_date"):
            if key in data and data[key] not in (None, ""):
                rows.append([key.replace("_", " ").title() + ":", data[key]])

        for section_key in ("totals", "opening_balance", "closing_balance"):
            section = data.get(section_key)
            if isinstance(section, dict):
                rows.append([])
                rows.append([section_key.replace("_", " ").title()])
                for k, v in section.items():
                    rows.append([k.replace("_", " ").title() + ":", v])

        parties = data.get("parties")
        if isinstance(parties, list) and parties:
            rows.append([])
            header = ReportExporter._header_for(ReportExporter._PARTY_COLUMNS, parties)
            rows.append(header)
            for item in parties:
                if isinstance(item, dict):
                    rows.append([item.get(col, "") for col in header])

        transactions = data.get("transactions")
        if isinstance(transactions, list) and transactions:
            rows.append([])
            header = ReportExporter._header_for(ReportExporter._TRANSACTION_COLUMNS, transactions)
            rows.append(header)
            for item in transactions:
                if isinstance(item, dict):
                    rows.append([item.get(col, "") for col in header])

        if not parties and not transactions:
            rows.append([])
            rows.append(["data", json.dumps(data, default=str)])

        return rows


report_exporter = ReportExporter()
