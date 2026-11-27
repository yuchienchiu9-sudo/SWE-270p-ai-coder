"""Deterministic QuickDelivery business logic shared by MCP tools.

This is intentionally a DEMO: restaurants, coordinates, prices, ETA, and payment
are simulated. SQLite persists cart/orders across short-lived MCP subprocesses.
"""
from __future__ import annotations

import math
import os
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(os.environ.get("QUICKDELIVERY_DB", str(Path(__file__).resolve().parent / "quickdelivery.db")))
DESTINATIONS = {"UCI Campus": (33.6405, -117.8443), "Irvine Spectrum": (33.6507, -117.7434)}
RESTAURANTS = [
    {"id": "r1", "name": "Spice Bowl", "cuisine": "Thai", "rating": 4.6, "lat": 33.6465, "lon": -117.8390,
     "menu": [{"id": "m1", "name": "Spicy Basil Chicken", "price": 14.50, "spicy": True, "description": "Basil, chili, rice"}, {"id": "m2", "name": "Pad Thai", "price": 13.00, "spicy": False, "description": "Rice noodles, peanuts"}]},
    {"id": "r2", "name": "Noodle Garden", "cuisine": "Chinese", "rating": 4.5, "lat": 33.6590, "lon": -117.8290,
     "menu": [{"id": "m3", "name": "Dan Dan Noodles", "price": 15.25, "spicy": True, "description": "Sesame chili noodles"}, {"id": "m4", "name": "Pork Dumplings", "price": 11.00, "spicy": False, "description": "Steamed dumplings"}]},
    {"id": "r3", "name": "Green Plate", "cuisine": "Mediterranean", "rating": 4.7, "lat": 33.6315, "lon": -117.8245,
     "menu": [{"id": "m5", "name": "Falafel Bowl", "price": 12.75, "spicy": False, "description": "Falafel and hummus"}, {"id": "m6", "name": "Harissa Wrap", "price": 13.50, "spicy": True, "description": "Spicy harissa sauce"}]},
    {"id": "r4", "name": "Pizza Corner", "cuisine": "Italian", "rating": 4.3, "lat": 33.6700, "lon": -117.8580,
     "menu": [{"id": "m7", "name": "Margherita Pizza", "price": 16.00, "spicy": False, "description": "Basil and mozzarella"}, {"id": "m8", "name": "Hot Honey Pizza", "price": 18.00, "spicy": True, "description": "Chili and hot honey"}]},
]


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("CREATE TABLE IF NOT EXISTS carts (session_id TEXT NOT NULL, restaurant_id TEXT NOT NULL, item_id TEXT NOT NULL, quantity INTEGER NOT NULL, PRIMARY KEY(session_id, item_id))")
    conn.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, restaurant_id TEXT NOT NULL, total_cents INTEGER NOT NULL, created_at REAL NOT NULL, items TEXT NOT NULL)")
    return conn


def list_restaurants() -> list[dict]:
    """Return the deterministic local restaurant catalog without internal coordinates."""
    return [{"id": r["id"], "name": r["name"], "cuisine": r["cuisine"], "rating": r["rating"]} for r in RESTAURANTS]


def _restaurant(restaurant_id: str) -> dict:
    return next((r for r in RESTAURANTS if r["id"] == restaurant_id), None) or _error("Unknown restaurant")


def _error(message: str):
    raise ValueError(message)


def get_menu(restaurant_id: str) -> dict:
    r = _restaurant(restaurant_id)
    return {"restaurant_id": r["id"], "name": r["name"], "items": [dict(item) for item in r["menu"]]}


def search_dishes(max_price: float = 25, spicy_only: bool = False) -> list[dict]:
    if isinstance(max_price, bool) or not isinstance(max_price, (float, int)) or not math.isfinite(max_price) or max_price <= 0:
        raise ValueError("max_price must be positive")
    return [{"restaurant_id": r["id"], "restaurant": r["name"], **item} for r in RESTAURANTS for item in r["menu"] if item["price"] <= max_price and (not spicy_only or item["spicy"])]


def estimate_delivery(restaurant_id: str, destination: str) -> dict:
    """Haversine distance with an explicit simulated ETA; NOT real maps/routing."""
    r = _restaurant(restaurant_id)
    if destination not in DESTINATIONS:
        raise ValueError("Unknown destination")
    lat2, lon2 = DESTINATIONS[destination]
    lat1, lon1 = r["lat"], r["lon"]
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    km = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return {"restaurant_id": restaurant_id, "destination": destination, "straight_line_km": round(km, 2), "estimated_minutes": max(12, round(12 + km * 4)), "simulated": True}


def _item(restaurant_id: str, item_id: str) -> dict:
    return next((i for i in _restaurant(restaurant_id)["menu"] if i["id"] == item_id), None) or _error("Unknown item for restaurant")


def _session(session_id: str):
    if not isinstance(session_id, str) or not 1 <= len(session_id) <= 80 or not all(c.isalnum() or c in "-_" for c in session_id):
        raise ValueError("Invalid session ID")


def add_to_cart(session_id: str, restaurant_id: str, item_id: str, quantity: int) -> dict:
    _session(session_id)
    if type(quantity) is not int or quantity < 1 or quantity > 99:
        raise ValueError("quantity must be an integer between 1 and 99")
    _item(restaurant_id, item_id)
    with _connect() as conn:
        existing = conn.execute("SELECT DISTINCT restaurant_id FROM carts WHERE session_id=?", (session_id,)).fetchone()
        if existing and existing["restaurant_id"] != restaurant_id:
            raise ValueError("A cart can contain items from only one restaurant; clear it first")
        conn.execute("INSERT INTO carts VALUES (?,?,?,?) ON CONFLICT(session_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity", (session_id, restaurant_id, item_id, quantity))
    return get_cart(session_id)


def get_cart(session_id: str) -> dict:
    _session(session_id)
    with _connect() as conn:
        rows = conn.execute("SELECT restaurant_id,item_id,quantity FROM carts WHERE session_id=? ORDER BY item_id", (session_id,)).fetchall()
    items = []
    for row in rows:
        item = _item(row["restaurant_id"], row["item_id"])
        items.append({"item_id": item["id"], "name": item["name"], "quantity": row["quantity"], "price": item["price"], "subtotal": round(item["price"]*row["quantity"], 2)})
    return {"restaurant_id": rows[0]["restaurant_id"] if rows else None, "items": items, "total": round(sum(i["subtotal"] for i in items), 2)}


def clear_cart(session_id: str) -> dict:
    _session(session_id)
    with _connect() as conn:
        conn.execute("DELETE FROM carts WHERE session_id=?", (session_id,))
    return get_cart(session_id)


def place_order(session_id: str, confirmed: bool = False) -> dict:
    """Place a SIMULATED order only after explicit user confirmation, no payment."""
    _session(session_id)
    if confirmed is not True:
        raise ValueError("Explicit user confirmation is required")
    import json
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT restaurant_id,item_id,quantity FROM carts WHERE session_id=?", (session_id,)).fetchall()
        if not rows:
            raise ValueError("Cart is empty")
        items = [{"name": _item(r["restaurant_id"],r["item_id"])["name"], "quantity": r["quantity"], "price": _item(r["restaurant_id"],r["item_id"])["price"]} for r in rows]
        cents = sum(round(item["price"]*100)*item["quantity"] for item in items)
        order_id = "ORD-" + uuid.uuid4().hex[:10].upper()
        conn.execute("INSERT INTO orders VALUES (?,?,?,?,?,?)", (order_id,session_id,rows[0]["restaurant_id"],cents,time.time(),json.dumps(items)))
        conn.execute("DELETE FROM carts WHERE session_id=?", (session_id,))
    return {"order_id": order_id, "total": cents/100, "status": "Pending", "simulated_payment": True}


def list_orders(session_id: str) -> list[dict]:
    _session(session_id)
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM orders WHERE session_id=? ORDER BY created_at DESC", (session_id,)).fetchall()
    statuses = ["Pending", "Preparing", "Delivering", "Delivered"]
    return [{"order_id": row["id"], "restaurant_id": row["restaurant_id"], "total":row["total_cents"]/100, "status": statuses[min(3, int(max(0,time.time()-row["created_at"])//10))]} for row in rows]
