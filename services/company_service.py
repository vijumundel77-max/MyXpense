from __future__ import annotations

from typing import TYPE_CHECKING, Any

from models.company import Company
from utils.validators import ValidationError, validate_company_fields

if TYPE_CHECKING:
    from database import Database


class CompanyServiceError(Exception):
    """Raised when a company operation cannot be completed."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class CompanyService:
    """Business logic for company master operations."""

    def __init__(self, database: Database):
        self._db = database

    def load_company(self) -> Company | None:
        row = self._db.get_company()
        if row is None:
            return None
        return self._company_from_row(row)

    def save_company(
        self,
        company_name: str,
        address: str,
        mobile: str,
        email: str,
    ) -> Company:
        self._validate(company_name, mobile, email)

        if self._db.company_exists():
            raise CompanyServiceError(
                "A company already exists. Use Update to modify it."
            )

        if self._db.company_name_exists(company_name.strip()):
            raise CompanyServiceError(
                "A company with this name already exists."
            )

        company_id = self._db.insert_company(
            company_name.strip(),
            address.strip(),
            mobile.strip(),
            email.strip(),
        )
        return Company(
            id=company_id,
            company_name=company_name.strip(),
            address=address.strip(),
            mobile=mobile.strip(),
            email=email.strip(),
        )

    def update_company(
        self,
        company_id: int,
        company_name: str,
        address: str,
        mobile: str,
        email: str,
    ) -> Company:
        self._validate(company_name, mobile, email)

        existing = self._db.get_company_by_id(company_id)
        if existing is None:
            raise CompanyServiceError("Company record not found.")

        if self._db.company_name_exists(
            company_name.strip(),
            exclude_id=company_id,
        ):
            raise CompanyServiceError(
                "Another company with this name already exists."
            )

        self._db.update_company(
            company_id,
            company_name.strip(),
            address.strip(),
            mobile.strip(),
            email.strip(),
        )
        return Company(
            id=company_id,
            company_name=company_name.strip(),
            address=address.strip(),
            mobile=mobile.strip(),
            email=email.strip(),
        )

    def delete_company(self, company_id: int) -> None:
        existing = self._db.get_company_by_id(company_id)
        if existing is None:
            raise CompanyServiceError("Company record not found.")

        self._db.delete_company(company_id)

    @staticmethod
    def _validate(company_name: str, mobile: str, email: str) -> None:
        try:
            validate_company_fields(company_name, mobile, email)
        except ValidationError as exc:
            raise CompanyServiceError(exc.message) from exc

    @staticmethod
    def _company_from_row(row: Any) -> Company:
        if hasattr(row, "keys"):
            return Company(
                id=row["id"],
                company_name=row["company_name"],
                address=row["address"] or "",
                mobile=row["mobile"] or "",
                email=row["email"] or "",
            )
        return Company.from_row(row)
