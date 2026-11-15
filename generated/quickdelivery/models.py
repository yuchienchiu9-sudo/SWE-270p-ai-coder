"""
models.py

Defines data structures and logic for shopping cart management, order handling,
and order status validation for the QuickDelivery application.
"""

class Cart:
    """Manages items in the user's shopping cart."""

    def __init__(self):
        # Dictionary mapping item_id (str) to a dict containing name, price, quantity, restaurant_id
        self.items = {}

    def add_item(self, item_id: str, name: str, price: float, quantity: int, restaurant_id: str) -> None:
        """Add or update an item in the cart with a positive integer quantity."""
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
        
        # If cart already has items from another restaurant, enforce single restaurant cart
        existing_restaurant = self.get_restaurant_id()
        if existing_restaurant and existing_restaurant != restaurant_id:
            raise ValueError("Cannot add items from different restaurants to the same cart.")

        if item_id in self.items:
            self.items[item_id]["quantity"] += quantity
        else:
            self.items[item_id] = {
                "name": name,
                "price": price,
                "quantity": quantity,
                "restaurant_id": restaurant_id
            }

    def remove_item(self, item_id: str, quantity: int = None) -> None:
        """Remove a specific quantity of an item, or remove it entirely if quantity is None or >= existing."""
        if item_id not in self.items:
            return

        if quantity is None:
            del self.items[item_id]
        else:
            if not isinstance(quantity, int) or quantity <= 0:
                raise ValueError("Quantity to remove must be a positive integer.")
            
            self.items[item_id]["quantity"] -= quantity
            if self.items[item_id]["quantity"] <= 0:
                del self.items[item_id]

    def get_restaurant_id(self) -> str:
        """Return the restaurant ID of the items currently in the cart, or None if empty."""
        for item in self.items.values():
            return item["restaurant_id"]
        return None

    def get_total_price(self) -> float:
        """Calculate total price of all items in the cart."""
        return sum(item["price"] * item["quantity"] for item in self.items.values())

    def clear(self) -> None:
        """Clear all items from the cart."""
        self.items.clear()

    def to_list(self) -> list:
        """Return a list representation of cart items."""
        result = []
        for item_id, details in self.items.items():
            item_copy = details.copy()
            item_copy["item_id"] = item_id
            result.append(item_copy)
        return result


class Order:
    """Represents a food order and tracks its lifecycle status."""

    VALID_STATUSES = ["Pending", "Preparing", "Delivering", "Delivered"]

    def __init__(self, order_id: str, restaurant_id: str, items: list, total_amount: float):
        self.order_id = order_id
        self.restaurant_id = restaurant_id
        self.items = items
        self.total_amount = total_amount
        self.status = "Pending"

    def update_status(self, new_status: str) -> None:
        """Update the order status if it is a valid transition."""
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}. Must be one of {self.VALID_STATUSES}.")
        
        current_index = self.VALID_STATUSES.index(self.status)
        new_index = self.VALID_STATUSES.index(new_status)

        # Enforce forward progression only
        if new_index < current_index:
            raise ValueError(f"Cannot transition backwards from {self.status} to {new_status}.")

        self.status = new_status

    def to_dict(self) -> dict:
        """Serialize order details into a dictionary."""
        return {
            "order_id": self.order_id,
            "restaurant_id": self.restaurant_id,
            "items": self.items,
            "total_amount": self.total_amount,
            "status": self.status
        }
