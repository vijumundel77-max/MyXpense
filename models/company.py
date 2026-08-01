from dataclasses import dataclass


@dataclass
class Company:
    id: int | None
    company_name: str
    address: str
    mobile: str
    email: str

    @classmethod
    def from_row(cls, row: tuple) -> "Company":
        return cls(
            id=row[0],
            company_name=row[1],
            address=row[2] or "",
            mobile=row[3] or "",
            email=row[4] or "",
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_name": self.company_name,
            "address": self.address,
            "mobile": self.mobile,
            "email": self.email,
        }
