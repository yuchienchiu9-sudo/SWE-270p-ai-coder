QuickDelivery is a simplified food delivery application built with Python and Streamlit.

Requirements:
1. Users can browse a predefined list of restaurants and view each restaurant's menu (item name and price).
2. Users can add food items to a shopping cart and remove them from it.
3. Cart quantities must be positive integers; invalid quantities are rejected with an error.
4. A cart can only contain items from one restaurant at a time.
5. The cart shows each item's subtotal and the cart total.
6. Users can place an order from a non-empty cart.
7. Payment is simulated (no real transactions): card number, expiry date and CVV are checked for a basic valid format, and the payment is approved or declined.
8. A successful payment creates an order with a unique order ID and empties the cart.
9. Each order has a status of Pending, Preparing, Delivering or Delivered. Order progress is simulated: a new order starts as Pending and automatically moves forward one step every 10 seconds until it is Delivered. The status never moves backward.
10. Users can view all their orders with the current status, a progress bar, and the time of the next update; the order view refreshes by itself without the user clicking anything.
11. The main sections (Restaurants, Cart, Orders) are shown as tabs at the top of the page, so users can switch between them with one click.
