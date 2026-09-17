from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import UserRole, LoadStatus, TruckStatus, OfferStatus


# ---------- Auth ----------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole
    company_name: str = Field(min_length=1, max_length=120)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: UserRole
    company_name: str


# ---------- Loads ----------
class LoadCreate(BaseModel):
    origin_city: str
    origin_lat: float = Field(ge=-90, le=90)
    origin_lon: float = Field(ge=-180, le=180)
    dest_city: str
    dest_lat: float = Field(ge=-90, le=90)
    dest_lon: float = Field(ge=-180, le=180)
    pickup_at: datetime
    delivery_deadline: Optional[datetime] = None
    weight_kg: float = Field(gt=0)
    equipment_type: str = Field(min_length=1, max_length=40)
    offered_rate_cents: int = Field(ge=0)


class LoadUpdate(BaseModel):
    pickup_at: Optional[datetime] = None
    delivery_deadline: Optional[datetime] = None
    weight_kg: Optional[float] = Field(default=None, gt=0)
    equipment_type: Optional[str] = None
    offered_rate_cents: Optional[int] = Field(default=None, ge=0)
    status: Optional[LoadStatus] = None


class LoadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shipper_id: int
    origin_city: str
    dest_city: str
    pickup_at: datetime
    weight_kg: float
    equipment_type: str
    offered_rate_cents: int
    status: LoadStatus
    assigned_truck_id: Optional[int]


# ---------- Trucks ----------
class TruckCreate(BaseModel):
    current_city: str
    current_lat: float = Field(ge=-90, le=90)
    current_lon: float = Field(ge=-180, le=180)
    equipment_type: str = Field(min_length=1, max_length=40)
    capacity_kg: float = Field(gt=0)
    available_from: datetime
    available_until: datetime


class TruckUpdate(BaseModel):
    current_city: Optional[str] = None
    current_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    current_lon: Optional[float] = Field(default=None, ge=-180, le=180)
    equipment_type: Optional[str] = None
    capacity_kg: Optional[float] = Field(default=None, gt=0)
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    status: Optional[TruckStatus] = None


class TruckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    carrier_id: int
    current_city: str
    equipment_type: str
    capacity_kg: float
    available_from: datetime
    available_until: datetime
    status: TruckStatus


# ---------- Offers ----------
class OfferCreate(BaseModel):
    truck_id: int
    price_cents: int = Field(ge=0)
    note: Optional[str] = Field(default=None, max_length=500)


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    load_id: int
    carrier_id: int
    truck_id: int
    price_cents: int
    note: Optional[str]
    status: OfferStatus


# ---------- Matching ----------
class MatchOut(BaseModel):
    truck: TruckOut
    score: float
    distance_to_origin_km: float
    reasons: List[str]
