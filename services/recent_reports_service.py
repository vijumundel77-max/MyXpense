"""
Expenzo — Recently Opened Reports service.

UI-safe tracking of report openings for the Reports hub's "Recently Opened
Reports" panel.  This records only report navigation events (name, timestamp,
user) per company — it never touches accounting transactions or balances.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from database.database import db
import config

MAX_RECENT = 8


def record_report_open(company_id: int, report_name: str, opened_by: str = "Admin") -> None:
    """Record a report opening for a company (most recent first).

    The same report opened again is bumped to the top of the history.
    """
    if not report_name or not company_id:
        return
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return
    try:
        with db.transaction() as cursor:
            cursor.execute(
                "DELETE FROM recent_reports WHERE company_id = ? AND report_name = ?",
                (company_id, report_name),
            )
            cursor.execute(
                """
                INSERT INTO recent_reports (company_id, report_name, opened_by, opened_at)
                VALUES (?, ?, ?, ?)
                """,
                (company_id, report_name, opened_by,
                 datetime.now().strftime(config.DB_DATETIME_FORMAT)),
            )
            cursor.execute(
                """
                DELETE FROM recent_reports WHERE company_id = ? AND id NOT IN (
                    SELECT id FROM recent_reports
                    WHERE company_id = ?
                    ORDER BY opened_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (company_id, company_id, MAX_RECENT),
            )
    except Exception:
        # Recent-report tracking must never break report opening.
        pass


def recent_reports(company_id: int, limit: int = MAX_RECENT) -> List[Dict[str, str]]:
    """Most recently opened reports for a company, newest first."""
    try:
        company_id = int(company_id)
    except (TypeError, ValueError):
        return []
    rows = db.fetch_all(
        """
        SELECT report_name, opened_by, opened_at
        FROM recent_reports
        WHERE company_id = ?
        ORDER BY opened_at DESC, id DESC
        LIMIT ?
        """,
        (company_id, limit),
    )
    return [dict(row) for row in rows]


def clear_recent_reports(company_id: Optional[int] = None) -> None:
    """Clear recent-report history (used by tests / a future Clear action)."""
    if company_id is None:
        db.execute("DELETE FROM recent_reports")
    else:
        db.execute("DELETE FROM recent_reports WHERE company_id = ?", (int(company_id),))
