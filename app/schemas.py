from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    age: int = Field(ge=13, le=100)
    gender: str = Field(default="Prefer not to say", max_length=30)
    city: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class CustomerCreate(RegisterRequest):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    age: int | None = Field(default=None, ge=13, le=100)
    gender: str | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, min_length=2, max_length=100)


class CustomerOut(Schema):
    customer_id: int
    name: str
    email: EmailStr
    role: str
    age: int
    gender: str
    city: str
    registration_date: date
    total_purchases: int
    total_spending: float
    average_order_value: float
    website_visits: int


class ProductCreate(BaseModel):
    product_name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    price: float = Field(gt=0, le=1_000_000)
    rating: float = Field(default=4, ge=0, le=5)
    stock: int = Field(default=0, ge=0)
    discount: float = Field(default=0, ge=0, le=100)
    image_url: str = Field(default="", max_length=500)


class ProductUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=2, max_length=160)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    price: float | None = Field(default=None, gt=0, le=1_000_000)
    rating: float | None = Field(default=None, ge=0, le=5)
    stock: int | None = Field(default=None, ge=0)
    discount: float | None = Field(default=None, ge=0, le=100)
    image_url: str | None = Field(default=None, max_length=500)


class ProductOut(Schema):
    product_id: int
    product_name: str
    category: str
    price: float
    rating: float
    stock: int
    discount: float
    image_url: str


class CartCreate(BaseModel):
    customer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)


class CartUpdate(BaseModel):
    quantity: int = Field(gt=0, le=100)


class CartOut(Schema):
    cart_id: int
    customer_id: int
    product_id: int
    quantity: int


class OrderItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)


class OrderCreate(BaseModel):
    items: list[OrderItemCreate] = Field(min_length=1)
    payment_method: str = Field(min_length=2, max_length=40)


class OrderItemOut(Schema):
    order_item_id: int
    order_id: int
    product_id: int
    quantity: int
    price: float


class OrderOut(Schema):
    order_id: int
    customer_id: int
    order_date: datetime
    payment_method: str
    order_status: str
    total_amount: float


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: CustomerOut


class PredictionRequest(BaseModel):
    customer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)


class PredictionResponse(BaseModel):
    customer_id: int
    product_id: int
    purchase_probability: float
    prediction: str


class Recommendation(BaseModel):
    product_id: int
    product_name: str
    category: str
    price: float
    rating: float
    score: float
    image_url: str


class RecommendationResponse(BaseModel):
    customer_id: int
    recommendations: list[Recommendation]