import time
import streamlit as st
from models import INITIAL_RESTAURANTS
from cart import CartManager
from order_manager import OrderManager


def get_cart_manager() -> CartManager:
    """Retrieves or initializes the CartManager in session state."""
    if "cart_manager" not in st.session_state:
        st.session_state.cart_manager = CartManager()
    return st.session_state.cart_manager


def get_order_manager() -> OrderManager:
    """Retrieves or initializes the OrderManager in session state."""
    if "order_manager" not in st.session_state:
        st.session_state.order_manager = OrderManager()
    return st.session_state.order_manager


def main():
    """Main entry point for the QuickDelivery Streamlit application."""
    st.set_page_config(
        page_title="QuickDelivery",
        page_icon="🍔",
        layout="wide"
    )

    # Initialize managers
    cart_mgr = get_cart_manager()
    order_mgr = get_order_manager()

    # Header
    st.title("🍔 QuickDelivery")
    st.caption("Delicious meals delivered fast to your doorstep.")

    # Main navigation tabs
    tab_restaurants, tab_cart, tab_orders = st.tabs([
        ":material/restaurant: Restaurants",
        ":material/shopping_cart: Cart",
        ":material/receipt_long: Orders"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: RESTAURANTS
    # -------------------------------------------------------------------------
    with tab_restaurants:
        st.subheader("Explore Restaurants & Menus")
        st.caption("Select a restaurant to browse their delicious menu items and add them to your cart.")

        # Display restaurants in a grid of 2 columns
        cols = st.columns(2)
        for idx, restaurant in enumerate(INITIAL_RESTAURANTS):
            col_target = cols[idx % 2]
            with col_target:
                with st.container(border=True):
                    st.markdown(f"### {restaurant.name}")
                    st.caption(f"Cuisine: **{restaurant.cuisine}** | ⭐ {restaurant.rating} | ⏱️ {restaurant.delivery_time}")
                    st.divider()

                    st.markdown("**Menu:**")
                    for item in restaurant.menu:
                        item_col1, item_col2 = st.columns([3, 1])
                        with item_col1:
                            st.markdown(f"**{item.name}** — \\${item.price:.2f}")
                            st.caption(item.description)
                        with item_col2:
                            qty = st.number_input(
                                "Qty",
                                min_value=1,
                                max_value=20,
                                value=1,
                                step=1,
                                key=f"qty_{restaurant.id}_{item.id}",
                                label_visibility="collapsed"
                            )
                            if st.button(
                                "Add",
                                icon=":material/add_shopping_cart:",
                                key=f"add_{restaurant.id}_{item.id}"
                            ):
                                try:
                                    cart_mgr.add_item(
                                        restaurant_id=restaurant.id,
                                        restaurant_name=restaurant.name,
                                        menu_item=item,
                                        quantity=int(qty)
                                    )
                                    st.toast(f"Added {qty}x {item.name} to cart!", icon="🛒")
                                    st.rerun()
                                except ValueError as e:
                                    st.error(str(e))

        st.divider()

    # -------------------------------------------------------------------------
    # TAB 2: CART & CHECKOUT
    # -------------------------------------------------------------------------
    with tab_cart:
        st.subheader("Your Shopping Cart")

        if not cart_mgr.items:
            st.info("Your cart is currently empty. Browse restaurants and add some tasty items to get started!")
        else:
            restaurant_name = cart_mgr.items[0].restaurant_name
            st.caption(f"Ordering from: **{restaurant_name}** (A cart can only contain items from one restaurant)")

            # Cart Items Table / List
            for item in list(cart_mgr.items):
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                    with c1:
                        st.markdown(f"**{item.menu_item.name}**")
                        st.caption(f"Price: \\${item.menu_item.price:.2f} each")
                    with c2:
                        new_qty = st.number_input(
                            "Quantity",
                            min_value=1,
                            max_value=99,
                            value=item.quantity,
                            step=1,
                            key=f"cart_qty_{item.menu_item.id}"
                        )
                        if new_qty != item.quantity:
                            try:
                                cart_mgr.update_quantity(item.menu_item.id, int(new_qty))
                                st.rerun()
                            except ValueError as e:
                                st.error(str(e))
                    with c3:
                        subtotal = cart_mgr.get_subtotal(item)
                        st.markdown(f"**Subtotal:** \\${subtotal:.2f}")
                    with c4:
                        if st.button("Remove", icon=":material/delete:", key=f"remove_{item.menu_item.id}"):
                            cart_mgr.remove_item(item.menu_item.id)
                            st.toast("Item removed from cart.", icon="🗑️")
                            st.rerun()

            st.divider()

            # Cart Totals and Clear Button
            total_cost = cart_mgr.get_total()
            col_tot1, col_tot2 = st.columns([2, 1])
            with col_tot1:
                st.metric("Total Amount", f"${total_cost:.2f}")
            with col_tot2:
                if st.button("Clear Cart", icon=":material/remove_shopping_cart:"):
                    cart_mgr.clear()
                    st.toast("Cart cleared.", icon="🧹")
                    st.rerun()

            st.divider()

            # Checkout / Payment Section
            st.subheader("Simulated Checkout")
            st.caption("Please enter your credit card information to place your order. No real charges will occur.")

            with st.form("checkout_form"):
                card_number = st.text_input("Card Number", placeholder="1234 5678 9012 3456")
                col_exp, col_cvv = st.columns(2)
                with col_exp:
                    expiry_date = st.text_input("Expiry Date", placeholder="MM/YY")
                with col_cvv:
                    cvv = st.text_input("CVV", placeholder="123", type="password")

                submitted = st.form_submit_button("Place Order", type="primary", icon=":material/check_circle:")
                if submitted:
                    success, msg, order = order_mgr.place_order(
                        cart_manager=cart_mgr,
                        card_number=card_number,
                        expiry_date=expiry_date,
                        cvv=cvv
                    )
                    if success:
                        st.success(msg)
                        st.toast("Order placed successfully!", icon="🎉")
                        st.rerun()
                    else:
                        st.error(msg)

    # -------------------------------------------------------------------------
    # TAB 3: ORDERS (AUTO-REFRESHING)
    # -------------------------------------------------------------------------
    with tab_orders:
        st.subheader("Order Tracking")
        st.caption("Active orders progress automatically from Pending -> Preparing -> Delivering -> Delivered.")

        @st.fragment(run_every="2s")
        def render_orders_fragment():
            # Update order statuses based on elapsed time
            order_mgr.update_order_statuses()

            orders = order_mgr.get_all_orders()
            if not orders:
                st.info("You haven't placed any orders yet. Place an order from your cart to track it here.")
                return

            # Display orders in reverse chronological order (newest first)
            for order in reversed(orders):
                with st.container(border=True):
                    header_col1, header_col2 = st.columns([3, 1])
                    with header_col1:
                        st.markdown(f"### Order ID: {order.id}")
                        st.caption(f"Restaurant: **{order.restaurant_name}** | Total: \\${order.total_amount:.2f}")
                    with header_col2:
                        # Status badge color mapping
                        status_colors = {
                            "Pending": "orange",
                            "Preparing": "blue",
                            "Delivering": "violet",
                            "Delivered": "green"
                        }
                        color = status_colors.get(order.status, "gray")
                        st.badge(order.status, color=color)

                    # Progress bar calculation
                    progress_mapping = {
                        "Pending": 0.25,
                        "Preparing": 0.50,
                        "Delivering": 0.75,
                        "Delivered": 1.00
                    }
                    prog_val = progress_mapping.get(order.status, 0.0)
                    st.progress(prog_val, text=f"Current Status: {order.status}")

                    with st.expander("View Order Items"):
                        for item in order.items:
                            st.write(f"- {item.quantity}x {item.menu_item.name} (\\${item.menu_item.price:.2f} each)")

                    st.caption(f"Next update refreshing automatically... (Time: {time.strftime('%H:%M:%S', time.localtime())})")

        render_orders_fragment()


if __name__ == "__main__":
    main()
