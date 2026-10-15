from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import jwt
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.ml import customer_segment, load_purchase_model, purchase_probability
from app.models import CartItem, Customer, CustomerActivity, Order, OrderItem, Product
from app.schemas import (
    CartCreate, CartOut, CartUpdate, CustomerCreate, CustomerOut, CustomerUpdate,
    LoginRequest, OrderCreate, OrderOut, PredictionRequest, PredictionResponse,
    ProductCreate, ProductOut, ProductUpdate, Recommendation, RegisterRequest, TokenResponse,
    RecommendationResponse,
)
from app.security import JWT_ALGORITHM, JWT_SECRET, create_access_token, hash_password, verify_password


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"
bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        has_customers = db.scalar(select(Customer.customer_id).limit(1)) is not None
    if not has_customers:
        from app.seed import main as seed_main
        seed_main()
    yield


app = FastAPI(title="SmartCart API", version="1.0.0", description="E-commerce APIs with purchase prediction and customer insights.", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def storefront():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "SmartCart"}


def current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Customer:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        customer_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return customer


def optional_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Customer | None:
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        customer_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    return db.get(Customer, customer_id)


def admin_customer(customer: Customer = Depends(current_customer)) -> Customer:
    if customer.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return customer


def require_owner(customer_id: int, user: Customer) -> None:
    if user.role != "admin" and user.customer_id != customer_id:
        raise HTTPException(status_code=403, detail="You can only access your own account")


def find_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def find_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


def activity_for(db: Session, customer_id: int, product_id: int) -> CustomerActivity:
    activity = db.get(CustomerActivity, (customer_id, product_id))
    if activity is None:
        activity = CustomerActivity(customer_id=customer_id, product_id=product_id)
        db.add(activity)
        db.flush()
    return activity


def feature_row(customer: Customer, product: Product, activity: CustomerActivity | None) -> dict:
    return {
        "customer_age": customer.age,
        "total_purchases": customer.total_purchases,
        "total_spending": customer.total_spending,
        "average_order_value": customer.average_order_value,
        "website_visits": customer.website_visits,
        "product_price": product.price,
        "product_rating": product.rating,
        "product_views": activity.product_views if activity else 0,
        "cart_additions": activity.cart_additions if activity else 0,
        "wishlist_additions": activity.wishlist_additions if activity else 0,
        "previous_purchases": activity.previous_purchases if activity else 0,
        "time_spent": activity.time_spent if activity else 0,
    }


def recommendations_for(db: Session, customer_id: int, limit: int = 5) -> list[dict]:
    customer = find_customer(db, customer_id)
    purchased_ids = set(db.scalars(select(OrderItem.product_id).join(Order).where(Order.customer_id == customer_id, Order.order_status != "cancelled")).all())
    category_counts = db.execute(
        select(Product.category, func.sum(OrderItem.quantity))
        .join(OrderItem, OrderItem.product_id == Product.product_id)
        .join(Order, Order.order_id == OrderItem.order_id)
        .where(Order.customer_id == customer_id, Order.order_status != "cancelled")
        .group_by(Product.category)
    ).all()
    preferences = {category: count for category, count in category_counts}
    products = db.scalars(select(Product).where(Product.stock > 0)).all()
    if not products:
        return []
    max_rating = max((product.rating for product in products), default=5) or 5
    max_price = max((product.price for product in products), default=1) or 1
    ranked = []
    for product in products:
        if product.product_id in purchased_ids:
            continue
        affinity = preferences.get(product.category, 0)
        stock_factor = min(product.stock / 25, 1)
        rating_factor = product.rating / max_rating
        value_factor = 1 - product.price / max_price
        score = 0.54 * (affinity / max(preferences.values(), default=1)) + 0.33 * rating_factor + 0.08 * stock_factor + 0.05 * value_factor
        ranked.append((score, product))
    if not ranked:
        ranked = [(0.7 * product.rating / max_rating + 0.3 * (1 - product.price / max_price), product) for product in products]
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [{
        "product_id": product.product_id,
        "product_name": product.product_name,
        "category": product.category,
        "price": round(product.price, 2),
        "rating": product.rating,
        "score": round(float(score), 3),
        "image_url": product.image_url,
    } for score, product in ranked[:limit]]


@app.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(Customer.customer_id).where(func.lower(Customer.email) == payload.email.lower())):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    customer = Customer(
        name=payload.name, email=payload.email.lower(), password_hash=hash_password(payload.password),
        age=payload.age, gender=payload.gender, city=payload.city,
    )
    db.add(customer)
    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return {"access_token": create_access_token(customer.customer_id, customer.role), "customer": customer}


@app.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    customer = db.scalar(select(Customer).where(func.lower(Customer.email) == payload.email.lower()))
    if customer is None or not verify_password(payload.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"access_token": create_access_token(customer.customer_id, customer.role), "customer": customer}


@app.get("/customers", response_model=list[CustomerOut])
def list_customers(_: Customer = Depends(admin_customer), db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return db.scalars(select(Customer).order_by(Customer.customer_id).offset(offset).limit(limit)).all()


@app.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerCreate, _: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    if db.scalar(select(Customer.customer_id).where(func.lower(Customer.email) == payload.email.lower())):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    customer_data = payload.model_dump(exclude={"password", "email"})
    customer = Customer(**customer_data, email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(customer)
    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return customer


@app.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    return find_customer(db, customer_id)


@app.put("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    customer = find_customer(db, customer_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(customer, key, value)
    db.commit()
    db.refresh(customer)
    return customer


@app.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    customer = find_customer(db, customer_id)
    db.delete(customer)
    db.commit()


@app.get("/products", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db), search: str | None = None, category: str | None = None,
    limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
):
    query = select(Product)
    if search:
        query = query.where(Product.product_name.ilike(f"%{search.strip()}%"))
    if category:
        query = query.where(Product.category == category)
    return db.scalars(query.order_by(Product.product_id).offset(offset).limit(limit)).all()


@app.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, _: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db), user: Customer | None = Depends(optional_customer)):
    product = find_product(db, product_id)
    if user is not None:
        activity_for(db, user.customer_id, product_id).product_views += 1
        user.website_visits += 1
        db.commit()
    return product


@app.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, _: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    product = find_product(db, product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, _: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    product = find_product(db, product_id)
    try:
        db.delete(product)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Product is referenced by an order and cannot be deleted")


@app.post("/cart", response_model=CartOut, status_code=201)
def add_to_cart(payload: CartCreate, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(payload.customer_id, user)
    product = find_product(db, payload.product_id)
    if product.stock < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")
    item = db.scalar(select(CartItem).where(CartItem.customer_id == user.customer_id, CartItem.product_id == product.product_id))
    if item:
        if product.stock < item.quantity + payload.quantity:
            raise HTTPException(status_code=409, detail="Insufficient stock for requested cart quantity")
        item.quantity += payload.quantity
    else:
        item = CartItem(customer_id=user.customer_id, product_id=product.product_id, quantity=payload.quantity)
        db.add(item)
    activity_for(db, user.customer_id, product.product_id).cart_additions += 1
    db.commit()
    db.refresh(item)
    return item


@app.get("/cart/{customer_id}")
def get_cart(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    items = db.scalars(select(CartItem).where(CartItem.customer_id == customer_id)).all()
    return [{"cart_id": item.cart_id, "customer_id": item.customer_id, "product_id": item.product_id, "quantity": item.quantity, "product": find_product(db, item.product_id)} for item in items]


@app.put("/cart/{cart_id}", response_model=CartOut)
def update_cart(cart_id: int, payload: CartUpdate, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    item = db.get(CartItem, cart_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    require_owner(item.customer_id, user)
    if find_product(db, item.product_id).stock < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")
    item.quantity = payload.quantity
    db.commit()
    db.refresh(item)
    return item


@app.delete("/cart/{cart_id}", status_code=204)
def delete_cart_item(cart_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    item = db.get(CartItem, cart_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Cart item not found")
    require_owner(item.customer_id, user)
    db.delete(item)
    db.commit()


def place_order(customer: Customer, payload: OrderCreate, db: Session) -> Order:
    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    products = {product_id: find_product(db, product_id) for product_id in quantities}
    for product_id, quantity in quantities.items():
        if products[product_id].stock < quantity:
            raise HTTPException(status_code=409, detail=f"Insufficient stock for {products[product_id].product_name}")
    order = Order(customer_id=customer.customer_id, payment_method=payload.payment_method, order_status="completed")
    db.add(order)
    db.flush()
    total = 0.0
    for product_id, quantity in quantities.items():
        product = products[product_id]
        unit_price = round(product.price * (1 - product.discount / 100), 2)
        total += unit_price * quantity
        product.stock -= quantity
        db.add(OrderItem(order_id=order.order_id, product_id=product_id, quantity=quantity, price=unit_price))
        activity = activity_for(db, customer.customer_id, product_id)
        activity.previous_purchases += quantity
        activity.purchased = 1
        cart_item = db.scalar(select(CartItem).where(CartItem.customer_id == customer.customer_id, CartItem.product_id == product_id))
        if cart_item:
            db.delete(cart_item)
    order.total_amount = round(total, 2)
    customer.total_purchases += 1
    customer.total_spending += order.total_amount
    customer.average_order_value = customer.total_spending / customer.total_purchases
    db.commit()
    db.refresh(order)
    return order


@app.post("/orders", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    return place_order(user, payload, db)


@app.get("/orders", response_model=list[OrderOut])
def list_orders(user: Customer = Depends(current_customer), db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500)):
    query = select(Order).order_by(Order.order_date.desc()).limit(limit)
    if user.role != "admin":
        query = query.where(Order.customer_id == user.customer_id)
    return db.scalars(query).all()


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    require_owner(order.customer_id, user)
    return order


@app.get("/customers/{customer_id}/orders", response_model=list[OrderOut])
def customer_orders(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    return db.scalars(select(Order).where(Order.customer_id == customer_id).order_by(Order.order_date.desc())).all()


@app.post("/predict-purchase", response_model=PredictionResponse)
def predict_purchase(payload: PredictionRequest, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(payload.customer_id, user)
    customer = find_customer(db, payload.customer_id)
    product = find_product(db, payload.product_id)
    activity = db.get(CustomerActivity, (customer.customer_id, product.product_id))
    try:
        probability = purchase_probability(feature_row(customer, product, activity))
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error))
    if activity is not None:
        activity.product_views += 1
        activity.time_spent += 12
        db.commit()
    return {"customer_id": customer.customer_id, "product_id": product.product_id, "purchase_probability": round(probability, 4), "prediction": "Likely to Purchase" if probability >= 0.5 else "Unlikely to Purchase"}


@app.get("/recommendations/{customer_id}", response_model=RecommendationResponse)
def get_recommendations(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    return {"customer_id": customer_id, "recommendations": recommendations_for(db, customer_id)}


@app.get("/customer-segment/{customer_id}")
def get_customer_segment(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    customer = find_customer(db, customer_id)
    try:
        segment = customer_segment(customer.__dict__)
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return {"customer_id": customer_id, "segment": segment}


@app.get("/customer-dashboard/{customer_id}")
def customer_dashboard(customer_id: int, user: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    require_owner(customer_id, user)
    customer = find_customer(db, customer_id)
    orders = db.scalars(select(Order).where(Order.customer_id == customer_id, Order.order_status != "cancelled")).all()
    recommendations = recommendations_for(db, customer_id)
    try:
        segment = customer_segment(customer.__dict__)
        model = load_purchase_model()
        predictions = []
        for recommendation in recommendations[:3]:
            product = db.get(Product, recommendation["product_id"])
            activity = db.get(CustomerActivity, (customer_id, product.product_id))
            probability = purchase_probability(feature_row(customer, product, activity))
            predictions.append({"product_id": product.product_id, "product_name": product.product_name, "purchase_probability": round(probability, 4)})
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return {
        "customer": CustomerOut.model_validate(customer),
        "total_orders": len(orders),
        "total_spending": round(sum(order.total_amount for order in orders), 2),
        "average_order_value": round(sum(order.total_amount for order in orders) / len(orders), 2) if orders else 0,
        "previous_purchases": customer.total_purchases,
        "segment": segment,
        "recommended_products": recommendations,
        "purchase_predictions": predictions,
    }


def admin_sales_data(db: Session) -> pd.DataFrame:
    rows = db.execute(
        select(Order.order_id, Order.customer_id, Order.order_date, Order.payment_method, OrderItem.product_id, OrderItem.quantity, OrderItem.price)
        .join(OrderItem, Order.order_id == OrderItem.order_id)
        .where(Order.order_status != "cancelled")
    ).all()
    return pd.DataFrame(rows, columns=["order_id", "customer_id", "order_date", "payment_method", "product_id", "quantity", "price"])


@app.get("/admin/sales-summary")
def sales_summary(_: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    sales = admin_sales_data(db)
    if sales.empty:
        return {"revenue": 0, "order_count": 0, "average_order_value": 0, "monthly_revenue": []}
    sales["revenue"] = sales.quantity * sales.price
    by_order = sales.groupby("order_id").revenue.sum()
    monthly = sales.assign(month=pd.to_datetime(sales.order_date).dt.to_period("M").astype(str)).groupby("month").revenue.sum()
    return {"revenue": round(float(sales.revenue.sum()), 2), "order_count": int(by_order.size), "average_order_value": round(float(by_order.mean()), 2), "monthly_revenue": [{"month": month, "revenue": round(float(value), 2)} for month, value in monthly.items()]}


@app.get("/admin/top-products")
def top_products(_: Customer = Depends(admin_customer), db: Session = Depends(get_db), limit: int = Query(10, ge=1, le=50)):
    rows = db.execute(
        select(Product.product_id, Product.product_name, Product.category, func.sum(OrderItem.quantity).label("units"), func.sum(OrderItem.quantity * OrderItem.price).label("revenue"))
        .join(OrderItem, Product.product_id == OrderItem.product_id).join(Order, Order.order_id == OrderItem.order_id)
        .where(Order.order_status != "cancelled").group_by(Product.product_id).order_by(func.sum(OrderItem.quantity * OrderItem.price).desc()).limit(limit)
    ).all()
    return [{"product_id": row.product_id, "product_name": row.product_name, "category": row.category, "units_sold": row.units, "revenue": round(float(row.revenue), 2)} for row in rows]


@app.get("/admin/top-customers")
def top_customers(_: Customer = Depends(admin_customer), db: Session = Depends(get_db), limit: int = Query(10, ge=1, le=50)):
    rows = db.execute(
        select(Customer.customer_id, Customer.name, Customer.city, func.sum(Order.total_amount).label("spending"), func.count(Order.order_id).label("orders"))
        .join(Order, Order.customer_id == Customer.customer_id).where(Order.order_status != "cancelled")
        .group_by(Customer.customer_id).order_by(func.sum(Order.total_amount).desc()).limit(limit)
    ).all()
    return [{"customer_id": row.customer_id, "name": row.name, "city": row.city, "total_spending": round(float(row.spending), 2), "orders": row.orders} for row in rows]


@app.get("/admin/category-sales")
def category_sales(_: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Product.category, func.sum(OrderItem.quantity).label("units"), func.sum(OrderItem.quantity * OrderItem.price).label("revenue"))
        .join(OrderItem, Product.product_id == OrderItem.product_id).join(Order, Order.order_id == OrderItem.order_id)
        .where(Order.order_status != "cancelled").group_by(Product.category).order_by(func.sum(OrderItem.quantity * OrderItem.price).desc())
    ).all()
    return [{"category": row.category, "units_sold": row.units, "revenue": round(float(row.revenue), 2)} for row in rows]


@app.get("/admin/customer-segments")
def customer_segments(_: Customer = Depends(admin_customer), db: Session = Depends(get_db)):
    customers = db.scalars(select(Customer).where(Customer.role == "customer")).all()
    counts: dict[str, int] = {}
    for customer in customers:
        try:
            segment = customer_segment(customer.__dict__)
        except FileNotFoundError as error:
            raise HTTPException(status_code=503, detail=str(error))
        counts[segment] = counts.get(segment, 0) + 1
    return [{"segment": segment, "customer_count": count} for segment, count in counts.items()]


@app.get("/admin/low-stock-products", response_model=list[ProductOut])
def low_stock_products(_: Customer = Depends(admin_customer), db: Session = Depends(get_db), threshold: int = Query(10, ge=0, le=100)):
    return db.scalars(select(Product).where(Product.stock < threshold).order_by(Product.stock)).all()