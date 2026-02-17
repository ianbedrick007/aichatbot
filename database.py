import os

from dotenv import load_dotenv
import jwt
from fastapi import Depends, status, Request
from fastapi.exceptions import HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker, Session

from config import settings
from models import User

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("CHATBOT_DB")

connect_args = {}
if not SQLALCHEMY_DATABASE_URL:
    SQLALCHEMY_DATABASE_URL = "sqlite:///./chatbot.db"

if "sqlite" in SQLALCHEMY_DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    pass


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


def decode_token_and_get_user_id(token: str) -> int:
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


def get_current_user(
        request: Request,
        db: Session = Depends(get_db)
):
    # Read JWT from cookie
    token = request.cookies.get("access_token")
    if not token:
        # Redirect to login if no token found
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
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user
