from dataclasses import dataclass


@dataclass
class Company:
    id: int | None
    company_name: str
    address: str
    mobile: str
    email: str
    financial_year_start: str = "01-04"
    financial_year_end: str = "31-03"
    books_begin_date: str = ""
    state: str = ""
    country: str = ""
    pincode: str = ""

    @classmethod
    def from_row(cls, row: tuple) -> "Company":
        return cls(
            id=row[0],
            company_name=row[1],
            address=row[2] or "",
            mobile=row[3] or "",
            email=row[4] or "",
            financial_year_start=row[5] if len(row) > 5 else "01-04",
            financial_year_end=row[6] if len(row) > 6 else "31-03",
            books_begin_date=row[7] if len(row) > 7 else "",
            state=row[8] if len(row) > 8 else "",
            country=row[9] if len(row) > 9 else "",
            pincode=row[10] if len(row) > 10 else "",
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_name": self.company_name,
            "address": self.address,
            "mobile": self.mobile,
            "email": self.email,
            "financial_year_start": self.financial_year_start,
            "financial_year_end": self.financial_year_end,
            "books_begin_date": self.books_begin_date,
            "state": self.state,
            "country": self.country,
            "pincode": self.pincode,
        }
