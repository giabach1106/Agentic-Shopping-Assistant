from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProductOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None

    price: Optional[float] = None
    currency: str

    avg_rating: Optional[float] = None
    rating_count: Optional[int] = None

    image_url: Optional[str] = None
    product_url: str

    source_site: str
    overall_score: Optional[float] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    title: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "USD"
    avg_rating: Optional[float] = None
    rating_count: Optional[int] = None
    image_url: Optional[str] = None
    product_url: str
    source_site: str
    overall_score: Optional[float] = None


class InteractionIn(BaseModel):
    event_type: str  # viewed/clicked/ordered


class OrderOut(BaseModel):
    id: str
    user_id: str
    product_id: str
    status: str
    store_url: str
    created_at: datetime

    class Config:
        from_attributes = True