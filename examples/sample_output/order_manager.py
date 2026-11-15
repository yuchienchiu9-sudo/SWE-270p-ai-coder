import time
import uuid
from typing import List, Optional
from models import Order, CartItem
from cart import CartManager
from payment import validate_payment


class OrderManager:
    """Manages food orders, placement, and automatic status progression based on elapsed time."""

    def __init__(self):
        """Initializes an empty list of orders."""
        self.orders: List[Order] = []

    def place_order(
        self,
        cart_manager: CartManager,
        card_number: str,
        expiry_date: str,
        cvv: str,
        current_time: Optional[float] = None
    ) -> tuple[bool, str, Optional[Order]]:
        """Validates payment for items in the cart and creates a new order if successful.

        Empties the cart upon successful payment and assigns a unique order ID.
        Returns a tuple of (success, message, created_order).
        """
        if not cart_manager.items:
            return False, "Your cart is empty. Please add items before placing an order.", None

        # Validate payment
        is_valid, payment_message = validate_payment(card_number, expiry_date, cvv)
        if not is_valid:
            return False, payment_message, None

        # Create order
        order_id = "ORD-" + str(uuid.uuid4())[:8].upper()
        restaurant_name = cart_manager.items[0].restaurant_name
        total_amount = cart_manager.get_total()
        created_at = current_time if current_time is not None else time.time()

        new_order = Order(
            id=order_id,
            restaurant_name=restaurant_name,
            items=list(cart_manager.items),
            total_amount=total_amount,
            status="Pending",
            created_at=created_at
        )

        self.orders.append(new_order)
        cart_manager.clear()

        return True, "Payment successful! Your order has been placed.", new_order

    def update_order_statuses(self, current_time: Optional[float] = None) -> None:
        """Automatically updates order statuses based on elapsed time.

        Progression rules:
        - 0-10 seconds: Pending
        - 10-20 seconds: Preparing
        - 20-30 seconds: Delivering
        - 30+ seconds: Delivered
        Statuses never move backward.
        """
        now = current_time if current_time is not None else time.time()

        for order in self.orders:
            elapsed = now - order.created_at

            if elapsed >= 30:
                order.status = "Delivered"
            elif elapsed >= 20:
                if order.status in ["Pending", "Preparing"]:
                    order.status = "Delivering"
            elif elapsed >= 10:
                if order.status == "Pending":
                    order.status = "Preparing"
            else:
                # Keep as Pending if under 10 seconds
                pass

    def get_order_by_id(self, order_id: str) -> Optional[Order]:
        """Retrieves an order by its unique ID."""
        for order in self.orders:
            if order.id == order_id:
                return order
        return None

    def get_all_orders(self) -> List[Order]:
        """Returns all placed orders."""
        return self.orders
