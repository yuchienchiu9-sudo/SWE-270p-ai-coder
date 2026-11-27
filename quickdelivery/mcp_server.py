"""QuickDelivery domain MCP server (distinct from the AI Coder MCP server)."""
from mcp.server.fastmcp import FastMCP
from quickdelivery import service

mcp = FastMCP("QuickDelivery")

@mcp.tool()
def list_restaurants() -> list[dict]:
    """List available demo restaurants, including cuisines and ratings."""
    return service.list_restaurants()

@mcp.tool()
def get_menu(restaurant_id: str) -> dict:
    """Return dishes, descriptions and prices at a given restaurant."""
    return service.get_menu(restaurant_id)

@mcp.tool()
def search_dishes(max_price: float = 25.0, spicy_only: bool = False) -> list[dict]:
    """Search dishes by budget and optional spicy preference."""
    return service.search_dishes(max_price, spicy_only)

@mcp.tool()
def estimate_delivery(restaurant_id: str, destination: str) -> dict:
    """Estimate SIMULATED time and straight-line distance to a demo destination."""
    return service.estimate_delivery(restaurant_id, destination)

@mcp.tool()
def add_to_cart(session_id: str, restaurant_id: str, item_id: str, quantity: int = 1) -> dict:
    """Add a positive quantity, enforcing single-restaurant carts."""
    return service.add_to_cart(session_id, restaurant_id, item_id, quantity)

@mcp.tool()
def get_cart(session_id: str) -> dict:
    """Return the current shopping cart and calculated total."""
    return service.get_cart(session_id)

@mcp.tool()
def clear_cart(session_id: str) -> dict:
    """Clear the shopping cart for this session."""
    return service.clear_cart(session_id)

@mcp.tool()
def place_order(session_id: str, confirmed: bool = False) -> dict:
    """Create a simulated order, only after explicit human confirmation."""
    return service.place_order(session_id, confirmed)

@mcp.tool()
def list_orders(session_id: str) -> list[dict]:
    """List a session's simulated orders and elapsed-time status."""
    return service.list_orders(session_id)

if __name__ == "__main__":
    mcp.run(transport="stdio")
