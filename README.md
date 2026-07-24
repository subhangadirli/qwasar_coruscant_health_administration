# Coruscant Health Administration
***

## Task
Rebuild the Coruscant Health Administration's Medical Management System: a
web application where patients upload device health readings, doctors review
records and prescribe reports, departments execute service orders (CT/PET
scans, labs), administrators approve registrations, and emergency services
perform fast patient intake. Uploaded documents are encrypted at rest.

## Description
A Django application backed by a relational database (SQLite for local dev,
PostgreSQL in production). Server-rendered templates styled with Tailwind and
enhanced with HTMX. Role-based access control with an administrator approval
gate for patient and doctor registrations. See `roadmap.md` for the full plan.

## Installation
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit values
python manage.py migrate
python manage.py createsuperuser
```

## Usage
```
python manage.py runserver
```
Then open http://127.0.0.1:8000/ — health probe at `/health/`, admin at
`/admin/`. Run the tests with `python manage.py test`.

### Patient readings
Approved patients can record health data three ways, all reachable from
`/records/readings/`:

- **By hand** — a single measurement at `/records/readings/add/`.
- **CSV** — a device export at `/records/readings/upload/`, with columns
  `metric,value,recorded_at` and an optional `unit`.
- **Device API** — generate a bearer token at `/records/device-token/`, then:

```
curl -X POST http://127.0.0.1:8000/records/api/readings/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"readings":[{"metric":"heart_rate","value":72,"recorded_at":"2026-07-20T08:30:00Z"}]}'
```

CSV and API uploads are all-or-nothing: if any row is invalid, nothing is
saved. Tokens are stored only as a hash and shown once, so a replacement
token is the way to recover from a lost one.

## Project layout
```
config/            project + split settings (base/dev/prod)
apps/accounts      custom User model, roles, approval gate
apps/records       health readings, device tokens, reports, prescriptions
apps/orders        service orders + department results
apps/documents     encrypted document upload/storage
apps/dashboard     landing + role dashboards
templates/         base + page templates
```

### The Core Team
Subhan Gadirli · Zahra Suleymanli

<span><i>Made at <a href='https://qwasar.io'>Qwasar SV -- Software Engineering School</a></i></span>
<span><img alt='Qwasar SV -- Software Engineering School's Logo' src='https://storage.googleapis.com/qwasar-public/qwasar-logo_50x50.png' width='20px' /></span>
