def process_payment(card_number: str, expiry: str, cvv: str, amount: float) -> bool:
    """
    Simulate payment processing for QuickDelivery orders.
    
    Args:
        card_number (str): The credit card number.
        expiry (str): Expiration date in MM/YY format.
        cvv (str): 3 or 4-digit security code.
        amount (float): The total amount to charge.
        
    Returns:
        bool: True if payment is successful, False otherwise.
    """
    # Basic validation rules for simulation
    if not card_number or len(card_number.replace(" ", "")) < 12:
        return False
    if not expiry or len(expiry) < 4:
        return False
    if not cvv or len(cvv) < 3:
        return False
    if amount <= 0:
        return False
        
    # All basic checks passed; simulate a successful transaction
    return True
