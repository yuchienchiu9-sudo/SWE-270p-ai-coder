import pytest
import time
from datetime import datetime, timedelta

from models import MenuItem, Restaurant, CartItem, Order, INITIAL_RESTAURANTS
from cart import CartManager
from payment import validate_payment
from order_manager import OrderManager


def test_initial_restaurants_seed_data():
    """Test that initial restaurants are properly structured and seeded."""
    assert len(INITIAL_RESTAURANTS) >= 4
    for r in INITIAL_RESTAURANTS:
        assert isinstance(r, Restaurant)
        assert r.id
        assert r.name
        assert r.cuisine
        assert 0.0 <= r.rating <= 5.0
        assert r.delivery_time
        assert len(r.menu) > 0
        for item in r.menu:
            assert isinstance(item, MenuItem)
            assert item.id
            assert item.name
            assert item.price > 0.0


def test_cart_add_item_success():
    """Test successfully adding items to the cart."""
    cart = CartManager()
    menu_item = INITIAL_RESTAURANTS[0].menu[0]
    restaurant = INITIAL_RESTAURANTS[0]

    cart.add_item(restaurant.id, restaurant.name, menu_item, 2)
    assert len(cart.items) == 1
    assert cart.items[0].quantity == 2
    assert cart.items[0].menu_item.id == menu_item.id
    assert cart.get_restaurant_id() == restaurant.id


def test_cart_add_item_invalid_quantity():
    """Test that adding items with non-positive quantities raises ValueError."""
    cart = CartManager()
    menu_item = INITIAL_RESTAURANTS[0].menu[0]
    restaurant = INITIAL_RESTAURANTS[0]

    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.add_item(restaurant.id, restaurant.name, menu_item, 0)

    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.add_item(restaurant.id, restaurant.name, menu_item, -3)


def test_cart_single_restaurant_enforcement():
    """Test that adding items from a different restaurant raises ValueError."""
    cart = CartManager()
    rest1 = INITIAL_RESTAURANTS[0]
    rest2 = INITIAL_RESTAURANTS[1]

    cart.add_item(rest1.id, rest1.name, rest1.menu[0], 1)

    with pytest.raises(ValueError, match="Your cart contains items from another restaurant"):
        cart.add_item(rest2.id, rest2.name, rest2.menu[0], 1)


def test_cart_remove_item():
    """Test removing an item from the cart by its menu item ID."""
    cart = CartManager()
    rest = INITIAL_RESTAURANTS[0]
    item1 = rest.menu[0]
    item2 = rest.menu[1]

    cart.add_item(rest.id, rest.name, item1, 1)
    cart.add_item(rest.id, rest.name, item2, 2)
    assert len(cart.items) == 2

    cart.remove_item(item1.id)
    assert len(cart.items) == 1
    assert cart.items[0].menu_item.id == item2.id


def test_cart_update_quantity():
    """Test updating quantity of an existing cart item and handling invalid values."""
    cart = CartManager()
    rest = INITIAL_RESTAURANTS[0]
    item = rest.menu[0]

    cart.add_item(rest.id, rest.name, item, 1)
    cart.update_quantity(item.id, 5)
    assert cart.items[0].quantity == 5

    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.update_quantity(item.id, 0)

    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.update_quantity(item.id, -2)


def test_cart_calculations():
    """Test subtotal and total calculations for cart items."""
    cart = CartManager()
    rest = INITIAL_RESTAURANTS[0]
    item1 = rest.menu[0]  # price: 8.99
    item2 = rest.menu[2]  # price: 3.99

    cart.add_item(rest.id, rest.name, item1, 2)  # 17.98
    cart.add_item(rest.id, rest.name, item2, 1)  # 3.99

    assert cart.get_subtotal(cart.items[0]) == round(8.99 * 2, 2)
    assert cart.get_subtotal(cart.items[1]) == round(3.99 * 1, 2)
    assert cart.get_total() == round(17.98 + 3.99, 2)

    cart.clear()
    assert len(cart.items) == 0
    assert cart.get_total() == 0.0
    assert cart.get_restaurant_id() is None


def test_validate_payment_success():
    """Test valid credit card details validation."""
    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"
    valid, msg = validate_payment("4532-1234-5678-9010", f"12/{future_year_str}", "123")
    assert valid is True
    assert "approved" in msg


def test_validate_payment_invalid_card():
    """Test invalid card numbers in payment validation."""
    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"
    
    # Too short
    valid, msg = validate_payment("12345", f"12/{future_year_str}", "123")
    assert valid is False
    assert "card number" in msg.lower()

    # Non-digits
    valid, msg = validate_payment("4532-ABCD-5678-9010", f"12/{future_year_str}", "123")
    assert valid is False
    assert "card number" in msg.lower()


def test_validate_payment_invalid_expiry():
    """Test invalid or expired dates in payment validation."""
    # Bad format
    valid, msg = validate_payment("4532123456789010", "13/25", "123")
    assert valid is False
    assert "expiry date" in msg.lower()

    # Expired date
    valid, msg = validate_payment("4532123456789010", "01/20", "123")
    assert valid is False
    assert "expired" in msg.lower()


def test_validate_payment_invalid_cvv():
    """Test invalid CVV values in payment validation."""
    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"

    valid, msg = validate_payment("4532123456789010", f"12/{future_year_str}", "12")
    assert valid is False
    assert "cvv" in msg.lower()

    valid, msg = validate_payment("4532123456789010", f"12/{future_year_str}", "12345")
    assert valid is False
    assert "cvv" in msg.lower()


def test_order_placement_empty_cart():
    """Test placing an order with an empty cart fails."""
    cart = CartManager()
    manager = OrderManager()
    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"

    success, msg, order = manager.place_order(cart, "4532123456789010", f"12/{future_year_str}", "123")
    assert success is False
    assert "empty" in msg.lower()
    assert order is None


def test_order_placement_success_and_cart_clear():
    """Test successful order placement empties the cart and creates a valid order."""
    cart = CartManager()
    rest = INITIAL_RESTAURANTS[0]
    cart.add_item(rest.id, rest.name, rest.menu[0], 2)

    manager = OrderManager()
    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"

    success, msg, order = manager.place_order(cart, "4532123456789010", f"12/{future_year_str}", "123")
    assert success is True
    assert order is not None
    assert order.id.startswith("ORD-")
    assert order.status == "Pending"
    assert len(cart.items) == 0
    assert len(manager.get_all_orders()) == 1
    assert manager.get_order_by_id(order.id) == order


def test_order_status_progression():
    """Test automatic status progression of orders based on elapsed time rules."""
    manager = OrderManager()
    cart = CartManager()
    rest = INITIAL_RESTAURANTS[0]
    cart.add_item(rest.id, rest.name, rest.menu[0], 1)

    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"

    base_time = 1000.0
    success, msg, order = manager.place_order(
        cart, "4532123456789010", f"12/{future_year_str}", "123", current_time=base_time
    )
    assert order.status == "Pending"

    # 5 seconds elapsed -> Pending
    manager.update_order_statuses(current_time=base_time + 5)
    assert order.status == "Pending"

    # 12 seconds elapsed -> Preparing
    manager.update_order_statuses(current_time=base_time + 12)
    assert order.status == "Preparing"

    # 22 seconds elapsed -> Delivering
    manager.update_order_statuses(current_time=base_time + 22)
    assert order.status == "Delivering"

    # 35 seconds elapsed -> Delivered
    manager.update_order_statuses(current_time=base_time + 35)
    assert order.status == "Delivered"


def test_order_status_never_moves_backward():
    """Test that order statuses never move backward even if time goes backward or updates occur."""
    manager = OrderManager()
    cart = CartManager()
    rest = INITIAL_RESTAURANTS[0]
    cart.add_item(rest.id, rest.name, rest.menu[0], 1)

    future_year = (datetime.now().year + 1) % 100
    future_year_str = f"{future_year:02d}"

    base_time = 2000.0
    _, _, order = manager.place_order(
        cart, "4532123456789010", f"12/{future_year_str}", "123", current_time=base_time
    )

    # Advance to Delivered
    manager.update_order_statuses(current_time=base_time + 35)
    assert order.status == "Delivered"

    # Try updating with an earlier timestamp
    manager.update_order_statuses(current_time=base_time + 5)
    assert order.status == "Delivered"
