from typing import List, Dict
from models import MenuItem, CartItem


class CartManager:
    """Manages the shopping cart items, single-restaurant enforcement, and pricing calculations."""

    def __init__(self):
        """Initializes an empty shopping cart."""
        self.items: List[CartItem] = []

    def add_item(self, restaurant_id: str, restaurant_name: str, menu_item: MenuItem, quantity: int = 1) -> None:
        """Adds an item to the cart or updates quantity if it already exists.

        Enforces the rule that a cart can only contain items from one restaurant at a time.
        Raises ValueError if quantity is not a positive integer or if items from a different
        restaurant are already in the cart.
        """
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")

        # Enforce single-restaurant rule
        if self.items:
            current_restaurant_id = self.items[0].restaurant_id
            if current_restaurant_id != restaurant_id:
                raise ValueError(
                    f"Your cart contains items from another restaurant ({self.items[0].restaurant_name}). "
                    "Please clear your cart before ordering from a different restaurant."
                )

        # Check if item already exists in cart
        existing_item = None
        for item in self.items:
            if item.menu_item.id == menu_item.id:
                existing_item = item
                break

        if existing_item:
            existing_item.quantity += quantity
        else:
            self.items.append(
                CartItem(
                    menu_item=menu_item,
                    quantity=quantity,
                    restaurant_id=restaurant_id,
                    restaurant_name=restaurant_name
                )
            )

    def remove_item(self, menu_item_id: str) -> None:
        """Removes an item from the cart by its menu item ID."""
        self.items = [item for item in self.items if item.menu_item.id != menu_item_id]

    def update_quantity(self, menu_item_id: str, quantity: int) -> None:
        """Updates the quantity of a specific cart item.

        Raises ValueError if the quantity is not a positive integer.
        """
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")

        for item in self.items:
            if item.menu_item.id == menu_item_id:
                item.quantity = quantity
                return

    def get_subtotal(self, item: CartItem) -> float:
        """Calculates the subtotal for a specific cart item."""
        return item.menu_item.price * item.quantity

    def get_total(self) -> float:
        """Calculates the total cost of all items in the cart."""
        return sum(self.get_subtotal(item) for item in self.items)

    def clear(self) -> None:
        """Clears all items from the cart."""
        self.items = []

    def get_restaurant_id(self) -> str | None:
        """Returns the ID of the restaurant associated with items currently in the cart."""
        if not self.items:
            return None
        return self.items[0].restaurant_id
