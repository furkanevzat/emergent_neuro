from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    CLIENT = "client"
    STAFF = "staff"

class OrderStatus(str, Enum):
    REVIEWING = "reviewing"
    QUOTED = "quoted"
    PRODUCTION = "production"
    SHIPPED = "shipped"
    DELIVERED = "delivered"

# User Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: UserRole = UserRole.CLIENT
    created_at: datetime

# Order Models
class OrderSpecs(BaseModel):
    substrate: Optional[str] = "FR-4 Standard (TG150)"
    layers: Optional[int] = 2
    thickness: Optional[str] = "1.6 mm"
    quantity: Optional[int] = 10
    finish: Optional[str] = "HASL (Lead-Free)"
    mask_color: Optional[str] = "Green"
    silkscreen: Optional[str] = "White"
    copper_weight: Optional[str] = "1oz"

class OrderCreate(BaseModel):
    specs: OrderSpecs

class Order(BaseModel):
    order_id: str
    user_id: str
    status: OrderStatus
    gerber_file: Optional[str] = None
    specs: OrderSpecs
    price: float = 0.00
    submitted_at: datetime
    updated_at: datetime

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    price: Optional[float] = None
