"""Strict numeric parsing shared by workbook and schedule validation."""

from decimal import Decimal, InvalidOperation


def integer(value, label, minimum=0, maximum=None):
    try:
        number = Decimal(str(value).strip())
        if isinstance(value, bool) or not number.is_finite() or number != number.to_integral_value():
            raise InvalidOperation
        result = int(number)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a whole number.") from None
    if result < minimum or (maximum is not None and result > maximum):
        limit = f"{minimum} to {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{label} must be {limit}.")
    return result
