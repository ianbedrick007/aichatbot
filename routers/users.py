from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session, selectinload

from auth import (
    create_access_token,
    verify_password, hash_password, verify_access_token, oauth2_scheme
)
from config import settings
from database import get_db
from models import User, Business, Product
from schemas import Token, UserResponse, SignupRequest, UserPrivate, UserUpdate, ProductResponse, UserPublic

router = APIRouter()


@router.post("/api/v1/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Users"])
def create_user(request: SignupRequest, db: Annotated[Session, Depends(get_db)]):
    username = request.username.strip()
    email = request.email
    password = request.password.strip()
    business_name = request.business_name.strip()
    phone_number_id = request.phone_number_id if request.phone_number_id else None
    # Basic validation
    if not username or not password or not business_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username, password, and business name are required."
        )

    # Prevent duplicates
    if (db.execute(select(User).where(User.username == username))).scalar():
        raise HTTPException(status_code=400, detail="Username already exists.")

    if email and (db.execute(select(User).where(User.email == email))).scalar():
        raise HTTPException(status_code=400, detail="Email already exists.")

    if phone_number_id and (db.execute(
            select(Business).where(Business.phone_number_id == phone_number_id)
    )).scalar():
        raise HTTPException(status_code=400, detail="This WhatsApp phone number is already registered.")

    # Atomic transaction
    try:
        new_user = User(
            username=username,
            email=email or "",
            password_hash=hash_password(password)
        )
        db.add(new_user)
        db.flush()  # ensures new_user.id is available

        new_business = Business(
            name=business_name,
            user_id=new_user.id,
            phone_number_id=int(phone_number_id) if phone_number_id else None
        )
        db.add(new_business)

        db.commit()
        db.refresh(new_user)
        return new_user

    except Exception:
        db.rollback()
        raise


@router.post("/token", response_model=Token)
def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        db: Annotated[Session, Depends(get_db)],
):
    # Look up user by email (case-insensitive)
    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat it as email
    result = db.execute(
        select(User).where(
            or_(
                func.lower(User.username) == func.lower(form_data.username),
                func.lower(User.email) == func.lower(form_data.username)
            )
        ),
    )
    user = result.scalars().first()

    # Verify user exists and password is correct
    # Don't reveal which one failed (security best practice)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token with user id as subject
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserPrivate)
def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        db: Annotated[Session, Depends(get_db)],
):
    """Get the currently authenticated user."""
    user_id = verify_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate user_id is a valid integer (defense against malformed JWT)
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = db.execute(
        select(User).where(User.id == user_id_int),
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.get("/{user_id}", response_model=UserPublic)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.get("/{business_id}/products", response_model=list[ProductResponse])
def get_business_products(business_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(Business).where(Business.id == business_id))
    business = result.scalars().first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    result = db.execute(
        select(Product)
        .options(selectinload(Product.business))
        .where(Product.business_id == business_id)
        .order_by(Product.created_at.desc()),
    )
    products = result.scalars().all()
    return products


@router.patch("/{user_id}", response_model=UserPrivate)
def update_user(
        user_id: int,
        user_update: UserUpdate,
        db: Annotated[Session, Depends(get_db)],
):
    result = db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    if (
            user_update.username is not None
            and user_update.username.lower() != user.username.lower()
    ):
        result = db.execute(
            select(User).where(
                User.username == user_update.username.lower(),
            ),
        )
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )
    if (
            user_update.email is not None
            and user_update.email.lower() != user.email.lower()
    ):
        result = db.execute(
            select(User).where(
                User.email == user_update.email.lower(),
            ),
        )
        existing_email = result.scalars().first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    if user_update.username is not None:
        user.username = user_update.username
    if user_update.email is not None:
        user.email = user_update.email.lower()
    if user_update.image_file is not None:
        user.image_file = user_update.image_file

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db.delete(user)
    db.commit()
