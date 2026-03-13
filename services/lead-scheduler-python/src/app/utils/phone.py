"""
Phone number normalization to E.164 for consistent storage and stop-list checks.
"""
import re
from typing import Optional

# Basic normalization: strip non-digits, then ensure +prefix for E.164
def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """
    Normalize to E.164-like form: digits only, optional leading +.
    If input is None or empty, returns None.
    """
    if not phone or not isinstance(phone, str):
        return None
    digits = re.sub(r"\D", "", phone.strip())
    if not digits:
        return None
    # US/NA: assume 10 digits => +1XXXXXXXXXX; 11 digits starting with 1 => +1...
    if len(digits) == 10 and digits[0] in "2-9":
        return "+1" + digits
    if len(digits) == 11 and digits[0] == "1":
        return "+" + digits
    # Otherwise return + and all digits (international)
    return "+" + digits.lstrip("0") if digits != "0" else "+" + digits
