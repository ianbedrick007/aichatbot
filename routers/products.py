from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db, get_current_user
from models import Product, Business, User
from schemas import ProductResponse, ProductUpdate, ProductCreate

router = APIRouter()


@router.get("/api/v1/products/{business_id}", response_model=list[ProductResponse], tags=["Products"])
def get_products(business_id: int, db: Session = Depends(get_db)):
    # products = db.query(Product).filter(Product.business_id == business_id).all()
    products = db.execute(
        select(Product).where(Product.business_id == business_id)).scalars().all()
    return products


@router.post("/api/v1/products", tags=["Products"])
def add_product(
        name: str = Form(...),
        price: float = Form(...),
        description: str = Form(None),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    business = db.execute(
        select(Business).where(Business.user_id == current_user.id)
    ).scalar()

    if not business:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business not found")

    if db.execute(
            select(Product).where(Product.name == name, Product.business_id == business.id)).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product already exists")

    new_product = Product(name=name,
                          price=price,
                          description=description,
                          business_id=business.id)
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return RedirectResponse(url="/products", status_code=status.HTTP_303_SEE_OTHER)


@router.patch("/api/v1/products/{product_id}", response_model=ProductResponse, tags=["Products"])
async def update_product(product_id: int, product: ProductUpdate, db: Session = Depends(get_db)):
    existing_product = db.query(Product).filter(Product.id == product_id).first()

    if not existing_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if product.name:
        existing_product.name = product.name
    if product.price:
        existing_product.price = product.price
    if product.description:
        existing_product.description = product.description

    db.commit()
    db.refresh(existing_product)
    return existing_product


@router.put("/api/v1/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def replace_product(product_id: int, product: ProductCreate, db: Annotated[Session, Depends(get_db)]):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    db_product.name = product.name
    db_product.price = product.price
    db_product.description = product.description
    if product.business_id:
        db_product.business_id = product.business_id

    db.commit()
    db.refresh(db_product)
    return db_product


@router.delete("/api/v1/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Products"])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    db.delete(product)
    db.commit()
