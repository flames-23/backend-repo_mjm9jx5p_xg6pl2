"""
Database Schemas for HealthLab App

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime


class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    role: Literal["user", "doctor", "admin"] = Field("user")
    pin: Optional[str] = Field(None, description="4-digit report access PIN")
    is_active: bool = True


class Test(BaseModel):
    name: str
    code: str = Field(..., description="Short code e.g., CBC, LFT")
    category: str = Field("General")
    price: float = Field(..., ge=0)
    description: Optional[str] = None
    preparation: Optional[str] = Field(None, description="Fasting etc.")


class Booking(BaseModel):
    user_id: str
    test_code: str
    scheduled_at: datetime
    status: Literal["booked", "in_progress", "completed", "cancelled"] = "booked"
    address: Optional[str] = None
    payment_status: Literal["pending", "paid", "refunded"] = "pending"
    notes: Optional[str] = None
    promo_code: Optional[str] = None
    discount_applied: Optional[float] = 0


class Report(BaseModel):
    booking_id: str
    test_code: str
    url: Optional[str] = Field(None, description="PDF or external URL")
    summary: Optional[str] = None
    values: Optional[dict] = None


class Promo(BaseModel):
    code: str
    type: Literal["percent", "flat"] = "percent"
    value: float = Field(..., ge=0)
    active: bool = True
    note: Optional[str] = None


class Message(BaseModel):
    user_id: str
    role: Literal["user", "assistant"]
    text: str
    context: Optional[dict] = None


# Optional reference examples (kept for viewer compatibility)
class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
