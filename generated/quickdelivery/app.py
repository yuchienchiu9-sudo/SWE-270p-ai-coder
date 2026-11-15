"""
app.py

Streamlit user interface for QuickDelivery, integrating restaurant browsing,
cart management, mock payments, and order status tracking.
"""

import streamlit as st
import uuid
from data import RESTAURANTS
from models import Cart, Order
from payment import process_payment

st.set_page_config(
    page_title="QuickDelivery",
    page_icon="🍔",
    layout="wide"
)

# Initialize session state for cart, orders, and active navigation
if "cart" not in st.session_state:
    st.session_state.cart = Cart()

if "orders" not in st.session_state:
    st.session_state.orders = {}

st.title("🍔 QuickDelivery")
st.write("Browse restaurants, add items to your cart, and track your food delivery in real-time!")

# Sidebar navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Browse Restaurants", "Shopping Cart", "Order Tracking"])

if page == "Browse Restaurants":
    st.header("Restaurants & Menus")
    
    # Optional restaurant filter or search
    search_query = st.text_input("Search restaurants or cuisines", "")
    
    filtered_restaurants = [
        r for r in RESTAURANTS 
        if search_query.lower() in r["name"].lower() or search_query.lower() in r["cuisine"].lower()
    ]

    for restaurant in filtered_restaurants:
        with st.expander(f"{restaurant['name']} ({restaurant['cuisine']})"):
            st.write(f"**Cuisine:** {restaurant['cuisine']}")
            st.markdown("---grid---")
            for item in restaurant["menu"]:
                col1, col2, col3 = st.columns([3, 1, 2])
                with col1:
                    st.write(f"**{item['name']}**")
                    st.write(f"${item['price']:.2f}")
                with col2:
                    qty = st.number_input(
                        "Qty", 
                        min_value=1, 
                        max_value=10, 
                        value=1, 
                        step=1, 
                        key=f"qty_{restaurant['id']}_{item['id']}"
                    )
                with col3:
                    if st.button("Add to Cart", key=f"add_{restaurant['id']}_{item['id']}"):
                        try:
                            st.session_state.cart.add_item(
                                item_id=str(item["id"]),
                                name=item["name"],
                                price=item["price"],
                                quantity=qty,
                                restaurant_id=str(restaurant["id"])
                            )
                            st.success(f"Added {qty}x {item['name']} to cart!")
                        except ValueError as e:
                            st.error(str(e))

elif page == "Shopping Cart":
    st.header("Your Shopping Cart")
    
    cart_items = st.session_state.cart.to_list()
    
    if not cart_items:
        st.info("Your cart is empty. Start browsing restaurants to add items!")
    else:
        current_restaurant_id = st.session_state.cart.get_restaurant_id()
        restaurant_name = "Unknown"
        for r in RESTAURANTS:
            if str(r["id"]) == current_restaurant_id:
                restaurant_name = r["name"]
                break

        st.subheader(f"Ordering from: {restaurant_name}")

        for item in cart_items:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.write(f"**{item['name']}**")
                st.write(f"Price: ${item['price']:.2f}")
            with col2:
                st.write(f"Qty: {item['quantity']}")
            with col3:
                st.write(f"Subtotal: ${item['price'] * item['quantity']:.2f}")
            with col4:
                if st.button("Remove", key=f"remove_{item['item_id']}"):
                    st.session_state.cart.remove_item(item["item_id"], quantity=None)
                    st.rerun()

        st.markdown("---income---")
        total_price = st.session_state.cart.get_total_price()
        st.markdown(f"### Total Amount: ${total_price:.2f}")

        if st.button("Clear Cart"):
            st.session_state.cart.clear()
            st.rerun()

        st.subheader("Checkout & Payment")
        with st.form("payment_form"):
            card_number = st.text_input("Credit Card Number", placeholder="1234 5678 9012 3456")
            expiry = st.text_input("Expiration Date (MM/YY)", placeholder="12/26")
            cvv = st.text_input("CVV", type="password", placeholder="123")
            
            submitted = st.form_submit_button("Place Order")
            
            if submitted:
                # Process payment
                payment_success = process_payment(
                    card_number=card_number,
                    expiry=expiry,
                    cvv=cvv,
                    amount=total_price
                )
                
                if payment_success:
                    order_id = str(uuid.uuid4())[:8]
                    new_order = Order(
                        order_id=order_id,
                        restaurant_id=current_restaurant_id,
                        items=cart_items,
                        total_amount=total_price
                    )
                    st.session_state.orders[order_id] = new_order
                    st.session_state.cart.clear()
                    st.success(f"Payment successful! Order #{order_id} has been placed.")
                    st.info("Go to 'Order Tracking' to view your order status.")
                else:
                    st.error("Payment failed. Please check your card details and try again.")

elif page == "Order Tracking":
    st.header("Order Tracking")
    
    if not st.session_state.orders:
        st.info("No active orders found. Place an order from the Shopping Cart page.")
    else:
        order_ids = list(st.session_state.orders.keys())
        selected_order_id = st.selectbox("Select Order ID", order_ids)
        
        order = st.session_state.orders[selected_order_id]
        
        st.subheader(f"Order #{order.order_id}")
        st.write(f"**Status:** {order.status}")
        st.write(f"**Total Amount:** ${order.total_amount:.2f}")
        
        # Status progression visual or selector for simulation
        st.markdown("### Update Status (Simulation Control)")
        current_status_idx = Order.VALID_STATUSES.index(order.status)
        
        col1, col2 = st.columns(2)
        with col1:
            next_status_options = Order.VALID_STATUSES[current_status_idx:]
            chosen_status = st.selectbox("Change status to", next_status_options, key=f"status_select_{order.order_id}")
            
            if st.button("Update Status", key=f"update_btn_{order.order_id}"):
                try:
                    order.update_status(chosen_status)
                    st.success(f"Order status updated to {chosen_status}!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        st.markdown("---details---")
        st.write("**Ordered Items:**")
        for item in order.items:
            st.write(f"- {item['quantity']}x {item['name']} (${item['price']:.2f} each)")
