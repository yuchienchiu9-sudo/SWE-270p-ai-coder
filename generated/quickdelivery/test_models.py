import pytest
from models import Cart, Order

def test_cart_initialization():
    cart = Cart()
    assert cart.items == {}
    assert cart.get_restaurant_id() is None
    assert cart.get_total_price() == 0.0
    assert cart.to_list() == []

def test_cart_add_item_normal():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    assert len(cart.items) == 1
    assert cart.items["item1"]["quantity"] == 2
    assert cart.get_restaurant_id() == "rest1"
    assert cart.get_total_price() == 20.0

def test_cart_add_item_invalid_quantity():
    cart = Cart()
    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.add_item("item1", "Pizza", 10.0, 0, "rest1")
    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.add_item("item1", "Pizza", 10.0, -1, "rest1")
    with pytest.raises(ValueError, match="Quantity must be a positive integer."):
        cart.add_item("item1", "Pizza", 10.0, "2", "rest1")

def test_cart_add_item_multiple_restaurants():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    with pytest.raises(ValueError, match="Cannot add items from different restaurants to the same cart."):
        cart.add_item("item2", "Burger", 8.0, 1, "rest2")

def test_cart_add_item_accumulates():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    cart.add_item("item1", "Pizza", 10.0, 3, "rest1")
    assert cart.items["item1"]["quantity"] == 5
    assert cart.get_total_price() == 50.0

def test_cart_remove_item_entirely():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    cart.remove_item("item1", None)
    assert "item1" not in cart.items
    assert cart.get_restaurant_id() is None

def test_cart_remove_item_partial():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 5, "rest1")
    cart.remove_item("item1", 2)
    assert cart.items["item1"]["quantity"] == 3
    assert cart.get_total_price() == 30.0

def test_cart_remove_item_excessive_quantity():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    cart.remove_item("item1", 5)
    assert "item1" not in cart.items

def test_cart_remove_item_invalid_quantity():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    with pytest.raises(ValueError, match="Quantity to remove must be a positive integer."):
        cart.remove_item("item1", 0)
    with pytest.raises(ValueError, match="Quantity to remove must be a positive integer."):
        cart.remove_item("item1", -1)
    with pytest.raises(ValueError, match="Quantity to remove must be a positive integer."):
        cart.remove_item("item1", "1")

def test_cart_remove_nonexistent_item():
    cart = Cart()
    cart.remove_item("nonexistent", 1)
    assert cart.items == {}

def test_cart_clear():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    cart.clear()
    assert cart.items == {}
    assert cart.get_restaurant_id() is None
    assert cart.get_total_price() == 0.0

def test_cart_to_list():
    cart = Cart()
    cart.add_item("item1", "Pizza", 10.0, 2, "rest1")
    lst = cart.to_list()
    assert len(lst) == 1
    assert lst[0]["item_id"] == "item1"
    assert lst[0]["name"] == "Pizza"
    assert lst[0]["price"] == 10.0
    assert lst[0]["quantity"] == 2
    assert lst[0]["restaurant_id"] == "rest1"

def test_order_initialization():
    items = [{"item_id": "item1", "name": "Pizza", "price": 10.0, "quantity": 2, "restaurant_id": "rest1"}]
    order = Order("ord1", "rest1", items, 20.0)
    assert order.order_id == "ord1"
    assert order.restaurant_id == "rest1"
    assert order.items == items
    assert order.total_amount == 20.0
    assert order.status == "Pending"

def test_order_update_status_valid():
    items = []
    order = Order("ord1", "rest1", items, 0.0)
    order.update_status("Preparing")
    assert order.status == "Preparing"
    order.update_status("Delivering")
    assert order.status == "Delivering"
    order.update_status("Delivered")
    assert order.status == "Delivered"

def test_order_update_status_invalid():
    items = []
    order = Order("ord1", "rest1", items, 0.0)
    with pytest.raises(ValueError, match="Invalid status: Unknown."):
        order.update_status("Unknown")

def test_order_update_status_backward_progression():
    items = []
    order = Order("ord1", "rest1", items, 0.0)
    order.update_status("Preparing")
    with pytest.raises(ValueError, match="Cannot transition backwards from Preparing to Pending."):
        order.update_status("Pending")

def test_order_to_dict():
    items = [{"item_id": "item1", "name": "Pizza", "price": 10.0, "quantity": 2, "restaurant_id": "rest1"}]
    order = Order("ord1", "rest1", items, 20.0)
    d = order.to_dict()
    assert d == {
        "order_id": "ord1",
        "restaurant_id": "rest1",
        "items": items,
        "total_amount": 20.0,
        "status": "Pending"
    }
