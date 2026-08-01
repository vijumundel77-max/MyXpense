import re


class ValidationError(Exception):
    """Raised when user input fails validation."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MOBILE_PATTERN = re.compile(r"^[0-9+\-\s()]{7,15}$")


def validate_company_fields(
    company_name: str,
    mobile: str,
    email: str,
) -> None:
    name = company_name.strip()
    if not name:
        raise ValidationError("Company name is required.")

    if len(name) > 200:
        raise ValidationError("Company name must be 200 characters or fewer.")

    mobile_value = mobile.strip()
    if mobile_value and not _MOBILE_PATTERN.match(mobile_value):
        raise ValidationError("Enter a valid mobile number (7–15 digits).")

    email_value = email.strip()
    if email_value and not _EMAIL_PATTERN.match(email_value):
        raise ValidationError("Enter a valid email address.")
