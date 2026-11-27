"""Offline domain tests; no Gemini, Streamlit or MCP required."""
import pytest
from quickdelivery import service


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DB_PATH", tmp_path / "orders.db")


def test_domain_menu_search_and_simulated_eta():
    assert len(service.list_restaurants()) >= 4
    assert service.get_menu("r1")["items"]
    assert all(d["spicy"] and d["price"] <= 15 for d in service.search_dishes(15, True))
    eta = service.estimate_delivery("r1", "UCI Campus")
    assert eta["simulated"] is True and eta["estimated_minutes"] > 0
    with pytest.raises(ValueError):
        service.estimate_delivery("r1", "unknown")


def test_cart_single_restaurant_validation_and_checkout():
    s = "user-demo"
    with pytest.raises(ValueError):
        service.add_to_cart(s, "r1", "m1", 0)
    cart = service.add_to_cart(s, "r1", "m1", 2)
    assert cart["total"] == 29.0
    with pytest.raises(ValueError, match="one restaurant"):
        service.add_to_cart(s, "r2", "m3", 1)
    with pytest.raises(ValueError, match="confirmation"):
        service.place_order(s, confirmed=False)
    order = service.place_order(s, confirmed=True)
    assert order["status"] == "Pending"
    assert service.get_cart(s)["items"] == []
    assert service.list_orders(s)[0]["order_id"] == order["order_id"]


def test_sessions_are_isolated_and_empty_order_fails():
    service.add_to_cart("one", "r1", "m2", 1)
    assert service.get_cart("two")["items"] == []
    with pytest.raises(ValueError, match="empty"):
        service.place_order("two", confirmed=True)


def test_invalid_session_and_budget():
    with pytest.raises(ValueError):
        service.get_cart("../invalid")
    with pytest.raises(ValueError):
        service.search_dishes(float("nan"))
