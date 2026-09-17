from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum, BigInteger,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    shipper = "shipper"
    carrier = "carrier"


class LoadStatus(str, enum.Enum):
    open = "open"
    assigned = "assigned"
    in_transit = "in_transit"
    delivered = "delivered"
    cancelled = "cancelled"


class TruckStatus(str, enum.Enum):
    available = "available"
    assigned = "assigned"


class OfferStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    company_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    loads = relationship("Load", back_populates="shipper")
    trucks = relationship("Truck", back_populates="carrier")
    offers = relationship("Offer", back_populates="carrier")


class Load(Base):
    __tablename__ = "loads"

    id = Column(Integer, primary_key=True, index=True)
    shipper_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    origin_city = Column(String, nullable=False)
    origin_lat = Column(Float, nullable=False)
    origin_lon = Column(Float, nullable=False)
    dest_city = Column(String, nullable=False)
    dest_lat = Column(Float, nullable=False)
    dest_lon = Column(Float, nullable=False)
    pickup_at = Column(DateTime(timezone=True), nullable=False)
    delivery_deadline = Column(DateTime(timezone=True), nullable=True)
    weight_kg = Column(Float, nullable=False)
    equipment_type = Column(String, nullable=False)  # dry_van, reefer, flatbed, etc.
    offered_rate_cents = Column(BigInteger, nullable=False)
    status = Column(SAEnum(LoadStatus), default=LoadStatus.open, nullable=False)
    assigned_truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    shipper = relationship("User", back_populates="loads")
    offers = relationship("Offer", back_populates="load")


class Truck(Base):
    __tablename__ = "trucks"

    id = Column(Integer, primary_key=True, index=True)
    carrier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    current_city = Column(String, nullable=False)
    current_lat = Column(Float, nullable=False)
    current_lon = Column(Float, nullable=False)
    equipment_type = Column(String, nullable=False)
    capacity_kg = Column(Float, nullable=False)
    available_from = Column(DateTime(timezone=True), nullable=False)
    available_until = Column(DateTime(timezone=True), nullable=False)
    status = Column(SAEnum(TruckStatus), default=TruckStatus.available, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    carrier = relationship("User", back_populates="trucks")
    offers = relationship("Offer", back_populates="truck")


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    load_id = Column(Integer, ForeignKey("loads.id"), nullable=False)
    carrier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    truck_id = Column(Integer, ForeignKey("trucks.id"), nullable=False)
    price_cents = Column(BigInteger, nullable=False)
    note = Column(String, nullable=True)
    status = Column(SAEnum(OfferStatus), default=OfferStatus.pending, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    load = relationship("Load", back_populates="offers")
    carrier = relationship("User", back_populates="offers")
    truck = relationship("Truck", back_populates="offers")
