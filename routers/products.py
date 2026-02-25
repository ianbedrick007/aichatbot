from typing import Annotated
from datetime import datetime, timezone
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from PIL import Image

from database import get_db, get_current_user
from models import Product, Business, User
from schemas import ProductResponse, ProductUpdate, ProductCreate
from ai.image_embeddings import generate_image_embedding

router = APIRouter()

# Directory where product images are stored
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "media", "products")
os.makedirs(MEDIA_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def save_upload_file(upload_file: UploadFile) -> str:
    """Save an uploaded file and return the relative URL path."""
    # Validate extension
    ext = os.path.splitext(upload_file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Generate unique filename
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(MEDIA_DIR, filename)

    # Read and validate the image
    contents = upload_file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds 10MB limit"
        )

    # Validate it's a real image
    try:
        from io import BytesIO
        img = Image.open(BytesIO(contents))
        img.verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file"
        )

    # Save to disk
    with open(filepath, "wb") as f:
        f.write(contents)

    return filename, filepath


@router.get("/api/v1/products/{business_id}", response_model=list[ProductResponse], tags=["Products"])
def get_products(business_id: int, db: Session = Depends(get_db)):
    products = db.execute(
        select(Product).where(Product.business_id == business_id)).scalars().all()
    return products


@router.post("/api/v1/products", tags=["Products"])
def add_product(
        name: str = Form(...),
        price: float = Form(...),
        description: str = Form(None),
        image: UploadFile | None = File(None),
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

    # Handle image upload and embedding
    image_url = None
    image_embedding = None

    if image and image.filename:
        filename, filepath = save_upload_file(image)
        image_url = f"/media/products/{filename}"

        # Generate vector embedding from the image
        try:
            embedding = generate_image_embedding(filepath)
            image_embedding = embedding
        except Exception as e:
            print(f"[WARNING] Failed to generate embedding for new product: {e}")

    new_product = Product(
        name=name,
        price=price,
        description=description,
        image_url=image_url,
        image_embedding=image_embedding,
        business_id=business.id,
        created_at=datetime.now(timezone.utc)
    )
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


@router.post("/api/v1/products/{product_id}/image", tags=["Products"])
async def update_product_image(
        product_id: int,
        image: UploadFile = File(...),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Upload or replace a product's image and regenerate its embedding."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Delete old image if it exists
    if product.image_url:
        old_path = os.path.join(MEDIA_DIR, os.path.basename(product.image_url))
        if os.path.exists(old_path):
            os.remove(old_path)

    # Save new image
    filename, filepath = save_upload_file(image)
    product.image_url = f"/media/products/{filename}"

    # Generate new embedding
    try:
        embedding = generate_image_embedding(filepath)
        product.image_embedding = embedding
    except Exception as e:
        print(f"[WARNING] Failed to generate embedding for updated image: {e}")

    db.commit()
    db.refresh(product)
    return {"message": "Image updated", "image_url": product.image_url}


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

    # Clean up the image file
    if product.image_url:
        image_path = os.path.join(MEDIA_DIR, os.path.basename(product.image_url))
        if os.path.exists(image_path):
            os.remove(image_path)

    db.delete(product)
    db.commit()
