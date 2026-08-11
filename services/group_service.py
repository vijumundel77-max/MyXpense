"""
Group Service
CRUD + hierarchy helpers for the Chart of Accounts ``groups`` master.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from database.database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_GROUP_TYPES = ("Assets", "Liabilities", "Capital", "Income", "Expense")


class GroupServiceError(Exception):
    """Raised when a group operation cannot be completed."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class GroupService:
    """Service for group master CRUD."""

    GROUP_TYPES = DEFAULT_GROUP_TYPES

    @staticmethod
    def _row_value(row: Any, key: str, default: Any = None) -> Any:
        if row is None:
            return default
        try:
            return row[key]
        except Exception:
            try:
                return row.get(key, default)  # type: ignore[attr-defined]
            except Exception:
                return default

    @staticmethod
    def _to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": GroupService._row_value(row, "id"),
            "company_id": GroupService._row_value(row, "company_id"),
            "name": GroupService._row_value(row, "name", ""),
            "group_type": GroupService._row_value(row, "group_type", "Assets"),
            "parent_id": GroupService._row_value(row, "parent_id"),
            "behaves_like_sub_ledger": bool(GroupService._row_value(row, "behaves_like_sub_ledger", 0)),
            "net_balance_for_reporting": bool(GroupService._row_value(row, "net_balance_for_reporting", 0)),
            "used_for_calculation": bool(GroupService._row_value(row, "used_for_calculation", 0)),
            "allocation_method": GroupService._row_value(row, "allocation_method", ""),
            "is_active": bool(GroupService._row_value(row, "is_active", 1)),
        }

    @staticmethod
    def list_groups(company_id: int, search_term: str = "", include_inactive: bool = False) -> List[Dict[str, Any]]:
        """List groups for a company, optionally filtered by search term."""
        try:
            where = ["company_id = ?"]
            params: List[Any] = [company_id]
            if search_term:
                where.append("LOWER(name) LIKE ?")
                params.append(f"%{search_term.lower()}%")
            if not include_inactive:
                where.append("is_active = 1")
            rows = db.fetch_all(
                f"""
                SELECT id, company_id, name, group_type, parent_id, is_active,
                       behaves_like_sub_ledger, net_balance_for_reporting,
                       used_for_calculation, allocation_method
                FROM groups
                WHERE {' AND '.join(where)}
                ORDER BY group_type, name
                """,
                tuple(params),
            )
            return [GroupService._to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return []

    @staticmethod
    def get_group(group_id: int) -> Optional[Dict[str, Any]]:
        try:
            row = db.fetch_one(
                """
                SELECT id, company_id, name, group_type, parent_id, is_active,
                       behaves_like_sub_ledger, net_balance_for_reporting,
                       used_for_calculation, allocation_method
                FROM groups
                WHERE id = ?
                """,
                (group_id,),
            )
            return GroupService._to_dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting group: {e}")
            return None

    @staticmethod
    def group_name_exists(company_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
        if exclude_id is None:
            row = db.fetch_one(
                "SELECT COUNT(*) AS count FROM groups WHERE company_id = ? AND LOWER(name) = LOWER(?)",
                (company_id, name),
            )
        else:
            row = db.fetch_one(
                "SELECT COUNT(*) AS count FROM groups WHERE company_id = ? AND LOWER(name) = LOWER(?) AND id != ?",
                (company_id, name, exclude_id),
            )
        count = int(GroupService._row_value(row, "count", 0) or 0) if row else 0
        return count > 0

    @staticmethod
    def group_has_children(group_id: int) -> bool:
        row = db.fetch_one("SELECT COUNT(*) AS count FROM groups WHERE parent_id = ?", (group_id,))
        count = int(GroupService._row_value(row, "count", 0) or 0) if row else 0
        return count > 0

    @staticmethod
    def group_has_ledgers(group_id: int, company_id: int) -> bool:
        group = GroupService.get_group(group_id)
        if not group:
            return False
        row = db.fetch_one(
            "SELECT COUNT(*) AS count FROM accounts WHERE company_id = ? AND LOWER(account_group) = LOWER(?)",
            (company_id, group["name"]),
        )
        count = int(GroupService._row_value(row, "count", 0) or 0) if row else 0
        return count > 0

    @staticmethod
    def create_group(company_id: int, name: str, group_type: str = "Assets", parent_id: Optional[int] = None, is_active: bool = True,
                     behaves_like_sub_ledger: bool = False, net_balance_for_reporting: bool = False,
                     used_for_calculation: bool = False, allocation_method: str = "") -> Tuple[bool, str, Optional[int]]:
        """Create a group. Returns (success, message, group_id)."""
        try:
            name = str(name or "").strip()
            group_type = str(group_type or "Assets").strip()
            if not name:
                return False, "Group name is required", None
            if group_type not in GroupService.GROUP_TYPES:
                return False, "Invalid group type", None
            if GroupService.group_name_exists(company_id, name):
                return False, "A group with this name already exists", None
            if parent_id is not None:
                parent = GroupService.get_group(parent_id)
                if not parent or parent["company_id"] != company_id:
                    return False, "Selected parent group is invalid", None

            group_id = db.execute(
                """
                INSERT INTO groups (
                    company_id, name, group_type, parent_id, is_active,
                    behaves_like_sub_ledger, net_balance_for_reporting,
                    used_for_calculation, allocation_method
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, name, group_type, parent_id if parent_id else None, 1 if is_active else 0,
                    1 if behaves_like_sub_ledger else 0,
                    1 if net_balance_for_reporting else 0,
                    1 if used_for_calculation else 0,
                    allocation_method or "",
                ),
            )
            return True, "Group saved successfully", group_id
        except Exception as e:
            logger.error(f"Error creating group: {e}")
            return False, f"Failed to save group: {str(e)}", None

    @staticmethod
    def update_group(group_id: int, name: str, group_type: str = "Assets", parent_id: Optional[int] = None, is_active: bool = True,
                     behaves_like_sub_ledger: bool = False, net_balance_for_reporting: bool = False,
                     used_for_calculation: bool = False, allocation_method: str = "") -> Tuple[bool, str]:
        try:
            existing = GroupService.get_group(group_id)
            if not existing:
                return False, "Group not found"

            name = str(name or "").strip()
            group_type = str(group_type or "Assets").strip()
            if not name:
                return False, "Group name is required"
            if group_type not in GroupService.GROUP_TYPES:
                return False, "Invalid group type"
            if GroupService.group_name_exists(existing["company_id"], name, exclude_id=group_id):
                return False, "Another group with this name already exists"

            if parent_id is not None:
                if int(parent_id) == int(group_id):
                    return False, "A group cannot be its own parent"
                if GroupService._is_descendant(group_id, parent_id):
                    return False, "A group cannot be a parent of its own ancestor"
                parent = GroupService.get_group(parent_id)
                if not parent or parent["company_id"] != existing["company_id"]:
                    return False, "Selected parent group is invalid"

            db.execute(
                """
                UPDATE groups
                SET name = ?, group_type = ?, parent_id = ?, is_active = ?,
                    behaves_like_sub_ledger = ?, net_balance_for_reporting = ?,
                    used_for_calculation = ?, allocation_method = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    name, group_type, parent_id if parent_id else None, 1 if is_active else 0,
                    1 if behaves_like_sub_ledger else 0,
                    1 if net_balance_for_reporting else 0,
                    1 if used_for_calculation else 0,
                    allocation_method or "",
                    group_id,
                ),
            )
            return True, "Group updated successfully"
        except Exception as e:
            logger.error(f"Error updating group: {e}")
            return False, f"Failed to update group: {str(e)}"

    @staticmethod
    def _is_descendant(ancestor_id: int, candidate_id: int) -> bool:
        """True when ``candidate_id`` is a descendant of ``ancestor_id``."""
        seen: set[int] = set()
        current: Optional[int] = candidate_id
        while current is not None:
            if current in seen:
                return False
            seen.add(current)
            row = db.fetch_one("SELECT parent_id FROM groups WHERE id = ?", (current,))
            if row is None:
                return False
            parent_id = GroupService._row_value(row, "parent_id")
            if parent_id is None:
                return False
            if int(parent_id) == int(ancestor_id):
                return True
            current = int(parent_id)
        return False

    @staticmethod
    def delete_group(group_id: int) -> Tuple[bool, str]:
        try:
            existing = GroupService.get_group(group_id)
            if not existing:
                return False, "Group not found"
            if GroupService.group_has_children(group_id):
                return False, "Cannot delete a group that has sub-groups"
            if GroupService.group_has_ledgers(group_id, existing["company_id"]):
                return False, "Cannot delete a group that has ledgers assigned"
            db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            return True, "Group deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting group: {e}")
            return False, f"Failed to delete group: {str(e)}"

    @staticmethod
    def search_groups(company_id: int, search_term: str) -> List[Dict[str, Any]]:
        return GroupService.list_groups(company_id, search_term)

    # ------------------------------------------------------------------ #
    # default Chart of Accounts groups (Tally-style)
    # ------------------------------------------------------------------ #
    # The canonical 30-group default list. Seeded idempotently per company:
    # existing groups are preserved, missing ones are created, duplicates are
    # never inserted, and existing accounting data is never reset.
    DEFAULT_GROUPS = [
        "Bank Accounts",
        "Bank OCC A/c",
        "Bank OD A/c",
        "Branch / Divisions",
        "Capital Account",
        "Cash-in-Hand",
        "Current Assets",
        "Current Liabilities",
        "Deposits (Asset)",
        "Direct Expenses",
        "Direct Incomes",
        "Duties & Taxes",
        "Fixed Assets",
        "Indirect Expenses",
        "Indirect Incomes",
        "Investments",
        "Loans & Advances (Asset)",
        "Loans (Liability)",
        "Misc. Expenses (ASSET)",
        "Provisions",
        "Purchase Accounts",
        "Reserves & Surplus",
        "Retained Earnings",
        "Sales Accounts",
        "Secured Loans",
        "Stock-in-Hand",
        "Sundry Creditors",
        "Sundry Debtors",
        "Suspense A/c",
        "Unsecured Loans",
    ]

    # Map each default group to its accounting nature for the group_type column.
    DEFAULT_GROUP_TYPES = {
        "Bank Accounts": "Assets",
        "Bank OCC A/c": "Assets",
        "Bank OD A/c": "Liabilities",
        "Branch / Divisions": "Assets",
        "Capital Account": "Capital",
        "Cash-in-Hand": "Assets",
        "Current Assets": "Assets",
        "Current Liabilities": "Liabilities",
        "Deposits (Asset)": "Assets",
        "Direct Expenses": "Expense",
        "Direct Incomes": "Income",
        "Duties & Taxes": "Liabilities",
        "Fixed Assets": "Assets",
        "Indirect Expenses": "Expense",
        "Indirect Incomes": "Income",
        "Investments": "Assets",
        "Loans & Advances (Asset)": "Assets",
        "Loans (Liability)": "Liabilities",
        "Misc. Expenses (ASSET)": "Assets",
        "Provisions": "Liabilities",
        "Purchase Accounts": "Expense",
        "Reserves & Surplus": "Capital",
        "Retained Earnings": "Capital",
        "Sales Accounts": "Income",
        "Secured Loans": "Liabilities",
        "Stock-in-Hand": "Assets",
        "Sundry Creditors": "Liabilities",
        "Sundry Debtors": "Assets",
        "Suspense A/c": "Assets",
        "Unsecured Loans": "Liabilities",
    }

    @staticmethod
    def seed_default_groups(company_id: int) -> List[str]:
        """Idempotently seed the 30 default groups for a company.

        Existing groups (matched case-insensitively) are preserved untouched;
        only missing groups are inserted. Returns the names that were created.
        """
        created: List[str] = []
        try:
            existing = GroupService.list_groups(company_id, include_inactive=True)
            existing_names = {g["name"].strip().lower() for g in existing}

            for name in GroupService.DEFAULT_GROUPS:
                key = name.strip().lower()
                if key in existing_names:
                    continue
                group_type = GroupService.DEFAULT_GROUP_TYPES.get(name, "Assets")
                db.execute(
                    """
                    INSERT INTO groups (company_id, name, group_type, parent_id, is_active)
                    VALUES (?, ?, ?, NULL, 1)
                    """,
                    (company_id, name, group_type),
                )
                existing_names.add(key)
                created.append(name)
        except Exception as e:
            logger.error(f"Error seeding default groups: {e}")
        return created

    @staticmethod
    def group_tree(company_id: int, search_term: str = "", include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Flattened group list with an indented display name for hierarchy."""
        groups = GroupService.list_groups(company_id, search_term, include_inactive=include_inactive)
        by_parent: Dict[Optional[int], List[Dict[str, Any]]] = {}
        for group in groups:
            by_parent.setdefault(group.get("parent_id"), []).append(group)

        ordered: List[Dict[str, Any]] = []

        def walk(parent_id: Optional[int], depth: int) -> None:
            for group in sorted(by_parent.get(parent_id, []), key=lambda g: g["name"].lower()):
                group = dict(group)
                group["depth"] = depth
                group["display_name"] = ("  " * depth) + group["name"]
                ordered.append(group)
                walk(group["id"], depth + 1)

        walk(None, 0)
        return ordered


group_service = GroupService()
