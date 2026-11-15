import uuid
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class MenuItem:
    """Represents an item on a restaurant menu."""
    id: str
    name: str
    description: str
    price: float

@dataclass
class Restaurant:
    """Represents a restaurant with cuisine, rating, delivery time, and menu."""
    id: str
    name: str
    cuisine: str
    rating: float
    delivery_time: str
    menu: List[MenuItem]

@dataclass
class CartItem:
    """Represents an item added to the shopping cart."""
    menu_item: MenuItem
    quantity: int
    restaurant_id: str
    restaurant_name: str

@dataclass
class Order:
    """Represents a placed food order."""
    id: str
    restaurant_name: str
    items: List[CartItem]
    total_amount: float
    status: str  # "Pending", "Preparing", "Delivering", "Delivered"
    created_at: float  # timestamp

# Initial seed data for the application
INITIAL_RESTAURANTS: List[Restaurant] = [
    Restaurant(
        id="rest_1",
        name="Burger Joint",
        cuisine="Fast Food",
        rating=4.5,
        delivery_time="20-30 min",
        menu=[
            MenuItem(id="m_1_1", name="Classic Cheeseburger", description="Juicy beef patty with cheddar cheese, lettuce, and special sauce.", price=8.99),
            MenuItem(id="m_1_2", name="Bacon Deluxe Burger", description="Double beef patty with crispy bacon, BBQ sauce, and onion rings.", price=11.49),
            MenuItem(id="m_1_3", name="Crispy Fries", description="Golden, perfectly seasoned french fries.", price=3.99),
            MenuItem(id="m_1_4", name="Chocolate Milkshake", description="Rich and creamy chocolate shake topped with whipped cream.", price=4.99),
        ]
    ),
    Restaurant(
        id="rest_2",
        name="Little Italy Pizzeria",
        cuisine="Italian",
        rating=4.7,
        delivery_time="30-45 min",
        menu=[
            MenuItem(id="m_2_1", name="Margherita Pizza", description="Fresh mozzarella, tomatoes, basil, and extra virgin olive oil.", price=13.99),
            MenuItem(id="m_2_2", name="Pepperoni Feast", description="Loaded with spicy pepperoni and mozzarella cheese.", price=15.99),
            MenuItem(id="m_2_3", name="Garlic Breadsticks", description="Warm breadsticks brushed with garlic butter and herbs, served with marinara.", price=5.49),
            MenuItem(id="m_2_4", name="Tiramisu", description="Classic Italian dessert with ladyfingers, espresso, and mascarpone cream.", price=6.99),
        ]
    ),
    Restaurant(
        id="rest_3",
        name="Sakura Sushi Bar",
        cuisine="Japanese",
        rating=4.8,
        delivery_time="25-40 min",
        menu=[
            MenuItem(id="m_3_1", name="California Roll", description="Crab stick, avocado, cucumber, and tobiko wrapped in seaweed and rice.", price=9.99),
            MenuItem(id="m_3_2", name="Salmon Nigiri", description="Fresh slices of premium Atlantic salmon over seasoned sushi rice.", price=12.99),
            MenuItem(id="m_3_3", name="Spicy Tuna Roll", description="Fresh tuna mixed with spicy mayo and scallions.", price=11.99),
            MenuItem(id="m_3_4", name="Miso Soup", description="Traditional Japanese soup with tofu, wakame seaweed, and green onions.", price=3.49),
        ]
    ),
    Restaurant(
        id="rest_4",
        name="Taco Fiesta",
        cuisine="Mexican",
        rating=4.6,
        delivery_time="15-25 min",
        menu=[
            MenuItem(id="m_4_1", name=" Carne Asada Tacos (3 pcs)", description="Grilled steak tacos with fresh cilantro, onions, and lime.", price=10.99),
            MenuItem(id="m_4_2", name="Chicken Burrito", description="Flour tortilla filled with seasoned chicken, rice, beans, cheese, and salsa.", price=9.49),
            MenuItem(id="m_4_3", name="Guacamole & Chips", description="Freshly made guacamole served with crispy corn tortilla chips.", price=5.99),
            MenuItem(id="m_4_4", name="Churros", description="Crispy fried dough dusted with cinnamon sugar and served with caramel dip.", price=4.99),
        ]
    )
]
