from .db import SessionLocal
from .models import Product


def seed():
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            return

        db.add_all(
            [
                Product(
                    title="Sony WH-1000XM5 Wireless Headphones",
                    description="Noise cancelling, long battery life.",
                    price=299.99,
                    currency="USD",
                    avg_rating=4.7,
                    rating_count=25000,
                    image_url="https://example.com/xm5.jpg",
                    product_url="https://example.com/buy-xm5",
                    source_site="amazon",
                    overall_score=0.92,
                ),
                Product(
                    title="Logitech MX Master 3S Mouse",
                    description="Ergonomic productivity mouse.",
                    price=89.99,
                    currency="USD",
                    avg_rating=4.8,
                    rating_count=18000,
                    image_url="https://example.com/mx3s.jpg",
                    product_url="https://example.com/buy-mx3s",
                    source_site="amazon",
                    overall_score=0.88,
                ),
                Product(
                    title="Anker 737 Power Bank",
                    description="High capacity fast charging power bank.",
                    price=109.99,
                    currency="USD",
                    avg_rating=4.6,
                    rating_count=9000,
                    image_url="https://example.com/anker737.jpg",
                    product_url="https://example.com/buy-anker737",
                    source_site="walmart",
                    overall_score=0.84,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()