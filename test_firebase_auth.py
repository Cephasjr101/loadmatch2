"""Firebase auth path tests — no real Firebase credentials required.

We monkeypatch `app.main.verify_firebase_token` to simulate a verified
Firebase ID token, exercising the local user-provisioning logic.
"""
import os
os.environ["LOADMATCH_SECRET"] = "test-secret"

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


def test_firebase_token_provisions_new_user(monkeypatch):
    claims = {
        "email": "fb-shipper@demo.io",
        "role": "shipper",
        "company_name": "Firebase Shipper Co",
    }
    monkeypatch.setattr("app.main.verify_firebase_token", lambda t: claims if t == "fb-token" else None)

    r = client.get("/me", headers={"Authorization": "Bearer fb-token"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "fb-shipper@demo.io"
    assert body["role"] == "shipper"
    assert body["company_name"] == "Firebase Shipper Co"

    # Second call returns the SAME local user (no duplicates)
    r2 = client.get("/me", headers={"Authorization": "Bearer fb-token"})
    assert r2.json()["id"] == body["id"]


def test_firebase_custom_claim_role(monkeypatch):
    monkeypatch.setattr(
        "app.main.verify_firebase_token",
        lambda t: {"email": "fb-carrier@demo.io", "role": "carrier"} if t == "fb-carrier-token" else None,
    )
    r = client.get("/me", headers={"Authorization": "Bearer fb-carrier-token"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "carrier"


def test_invalid_token_still_rejected(monkeypatch):
    monkeypatch.setattr("app.main.verify_firebase_token", lambda t: None)
    r = client.get("/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
