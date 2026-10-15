from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint("age >= 13 AND age <= 100", name="valid_customer_age"),)

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="customer", nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(30), default="Prefer not to say", nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    registration_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    total_purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spending: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    average_order_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    website_visits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price > 0", name="positive_product_price"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="valid_product_rating"),
        CheckConstraint("stock >= 0", name="nonnegative_product_stock"),
    )

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=4, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False)
    order_status: Mapped[str] = mapped_column(String(30), default="completed", nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)


class OrderItem(Base):
    __tablename__ = "order_items"
    order_item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)


class CartItem(Base):
    __tablename__ = "cart"
    __table_args__ = (UniqueConstraint("customer_id", "product_id", name="unique_cart_product"),)
    cart_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class WishlistItem(Base):
    __tablename__ = "wishlist"
    __table_args__ = (UniqueConstraint("customer_id", "product_id", name="unique_wishlist_product"),)
    wishlist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), index=True)


class CustomerActivity(Base):
    __tablename__ = "customer_activity"
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id", ondelete="CASCADE"), primary_key=True)
    product_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cart_additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wishlist_additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    previous_purchases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_spent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    purchased: Mapped[int] = mapped_column(Integer, default=0, nullable=False)