from __future__ import annotations
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Float, BigInteger, Boolean, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase
from pgvector.sqlalchemy import Vector
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class Base(DeclarativeBase):
    pass


class Business(Base):
    __tablename__ = 'businesses'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # ✅ 1:1: each business has exactly one user login
    # unique=True enforces "one user -> one business"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, unique=True)

    # ✅ NEW: WhatsApp phone number ID mapping
    # Stored as String to safely support large phone number IDs
    phone_number_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    # ✅ Business persona: defines the AI's personality/instructions
    persona: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="business")
    messages_list = relationship('Message', back_populates='business', lazy=True, cascade='all, delete-orphan')
    products: Mapped[list["Product"]] = relationship("Product", back_populates="business", lazy=True)


# User model
class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # ✅ 1:1 relationship: one user has one business (business is the "account")
    business: Mapped["Business"] = relationship('Business', back_populates='user', uselist=False, lazy=True,
                                                cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if the provided password matches the hash"""
        return check_password_hash(self.password_hash, password)


# Message model
class Message(Base):
    __tablename__ = 'messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ✅ Messages belong to the business
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey('businesses.id'), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default='web', nullable=False)
    
    # Track the specific conversation
    customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    
    text: Mapped[str] = mapped_column(Text, nullable=True)
    sender: Mapped[str] = mapped_column(String(120), nullable=False)  # 'wa_id' or 'bot' or 'user'
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), server_default=func.now())

    # Relationship back to business
    business = relationship('Business', back_populates='messages_list', lazy=True)


class Product(Base):
    __tablename__ = 'products'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # ✅ Products belong to the business
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey('businesses.id'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    image_embedding = mapped_column(Vector(1408), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    business: Mapped["Business"] = relationship('Business', back_populates='products', lazy=True)

    # @property
    # def image_path(self) -> str:
    #     if self.image_url:
    #         return f"/media/product_pics/{self.image_url}"