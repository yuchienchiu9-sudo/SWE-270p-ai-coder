# QuickDelivery — MCP-powered food delivery demo (phase 1)

This is a **separate application** from the existing AI Coder. It answers the
course demo feedback by offering **domain-specific MCP tools** rather than only
software-generation tools. The previous AI Coder remains unchanged.

## Run

From the repository root, install the existing `requirements.txt`, set up
`.env` with `GEMINI_API_KEY` to use the optional AI recommendation, then run:

```bash
python -m streamlit run quickdelivery/app.py
```

The Restaurants, Cart and Orders tabs work **without Gemini**. The AI
recommendation tab uses Gemini and consumes API tokens.

## Architecture

```text
Streamlit QuickDelivery UI
       |
       | MCP Client (stdio)
       v
QuickDelivery MCP Server
       +-- list_restaurants / get_menu / search_dishes
       +-- estimate_delivery (simulated straight-line distance and ETA)
       +-- add_to_cart / get_cart / clear_cart
       +-- place_order (requires human confirmation) / list_orders
       |
       v
SQLite cart/order state (separate browser sessions)

AI recommendation (optional):
  Restaurant Agent -- MCP search_dishes + Gemini selection
  Delivery Agent   -- MCP estimate_delivery + Gemini ranking
  Both return recommendations; neither can place an order.
```

**Important:** A domain MCP tool is not an AI agent. The two recommendation
specialists each make their own Gemini call based on results from MCP tools.
The UI exposes the MCP trace so these steps can be demonstrated.

**Scope:** Menu and restaurant data are predefined. Routes use straight-line
haversine distances and a deliberately simulated ETA; they are **not** Google
Maps, real driving directions, or live estimates. No actual payment processing
or delivery is performed. The app intentionally keeps checkout user-confirmed.

This first implementation is not a complete Uber Eats clone. Potential next
steps include a true map/routing provider, customer-selected arbitrary addresses,
real-time order updates, stronger session auth and an agent task router.

Run offline business-logic tests:

```bash
python -m pytest tests/test_quickdelivery_domain.py -v
```

`quickdelivery/quickdelivery.db` is local runtime data and must not be committed.
