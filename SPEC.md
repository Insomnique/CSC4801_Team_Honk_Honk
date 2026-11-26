# Specification — CSC4801 Team Honk Honk Recruiting Platform

This document describes the architecture, data model, authorization design, routes, matching contract, booking transaction, and security controls of the submitted system.

## 1. Architecture

Two roles, one Django project, one PostgreSQL database, one container each for app and DB.

```
browser
  │
  ▼
Django (web container)
  ├── accounts app   — User, CandidateProfile, EmployerProfile
  ├── jobs app       — Job, Application, Slot, Booking, matching
  ├── templates      — server-rendered HTML
  └── Django ORM  ───► PostgreSQL 16 (db container)
```

- **UI**: Django templates (`templates/`), auto-escaping enabled globally.
- **Backend**: Django function views, decorators for auth, explicit role + ownership checks.
- **Database**: PostgreSQL 16 via `psycopg[binary]` — all queries via the Django ORM (parameterized).
- **Container**: `python:3.12.8-slim` (app) + `postgres:16` (db), orchestrated by `docker-compose.yml`.

## 2. Data model

### Accounts

- **User** — extends `AbstractUser`; fields `username` (unique), `email` (unique enforced at the form layer), `password` (hashed), `role` (enum: `candidate` | `employer`).
- **CandidateProfile** — `OneToOneField(User)`, `display_name`, `skills` (JSON list of strings), `resume_text`.
- **EmployerProfile** — `OneToOneField(User)`, `company_name`, `description`.

### Jobs

- **Job** — `ForeignKey(User, role=employer)`, `title`, `description`, `required_skills` (JSON list), `is_deleted` (soft-delete flag), `created_at`.
- **Application** — `ForeignKey(User, role=candidate)`, `ForeignKey(Job)`, `status` (enum: `pending` | `interviewing` | `rejected` | `accepted`, default `pending`), `created_at`; **UNIQUE(candidate, job)** — one application per candidate per job, enforced by the database.
- **Slot** — `ForeignKey(User, role=employer)`, `start_time`, `end_time`; validated as future, exactly 30 minutes. The database enforces the duration with two `CHECK` constraints: `slot_exactly_30_minutes` (`end_time = start_time + 30 min`) and `slot_end_after_start` (`end_time > start_time`).
**Timezone.** All slot times are stored and displayed in **UTC** (`TIME_ZONE = "UTC"`, `USE_TZ = True`). The slot form's "Start time (UTC)" field is read as UTC, and every page that shows a slot or booking time labels it "UTC". For example, 10:00 in Perth (UTC+8) is entered as 02:00.
- **Booking** — `OneToOneField(Application)`, `OneToOneField(Slot)` — two `UNIQUE` constraints, one per side, enforced by the database.

### Relationship diagram (text)

```
User (candidate) ─1:1─ CandidateProfile
User (employer)  ─1:1─ EmployerProfile
User (employer)  ─1:N─ Job
User (candidate) ─1:N─ Application ─N:1─ Job
User (employer)  ─1:N─ Slot
Application     ─1:1─ Booking ─1:1─ Slot
```

## 3. Authentication and authorization

- **Registration** — `accounts/forms.py::RegisterForm` extends `UserCreationForm`; adds `email` (required, unique, case-insensitive) and `role` (Candidate / Employer).
- **Login / logout** — Django `LoginView` / `LogoutView`; logout is POST-only (Django 5 default).
- **Password storage** — Django `AbstractUser` uses PBKDF2-SHA256 by default. Plaintext, reversible encryption, and fast unsalted hashes are not used.
- **Authorization** — every protected view:
  - `@login_required` on the view;
  - explicit role check (e.g. `if request.user.role != "candidate": return 403`);
  - object ownership check after fetching the object with `get_object_or_404`.
- **Response contract**:
  - unauthenticated → 302 redirect to `/accounts/login/`
  - authenticated but wrong role or wrong owner → 403
  - missing object the caller would otherwise be allowed to see → 404

## 4. Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | any | Redirect to `/accounts/dashboard/` |
| GET/POST | `/accounts/register/` | anon | Register (choose role) |
| GET/POST | `/accounts/login/` | anon | Log in |
| POST | `/accounts/logout/` | auth | Log out |
| GET | `/accounts/dashboard/` | auth | Role-specific dashboard |
| GET/POST | `/accounts/profile/` | candidate | Edit own candidate profile (skills, resume) |
| GET/POST | `/accounts/company/` | employer | Edit own company profile |
| GET | `/jobs/` | employer | List own job postings |
| GET/POST | `/jobs/new/` | employer | Create job |
| GET/POST | `/jobs/<id>/edit/` | employer (owner) | Edit job |
| GET/POST | `/jobs/<id>/delete/` | employer (owner) | Soft-delete job; 409 if applications exist |
| GET | `/jobs/<id>/` | auth | Job detail (candidate sees match score) |
| GET | `/jobs/dashboard/` | candidate | Jobs ranked by match score |
| POST | `/jobs/<id>/apply/` | candidate | Apply once; 409 on duplicate |
| GET | `/jobs/my-applications/` | candidate | Own applications + status + booking |
| GET | `/jobs/<id>/applicants/` | employer (owner) | Applicant list sorted by score |
| POST | `/jobs/applications/<id>/status/` | employer (owner) | Update status to one of 4 values |
| GET | `/jobs/slots/` | employer | Own availability slots |
| GET/POST | `/jobs/slots/new/` | employer | Create 30-minute future slot |
| GET/POST | `/jobs/slots/<id>/delete/` | employer (owner) | Delete; 409 if booked |
| GET | `/jobs/applications/<id>/slots/` | candidate (owner) | Bookable slots for own interviewing application |
| POST | `/jobs/slots/<id>/book/` | candidate | Book slot (atomic; 409 "Slot already booked") |

## 5. Matching contract

The score is a pure function in `jobs/matching.py::match_score`:

```python
def normalize_skills(skills):
    return {str(s).strip().lower() for s in (skills or []) if str(s).strip()}

def match_score(candidate_skills, required_skills) -> int:
    C, R = normalize_skills(candidate_skills), normalize_skills(required_skills)
    if len(R) == 0:
        return 100
    return (100 * len(C & R)) // len(R)
```

Both the candidate dashboard (`candidate_dashboard`) and the employer applicant list (`job_applicants`) call **this same function** — the score displayed to either side is identical.

**Tie-breaking**:
- Candidate dashboard: sort key `(-score, job.title.lower(), job.id)` — `candidate_job_sort_key`.
- Employer applicant list: sort key `(-score, (display_name or username).lower(), user.id)` — `employer_applicant_sort_key`.

**Required examples verified in tests** (`MatchScoreRequiredExamplesTests`):

| Candidate skills | Required skills | Expected |
|---|---|---|
| Python, SQL | Python, SQL | 100 |
| Python | Python, SQL | 50 |
| Rust | Python, SQL | 0 |
| any | (empty) | 100 |

## 6. Booking transaction (atomicity)

The race condition: two candidates concurrently attempt to book the same slot. The requirement is that exactly one succeeds and the other fails with 409 and message "Slot already booked", with exactly one booking row in the database.

**Mechanism**: `Booking.slot` is a `OneToOneField`, which translates to a `UNIQUE` constraint on `slot_id` at the database level. When two `INSERT` statements race, PostgreSQL serializes them and the second fails with a unique violation. This is database-level atomicity — not an in-process check.

**View logic** (`jobs/views.py::book_slot`):
1. Validate the 5 eligibility rules (ownership, employer match, status, future, no existing booking) — return the appropriate 4xx on any violation.
2. Wrap the insert in `transaction.atomic()` and catch `IntegrityError`:
   ```python
   try:
       with transaction.atomic():
           Booking.objects.create(application=app, slot=slot)
   except IntegrityError:
       return HttpResponse("Slot already booked", status=409)
   ```

**Why the inner `transaction.atomic()`**: it creates a savepoint so a failed insert doesn't poison the outer transaction (needed because Django's `TestCase` wraps each test in a transaction; without the savepoint the follow-up query would fail with `TransactionManagementError`). In production it also allows the request to keep working after the conflict.

**Tested**: `AtomicityTests.test_concurrent_double_booking_one_wins` — inserts `Booking` for app1, then attempts for app2 on the same slot; asserts the second raises `IntegrityError` and that exactly one booking exists. `BookingEligibilityTests.test_slot_already_booked_by_other_409` — end-to-end view test asserting 409 and "Slot already booked" in the response body.

## 7. Security controls

| Control | Implementation |
|---|---|
| **Object access (FP-SEC-1)** | Every view: `@login_required` → role check → `get_object_or_404` → ownership check. Every 403/404 boundary tested. |
| **SQL injection (FP-SEC-2)** | All DB access via Django ORM (parameterized). Test: `SecurityTests.test_sql_injection_is_bound_not_executed` inserts `'; DROP TABLE jobs_job; --` as a job title and asserts the table survives and the string is stored verbatim. |
| **XSS (FP-SEC-3)** | Django templates auto-escape all variables. No `|safe` on user input anywhere. `description` uses `|linebreaks`, which escapes. Test: `SecurityTests.test_xss_payload_is_escaped` saves `<script>alert(1)</script>` as a job title, renders the detail page, asserts `&lt;script&gt;` present and raw `<script>alert(1)</script>` absent. |
| **Secrets (FP-SEC-4)** | `SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()`; `DEBUG = os.environ.get("DJANGO_DEBUG") == "1"`. `.env.example` contains placeholders only. `.env` is in `.gitignore`. |
| **Password storage (FP-AUTH-2)** | Django's default PBKDF2-SHA256 hashing; tested in `PasswordStorageTests.test_password_is_hashed`. |
| **Test isolation (FP-SEC-4)** | Every test uses Django's isolated `test_honk` database, created and destroyed by `manage.py test`. No real third-party services called. |

## 8. UI screens

| Screen | Route | Role |
|---|---|---|
| Register | `/accounts/register/` | anon |
| Log in | `/accounts/login/` | anon |
| Candidate dashboard | `/accounts/dashboard/` | candidate |
| Employer dashboard | `/accounts/dashboard/` | employer |
| Candidate profile | `/accounts/profile/` | candidate |
| Company profile | `/accounts/company/` | employer |
| Job recommendations | `/jobs/dashboard/` | candidate |
| Job detail + Apply | `/jobs/<id>/` | candidate |
| My applications | `/jobs/my-applications/` | candidate |
| Book interview | `/jobs/applications/<id>/slots/` | candidate |
| Employer job list | `/jobs/` | employer |
| Create/edit job | `/jobs/new/`, `/jobs/<id>/edit/` | employer |
| Applicant management | `/jobs/<id>/applicants/` | employer |
| Availability slots | `/jobs/slots/` | employer |

## 9. Deterministic seed data

`jobs/management/commands/seed.py` wipes and repopulates:

- 5 users total: 2 employers + 3 candidates
- 3 jobs: Backend Engineer (Python, SQL), Rust Systems Engineer (Rust), Graduate Generalist (no required skills)
- The four FP-MATCH-1 examples: Alice (Python, SQL) → Backend = 100; Bob (Python) → Backend = 50; Carol (Rust) → Backend = 0; any candidate → Graduate Generalist = 100
- 5 applications covering all four statuses (2 interviewing, 1 pending, 1 rejected, 1 accepted)
- 3 slots at fixed UTC times: the shared racing slot on 2027-06-01 02:00 UTC, a second future slot on 2027-06-02 02:00 UTC, and a past slot on 2025-01-01 (must not appear as bookable)
 
ID sequences are reset on every run, so repeated runs produce the same rows with the same IDs.

## 10. Known limitations (unchanged from README)