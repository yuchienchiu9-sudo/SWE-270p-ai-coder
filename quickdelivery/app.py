"""User-facing MCP-powered QuickDelivery demo. Run: streamlit run quickdelivery/app.py"""
import uuid
from pathlib import Path
import sys

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from quickdelivery.mcp_client import call_tool
from quickdelivery.service import DESTINATIONS

st.set_page_config(page_title="QuickDelivery · MCP", page_icon="🍔", layout="wide")
if "qd_session" not in st.session_state:
    st.session_state.qd_session = uuid.uuid4().hex
if "qd_trace" not in st.session_state:
    st.session_state.qd_trace = []


def tool(name, **arguments):
    result, trace = call_tool(name, **arguments)
    st.session_state.qd_trace.extend(trace)
    return result


st.title("🍔 QuickDelivery — MCP-powered delivery")
st.caption("Demo restaurants, simulated routes/ETA and simulated checkout. No real payment or delivery.")
restaurants_tab, cart_tab, orders_tab, assistant_tab, trace_tab = st.tabs(["Restaurants", "Cart & checkout", "Orders", "AI recommendation", "MCP trace"])

with restaurants_tab:
    try:
        restaurants = tool("list_restaurants")
        for restaurant in restaurants:
            with st.expander(f"{restaurant['name']} · {restaurant['cuisine']} · ⭐ {restaurant['rating']}"):
                menu = tool("get_menu", restaurant_id=restaurant["id"])
                for item in menu["items"]:
                    c1, c2, c3 = st.columns([4, 1, 1])
                    c1.write(f"**{item['name']}** — ${item['price']:.2f} · {item['description']}")
                    qty = c2.number_input("Qty", min_value=1, max_value=20, key=f"qty_{item['id']}")
                    if c3.button("Add", key=f"add_{item['id']}"):
                        try:
                            tool("add_to_cart", session_id=st.session_state.qd_session, restaurant_id=restaurant["id"], item_id=item["id"], quantity=int(qty))
                            st.success("Added to cart")
                        except Exception as exc:
                            st.error(str(exc))
    except Exception as exc:
        st.error(f"MCP server error: {exc}")

with cart_tab:
    try:
        cart = tool("get_cart", session_id=st.session_state.qd_session)
        st.write(cart["items"] if cart["items"] else "Your cart is empty.")
        st.metric("Total", f"${cart['total']:.2f}")
        if st.button("Clear cart"):
            tool("clear_cart", session_id=st.session_state.qd_session)
            st.rerun()
        if cart["items"]:
            st.warning("Demo checkout only: no payment is collected.")
            if st.button("Confirm simulated order", type="primary"):
                order = tool("place_order", session_id=st.session_state.qd_session, confirmed=True)
                st.success(f"Order {order['order_id']} placed (simulation)")
    except Exception as exc:
        st.error(str(exc))

with orders_tab:
    try:
        st.write(tool("list_orders", session_id=st.session_state.qd_session))
        st.caption("Statuses progress every 10 seconds when the page refreshes.")
    except Exception as exc:
        st.error(str(exc))

with assistant_tab:
    st.write("Restaurant Agent finds matching menu items; Delivery Agent compares simulated ETA via MCP tools.")
    preference = st.text_input("What would you like?", value="Something spicy and affordable")
    budget = st.number_input("Maximum item price ($)", 1.0, 100.0, 20.0)
    destination = st.selectbox("Demo destination", list(DESTINATIONS))
    if st.button("Ask two AI agents", type="primary"):
        try:
            from quickdelivery.agents import recommend_food
            with st.spinner("Consulting restaurant and delivery agents..."):
                reply = recommend_food(preference, budget, destination)
            st.session_state.qd_trace.extend(reply["trace"])
            st.write(reply["recommendations"])
            st.write(reply["agent_notes"])
            st.caption(f"LLM usage: {reply['usage']}")
            st.info("Recommendations do not place orders. Use Restaurants and confirm checkout yourself.")
        except Exception as exc:
            st.error(f"Agent request failed: {exc}")

with trace_tab:
    st.caption("Calls shown here are from the current Streamlit browser session.")
    st.json(st.session_state.qd_trace)
