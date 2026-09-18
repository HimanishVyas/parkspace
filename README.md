# ParkSpace

A marketplace where people and organisations list unused parking spaces, and
renters discover, book and pay for them by location, availability and duration.

This is the V1 pilot build: a modular monolith (FastAPI + PostgreSQL) behind a
responsive React app, sized for a single-city launch.

---

## Quick start

### With Docker (nothing else installed)

```bash
cp .env.example .env          # edit JWT_SECRET before any real deployment
docker-compose up --build
```

Then open:

| What            | Where                          |
| --------------- | ------------------------------ |
| Web app         | http://localhost:18080         |
| API             | http://localhost:18000/api/v1  |
| API docs        | http://localhost:18000/docs    |
| PostgreSQL      | localhost:55432                |

The API container waits for the database, applies migrations and seeds the admin
account before starting, so a clean `docker-compose up` gives a working system.

Load some sample listings:

```bash
docker-compose exec api python -m app.cli demo
```

That creates four listings in Ahmedabad plus two sign-ins:

| Role     | Email                  | Password        |
| -------- | ---------------------- | --------------- |
| Admin    | `admin@example.com`    | `admin12345`    |
| Provider | `provider@example.com` | `provider12345` |
| Renter   | `renter@example.com`   | `renter12345`   |

> Change `SEED_ADMIN_PASSWORD` before deploying anywhere real — the CLI refuses
> to seed the default password when `ENVIRONMENT=production`.

### Running it locally

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

docker-compose up -d db redis          # or point DATABASE_URL at your own
alembic upgrade head
python -m app.cli seed
python -m app.cli demo                 # optional sample data

uvicorn app.main:app --reload --port 18000
```

Frontend (Node 22):

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173, proxies /api
```

### Tests

```bash
cd backend && pytest
```

The suite runs against a real PostgreSQL database (`parking_test`, created
automatically). That is deliberate: the booking guarantees under test are
enforced by PostgreSQL itself, so an in-memory substitute would be testing
something else.

---

## How it is put together

```
frontend/          React + TypeScript (Vite), served by nginx in Docker
backend/
  app/
    core/          config, database, auth, errors, rate limiting, scheduler
    db/            declarative base, model registry
    modules/       one package per domain area
      auth  users  vehicles  providers  parking  availability
      bookings  payments  notifications  reviews  reports  admin
      settings  storage  audit
  alembic/         migrations
```

Each module owns its models, schemas, service and router. Routers are wired
together in `app/main.py` and nowhere else, so a module can be lifted out into
its own service later without unpicking imports. There are no microservices in
V1 by design.

### The parts worth knowing about

**Double-booking protection** — `backend/app/modules/bookings/service.py`

Three layers, of which only the last is authoritative:

1. Search hides spaces that are already taken (a convenience).
2. `assert_available` re-checks rules, blocks and bookings inside the booking
   transaction and picks a free slot.
3. A PostgreSQL **exclusion constraint** on `bookings` rejects an overlapping
   row at COMMIT:

   ```sql
   EXCLUDE USING gist (parking_space_id WITH =, slot_index WITH =, period WITH &&)
     WHERE (status IN ('PENDING_PAYMENT','PENDING_APPROVAL','CONFIRMED','ACTIVE','DISPUTED'))
   ```

   `period` is a generated column (`tstzrange(start_at, end_at, '[)')`), so it
   can never disagree with the timestamps beside it. Two requests that pass step
   2 at the same instant cannot both commit; the loser retries against a fresh
   read and gives up with `409 ALREADY_BOOKED` when the space is genuinely full.

   `tests/test_booking_conflicts.py` fires ten concurrent bookings at one slot
   and asserts exactly one wins.

**Availability semantics** — `backend/app/modules/availability/service.py`

Providers describe availability as recurring weekly windows (minutes from local
midnight, so a window can end at exactly midnight) plus explicit blocks.

* `HOURLY` bookings must fall entirely inside those windows, to the minute.
* `DAILY` / `MONTHLY` bookings require every date they touch to be an operating
  day, and then reserve the whole contiguous period — which is what renting a
  spot by the day or month means.

A provider who wants to sell monthly parking on a weekday-only space therefore
has to open the weekend too. That is the honest answer: a renter paying for
October should not find the gate shut on a Sunday.

**Money** — `backend/app/modules/bookings/pricing.py`

```
base parking price   = unit price x quantity
+ platform fee       = base x renter_fee_percent
+ tax                = platform fee x tax_percent
= what the renter pays

commission           = base x commission_percent  (or the society's revenue share)
provider earning     = base - commission
```

Every percentage comes from `platform_settings` in the database and is editable
from **Admin → Settings**. None are hard-coded. Amounts are `Decimal`, rounded
once per line, and frozen onto the booking at creation — so changing the
commission never rewrites what a provider was already told they earned.

**Payments** — `backend/app/modules/payments/gateway.py`

Booking logic never talks to a gateway. Everything goes through four operations:
`create_payment`, `verify_payment`, `refund_payment`, `parse_webhook`. Two
implementations ship: `MockGateway` (exercises the whole flow offline, used by
the tests and the sandbox) and `RazorpayGateway`. Webhook signatures are
verified before the body is read, and events are de-duplicated by id so a replay
is a no-op. No card number, CVV or cardholder data ever reaches this codebase.

**Location** — `backend/app/modules/parking/location.py`

No PostGIS in V1. A lat/lon bounding box prefilters using a plain B-tree index,
then an exact haversine distance runs in SQL. Everything geographic lives in
that one module, so swapping in PostGIS later touches nothing else.

**Booking lifecycle** — `backend/app/modules/bookings/maintenance.py`

Unpaid holds expire, confirmed bookings activate and then complete, and
reminders go out — all on a timer, from `app/core/scheduler.py`. Every pass is
idempotent, so a missed tick changes nothing. Moving this to a dedicated worker
later means calling `run_once` from there instead.

---

## Configuration

Every setting is an environment variable, documented in
[`.env.example`](.env.example). Nothing secret is committed; `.env` is
git-ignored.

| Variable | Default | What it does |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development`, `test` or `production` |
| `DEBUG` | `false` | Verbose logging |
| `API_PREFIX` | `/api/v1` | Version prefix for every route |
| `FRONTEND_URL` | `http://localhost:18080` | Used in emails and redirects |
| `CORS_ORIGINS` | localhost dev origins | JSON array of allowed browser origins |
| `TIMEZONE` | `Asia/Kolkata` | Availability rules are interpreted here |
| `DATABASE_URL` | local Postgres | `postgresql+asyncpg://…` |
| `REDIS_URL` | *(empty)* | Rate limiting; falls back to in-process |
| `JWT_SECRET` | `change-me-in-env` | **Set this.** `openssl rand -hex 32` |
| `ACCESS_TOKEN_MINUTES` | `60` | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | `30` | Refresh token lifetime |
| `STORAGE_BACKEND` | `local` | Where uploads go |
| `MEDIA_ROOT` / `MEDIA_URL` | `media` / `/media` | Upload path and public prefix |
| `MAX_UPLOAD_BYTES` | `5242880` | Upload size cap (5 MB) |
| `PAYMENT_GATEWAY` | `mock` | `mock` or `razorpay` |
| `RAZORPAY_KEY_ID` / `_KEY_SECRET` / `_WEBHOOK_SECRET` | *(empty)* | Razorpay credentials |
| `MOCK_GATEWAY_SECRET` | `mock-gateway-secret` | Signs simulated sandbox payments |
| `EMAIL_BACKEND` | `console` | `console` or `smtp` |
| `SMTP_*` | localhost:1025 | SMTP connection details |
| `GEOCODER_URL` | Nominatim | Address lookup; empty disables it |
| `MAINTENANCE_ENABLED` | `true` | Runs the booking lifecycle loop |
| `MAINTENANCE_INTERVAL_SECONDS` | `60` | How often it ticks |
| `RATE_LIMIT_ENABLED` | `true` | Rate limits on sensitive endpoints |
| `SEED_ADMIN_EMAIL` / `_PASSWORD` | `admin@example.com` / `admin12345` | Bootstrap admin |

Business rules — commission, fees, cancellation policy, hold durations, booking
limits — are **not** environment variables. They live in the `platform_settings`
table and are edited from the admin dashboard at runtime.

---

## API

Interactive docs are served at `/docs` (Swagger UI) and `/redoc`. The OpenAPI
schema is at `/api/v1/openapi.json`.

Every error uses one envelope, so clients branch on `code`, never on prose:

```json
{ "error": { "code": "ALREADY_BOOKED", "message": "…", "details": null } }
```

Main routes:

```
POST   /api/v1/auth/register          POST   /api/v1/auth/login
POST   /api/v1/auth/refresh           POST   /api/v1/auth/logout-all
GET    /api/v1/me                     PATCH  /api/v1/me

GET    /api/v1/vehicles               POST   /api/v1/vehicles

GET    /api/v1/parking                search: location, radius, dates, filters
POST   /api/v1/parking                GET    /api/v1/parking/{id}
GET    /api/v1/parking/mine           PATCH  /api/v1/parking/{id}
PUT    /api/v1/parking/{id}/availability
POST   /api/v1/parking/{id}/blocks    GET    /api/v1/parking/{id}/calendar
POST   /api/v1/parking/{id}/photos    POST   /api/v1/parking/{id}/publish

POST   /api/v1/bookings/quote         price and availability, reserves nothing
POST   /api/v1/bookings               GET    /api/v1/bookings?role=renter|provider
GET    /api/v1/bookings/{id}/confirmation
POST   /api/v1/bookings/{id}/cancel   POST   /api/v1/bookings/{id}/approve

POST   /api/v1/payments/create        POST   /api/v1/payments/confirm
POST   /api/v1/payments/webhook       unauthenticated; the signature is the auth

GET    /api/v1/providers/dashboard    GET    /api/v1/providers/earnings
POST   /api/v1/reviews                POST   /api/v1/reports

GET    /api/v1/admin/dashboard        GET    /api/v1/admin/users
GET    /api/v1/admin/listings         GET    /api/v1/admin/bookings
GET    /api/v1/admin/reports          GET/PATCH /api/v1/admin/settings
POST   /api/v1/admin/payouts          GET    /api/v1/admin/audit-logs
```

---

## Operations

```bash
python -m app.cli seed          # create the bootstrap admin (safe to re-run)
python -m app.cli demo          # sample listings and accounts (never in production)
python -m app.cli maintenance   # run one booking-lifecycle pass by hand

alembic upgrade head            # apply migrations
alembic revision --autogenerate -m "what changed"
alembic check                   # models and migrations still agree?
```

### Security posture

Passwords are bcrypt-hashed. JWT access and refresh tokens carry a
`token_version`, so suspending an account or changing a password invalidates
every live session immediately. Role and ownership checks run server-side on
every request — the frontend is never trusted. Uploads are validated by magic
bytes, not by filename or content type. Sensitive endpoints are rate limited.
Admin actions that change users, listings, bookings, payouts or settings write
an audit entry.

### Deploying

Before going live: set `JWT_SECRET` and `SEED_ADMIN_PASSWORD`, set
`ENVIRONMENT=production` and `DEBUG=false`, point `PAYMENT_GATEWAY` at Razorpay
with real credentials and a webhook secret, set `EMAIL_BACKEND=smtp`, set
`CORS_ORIGINS` to the real frontend origin, and put the whole thing behind TLS.
For more than one API instance, set `REDIS_URL` so rate limiting is shared, and
run the maintenance loop in exactly one place (`MAINTENANCE_ENABLED=false`
everywhere else, plus a cron calling `python -m app.cli maintenance`).

---

## Scope

V1 deliberately does not include smart locks, IoT sensors, RFID, ANPR, gate
integration, EV charging, insurance, wallets, loyalty or referral programmes,
subscriptions, native apps, or multi-country and multi-currency support. The
architecture leaves room for them; none of them block proving the marketplace
works.

The QR code on a booking confirmation is a digital identifier only. It opens no
barrier — a guard scans it to look the booking up.

The platform is not an insurer. Issue reports are recorded and reviewed;
liability for damage is governed by the terms and the agreement between the
parties.
