"""
Report Exporter
Minimal export helper for report data.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

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
            header = sorted({key for item in parties if isinstance(item, dict) for key in item.keys()})
            rows.append(header)
            for item in parties:
                if isinstance(item, dict):
                    rows.append([item.get(col, "") for col in header])

        transactions = data.get("transactions")
        if isinstance(transactions, list) and transactions:
            rows.append([])
            header = sorted({key for item in transactions if isinstance(item, dict) for key in item.keys()})
            rows.append(header)
            for item in transactions:
                if isinstance(item, dict):
                    rows.append([item.get(col, "") for col in header])

        if not parties and not transactions:
            rows.append([])
            rows.append(["data", json.dumps(data, default=str)])

        return rows


report_exporter = ReportExporter()
