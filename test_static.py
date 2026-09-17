"""Static file serving tests."""
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


def test_static_file_served():
    r = client.get("/static/robots.txt")
    assert r.status_code == 200, r.text
    assert "User-agent" in r.text


def test_landing_page():
    r = client.get("/")
    assert r.status_code == 200, r.text
    assert "LoadMatch" in r.text
