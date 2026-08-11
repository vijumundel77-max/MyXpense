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
    """Business logic for the Expenzo multi-company master.

    Manages rows in the ``companies`` table. The legacy single-row
    ``company`` table is left untouched for data preservation.
    """

    def __init__(self, database: Database):
        self._db = database

    # ------------------------------------------------------------------ #
    # list / load
    # ------------------------------------------------------------------ #
    def list_companies(self, search_term: str = "") -> list[dict[str, Any]]:
        """All companies (id, name, financial year, contact, address)."""
        if search_term:
            rows = self._db.fetch_all(
                """
                SELECT id, name, financial_year_start, financial_year_end,
                       address, state, country, pincode, mobile, email, books_begin_date
                FROM companies
                WHERE LOWER(name) LIKE ?
                ORDER BY name
                """,
                (f"%{search_term.lower()}%",),
            )
        else:
            rows = self._db.fetch_all(
                """
                SELECT id, name, financial_year_start, financial_year_end,
                       address, state, country, pincode, mobile, email, books_begin_date
                FROM companies
                ORDER BY name
                """
            )
        return [self._row_to_dict(row) for row in rows]

    def get_company(self, company_id: int) -> Company | None:
        row = self._db.fetch_one(
            """
            SELECT id, name, address, state, country, pincode, mobile, email,
                   financial_year_start, financial_year_end, books_begin_date
            FROM companies
            WHERE id = ?
            """,
            (company_id,),
        )
        if row is None:
            return None
        return self._company_from_row(row)

    def load_company(self) -> Company | None:
        """Legacy-compatible loader: returns the first company row."""
        row = self._db.fetch_one(
            """
            SELECT id, name, address, state, country, pincode, mobile, email,
                   financial_year_start, financial_year_end, books_begin_date
            FROM companies
            ORDER BY id
            LIMIT 1
            """
        )
        if row is None:
            return None
        return self._company_from_row(row)

    def get_company_by_id(self, company_id: int) -> Company | None:
        return self.get_company(company_id)

    # ------------------------------------------------------------------ #
    # save / update / delete
    # ------------------------------------------------------------------ #
    def save_company(
        self,
        company_name: str,
        address: str,
        mobile: str,
        email: str,
        financial_year_start: str = "01-04",
        financial_year_end: str = "31-03",
        books_begin_date: str = "",
        state: str = "",
        country: str = "",
        pincode: str = "",
    ) -> Company:
        """Legacy single-row save: refuses to create a second company.

        Multi-company creation goes through :meth:`create_company`.
        """
        self._validate(company_name, mobile, email)

        if self._db.company_exists():
            raise CompanyServiceError(
                "A company already exists. Use Update to modify it."
            )

        if self._db.company_name_exists(company_name.strip()):
            raise CompanyServiceError(
                "A company with this name already exists."
            )

        company_id = self._db.execute(
            """
            INSERT INTO companies (
                name, financial_year_start, financial_year_end,
                address, state, country, pincode, mobile, email, books_begin_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_name.strip(),
                financial_year_start,
                financial_year_end,
                address.strip(),
                state.strip(),
                country.strip(),
                pincode.strip(),
                mobile.strip(),
                email.strip(),
                books_begin_date,
            ),
        )
        return Company(
            id=company_id,
            company_name=company_name.strip(),
            address=address.strip(),
            mobile=mobile.strip(),
            email=email.strip(),
            financial_year_start=financial_year_start,
            financial_year_end=financial_year_end,
            books_begin_date=books_begin_date,
            state=state.strip(),
            country=country.strip(),
            pincode=pincode.strip(),
        )

    def create_company(
        self,
        company_name: str,
        address: str = "",
        mobile: str = "",
        email: str = "",
        financial_year_start: str = "01-04",
        financial_year_end: str = "31-03",
        books_begin_date: str = "",
        state: str = "",
        country: str = "",
        pincode: str = "",
    ) -> Company:
        """Multi-company create. Returns the new company."""
        self._validate(company_name, mobile, email)

        if self._db.company_name_exists(company_name.strip()):
            raise CompanyServiceError(
                "A company with this name already exists."
            )

        company_id = self._db.execute(
            """
            INSERT INTO companies (
                name, financial_year_start, financial_year_end,
                address, state, country, pincode, mobile, email, books_begin_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_name.strip(),
                financial_year_start,
                financial_year_end,
                address.strip(),
                state.strip(),
                country.strip(),
                pincode.strip(),
                mobile.strip(),
                email.strip(),
                books_begin_date,
            ),
        )
        return Company(
            id=company_id,
            company_name=company_name.strip(),
            address=address.strip(),
            mobile=mobile.strip(),
            email=email.strip(),
            financial_year_start=financial_year_start,
            financial_year_end=financial_year_end,
            books_begin_date=books_begin_date,
            state=state.strip(),
            country=country.strip(),
            pincode=pincode.strip(),
        )

    def update_company(
        self,
        company_id: int,
        company_name: str,
        address: str = "",
        mobile: str = "",
        email: str = "",
        financial_year_start: str = "01-04",
        financial_year_end: str = "31-03",
        books_begin_date: str = "",
        state: str = "",
        country: str = "",
        pincode: str = "",
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

        self._db.execute(
            """
            UPDATE companies
            SET name = ?, financial_year_start = ?, financial_year_end = ?,
                address = ?, state = ?, country = ?, pincode = ?,
                mobile = ?, email = ?, books_begin_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                company_name.strip(),
                financial_year_start,
                financial_year_end,
                address.strip(),
                state.strip(),
                country.strip(),
                pincode.strip(),
                mobile.strip(),
                email.strip(),
                books_begin_date,
                company_id,
            ),
        )
        return Company(
            id=company_id,
            company_name=company_name.strip(),
            address=address.strip(),
            mobile=mobile.strip(),
            email=email.strip(),
            financial_year_start=financial_year_start,
            financial_year_end=financial_year_end,
            books_begin_date=books_begin_date,
            state=state.strip(),
            country=country.strip(),
            pincode=pincode.strip(),
        )

    def delete_company(self, company_id: int) -> None:
        existing = self._db.get_company_by_id(company_id)
        if existing is None:
            raise CompanyServiceError("Company record not found.")

        self._db.execute("DELETE FROM companies WHERE id = ?", (company_id,))

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate(company_name: str, mobile: str, email: str) -> None:
        try:
            validate_company_fields(company_name, mobile, email)
        except ValidationError as exc:
            raise CompanyServiceError(exc.message) from exc

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "id": CompanyService._value(row, "id"),
            "name": CompanyService._value(row, "name", ""),
            "financial_year_start": CompanyService._value(row, "financial_year_start", "01-04"),
            "financial_year_end": CompanyService._value(row, "financial_year_end", "31-03"),
            "address": CompanyService._value(row, "address", ""),
            "state": CompanyService._value(row, "state", ""),
            "country": CompanyService._value(row, "country", ""),
            "pincode": CompanyService._value(row, "pincode", ""),
            "mobile": CompanyService._value(row, "mobile", ""),
            "email": CompanyService._value(row, "email", ""),
            "books_begin_date": CompanyService._value(row, "books_begin_date", ""),
        }

    @staticmethod
    def _value(row: Any, key: str, default: Any = None) -> Any:
        try:
            return row[key]
        except Exception:
            try:
                return row.get(key, default)  # type: ignore[attr-defined]
            except Exception:
                return default

    @staticmethod
    def _company_from_row(row: Any) -> Company:
        if hasattr(row, "keys"):
            return Company(
                id=row["id"],
                company_name=row["name"],
                address=row["address"] or "",
                mobile=row["mobile"] or "",
                email=row["email"] or "",
                financial_year_start=row["financial_year_start"] or "01-04",
                financial_year_end=row["financial_year_end"] or "31-03",
                books_begin_date=row["books_begin_date"] or "",
                state=row["state"] or "",
                country=row["country"] or "",
                pincode=row["pincode"] or "",
            )
        return Company.from_row(row)
