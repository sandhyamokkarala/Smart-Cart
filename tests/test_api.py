from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Customer, Product
from app.security import hash_password


def test_customer_purchase_journey(client) -> None:
    response = client.post("/register", json={
        "name": "New Shopper", "email": "new@example.com", "password": "newpassword1",
        "age": 31, "gender": "Female", "city": "Portland",
    })
    assert response.status_code == 201
    token = response.json()["access_token"]
    customer_id = response.json()["customer"]["customer_id"]
    headers = {"Authorization": f"Bearer {token}"}

    products = client.get("/products").json()
    assert len(products) == 3
    picks = client.get(f"/recommendations/{customer_id}", headers=headers)
    assert picks.status_code == 200 and len(picks.json()["recommendations"]) == 3
    assert client.get(f"/products/{products[0]['product_id']}", headers=headers).status_code == 200

    cart = client.post("/cart", headers=headers, json={"customer_id": customer_id, "product_id": products[0]["product_id"], "quantity": 2})
    assert cart.status_code == 201
    order = client.post("/orders", headers=headers, json={
        "payment_method": "Card", "items": [{"product_id": products[0]["product_id"], "quantity": 2}],
    })
    assert order.status_code == 201
    assert order.json()["total_amount"] == 142.2

    prediction = client.post("/predict-purchase", headers=headers, json={"customer_id": customer_id, "product_id": products[1]["product_id"]})
    assert prediction.status_code == 200
    assert 0 <= prediction.json()["purchase_probability"] <= 1
    assert client.get(f"/customer-segment/{customer_id}", headers=headers).status_code == 200
    dashboard = client.get(f"/customer-dashboard/{customer_id}", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_orders"] == 1
    assert dashboard.json()["previous_purchases"] == 1


def test_admin_access_and_error_responses(client) -> None:
    customer_token = login(client, "shopper@example.com", "customerpass1")
    admin_token = login(client, "admin@example.com", "adminpass123")
    assert client.get("/admin/sales-summary", headers={"Authorization": f"Bearer {customer_token}"}).status_code == 403
    assert client.get("/admin/sales-summary", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
    assert client.get("/products/999").status_code == 404
    assert client.post("/login", json={"email": "shopper@example.com", "password": "wrongpass1"}).status_code == 401
    assert client.post("/cart", headers={"Authorization": f"Bearer {customer_token}"}, json={"customer_id": 1, "product_id": 999, "quantity": 1}).status_code == 404


def login(client, email: str, password: str) -> str:
    response = client.post("/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)
    with testing_session() as db:
        db.add_all([
            Customer(name="Test Shopper", email="shopper@example.com", password_hash=hash_password("customerpass1"), age=29, gender="Female", city="Austin"),
            Customer(name="Test Admin", email="admin@example.com", password_hash=hash_password("adminpass123"), role="admin", age=35, gender="Male", city="Seattle"),
            Product(product_name="Test headphones", category="Electronics", price=79.0, rating=4.7, stock=12, discount=10),
            Product(product_name="Test lamp", category="Home", price=45.0, rating=4.4, stock=8),
            Product(product_name="Test bottle", category="Sports", price=25.0, rating=4.2, stock=20),
        ])
        db.commit()

    def override_get_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()