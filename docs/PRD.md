# Parking Marketplace — V1 Product Requirements Document

**Version:** 1.0
**Status:** MVP / V1
**Product Type:** Peer-to-peer + Society Parking Marketplace
**Primary Market:** India
**Target Launch:** Single-city pilot first

---

# 1. Product Vision

Build a marketplace that allows people and organizations with unused parking spaces to rent them to people who need parking.

The platform connects:

**Parking Providers → Parking Spaces → Renters**

The platform should support both:

1. **Individual parking providers** — e.g. owners of independent/tenement houses with unused parking.
2. **Societies / organizations** — where the society can make parking spaces available for paid parking through the platform.

The V1 objective is simple:

> A provider can list a parking space, control its availability and price, and a renter can discover, book, and pay for that parking space.

---

# 2. Core Business Model

The platform does NOT own parking spaces.

It acts as a marketplace and booking platform.

## Individual Provider

Example:

A house owner has one parking space but does not own a car.

They list:

* Location
* Parking type
* Vehicle type
* Price
* Available time
* Available dates
* Photos
* Instructions

A renter books the space.

The platform takes a commission from the transaction.

---

## Society Provider

A society may have:

* Open parking spaces
* Visitor parking
* Additional unused parking capacity
* Other parking areas that the society is legally/contractually permitted to rent

The society can enter into an agreement with the platform and make those spaces available.

The society receives its agreed share of revenue.

The platform handles:

* Listing
* Availability
* Booking
* Payment
* Booking records
* Basic parking management

---

# 3. V1 Goals

The V1 MUST allow the following complete flow:

## Provider Flow

Register → Create parking listing → Set price → Set availability → Publish listing → Receive booking → View booking → Manage availability → View earnings

## Renter Flow

Register → Search parking → View listing → Select date/time/duration → Book → Pay → Receive booking confirmation → View active booking

## Admin Flow

Login → Manage users → Manage parking listings → Manage bookings → Manage providers → View transactions → Handle basic disputes/reports

---

# 4. V1 User Roles

There are three primary roles.

## 4.1 Renter

A person who wants to rent a parking space.

Capabilities:

* Register/login
* Search parking
* View parking details
* Filter parking
* Book parking
* Pay
* View bookings
* Cancel booking according to rules
* View booking history
* Manage profile
* Register vehicle
* Report an issue

---

## 4.2 Parking Provider

A person or organization providing parking.

Capabilities:

* Register/login
* Create parking listing
* Upload parking photos
* Set price
* Set availability
* Block dates/times
* Accept/reject bookings if manual approval is enabled
* View bookings
* View earnings
* Manage parking listing
* Pause/unpublish listing

---

## 4.3 Admin

Platform administrator.

Capabilities:

* Manage users
* Manage providers
* Manage listings
* Approve/reject listings
* Manage bookings
* View payments
* View platform revenue
* Handle reports
* Suspend users/listings
* View basic analytics

---

# 5. Parking Listing

Every parking space should have a listing.

## Required Fields

### Basic Information

* Listing title
* Description
* Parking provider
* Parking type
* Vehicle type supported
* Address
* Latitude
* Longitude
* Photos

### Parking Type

V1 should support:

* Open parking
* Covered parking
* Basement parking
* Garage parking

### Vehicle Type

V1:

* Bike
* Car
* SUV

The architecture should allow adding more vehicle types later.

---

# 6. Location

Location is one of the most important parts of the application.

The renter should be able to:

1. Search by location
2. Search by address
3. Search around current location
4. View parking spaces on a map
5. View approximate distance

Each listing should store:

* Address
* Latitude
* Longitude

The backend should support geographical/radius-based searches.

For V1, PostgreSQL + PostGIS may be used if appropriate.

Do NOT over-engineer the location system.

---

# 7. Parking Availability

Providers must control when their parking space is available.

Example:

Parking Space:

**Monday–Friday**

08:00 AM → 08:00 PM

Or:

**Available for the entire month**

The provider should also be able to manually block dates/times.

Example:

> Parking normally available every day, but unavailable from 15 September to 20 September.

---

# 8. Availability Model

The system should support:

## Hourly

Example:

10:00 AM → 1:00 PM

## Daily

Example:

18 September → 19 September

## Monthly

Example:

1 October → 31 October

The architecture should be designed so additional duration types can be added later.

---

# 9. Provider Availability Management

Provider dashboard must contain a calendar.

Example:

```text
September

Mon Tue Wed Thu Fri Sat Sun

 1   2   3   4   5   6   7
 ✓   ✓   ✓   X   ✓   ✓   ✓

 8   9  10  11  12  13  14
 ✓   ✓   ✓   ✓   X   ✓   ✓
```

Provider can:

* Enable availability
* Disable availability
* Block dates
* Block time ranges
* View existing bookings

Existing bookings must automatically block that time slot from being booked by another renter.

---

# 10. Pricing

Provider controls the base price.

V1 should support:

* Price per hour
* Price per day
* Price per month

Example:

```text
Hourly: ₹50
Daily: ₹300
Monthly: ₹2,000
```

The platform should calculate:

```text
Base parking price
+ Platform fee
+ Applicable taxes/charges
= Final renter amount
```

The exact platform fee should be configurable from Admin settings.

Do NOT hard-code commission percentages throughout the application.

Store configurable platform fees in the database/configuration.

---

# 11. Booking Flow

## Step 1

Renter opens listing.

## Step 2

Selects:

* Date
* Start time
* End time / duration
* Vehicle

## Step 3

System checks availability.

## Step 4

System calculates price.

## Step 5

Renter confirms booking.

## Step 6

Payment is initiated.

## Step 7

Booking is created.

## Step 8

Both renter and provider receive confirmation.

---

# 12. Booking Status

Use the following statuses:

```text
PENDING_PAYMENT
CONFIRMED
ACTIVE
COMPLETED
CANCELLED
EXPIRED
DISPUTED
```

The architecture should make it easy to add more statuses later.

---

# 13. Booking Protection Against Double Booking

This is a critical requirement.

Two renters must NEVER be able to successfully book the same parking space for overlapping time periods.

The backend must perform an atomic availability check during booking.

Do not rely only on frontend availability checks.

The database/backend must enforce booking conflict protection.

---

# 14. Payment

V1 should support online payment.

Recommended architecture:

```text
Renter
   ↓
Payment Gateway
   ↓
Platform
   ↓
Booking Confirmation
```

Payment gateway should be abstracted behind a payment service/interface so that the provider can be changed later.

Example:

```text
PaymentService
    ├── create_payment()
    ├── verify_payment()
    ├── refund_payment()
    └── handle_webhook()
```

Do NOT store card numbers, CVV, or sensitive payment credentials.

---

# 15. Platform Commission

The platform earns money from each booking.

Example:

Parking price = ₹1,000

Platform commission = 15%

Platform revenue = ₹150

Provider payout = ₹850

The commission percentage must be configurable.

Future support may include:

* Different commission by provider
* Different commission by city
* Promotional discounts
* Provider subscription
* Society revenue-sharing agreements

These are NOT required for V1.

---

# 16. Provider Earnings

Provider dashboard should show:

```text
Total Earnings
Pending Payout
Completed Payout
Upcoming Bookings
Current Month Earnings
```

Example:

```text
September Earnings

Gross Booking Value     ₹12,500
Platform Fee             ₹1,875
Provider Earnings       ₹10,625
```

Actual payout implementation can initially be simple.

The architecture should allow automated payouts later.

---

# 17. Renter Vehicle Management

A renter should be able to save vehicles.

Example:

```text
My Vehicles

1. Car
   GJ01AB1234
   Hyundai i20

2. Bike
   GJ01CD5678
   Honda Activa
```

At booking time, renter selects the vehicle.

Vehicle number is mandatory for a confirmed booking.

---

# 18. Parking Access

V1 should NOT implement smart locks, IoT gates, RFID, or automated barriers.

For V1, use simple access instructions.

Example:

```text
Parking Instructions:

Enter through the left gate.
Parking space is number A-12.
Show booking confirmation to security.
```

Provider can add instructions to the listing.

The renter sees those instructions after booking.

---

# 19. Booking Confirmation

After successful booking, generate a booking confirmation.

It should contain:

```text
Booking ID
Parking Location
Provider
Renter
Vehicle Number
Date
Start Time
End Time
Amount
Parking Instructions
Booking Status
```

A QR code can optionally be generated for the booking.

For V1, QR code does not need to control physical access.

It is simply a digital booking identifier.

---

# 20. Search

Renter should be able to search:

```text
Location
Date
Start Time
End Time
Vehicle Type
```

Optional filters:

* Price
* Covered/Open
* Distance
* Hourly/Daily/Monthly

Search results should show:

```text
Parking title
Distance
Price
Parking type
Vehicle type
Rating (future-ready)
Photo
Availability
```

---

# 21. Map View

V1 should have a map view.

Each available parking space appears as a map marker.

Clicking a marker opens a small listing preview.

Example:

```text
₹50/hour
Covered Parking
0.4 km away
```

Then renter can open the full listing.

---

# 22. Listing Details Page

The listing page should contain:

### Photos

Parking photos.

### Information

* Parking type
* Vehicle type
* Availability
* Price
* Location
* Distance
* Description

### Provider information

Show limited provider information.

Do NOT expose unnecessary personal information.

### Booking CTA

```text
Book Parking
```

---

# 23. Reviews

Reviews are important for a marketplace but should be kept simple in V1.

After a completed booking:

Renter can rate parking:

**1–5 stars**

and optionally leave a comment.

Provider can also rate renter.

However, if implementation complexity becomes too high, reviews can be moved to V1.1.

The database should still be designed to support reviews.

---

# 24. Damage / Dispute Policy

V1 does NOT provide insurance.

The platform should NOT initially act as an insurer.

The product should provide a basic reporting mechanism.

Example:

```text
Report Issue

Booking ID
Issue Type
Description
Photos
```

Potential issue types:

* Parking space unavailable
* Another vehicle occupying space
* Access problem
* Property damage
* Payment problem
* Other

Admin can review reports.

The platform should clearly communicate that damage liability is governed by the platform's terms and the applicable agreement between the relevant parties.

Do not promise insurance or guaranteed compensation in V1.

---

# 25. Photo Evidence

For dispute handling, allow:

* Provider to upload parking photos
* Renter to upload issue photos

Future versions may support:

**Before parking → photo**

**After parking → photo**

This can become part of a future protection/insurance product.

Not mandatory for V1.

---

# 26. Notifications

V1 should support:

### Email

* Registration
* Booking confirmation
* Booking cancellation
* Booking reminder
* Booking completion

### In-app notifications

Same important events.

SMS/WhatsApp can be added later.

Notification system should be abstracted so additional providers can be integrated later.

---

# 27. Authentication

Support:

* Email/password
* Phone number authentication if practical

User should have:

```text
Name
Email
Phone
Profile photo
Role
Vehicles
```

Use secure password hashing.

Use JWT/session-based authentication according to the selected application architecture.

---

# 28. Admin Dashboard

Admin dashboard should provide:

## Dashboard

```text
Total Users
Total Providers
Total Listings
Active Listings
Total Bookings
Today's Bookings
Monthly Booking Value
Platform Revenue
```

## Users

* View
* Search
* Suspend
* Activate

## Providers

* View
* Approve
* Suspend
* View listings
* View earnings

## Listings

* Approve
* Reject
* Suspend
* View details

## Bookings

* Search
* Filter
* View details
* Cancel if necessary

## Reports

* View disputes
* View issue reports
* Update status

---

# 29. Society Management — V1

Society support should be intentionally simple.

A society can be represented as a provider organization.

Example:

```text
Society
    ↓
Society Admin
    ↓
Parking Spaces
    ↓
Bookings
    ↓
Revenue
```

Society Admin can:

* Manage society profile
* Add parking spaces
* Set prices
* Set availability
* Block parking spaces
* View bookings
* View revenue

Do NOT build a complicated resident-management system in V1.

---

# 30. Society Agreement

The platform should support recording a society's commercial agreement.

Basic information:

```text
Society
Agreement start date
Agreement end date
Revenue share
Number of parking spaces
Status
```

The actual legal agreement/document should be handled separately.

Do not build a legal contract-generation system into V1.

---

# 31. Individual Provider Verification

For individual providers, V1 should have a basic verification workflow.

Possible information:

* Name
* Phone
* Email
* Address
* Parking ownership/authorization declaration
* Identity verification status

Admin should be able to mark:

```text
UNVERIFIED
PENDING_VERIFICATION
VERIFIED
REJECTED
```

Do not overbuild KYC in V1.

---

# 32. Important Rule: Provider Must Have Authority

A provider must confirm that they have the right/authorization to rent the parking space.

For society/commercial spaces, the provider must confirm that the organization has authority to offer the parking space.

The application should include a checkbox/consent during listing creation:

> "I confirm that I have the necessary rights or authorization to offer this parking space for rent."

This does not replace legal review.

---

# 33. Cancellation

V1 should support cancellation.

Cancellation rules should be configurable.

Example configuration:

```text
Cancellation allowed until X hours before start time.

Refund:
100% / 50% / 0%
```

Do not hard-code cancellation rules.

---

# 34. Basic Security Requirements

The application must include:

* Password hashing
* Authentication
* Authorization
* Role-based access control
* Input validation
* Rate limiting for sensitive endpoints
* Secure file uploads
* API authentication
* Database transactions
* Payment webhook verification
* Protection against double booking
* Audit logs for important admin actions

Never trust frontend data.

All important business rules must be enforced on the backend.

---

# 35. Backend Architecture

Recommended initial architecture:

```text
Frontend
   |
   v
Backend API
   |
   +---- PostgreSQL
   |
   +---- Redis (optional)
   |
   +---- Object Storage
   |
   +---- Payment Gateway
   |
   +---- Email/Notification Provider
```

Do NOT create microservices for V1.

Use a modular monolith.

Suggested backend modules:

```text
auth
users
vehicles
parking
availability
bookings
payments
providers
societies
notifications
reviews
reports
admin
```

Keep modules separated internally so they can be extracted into services later if required.

---

# 36. Suggested Backend Technology

Preferred:

```text
Python
FastAPI
PostgreSQL
SQLAlchemy
Alembic
Redis
Docker
```

Use asynchronous code where appropriate.

Do not introduce unnecessary infrastructure.

---

# 37. Database Core Entities

At minimum:

```text
User
Vehicle
Provider
Society
ParkingSpace
ParkingPhoto
AvailabilityRule
AvailabilityBlock
Booking
Payment
Payout
Review
Report
Notification
PlatformSetting
AuditLog
```

Important relationships:

```text
User
 ├── Vehicles
 ├── Bookings
 └── Provider

Provider
 └── ParkingSpaces

Society
 └── ParkingSpaces

ParkingSpace
 ├── Photos
 ├── AvailabilityRules
 ├── AvailabilityBlocks
 └── Bookings

Booking
 ├── Renter
 ├── Vehicle
 ├── ParkingSpace
 └── Payment
```

Use UUIDs as primary identifiers.

---

# 38. API Design

Use REST APIs.

Example:

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/login
GET    /api/v1/me
PATCH  /api/v1/me

GET    /api/v1/parking
POST   /api/v1/parking
GET    /api/v1/parking/{id}
PATCH  /api/v1/parking/{id}
DELETE /api/v1/parking/{id}

GET    /api/v1/parking/{id}/availability
POST   /api/v1/parking/{id}/availability
POST   /api/v1/parking/{id}/blocks

POST   /api/v1/bookings
GET    /api/v1/bookings
GET    /api/v1/bookings/{id}
POST   /api/v1/bookings/{id}/cancel

POST   /api/v1/payments/create
POST   /api/v1/payments/webhook

GET    /api/v1/providers/dashboard
GET    /api/v1/providers/earnings

GET    /api/v1/admin/dashboard
GET    /api/v1/admin/users
GET    /api/v1/admin/listings
GET    /api/v1/admin/bookings
GET    /api/v1/admin/reports
```

Use API versioning from the beginning.

---

# 39. Frontend

V1 should be responsive and mobile-friendly.

It should work well on:

* Mobile browser
* Tablet
* Desktop

Main screens:

## Public

* Landing page
* Search
* Map
* Parking listing
* Login
* Registration

## Renter

* Dashboard
* Search
* Booking
* Active bookings
* Booking history
* Vehicles
* Profile

## Provider

* Dashboard
* My parking spaces
* Add parking
* Edit parking
* Calendar
* Bookings
* Earnings
* Profile

## Society

* Dashboard
* Parking spaces
* Availability
* Bookings
* Revenue
* Society profile

## Admin

* Dashboard
* Users
* Providers
* Listings
* Bookings
* Payments
* Reports
* Settings

---

# 40. Landing Page

The landing page should communicate the product immediately.

Primary message:

> **Find Parking. Rent Your Empty Space.**

Two primary CTAs:

```text
Find Parking
List My Parking
```

Explain the concept:

### Need parking?

Find and book nearby parking.

### Have unused parking?

Turn your empty parking space into income.

---

# 41. MVP Scope

The following MUST work in V1:

### Renter

* Registration/login
* Search
* Map
* Listing details
* Availability
* Vehicle
* Booking
* Payment
* Booking history

### Provider

* Registration
* Create listing
* Upload photos
* Set pricing
* Set availability
* Block dates
* Manage bookings
* Earnings

### Society

* Society provider account
* Add parking spaces
* Manage availability
* Manage bookings
* View revenue

### Admin

* Dashboard
* Users
* Listings
* Providers
* Bookings
* Payments
* Reports

---

# 42. Explicitly OUT OF SCOPE for V1

Do NOT build these unless required for the core flow:

* Insurance
* Automated insurance claims
* Smart locks
* IoT parking sensors
* RFID
* ANPR/camera recognition
* Automatic gate integration
* EV charging management
* Car wash
* Car detailing
* Loyalty program
* Referral program
* Wallet
* Subscription plans
* Complex society management
* Accounting system
* Advanced analytics
* AI recommendations
* Native Android app
* Native iOS app
* Multi-country support
* Multi-currency
* Complex tax engine

Build the marketplace first.

---

# 43. V1 Success Metrics

The first goal is NOT downloads.

Measure marketplace activity.

### Supply

* Number of registered providers
* Number of active parking spaces
* Number of verified parking spaces

### Demand

* Number of registered renters
* Search volume
* Booking attempts
* Successful bookings

### Marketplace

* Booking conversion rate
* Average booking value
* Parking utilization
* Repeat renters
* Provider retention

### Revenue

* Gross booking value
* Platform commission
* Net platform revenue

---

# 44. Pilot Strategy

Do not launch across India initially.

Start in one city/limited geographic area.

Goal:

```text
20–50 parking spaces
+
20–50 renters
```

Validate:

1. Will people list unused parking?
2. Will renters actually pay?
3. What duration is most popular?
4. What price works?
5. What problems occur during parking?
6. Do providers continue using the platform?
7. Do renters return?

Only after proving these should the platform expand.

---

# 45. Product Principles

The following principles should guide development.

## Principle 1 — Supply before scale

The platform is useless without parking spaces.

Make provider onboarding extremely easy.

## Principle 2 — Trust

Show enough information to make renters comfortable without unnecessarily exposing personal information.

## Principle 3 — Simple

A provider should be able to list a parking space in a few minutes.

## Principle 4 — Availability accuracy

Never show unavailable parking as available.

## Principle 5 — Payment reliability

Booking and payment state must always remain consistent.

## Principle 6 — Mobile first

Most renters will likely use the platform from a phone.

## Principle 7 — Don't overbuild

V1 is a marketplace, not a complete parking-management ecosystem.

---

# 46. Development Order

Claude Code should implement the system in this order:

## Phase 1 — Foundation

* Project setup
* Docker
* PostgreSQL
* Alembic
* Environment configuration
* Authentication
* User model
* Role system
* API structure
* Error handling
* Logging

## Phase 2 — Parking

* Provider
* Parking space
* Photos
* Location
* Pricing
* Availability
* Availability blocks

## Phase 3 — Search

* Location search
* Radius search
* Filters
* Map
* Listing details

## Phase 4 — Booking

* Booking model
* Availability validation
* Double-booking protection
* Booking lifecycle
* Cancellation

## Phase 5 — Payment

* Payment abstraction
* Gateway integration
* Webhooks
* Payment verification
* Commission calculation

## Phase 6 — Dashboards

* Renter dashboard
* Provider dashboard
* Society dashboard
* Admin dashboard

## Phase 7 — Notifications

* Email
* In-app notifications

## Phase 8 — Reports

* Issue reporting
* Admin dispute management

## Phase 9 — Testing

* Unit tests
* API tests
* Booking conflict tests
* Payment tests
* Authorization tests
* End-to-end core flow

---

# 47. Critical Acceptance Test

The following scenario MUST work completely:

### Provider

1. Registers.
2. Creates a parking space.
3. Adds location.
4. Adds photos.
5. Sets price = ₹50/hour.
6. Makes parking available from 8 AM–8 PM.
7. Publishes listing.

### Renter

1. Registers.
2. Searches the provider's location.
3. Finds the parking.
4. Selects 10 AM–1 PM.
5. Selects vehicle.
6. Sees calculated price = ₹150 + applicable platform fees.
7. Pays.
8. Receives confirmation.
9. Sees booking in dashboard.

### Provider

1. Receives booking.
2. Sees renter and vehicle details.
3. Sees the 10 AM–1 PM period blocked.
4. Earnings update.

### Second Renter

Attempts to book:

**11 AM–12 PM**

The system MUST reject the booking because the space is already booked.

This test is mandatory.

---

# 48. Definition of Done

V1 is considered complete only when:

* Authentication works.
* Role permissions work.
* Providers can create parking listings.
* Providers can manage availability.
* Renters can search parking.
* Renters can view listings.
* Renters can select duration.
* Availability is validated server-side.
* Double booking is prevented.
* Payments work in test/sandbox mode.
* Booking confirmation works.
* Provider earnings are calculated correctly.
* Admin can manage the marketplace.
* Basic issue reporting works.
* Core APIs have automated tests.
* Database migrations work from a clean installation.
* Application runs using Docker.
* Environment variables are documented.
* API documentation is available.
* No secrets are committed to source control.

---

# 49. Development Rules for Claude Code

Claude Code should follow these rules while implementing the project:

1. **Do not build features outside the V1 scope without explicit approval.**

2. **Do not create microservices for V1.**
   Use a modular monolith.

3. **Do not hard-code business rules.**
   Pricing, commission and cancellation configuration should be configurable.

4. **Do not trust frontend validation.**
   All critical validation must happen server-side.

5. **Prevent race conditions in booking.**

6. **Use database transactions for booking/payment operations.**

7. **Use migrations for all schema changes.**

8. **Write tests alongside important business logic.**

9. **Keep payment integration isolated from booking logic.**

10. **Keep location/search logic isolated so it can evolve later.**

11. **Do not store sensitive payment credentials.**

12. **Do not commit secrets or `.env` files.**

13. **Use clean, documented REST APIs.**

14. **Use UUIDs for public entity IDs.**

15. **Maintain an audit trail for important admin actions.**

16. **Build responsive UI.**

17. **Prefer simple, maintainable solutions over premature optimization.**

18. **Before implementing a feature, check whether it is actually required by this PRD.**

19. **If a requirement is ambiguous, document the assumption instead of silently implementing a complicated solution.**

20. **At the end of each development phase, run tests and verify the application from a clean environment.**

---

# 50. Future Vision — NOT V1

The architecture should leave room for future expansion.

Potential V2/V3 capabilities:

```text
Smart Parking
    ↓
IoT sensors
    ↓
Real-time availability

Access
    ↓
QR
    ↓
RFID
    ↓
ANPR

Services
    ↓
EV Charging
    ↓
Car Wash
    ↓
Car Detailing

Protection
    ↓
Parking Protection
    ↓
Insurance integration

Business
    ↓
Corporate Parking
    ↓
Society Parking
    ↓
Commercial Parking
    ↓
Airport/Event Parking
```

But none of these should delay V1.

---

# 51. Final Product Definition

The V1 product can be summarized in one sentence:

> **A marketplace where people and organizations can list unused parking spaces and renters can discover, book and pay for those spaces based on location, availability and duration.**

The first objective is not to build the biggest parking platform.

The first objective is to prove:

> **Unused parking space can be converted into bookable inventory, and people are willing to pay to use it.**

