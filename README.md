# LoadMatch — Backend MVP

Freight load-matching platform. Shippers post loads, carriers post truck
capacity, a matching engine pairs them, and offers flow through acceptance
to delivery.

## Stack
- **FastAPI** (Python 3.10+) — API layer
- **SQLAlchemy 2.0 + SQLite** — ORM & dev database (swap URL in `app/database.py` for Postgres)
- **Stdlib-only security** — PBKDF2 password hashing + HS256 JWT (no `passlib`/`python-jose` dependency headaches)

## Quick start

```bash
pip install -r requirements.txt
python seed.py          # creates fresh DB with demo data
uvicorn app.main:app --reload
```

Demo accounts (password `password123`):
- `shipper@demo.io` — Acme Manufacturing
- `carrier@demo.io` — FastHaul Logistics

Interactive docs: http://127.0.0.1:8000/docs

## API overview

| Method | Endpoint | Who | Description |
|---|---|---|---|
| POST | `/auth/register` | public | Create shipper/carrier account |
| POST | `/auth/login` | public | OAuth2 form login → JWT |
| GET | `/me` | any | Current user profile |
| POST | `/loads` | shipper | Post a load |
| GET | `/loads` | public | List/filter loads by status & equipment |
| GET/PATCH/DELETE | `/loads/{id}` | shipper (own) | Manage load |
| POST | `/trucks` | carrier | Register truck capacity |
| GET | `/trucks` | public | List/filter trucks |
| GET/PATCH | `/trucks/{id}` | carrier (own) | Manage truck |
| GET | `/loads/{id}/matches` | public | Ranked compatible trucks |
| POST | `/loads/{id}/offers` | carrier | Bid on a load |
| GET | `/loads/{id}/offers` | shipper (own) / carrier | List offers |
| POST | `/offers/{id}/accept` | shipper | Accept → load assigned, other offers auto-rejected, truck booked |
| POST | `/offers/{id}/reject` | shipper | Reject an offer |
| POST | `/loads/{id}/pickup` | system | assigned → in_transit |
| POST | `/loads/{id}/deliver` | system | in_transit → delivered, truck freed & relocated |

## Matching engine (`app/matching.py`)

Hard filters: equipment type, weight capacity, availability window covering
pickup time, status = available, truck within 500 km of origin.

Scoring (max ~120):
- −up to 60 pts by distance to origin (linear)
- +10 pts if truck is available exactly on pickup day
- +10 pts for tight capacity fit (efficient utilization)

## Status machines

- **Load:** open → assigned → in_transit → delivered (or cancelled)
- **Truck:** available ⇄ assigned (freed on delivery, relocated to destination)
- **Offer:** pending → accepted | rejected | withdrawn

Accepting an offer atomically: marks offer accepted, rejects all other
pending offers, books the truck.

## Firebase Auth (optional)

The API accepts **Firebase ID tokens** as Bearer tokens in addition to the
built-in local JWTs. Resolution order per request:

1. Try to verify the token as a Firebase ID token (only if configured).
2. Fall back to the local JWT.

When a Firebase token verifies for an email with no local user, a local
`User` row is auto-provisioned:

- `role` comes from a Firebase **custom claim** (`role: "shipper" | "carrier"`)
  or defaults to `shipper` — set claims via the Admin SDK or a Cloud Function
- `company_name` from the `company_name` claim or the email prefix
- an unusable random local password (Firebase users never log in locally)

### Setup

```bash
pip install firebase-admin
export FIREBASE_SERVICE_ACCOUNT=/path/to/serviceAccount.json
# or rely on GOOGLE_APPLICATION_CREDENTIALS
```

If `firebase-admin` is missing or credentials are absent/invalid, the app
logs a note and continues with local JWT only — startup never fails.

Frontend flow stays standard Firebase client-side: sign in with the
Firebase SDK, send `Authorization: Bearer <ID token>`.

## Static files

Anything in the `static/` directory is served at `/static/*` (mounted via
FastAPI's `StaticFiles`). The app also serves `static/index.html` at `/`
— drop a frontend build (or this placeholder) there.

- Default location: `./static` (relative to where you launch uvicorn)
- Override with the `STATIC_DIR` env var
- The directory is auto-created at startup if missing
- `/health` reports whether static serving is active and from where

## Tests

```bash
pytest tests/ -v
```

## MVP limitations / next steps
- No payments, documents (BOL/POD), or notifications yet
- Matching is synchronous, single-leg; no multi-stop or backhaul optimization
- SQLite single-writer; move to Postgres for production
- Add rate limiting, refresh tokens, email verification (Firebase handles token refresh client-side when enabled)
