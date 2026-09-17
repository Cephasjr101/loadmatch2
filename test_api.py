import os
os.environ["LOADMATCH_SECRET"] = "test-secret"

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine
from seed import run as seed_run

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    seed_run()
    yield
    Base.metadata.drop_all(bind=engine)


def login(email):
    r = client.post("/auth/login", data={"username": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health():
    assert client.get("/health").status_code == 200


def test_register_and_login():
    r = client.post("/auth/register", json={
        "email": "new@demo.io", "password": "supersecret1",
        "role": "carrier", "company_name": "NewCo",
    })
    assert r.status_code == 201, r.text
    assert login("new@demo.io")


def test_shipper_cannot_create_truck():
    h = login("shipper@demo.io")
    r = client.post("/trucks", headers=h, json={
        "current_city": "A", "current_lat": 40, "current_lon": -87,
        "equipment_type": "dry_van", "capacity_kg": 1000,
        "available_from": "2030-01-01T00:00:00Z", "available_until": "2030-01-02T00:00:00Z",
    })
    assert r.status_code == 403


def test_matching_returns_compatible_trucks():
    r = client.get("/loads/1/matches")
    assert r.status_code == 200, r.text
    matches = r.json()
    # Truck 1 is dry_van near Chicago -> should match; reefer truck should not.
    assert all(m["truck"]["equipment_type"] == "dry_van" for m in matches)
    assert len(matches) == 1


def test_full_offer_to_delivery_flow():
    shipper = login("shipper@demo.io")
    carrier = login("carrier@demo.io")

    # Carrier bids on load 1 with truck 1
    r = client.post("/loads/1/offers", headers=carrier, json={
        "truck_id": 1, "price_cents": 2300_00, "note": "Can pick up early.",
    })
    assert r.status_code == 201, r.text
    offer_id = r.json()["id"]

    # Shipper sees the offer and accepts
    r = client.get("/loads/1/offers", headers=shipper)
    assert len(r.json()) == 1
    r = client.post(f"/offers/{offer_id}/accept", headers=shipper)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "assigned"
    assert r.json()["assigned_truck_id"] == 1

    # Carrier cannot bid again on assigned load
    r = client.post("/loads/1/offers", headers=carrier, json={"truck_id": 1, "price_cents": 100})
    assert r.status_code == 409

    # Lifecycle: pickup -> deliver
    assert client.post("/loads/1/pickup").json()["status"] == "in_transit"
    r = client.post("/loads/1/deliver")
    assert r.json()["status"] == "delivered"

    # Truck is freed and relocated to destination
    truck = client.get("/trucks/1").json()
    assert truck["status"] == "available"
    assert truck["current_city"] == "Denver, CO"


def test_carrier_cannot_accept_own_offer():
    carrier = login("carrier@demo.io")
    r = client.post("/offers/1/accept", headers=carrier)
    assert r.status_code in (403, 404)
