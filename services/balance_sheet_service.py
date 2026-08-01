"""
Balance Sheet Service
Disabled in Expenzo V1 migration.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple


class BalanceSheetService:
    """Disabled balance sheet service placeholder."""

    @staticmethod
    def _disabled(*args, **kwargs) -> Dict[str, Any]:
        return {'success': False, 'error': 'Balance Sheet module is disabled in this build'}

    _validate_report_params = _disabled
    _extract_assets = _disabled
    _extract_liabilities = _disabled
    _extract_capital = _disabled
    _calculate_group_total = _disabled
    _calculate_section_total = _disabled
    _calculate_balance_sheet_difference = _disabled
    generate_balance_sheet = _disabled
    generate_balance_sheet_as_of = _disabled
    search_ledgers = _disabled
    export_balance_sheet_to_csv = _disabled
    export_balance_sheet_to_json = _disabled
    format_balance_sheet_for_print = _disabled
    get_net_worth = _disabled
    get_working_capital = _disabled


balance_sheet_service = BalanceSheetService()
