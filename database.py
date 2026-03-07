import os

import jwt
from dotenv import load_dotenv
from fastapi import Depends, status, Request
from fastapi.exceptions import HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase, selectinload

from config import settings
from models import User, Business

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("CHATBOT_DB")

if SQLALCHEMY_DATABASE_URL:
    # Clean up potential artifacts from .env parsing (whitespace, quotes, \r from Windows)
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.strip().strip('"').strip("'")
    # Ensure async driver for PostgreSQL
    if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

if not SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./chatbot.db"

connect_args = {}
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args
)

AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    pass


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


def decode_token_and_get_user_id(token: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )
        return int(payload.get("sub"))
    except jwt.InvalidTokenError:
        return None


async def get_current_user(
        request: Request,
        db: AsyncSession = Depends(get_db)
) -> User:
    # Read JWT from cookie
    token = request.cookies.get("access_token")
    if not token:
        # Redirect to log in if no token found
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Decode token → get user_id
    user_id = decode_token_and_get_user_id(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Fetch user
    result = await db.execute(
        select(User).options(selectinload(User.business)).where(User.id == int(user_id))
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


async def get_current_business(
        db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)
) -> Business:
    result = await db.execute(
        select(Business)
        .options(selectinload(Business.user))
        .where(Business.user_id == current_user.id
               ))
    business = result.scalars().first()

    return business
