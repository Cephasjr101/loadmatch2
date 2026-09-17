"""Seed the DB with demo shippers, carriers, loads, and trucks."""
from datetime import datetime, timedelta, timezone

from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password


def run():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        shipper = models.User(
            email="shipper@demo.io", password_hash=hash_password("password123"),
            role=models.UserRole.shipper, company_name="Acme Manufacturing",
        )
        carrier = models.User(
            email="carrier@demo.io", password_hash=hash_password("password123"),
            role=models.UserRole.carrier, company_name="FastHaul Logistics",
        )
        db.add_all([shipper, carrier])
        db.flush()

        now = datetime.now(timezone.utc)
        loads = [
            models.Load(
                shipper_id=shipper.id, origin_city="Chicago, IL",
                origin_lat=41.8781, origin_lon=-87.6298,
                dest_city="Denver, CO", dest_lat=39.7392, dest_lon=-104.9903,
                pickup_at=now + timedelta(days=2),
                weight_kg=18000, equipment_type="dry_van",
                offered_rate_cents=2_400_00,
            ),
            models.Load(
                shipper_id=shipper.id, origin_city="Chicago, IL",
                origin_lat=41.8781, origin_lon=-87.6298,
                dest_city="Dallas, TX", dest_lat=32.7767, dest_lon=-96.7970,
                pickup_at=now + timedelta(days=3),
                weight_kg=9000, equipment_type="reefer",
                offered_rate_cents=2_100_00,
            ),
        ]
        trucks = [
            models.Truck(
                carrier_id=carrier.id, current_city="Milwaukee, WI",
                current_lat=43.0389, current_lon=-87.9065,
                equipment_type="dry_van", capacity_kg=24000,
                available_from=now + timedelta(days=1),
                available_until=now + timedelta(days=5),
            ),
            models.Truck(
                carrier_id=carrier.id, current_city="Indianapolis, IN",
                current_lat=39.7684, current_lon=-86.1581,
                equipment_type="reefer", capacity_kg=20000,
                available_from=now + timedelta(days=1),
                available_until=now + timedelta(days=7),
            ),
        ]
        db.add_all(loads + trucks)
        db.commit()
        print("Seeded: shipper@demo.io / carrier@demo.io (password: password123)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
