# Coruscant Health Administration — Roadmap

Medical Management System for the CHA. Python + Django + relational DB, encrypted
document storage, cloud-hosted with CI/CD, and unit tests throughout.

> **Team:** Subhan Gadirli, Zahra Suleymanli · **Track:** Season 03 Fullstack Python

---

## 1. Analysis Summary

### Stakeholders & core capabilities

| Role | Must be able to |
|------|-----------------|
| **Patient** | Register (needs admin approval), upload device readings, view own readings, view doctor's prescriptions/reports, upload documents |
| **Doctor** | Register (needs admin approval), view assigned patient records, track patient trend (improving/worsening), write reports/prescriptions, place service orders (CT scan, PET scan, …), upload documents |
| **Department / Service** | Receive orders, execute them, upload results |
| **Administrator** | Approve/reject patient & doctor registrations, manage tables, monitor app, handle upgrades |
| **Emergency Services** | Rapidly intake a new patient (minimal-friction fast form) |

### Cross-cutting requirements
- **Database** of record for registrations, readings, feedback, orders, results.
- **Document management**: patient/doctor uploads, **encrypted at rest**, modern security standard.
- **Top UI/UX** — clean, responsive, role-aware dashboards.
- **Cloud hosting** — URL written to `my_coruscant_health_administration_url.txt` (URL only, nothing else).
- **CI/CD** pipeline.
- **Unit tests**.

### Key domain rules
1. Registration approval gate: patients & doctors are inactive until an admin acknowledges them.
2. Role-based access control — each role sees only what it should.
3. A "reading" is time-series device data → drives trend/improvement analysis.
4. Orders flow: Doctor → Department (queue) → Result upload → visible to Doctor/Patient.

---

## 2. Tech Stack

| Concern | Choice | Notes |
|---------|--------|-------|
| Language / Framework | Python 3.12+, Django 5.x | Spec-required |
| Database | PostgreSQL (prod), SQLite (local dev) | Postgres for cloud |
| Auth | Django custom `User` (role field) | Approval gate + RBAC |
| Document encryption | `cryptography` (Fernet) or field-level encryption + private storage | Encrypt at rest |
| File storage | Cloud object storage (S3 / GCS) private buckets, or encrypted local for MVP | Signed/expiring URLs |
| Frontend | Django templates + Bootstrap/Tailwind (or HTMX for interactivity) | "Top UI/UX" |
| Charts | Chart.js for health-reading trends | Trend visualization |
| Testing | `pytest-django` / Django `TestCase`, `coverage` | Unit + integration |
| CI/CD | GitHub Actions (or Gitea CI) → deploy | Lint + test + deploy |
| Hosting | Render / Railway / Fly.io / AWS / GCP | Whatever is simplest to ship |
| Secrets | Environment variables / `.env` (never committed) | 12-factor |

> Decision to confirm: object storage provider and hosting target. Pick the one
> with the least deployment friction unless the team has an AWS/GCP requirement.

---

## 3. Data Model (first pass)

- **User** — email/username, password, `role` (patient/doctor/admin/department/emergency), `is_approved`.
- **PatientProfile** — 1:1 User; demographics, device id, emergency-intake flag.
- **DoctorProfile** — 1:1 User; specialty, license no.
- **Department** — name, type (CT, PET, Lab, …).
- **HealthReading** — FK patient; metric type, value, unit, recorded_at (device upload).
- **Report / Prescription** — FK doctor, FK patient; body, created_at, status.
- **ServiceOrder** — FK doctor, FK patient, FK department; type, status (`ordered → in_progress → completed`), notes.
- **OrderResult** — FK ServiceOrder; result text, FK Document, uploaded_at.
- **Document** — owner, encrypted file ref, filename, content-type, checksum, uploaded_at.
- **PatientDoctorAssignment** — links patients to doctors (who can view whom).

---

## 4. Milestones

### M0 — Project scaffold *(foundation)* ✅
- [x] `django-admin startproject`, app split (`accounts`, `records`, `orders`, `documents`, `dashboard`).
- [x] Settings split (base/dev/prod), `.env`, `requirements.txt`, `.gitignore`.
- [x] Postgres + SQLite config, initial migrations.
- [x] Base template, static pipeline, health-check endpoint.
- [x] **Fill in README.md** (Task/Description/Installation/Usage).

### M1 — Auth, roles & approval gate ✅
- [x] Custom user model with `role` + `is_approved`.
- [x] Registration flows for patient & doctor (pending state).
- [x] Admin approval/rejection UI.
- [x] RBAC middleware/mixins; login/logout; role-based redirect to dashboards.
- [x] Tests: registration, approval gate, access control.

### M2 — Patient features ✅
- [x] Device data upload endpoint (API + form/CSV).
- [x] Patient dashboard: view readings (table + Chart.js trend).
- [x] View prescriptions/reports from doctor.
- [x] Tests.

> Notes: the device API is a plain JSON view (no DRF) authenticated by a
> per-patient bearer token, stored only as a SHA-256 digest. CSV and API
> uploads share one validator (`records.ingest`) and are all-or-nothing.
> `Report` drafts are invisible to patients; doctor-side authoring is M3.

### M3 — Doctor features ✅
- [x] View assigned patient records + reading trends.
- [x] Improvement/worsening indicator (compare recent vs. baseline).
- [x] Write report/prescription.
- [x] Place service orders.
- [x] Tests.

> Notes: doctor access runs through `PatientDoctorAssignment`, so an
> unassigned patient is a 404 rather than a check that runs after the
> record has been fetched. The indicator (`records.trends`) scores the
> recent mean against the previous block by movement toward or away from
> the metric's healthy range, which is what makes one rule work for
> metrics where lower is better and metrics where it is not. Reports are
> drafts until published, and publishing is final. Placing orders is here;
> the department queue, execution and results are M4.

### M4 — Department & orders lifecycle
- [x] Department order queue (receive).
- [x] Execute + upload result (with document).
- [x] Status transitions surfaced to doctor & patient.
- [x] Tests.

> The `ServiceOrder` model and its transitions (`start`, `complete`,
> `cancel`) landed with M3 so both sides share one set of rules. M4 added
> the department-facing queue (scoped by `department__staff`), the
> `OrderResult` model with an optional attachment, and read-only order
> views for the patient. Result files are served only through an
> access-checked download view (doctor, patient, or department staff),
> never a public media URL — M6 swaps in encrypted private storage behind
> that same check.

### M5 — Emergency intake
- [x] Minimal fast-intake form (create patient in seconds).
- [x] Auto-provisioning / expedited approval path.
- [x] Tests.

> The intake screen (`accounts:emergency_intake`, emergency role only) takes a
> name and an optional presenting complaint and calls
> `accounts.intake.admit_emergency_patient`, which creates an already-approved
> patient in one transaction — the expedited path, so an incoming patient never
> waits in the admin queue. The account is auto-provisioned with a generated
> password shown once (only its hash is stored), and the desk sees a scoped list
> of its own recent admissions.

### M6 — Document management (encrypted)
- [x] Upload for patients & doctors.
- [x] Encrypt at rest (Fernet / KMS-backed); private storage + signed URLs.
- [x] Access control on download; checksum integrity.
- [x] Tests: encryption round-trip, unauthorized-access denial.

> Documents belong to a `patient` and record their `owner` (the patient
> themselves, or a doctor uploading to an assigned patient). Files are written
> through `documents.storage.EncryptedFileSystemStorage`, which Fernet-encrypts
> the bytes at rest under `DOCUMENT_ENCRYPTION_KEY` — a leaked `MEDIA_ROOT`
> yields ciphertext. There is no public media URL; the only way out is the
> access-checked `download_document` view, which decrypts, re-hashes, and
> refuses to serve anything whose SHA-256 no longer matches the checksum taken
> at upload. Swapping to a KMS/S3 backend later means replacing the storage
> class, not the models, views, or access checks. The `cryptography` /
> `psycopg2-binary` deps and the `DOCUMENT_ENCRYPTION_KEY` settings (dev
> default, prod fail-fast) were already in place from the scaffold.

### M7 — UI/UX polish
- [x] Consistent responsive design, role-aware nav.
- [x] Empty/error/loading states, form validation UX.
- [ ] Accessibility pass.

### M8 — CI/CD & deployment
- [ ] GitHub/Gitea Actions: lint (`ruff`/`flake8`) + tests + coverage gate.
- [ ] Auto-deploy on main/dev merge.
- [ ] Provision Postgres + object storage in cloud.
- [ ] `collectstatic`, migrations on deploy, env secrets.
- [ ] **Write live URL to `my_coruscant_health_administration_url.txt` (URL only).**

### M9 — Hardening & handoff
- [ ] Security review (HTTPS, CSRF, secure cookies, `DEBUG=False`, ALLOWED_HOSTS).
- [ ] Seed/demo data & admin account.
- [ ] Coverage report; finalize docs.
- [ ] Peer-review readiness.

---

## 5. Security Checklist
- [x] Passwords hashed (Django default), password validators on.
- [x] Documents encrypted at rest; keys in secrets manager, not code.
- [x] Private file storage; no public bucket, expiring download links.
- [x] RBAC enforced server-side on every view (not just UI hiding).
- [x] `DEBUG=False`, `SECURE_SSL_REDIRECT`, HSTS, secure/HTTPOnly cookies in prod.
- [x] CSRF on all forms.
- [ ] Audit logging for sensitive actions.
- [x] No secrets in git; `.env` gitignored.

> `manage.py check --deploy` passes clean against `config.settings.prod`.
> Documents are Fernet-encrypted at rest (M6) with the key read from the
> environment — a dev default in `dev.py`, fail-fast in `prod.py` — and served
> only through an access-checked download view, so there is no public bucket.
> Expiring signed URLs are the S3 variant of that same check and arrive with
> object storage in M8. Audit logging is still open: rejection is recorded via
> `is_rejected`, but approvals, logins and report access are not logged
> anywhere.

---

## 6. Deliverables (grading-facing)
- [x] Working Django app in the repo.
- [ ] `my_coruscant_health_administration_url.txt` — live URL only.
- [x] Unit tests (251 passing).
- [ ] Passing CI.
- [x] Completed `README.md`.
- [x] This `roadmap.md`.

---

## 7. Suggested Order of Attack
M0 → M1 → M8 (get CI/deploy skeleton live early with a "hello" page) → M2 → M3
→ M4 → M6 → M5 → M7 → M9.

> Rationale: stand up deployment early (M8 skeleton) so integration pain surfaces
> before feature code piles up, then build features on a known-good pipeline.

---

## 8. Team Split (suggested)
- **Subhan:** accounts/RBAC (M1), orders/department (M4), CI/CD & deploy (M8).
- **Zahra:** patient/doctor features (M2, M3), document encryption (M6), UI/UX (M7).
- **Shared:** data model, emergency intake (M5), hardening (M9).
