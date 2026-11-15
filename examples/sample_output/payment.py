import re
from datetime import datetime

def validate_payment(card_number: str, expiry_date: str, cvv: str) -> tuple[bool, str]:
    """Validates credit card details for basic format correctness.
    
    Checks:
    - Card number: 13 to 19 digits, ignoring spaces or hyphens.
    - Expiry date: MM/YY format where MM is 01-12 and YY is valid (not expired based on current year/month).
    - CVV: 3 or 4 digits.
    
    Returns a tuple of (is_valid, error_message).
    """
    # Clean card number
    cleaned_card = re.sub(r'\s+|-', '', card_number)
    if not cleaned_card.isdigit() or not (13 <= len(cleaned_card) <= 19):
        return False, "Invalid card number. Must be between 13 and 19 digits."

    # Validate Expiry Date (MM/YY)
    if not re.match(r'^(0[1-9]|1[0-2])/\d{2}$', expiry_date.strip()):
        return False, "Invalid expiry date format. Use MM/YY."

    try:
        month_str, year_str = expiry_date.strip().split('/')
        exp_month = int(month_str)
        exp_year = int("20" + year_str)

        now = datetime.now()
        current_year = now.year
        current_month = now.month

        if exp_year < current_year or (exp_year == current_year and exp_month < current_month):
            return False, "Card has expired."
    except ValueError:
        return False, "Invalid expiry date values."

    # Validate CVV
    cleaned_cvv = cvv.strip()
    if not cleaned_cvv.isdigit() or not (3 <= len(cleaned_cvv) <= 4):
        return False, "Invalid CVV. Must be 3 or 4 digits."

    return True, "Payment approved successfully."
