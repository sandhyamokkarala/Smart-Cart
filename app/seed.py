from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sqlalchemy import select

from app.database import DATA_DIR, SessionLocal, Base, engine
from app.ml import train_models
from app.models import Customer, CustomerActivity, Order, OrderItem, Product
from app.security import hash_password


random.seed(47)
PRODUCTS = [
    ("Electronics", ["Wireless Headphones", "Smart Watch", "Bluetooth Speaker", "Tablet", "Mechanical Keyboard", "Webcam", "Power Bank", "USB-C Hub", "E-reader", "Wireless Mouse"]),
    ("Home", ["Ceramic Table Lamp", "Linen Throw", "Oak Side Table", "Cotton Duvet Set", "Stoneware Vase", "Woven Storage Basket", "Glass Water Bottle", "Desk Organizer", "Cotton Bath Towel", "Scented Candle"]),
    ("Fashion", ["Everyday Sneakers", "Canvas Tote", "Leather Wallet", "Linen Shirt", "Classic Sunglasses", "Wool Beanie", "Crossbody Bag", "Denim Jacket", "Running Cap", "Gold Hoop Earrings"]),
    ("Beauty", ["Hydrating Serum", "Daily Face Cream", "Mineral Sunscreen", "Cleansing Balm", "Rosewater Mist", "Lip Tint Set", "Hair Repair Mask", "Body Oil", "Vitamin C Drops", "Soft Bristle Brush"]),
    ("Sports", ["Yoga Mat", "Insulated Bottle", "Resistance Bands", "Running Belt", "Foam Roller", "Gym Duffle", "Cycling Gloves", "Jump Rope", "Trail Socks", "Training Tee"]),
]
CITIES = ["New York", "Austin", "Seattle", "Chicago", "Portland", "Miami", "Denver", "Boston", "Atlanta", "San Diego"]
CATEGORIES = list(dict.fromkeys(category for category, _ in PRODUCTS))
IMAGE_URLS = {
    "Electronics": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=85",
    "Home": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=900&q=85",
    "Fashion": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=900&q=85",
    "Beauty": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&w=900&q=85",
    "Sports": "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?auto=format&fit=crop&w=900&q=85",
}


def make_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    customers = pd.DataFrame([{
        "customer_id": index, "name": f"Customer {index:03d}", "email": f"customer{index}@example.com",
        "age": random.randint(18, 72), "gender": random.choice(["Female", "Male", "Non-binary", "Prefer not to say"]),
        "city": random.choice(CITIES), "registration_date": (date.today() - timedelta(days=random.randint(90, 1800))).isoformat(),
        "total_purchases": 0, "total_spending": 0.0, "average_order_value": 0.0, "website_visits": random.randint(2, 80),
    } for index in range(1, 101)])
    product_rows = []
    product_id = 1
    for category, names in PRODUCTS:
        for name in names:
            price = round(random.uniform(12, 480), 2)
            product_rows.append({
                "product_id": product_id, "product_name": name, "category": category, "price": price,
                "rating": round(random.uniform(3.2, 5.0), 1), "stock": random.randint(0, 90),
                "discount": random.choice([0, 0, 0, 5, 10, 15, 20]), "image_url": IMAGE_URLS[category],
            })
            product_id += 1
    products = pd.DataFrame(product_rows)
    order_rows = []
    start = date.today() - timedelta(days=365)
    payment_methods = ["Card", "PayPal", "Apple Pay", "Bank Transfer"]
    for order_id in range(1, 601):
        customer = customers.sample(1, random_state=order_id).iloc[0]
        product = products.sample(1, random_state=1000 + order_id).iloc[0]
        quantity = random.choices([1, 2, 3], weights=[0.76, 0.20, 0.04])[0]
        order_rows.append({
            "order_id": order_id, "customer_id": int(customer.customer_id), "product_id": int(product.product_id),
            "quantity": quantity, "order_date": (start + timedelta(days=random.randint(0, 365))).isoformat(),
            "price": float(product.price), "payment_method": random.choices(payment_methods, weights=[0.47, 0.25, 0.20, 0.08])[0],
            "order_status": random.choices(["completed", "shipped", "cancelled"], weights=[0.80, 0.17, 0.03])[0],
        })
    orders = pd.DataFrame(order_rows)
    completed = orders[orders.order_status != "cancelled"]
    purchase_counts = completed.groupby("customer_id").size()
    customer_spend = completed.assign(amount=completed.quantity * completed.price).groupby("customer_id").amount.sum()
    customers["total_purchases"] = customers.customer_id.map(purchase_counts).fillna(0).astype(int)
    customers["total_spending"] = customers.customer_id.map(customer_spend).fillna(0).round(2)
    customers["average_order_value"] = (customers.total_spending / customers.total_purchases.replace(0, 1)).round(2)

    bought_pairs = completed.groupby(["customer_id", "product_id"]).quantity.sum().to_dict()
    product_map = products.set_index("product_id")
    customer_map = customers.set_index("customer_id")
    activity_rows = []
    for customer_id in customers.customer_id:
        customer = customer_map.loc[customer_id]
        for product_id in products.product_id:
            previous = int(bought_pairs.get((customer_id, product_id), 0))
            views = random.randint(0, 8) + previous * 2
            cart_adds = random.randint(0, 3) + (1 if previous else 0)
            wishlist_adds = random.randint(0, 2)
            time_spent = round(random.uniform(5, 240), 1)
            score = -3.8 + views * 0.22 + cart_adds * 0.72 + wishlist_adds * 0.38 + previous * 1.8 + time_spent / 160 + customer.total_purchases * 0.018
            probability = 1 / (1 + pow(2.71828, -score))
            purchased = 1 if previous or random.random() < probability else 0
            activity_rows.append({
                "customer_id": int(customer_id), "product_id": int(product_id), "product_views": views,
                "cart_additions": cart_adds, "wishlist_additions": wishlist_adds, "previous_purchases": previous,
                "time_spent": time_spent, "purchased": purchased,
            })
    activity = pd.DataFrame(activity_rows)
    return customers, products, orders, activity


def clean_data(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame, activity: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    original = {"customers": customers.copy(), "products": products.copy(), "orders": orders.copy(), "customer_activity": activity.copy()}
    quality = {
        "missing_values": {name: frame.isna().sum().to_dict() for name, frame in original.items()},
        "duplicate_rows": {name: int(frame.duplicated().sum()) for name, frame in original.items()},
        "duplicate_customer_ids": int(customers.customer_id.duplicated().sum()),
        "duplicate_product_ids": int(products.product_id.duplicated().sum()),
        "invalid_ages": int((~pd.to_numeric(customers.age, errors="coerce").between(13, 100)).sum()),
        "invalid_prices": int((~pd.to_numeric(products.price, errors="coerce").gt(0)).sum()),
        "missing_ratings": int(products.rating.isna().sum()),
        "invalid_customer_order_ids": int((~orders.customer_id.isin(customers.customer_id)).sum()),
        "invalid_product_order_ids": int((~orders.product_id.isin(products.product_id)).sum()),
    }
    pd.Series(quality, dtype=object).to_json(DATA_DIR / "data_quality.json", indent=2)
    frames = [customers, products, orders, activity]
    for frame in frames:
        frame.drop_duplicates(inplace=True)
    customers["age"] = pd.to_numeric(customers.age, errors="coerce")
    customers = customers[customers.age.between(13, 100)].copy()
    products["price"] = pd.to_numeric(products.price, errors="coerce")
    products = products[products.price.gt(0)].copy()
    products["rating"] = pd.to_numeric(products.rating, errors="coerce").fillna(products.rating.median()).clip(0, 5)
    orders["customer_id"] = pd.to_numeric(orders.customer_id, errors="coerce")
    orders["product_id"] = pd.to_numeric(orders.product_id, errors="coerce")
    orders["order_date"] = pd.to_datetime(orders.order_date, errors="coerce")
    orders = orders.dropna(subset=["order_date"])
    orders = orders[orders.customer_id.isin(customers.customer_id) & orders.product_id.isin(products.product_id)]
    activity = activity[activity.customer_id.isin(customers.customer_id) & activity.product_id.isin(products.product_id)]
    return customers, products, orders, activity


def write_eda(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame) -> None:
    report_dir = DATA_DIR.parent / "reports"
    report_dir.mkdir(exist_ok=True)
    sales = orders[orders.order_status != "cancelled"].copy()
    sales["revenue"] = sales.quantity * sales.price
    merged = sales.merge(products[["product_id", "category", "product_name"]], on="product_id")
    revenue_by_month = merged.set_index("order_date").resample("MS").revenue.sum()
    summary = {
        "top_category": merged.groupby("category").revenue.sum().idxmax(),
        "top_products": merged.groupby("product_name").revenue.sum().nlargest(5).round(2).to_dict(),
        "top_customers": sales.assign(revenue=sales.quantity * sales.price).groupby("customer_id").revenue.sum().nlargest(5).round(2).to_dict(),
        "average_order_value": round(float(sales.groupby("order_id").revenue.sum().mean()), 2),
        "most_used_payment": sales.payment_method.mode().iat[0],
        "top_city": customers.city.value_counts().idxmax(),
        "highest_rated_products": products.nlargest(5, "rating")["product_name"].tolist(),
        "repeat_customer_percent": round(float((customers.total_purchases > 1).mean() * 100), 1),
        "monthly_revenue": {str(index.date()): round(float(value), 2) for index, value in revenue_by_month.items()},
        "low_stock_products": products[products.stock < 10]["product_name"].tolist(),
    }
    pd.Series(summary, dtype=object).to_json(report_dir / "eda_summary.json", indent=2)
    sns.set_theme(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    merged.groupby("category").revenue.sum().sort_values().plot.barh(ax=axes[0], color="#245a48")
    axes[0].set_title("Revenue by category")
    axes[0].set_xlabel("Revenue ($)")
    revenue_by_month.plot(ax=axes[1], marker="o", color="#bd5638")
    axes[1].set_title("Monthly revenue")
    axes[1].set_ylabel("Revenue ($)")
    fig.tight_layout()
    fig.savefig(report_dir / "sales_overview.png", dpi=150)
    plt.close(fig)
    products.nlargest(10, "rating").sort_values("rating").plot.barh(x="product_name", y="rating", legend=False, color="#c27b42", figsize=(9, 5))
    plt.title("Top-rated products")
    plt.xlabel("Rating / 5")
    plt.tight_layout()
    plt.savefig(report_dir / "top_rated_products.png", dpi=150)
    plt.close()


def seed_database(customers: pd.DataFrame, products: pd.DataFrame, orders: pd.DataFrame, activity: pd.DataFrame) -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(Customer.customer_id).limit(1)) is not None:
            for customer in db.scalars(select(Customer).where(Customer.email.like("%@smartcart.local"))).all():
                customer.email = f"admin@example.com" if customer.role == "admin" else f"customer{customer.customer_id}@example.com"
            db.commit()
            return
        customer_password = hash_password("customer1234")
        for row in customers.to_dict("records"):
            db.add(Customer(
                customer_id=int(row["customer_id"]), name=row["name"], email=row["email"], password_hash=customer_password,
                age=int(row["age"]), gender=row["gender"], city=row["city"], registration_date=date.fromisoformat(row["registration_date"]),
                total_purchases=int(row["total_purchases"]), total_spending=float(row["total_spending"]),
                average_order_value=float(row["average_order_value"]), website_visits=int(row["website_visits"]),
            ))
        admin = Customer(name="SmartCart Admin", email="admin@example.com", password_hash=hash_password("admin1234"), role="admin", age=35, gender="Prefer not to say", city="New York")
        db.add(admin)
        for row in products.to_dict("records"):
            db.add(Product(**row))
        db.flush()
        for row in orders.to_dict("records"):
            order = Order(order_id=int(row["order_id"]), customer_id=int(row["customer_id"]), order_date=pd.Timestamp(row["order_date"]).to_pydatetime(), payment_method=row["payment_method"], order_status=row["order_status"], total_amount=float(row["price"] * row["quantity"]))
            db.add(order)
            db.add(OrderItem(order_id=int(row["order_id"]), product_id=int(row["product_id"]), quantity=int(row["quantity"]), price=float(row["price"])))
        for row in activity.to_dict("records"):
            db.add(CustomerActivity(**row))
        db.commit()


def main() -> None:
    customers, products, orders, activity = clean_data(*make_data())
    customers.to_csv(DATA_DIR / "customers.csv", index=False)
    products.to_csv(DATA_DIR / "products.csv", index=False)
    orders.to_csv(DATA_DIR / "orders.csv", index=False)
    activity.to_csv(DATA_DIR / "customer_activity.csv", index=False)
    seed_database(customers, products, orders, activity)
    training_data = activity.merge(
        customers[["customer_id", "age", "total_purchases", "total_spending", "average_order_value", "website_visits"]],
        on="customer_id",
    ).merge(products[["product_id", "price", "rating"]], on="product_id")
    training_data = training_data.rename(columns={
        "age": "customer_age", "price": "product_price", "rating": "product_rating",
    })
    model_report = train_models(training_data, customers)
    write_eda(customers, products, orders)
    print(f"Created {len(customers)} customers, {len(products)} products, {len(orders)} orders, {len(activity)} activity rows.")
    print(f"Selected classifier: {model_report['selected_model']}")
    print(f"Metrics: {model_report['models']}")


if __name__ == "__main__":
    main()