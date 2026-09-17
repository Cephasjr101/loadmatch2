import os
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import secrets

from  database import Base, engine, 
import models, schemas
from  security import (
    create_access_token, decode_access_token, hash_password, verify_password,
)
from  firebase_auth import verify_firebase_token
from  matching import find_matches

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LoadMatch API", version="0.1.0")
bearer = HTTPBearer(auto_error=False)

# ---------------- static files ----------------
# Serve a static dir (landing page, frontend build, assets).
# Override the location with STATIC_DIR; auto-created so startup never fails.
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.getcwd(), "static"))
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def landing():
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "LoadMatch API", "docs": "/docs"}


# ---------------- auth helpers ----------------
def get_or_create_firebase_user(db: Session, claims: dict) -> models.User:
    """Map a verified Firebase identity onto a local User row.

    Role and company name can be seeded via Firebase custom claims
    (settable from a backend or Cloud Function) or default gracefully.
    """
    email = claims.get("email")
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firebase token has no email")
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return user
    try:
        role = models.UserRole(claims.get("role", models.UserRole.shipper.value))
    except ValueError:
        role = models.UserRole.shipper
    user = models.User(
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)),  # unusable locally
        role=role,
        company_name=claims.get("company_name") or email.split("@")[0],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = creds.credentials

    # 1) Firebase ID token (if Firebase is configured)
    fb_claims = verify_firebase_token(token)
    if fb_claims:
        return get_or_create_firebase_user(db, fb_claims)

    # 2) Local JWT fallback
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(models.User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


def require_role(user: models.User, role: models.UserRole):
    if user.role != role:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {role} role")


# ---------------- auth ----------------
@app.post("/auth/register", response_model=schemas.UserOut, status_code=201)
def register(data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(409, "Email already registered")
    user = models.User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        company_name=data.company_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad credentials")
    return schemas.TokenResponse(access_token=create_access_token(user.id, user.role.value))


@app.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


# ---------------- loads ----------------
@app.post("/loads", response_model=schemas.LoadOut, status_code=201)
def create_load(
    data: schemas.LoadCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.shipper)
    load = models.Load(shipper_id=user.id, **data.model_dump())
    db.add(load)
    db.commit()
    db.refresh(load)
    return load


@app.get("/loads", response_model=List[schemas.LoadOut])
def list_loads(
    status_filter: Optional[models.LoadStatus] = None,
    equipment_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Load)
    if status_filter:
        q = q.filter(models.Load.status == status_filter)
    if equipment_type:
        q = q.filter(models.Load.equipment_type == equipment_type)
    return q.order_by(models.Load.pickup_at).all()


@app.get("/loads/{load_id}", response_model=schemas.LoadOut)
def get_load(load_id: int, db: Session = Depends(get_db)):
    load = db.get(models.Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    return load


@app.patch("/loads/{load_id}", response_model=schemas.LoadOut)
def update_load(
    load_id: int,
    data: schemas.LoadUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.shipper)
    load = db.get(models.Load, load_id)
    if not load or load.shipper_id != user.id:
        raise HTTPException(404, "Load not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(load, field, value)
    db.commit()
    db.refresh(load)
    return load


@app.delete("/loads/{load_id}", status_code=204)
def delete_load(
    load_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.shipper)
    load = db.get(models.Load, load_id)
    if not load or load.shipper_id != user.id:
        raise HTTPException(404, "Load not found")
    if load.status != models.LoadStatus.open:
        raise HTTPException(409, "Only open loads can be deleted")
    db.delete(load)
    db.commit()


# ---------------- trucks ----------------
@app.post("/trucks", response_model=schemas.TruckOut, status_code=201)
def create_truck(
    data: schemas.TruckCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.carrier)
    truck = models.Truck(carrier_id=user.id, **data.model_dump())
    db.add(truck)
    db.commit()
    db.refresh(truck)
    return truck


@app.get("/trucks", response_model=List[schemas.TruckOut])
def list_trucks(
    equipment_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Truck)
    if equipment_type:
        q = q.filter(models.Truck.equipment_type == equipment_type)
    return q.all()


@app.get("/trucks/{truck_id}", response_model=schemas.TruckOut)
def get_truck(truck_id: int, db: Session = Depends(get_db)):
    truck = db.get(models.Truck, truck_id)
    if not truck:
        raise HTTPException(404, "Truck not found")
    return truck


@app.patch("/trucks/{truck_id}", response_model=schemas.TruckOut)
def update_truck(
    truck_id: int,
    data: schemas.TruckUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.carrier)
    truck = db.get(models.Truck, truck_id)
    if not truck or truck.carrier_id != user.id:
        raise HTTPException(404, "Truck not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(truck, field, value)
    db.commit()
    db.refresh(truck)
    return truck


# ---------------- matching ----------------
@app.get("/loads/{load_id}/matches", response_model=List[schemas.MatchOut])
def get_matches(load_id: int, db: Session = Depends(get_db)):
    load = db.get(models.Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    trucks = db.query(models.Truck).all()
    return find_matches(load, trucks)


# ---------------- offers ----------------
@app.post("/loads/{load_id}/offers", response_model=schemas.OfferOut, status_code=201)
def create_offer(
    load_id: int,
    data: schemas.OfferCreate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.carrier)
    load = db.get(models.Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    if load.status != models.LoadStatus.open:
        raise HTTPException(409, "Load is not open for offers")
    truck = db.get(models.Truck, data.truck_id)
    if not truck or truck.carrier_id != user.id:
        raise HTTPException(404, "Truck not found")
    if truck.status != models.TruckStatus.available:
        raise HTTPException(409, "Truck is not available")
    offer = models.Offer(
        load_id=load.id, carrier_id=user.id,
        truck_id=truck.id, price_cents=data.price_cents, note=data.note,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


@app.get("/loads/{load_id}/offers", response_model=List[schemas.OfferOut])
def list_offers(
    load_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    load = db.get(models.Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    if user.role == models.UserRole.shipper and load.shipper_id != user.id:
        raise HTTPException(403, "Not your load")
    return db.query(models.Offer).filter(models.Offer.load_id == load_id).all()


@app.post("/offers/{offer_id}/accept", response_model=schemas.LoadOut)
def accept_offer(
    offer_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.shipper)
    offer = db.get(models.Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    load = offer.load
    if load.shipper_id != user.id:
        raise HTTPException(403, "Not your load")
    if load.status != models.LoadStatus.open:
        raise HTTPException(409, "Load already assigned")

    offer.status = models.OfferStatus.accepted
    load.status = models.LoadStatus.assigned
    load.assigned_truck_id = offer.truck_id
    offer.truck.status = models.TruckStatus.assigned

    for other in load.offers:
        if other.id != offer.id and other.status == models.OfferStatus.pending:
            other.status = models.OfferStatus.rejected

    db.commit()
    db.refresh(load)
    return load


@app.post("/offers/{offer_id}/reject", response_model=schemas.OfferOut)
def reject_offer(
    offer_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_role(user, models.UserRole.shipper)
    offer = db.get(models.Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    if offer.load.shipper_id != user.id:
        raise HTTPException(403, "Not your load")
    if offer.status != models.OfferStatus.pending:
        raise HTTPException(409, "Offer already resolved")
    offer.status = models.OfferStatus.rejected
    db.commit()
    db.refresh(offer)
    return offer


# ---------------- lifecycle ----------------
@app.post("/loads/{load_id}/pickup", response_model=schemas.LoadOut)
def mark_pickup(load_id: int, db: Session = Depends(get_db)):
    load = db.get(models.Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    if load.status != models.LoadStatus.assigned:
        raise HTTPException(409, "Load must be assigned before pickup")
    load.status = models.LoadStatus.in_transit
    db.commit()
    db.refresh(load)
    return load


@app.post("/loads/{load_id}/deliver", response_model=schemas.LoadOut)
def mark_delivered(load_id: int, db: Session = Depends(get_db)):
    load = db.get(models.Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    if load.status != models.LoadStatus.in_transit:
        raise HTTPException(409, "Load must be in transit before delivery")
    load.status = models.LoadStatus.delivered
    if load.assigned_truck_id:
        truck = db.get(models.Truck, load.assigned_truck_id)
        if truck:
            truck.status = models.TruckStatus.available
            truck.current_city = load.dest_city
            truck.current_lat = load.dest_lat
            truck.current_lon = load.dest_lon
    db.commit()
    db.refresh(load)
    return load


@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z",
        "static_dir": STATIC_DIR,
        "static_serving": os.path.isdir(STATIC_DIR),
    }
