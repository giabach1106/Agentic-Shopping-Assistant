import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import engine, get_db, Base
from .models import Product, InteractionEvent, UserProduct, Order, User
from .schemas import ProductOut, InteractionIn, OrderOut
from .auth import get_current_user

load_dotenv()  # loads backend/.env

app = FastAPI(title="Agentic Shopping Assistant API",
              swagger_ui_parameters={"persistAuthorization": True},)
logger = logging.getLogger(__name__)

# CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_db_init() -> None:
    auto_init_db = os.getenv("AUTO_INIT_DB", "true").strip().lower() == "true"
    if not auto_init_db:
        logger.info("Skipping DB init because AUTO_INIT_DB is not true.")
        return

    try:
        Base.metadata.create_all(bind=engine)
        logger.info("DB init OK (create_all).")
    except Exception as exc:
        logger.exception("DB init failed during startup: %s", exc)


def ensure_user(db: Session, user_claims: dict) -> str:
    """
    Ensures a row exists in users table for this Cognito subject.
    Returns user_id (sub).
    """
    user_id = user_claims["sub"]
    email = user_claims.get("email")

    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id, email=email)
        db.add(user)
        db.flush()  # allocate row in same transaction
    else:
        if email and user.email != email:
            user.email = email

    return user_id


# ----------------------
# Basic endpoints
# ----------------------
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/me")
def me(
    db: Session = Depends(get_db),
    user_claims=Depends(get_current_user),
):
    user_id = ensure_user(db, user_claims)
    db.commit()
    user = db.get(User, user_id)
    return {"user_id": user.id, "email": user.email}


@app.get("/debug/env")
def debug_env():
    return {
        "COGNITO_REGION": os.getenv("COGNITO_REGION"),
        "COGNITO_USER_POOL_ID": os.getenv("COGNITO_USER_POOL_ID"),
        "COGNITO_APP_CLIENT_ID": os.getenv("COGNITO_APP_CLIENT_ID"),
        "DATABASE_URL": os.getenv("DATABASE_URL"),
    }


# ----------------------
# Products
# ----------------------
@app.get("/products", response_model=list[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    user_claims=Depends(get_current_user),
):
    # optional: ensure user exists for analytics consistency
    ensure_user(db, user_claims)
    db.commit()

    return db.query(Product).order_by(Product.created_at.desc()).limit(50).all()


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    user_claims=Depends(get_current_user),
):
    ensure_user(db, user_claims)
    db.commit()

    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


# ----------------------
# Interaction tracking
# ----------------------
@app.post("/products/{product_id}/interaction")
def track_interaction(
    product_id: str,
    payload: InteractionIn,
    db: Session = Depends(get_db),
    user_claims=Depends(get_current_user),
):
    event = payload.event_type.strip().lower()
    if event not in {"viewed", "clicked", "ordered"}:
        raise HTTPException(
            status_code=400,
            detail="event_type must be one of: viewed, clicked, ordered",
        )

    # ensure user exists (FK)
    user_id = ensure_user(db, user_claims)

    # ensure product exists
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    # Save event
    db.add(InteractionEvent(user_id=user_id, product_id=product_id, event_type=event))

    # Upsert relationship row
    up = (
        db.query(UserProduct)
        .filter(UserProduct.user_id == user_id, UserProduct.product_id == product_id)
        .first()
    )
    if not up:
        up = UserProduct(user_id=user_id, product_id=product_id, last_status=event)
        db.add(up)
    else:
        up.last_status = event

    if event == "ordered":
        up.has_user_ordered_before = True

    db.commit()
    return {"ok": True}


# ----------------------
# Orders ("Buy" button)
# ----------------------
@app.post("/products/{product_id}/order", response_model=OrderOut)
def create_order(
    product_id: str,
    db: Session = Depends(get_db),
    user_claims=Depends(get_current_user),
):
    # ensure user exists (FK)
    user_id = ensure_user(db, user_claims)

    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    # Record ordered event (analytics)
    db.add(InteractionEvent(user_id=user_id, product_id=product_id, event_type="ordered"))

    # Update per-user relationship
    up = (
        db.query(UserProduct)
        .filter(UserProduct.user_id == user_id, UserProduct.product_id == product_id)
        .first()
    )
    if not up:
        up = UserProduct(
            user_id=user_id,
            product_id=product_id,
            last_status="ordered",
            has_user_ordered_before=True,
        )
        db.add(up)
    else:
        up.last_status = "ordered"
        up.has_user_ordered_before = True

    # Create order record
    order = Order(
        user_id=user_id,
        product_id=product_id,
        status="initiated",
        store_url=p.product_url,
    )
    db.add(order)

    db.commit()
    db.refresh(order)
    return order