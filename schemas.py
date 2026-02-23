from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# User Schemas
class UserBase(BaseModel):
    username: str = Field(max_length=80)
    email: str | None = Field(default=None, max_length=120)


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=255)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class UserPrivate(UserBase):
    model_config = ConfigDict(from_attributes=True)

    email: str | None


# Business Schemas
class BusinessBase(BaseModel):
    name: str = Field(max_length=120)
    phone_number_id: int | None = None
    persona: str | None = None


class BusinessCreate(BusinessBase):
    user_id: int


class BusinessUpdate(BaseModel):
    name: str | None = None
    phone_number_id: int | None = None
    persona: str | None = None


class BusinessResponse(BusinessBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    user: UserPrivate


class SignupRequest(BaseModel):
    username: str
    email: str | None = None
    password: str
    business_name: str
    phone_number_id: int | None = None


# Product Schemas
class ProductBase(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None
    price: float
    image_url: str | None = None


class ProductCreate(ProductBase):
    business_id: int


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    image_url: str | None = None


class ProductResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    created_at: datetime
    has_embedding: bool = False


# Message Schemas
class MessageBase(BaseModel):
    text: str | None = None
    sender: str = Field(max_length=10)


class MessageCreate(MessageBase):
    business_id: int


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_id: int
    timestamp: datetime


class ToggleAIRequest(BaseModel):
    customer_id: str
    enable_ai: bool
    message: str | None = None


class ChatRequest(BaseModel):
    message: str
