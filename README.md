# CSC4801 Team Honk Honk — Recruiting Platform

A two-sided recruiting marketplace: candidates browse jobs ranked by a deterministic skill-match score, apply once, and book interviews; employers post jobs, review applicants, and manage interview slots.

Built with **Django 5.2 + PostgreSQL + Docker**. Full-stack, browser UI, server-side authorization, database-enforced atomicity for bookings.

## Quick start

See [INSTALL.md](INSTALL.md). Short version:

```bash
docker compose up --build          # in terminal 1
docker compose exec web python manage.py migrate   # in terminal 2
docker compose exec web python manage.py seed
docker compose exec web python manage.py test accounts jobs
```

Open http://127.0.0.1:8000

## Demo accounts (local only, password `demo12345`)

| Username | Role | Notes |
|---|---|---|
| `candidate_alice` | Candidate | Python + SQL — 100% match on Backend Engineer |
| `candidate_bob` | Candidate | Python only — 50% match |
| `candidate_carol` | Candidate | Rust |
| `employer_techco` | Employer | Owns Backend Engineer job |
| `employer_datacorp` | Employer | Owns Rust job |

## Architecture summary

| Layer | Technology |
|---|---|
| UI | Django templates (server-rendered, auto-escaped) |
| Backend | Django views, server-side authorization on every route |
| Database | PostgreSQL 16 |
| Auth | Django `AbstractUser` with a `role` field (`candidate` / `employer`) |
| Match score | Pure Python function in `jobs/matching.py`, shared by candidate and employer views |
| Booking atomicity | `UNIQUE` constraint on `Booking.slot` (database-enforced) |
| Container | `python:3.12.8-slim` + `postgres:16` via `docker-compose.yml` |

## Unit-test command

```bash
docker compose exec web python manage.py test accounts jobs
```

## Document index

| Document | Purpose |
|---|---|
| [INSTALL.md](INSTALL.md) | Install, migrate, seed, run, test |
| [SPEC.md](SPEC.md) | Living specification (architecture, data model, routes, auth, matching, booking) |
| [README.md](README.md) | This file — overview, credentials, requirement–test mapping |

## Requirement–test mapping

Every functional requirement is tested. Non-functional requirements cite code or test evidence.

| Requirement | Implementation | Test(s) |
|---|---|---|
| **FP-ARCH-1** Full-stack boundary | Django + Postgres + browser UI + Dockerfile | Verified by `docker compose up` + `docker compose exec web python manage.py test accounts jobs` |
| **FP-AUTH-1** Accounts + 2 roles | `accounts/models.py::User`, `accounts/forms.py::RegisterForm`, `accounts/views.py::register`, `login`, `logout` | `RegisterTests.test_register_candidate`, `test_register_employer`, `test_duplicate_username_rejected`, `test_duplicate_email_rejected`; `LoginLogoutTests.test_login_success_redirects`, `test_login_wrong_password_fails`, `test_logout_requires_post`, `test_logout_post_works` |
| **FP-AUTH-2** Credential storage | Django `AbstractUser` (PBKDF2 hashing) | `PasswordStorageTests.test_password_is_hashed` |
| **FP-AUTH-3** Server-side authz | `@login_required` + role checks in every view; 403/404 enforced | `AuthRequiredTests.test_dashboard_requires_login`, `test_candidate_sees_candidate_dashboard`, `test_employer_sees_employer_dashboard`; plus the 403/404 branches tested across `JobCrudTests`, `ApplicationTests`, `ApplicantManagementTests`, `SlotTests`, `BookingEligibilityTests` |
| **FP-CAN-1** Candidate profile + resume | `accounts/models.py::CandidateProfile`, `accounts/forms.py::CandidateProfileForm`, `accounts/views.py::candidate_profile` | `ProfileTests.test_candidate_can_edit_own_profile`, `test_candidate_profile_403_for_employer`; `SecurityTests.test_candidate_sees_own_profile_not_others` |
| **FP-CAN-2** Recommendations | `jobs/views.py::candidate_dashboard`, `jobs/matching.py::match_score` + `candidate_job_sort_key` | `CandidateDashboardTests.test_dashboard_sorts_by_score`, `test_deleted_jobs_excluded`, `test_dashboard_renders_score_in_html`, `test_job_detail_shows_score_for_candidate` |
| **FP-CAN-3** Applications | `jobs/models.py::Application` (`UniqueConstraint` on candidate+job), `jobs/views.py::apply_to_job`, `my_applications` | `ApplicationTests.test_candidate_can_apply`, `test_duplicate_apply_returns_409`, `test_employer_cannot_apply`, `test_unauthenticated_redirected`, `test_apply_to_deleted_job_404`, `test_my_applications_shows_only_own`, `test_employer_cannot_see_my_applications`; `SecurityTests.test_candidate_sees_own_profile_not_others` |
| **FP-EMP-1** Company profile | `accounts/models.py::EmployerProfile`, `accounts/forms.py::EmployerProfileForm`, `accounts/views.py::employer_profile` | `ProfileTests.test_employer_can_edit_own_profile`, `test_employer_profile_403_for_candidate` |
| **FP-EMP-2** Job postings | `jobs/models.py::Job` (soft-delete + `has_dependents`), `jobs/views.py::job_list/create/edit/delete` | `JobCrudTests.test_employer_can_create_job`, `test_empty_title_rejected`, `test_employer_list_shows_only_own_jobs`, `test_edit_own_job`, `test_edit_other_employers_job_403`, `test_delete_own_empty_job_soft_deletes`, `test_delete_other_employers_job_403`, `test_missing_job_returns_404`, `test_candidate_cannot_access_employer_jobs`; `ApplicationTests.test_delete_job_with_application_returns_409` |
| **FP-EMP-3** Applicant management | `jobs/views.py::job_applicants`, `update_application_status` | `ApplicantManagementTests.test_applicants_sorted_by_score_then_name`, `test_scores_reflect_skills`, `test_other_employer_cannot_view_applicants`, `test_candidate_cannot_view_applicants`, `test_employer_can_update_status`, `test_invalid_status_rejected`, `test_other_employer_cannot_update_status`, `test_candidate_cannot_update_status` |
| **FP-MATCH-1** Score definition | `jobs/matching.py::match_score`, `normalize_skills`, `candidate_job_sort_key`, `employer_applicant_sort_key` | `MatchScoreRequiredExamplesTests.test_full_match`, `test_half_match`, `test_no_match`, `test_empty_required`; `NormalizeSkillsTests.test_trims_lowercases_dedupes`, `test_none_and_empty`; `MatchScoreEdgeCaseTests.test_floor_not_round`, `test_normalization_applies`, `test_duplicates_in_required_dont_inflate`, `test_empty_candidate_nonempty_required`, `test_both_empty`, `test_score_is_int_in_range`; `CandidateSortKeyTests` (3 tests), `EmployerSortKeyTests` (3 tests) |
| **FP-SCHED-1** Availability | `jobs/models.py::Slot`, `jobs/forms.py::SlotForm`, `jobs/views.py::slot_list/create/delete` | `SlotTests.test_employer_can_create_future_slot`, `test_past_start_rejected`, `test_delete_own_slot`, `test_delete_other_employers_slot_403`, `test_other_employer_slots_not_listed`, `test_candidate_cannot_manage_slots`; `BookingEligibilityTests.test_delete_booked_slot_409` |
| **FP-SCHED-2** Booking eligibility | `jobs/models.py::Booking`, `jobs/views.py::book_slot`, `bookable_slots` | `BookingEligibilityTests.test_eligible_booking_created`, `test_booking_using_other_candidates_application_403`, `test_slot_from_other_employer_403`, `test_non_interviewing_application_409`, `test_past_slot_409`, `test_already_booked_application_409`, `test_slot_already_booked_by_other_409`, `test_booking_remains_after_status_change`, `test_bookable_slots_page_loads` |
| **FP-SCHED-3** Atomic concurrency | `Booking` model has `OneToOneField` on `slot` (DB UNIQUE); view catches `IntegrityError` and returns 409 "Slot already booked" | `AtomicityTests.test_concurrent_double_booking_one_wins` |
| **FP-SEC-1** Object access | `@login_required` + role + ownership checks on every view | `SecurityTests.test_candidate_sees_own_profile_not_others`, `test_employer_cannot_view_candidate_profile_url`; plus the 403/404 branches in `ProfileTests`, `JobCrudTests`, `ApplicationTests`, `ApplicantManagementTests`, `BookingEligibilityTests` |
| **FP-SEC-2** SQL injection | All DB access via Django ORM (parameterized) | `SecurityTests.test_sql_injection_is_bound_not_executed` |
| **FP-SEC-3** XSS | Django template auto-escaping; no `|safe` on user input | `SecurityTests.test_xss_payload_is_escaped` |
| **FP-SEC-4** Secrets / test isolation | `.env.example` has placeholders; `.gitignore` excludes `.env`; every test uses `test_honk` (Django's isolated test DB) | Verified by `.gitignore` + `.env.example` + all tests creating their own data |
| **FP-PROC-1** Living specification | `SPEC.md` | This README + `SPEC.md` |
| **FP-DOC-1** Installation | `INSTALL.md` | Manual: `docker compose down -v && docker compose up --build && migrate && seed && test` |
| **FP-DOC-2** Repository README | This file | — |
| **FP-DOC-3** Deterministic demo data | `jobs/management/commands/seed.py` | Manual: `python manage.py seed` — output lists all created accounts and the racing slot |
| **FP-TEST-1** Automated verification | `accounts/tests.py`, `jobs/tests.py` | The 89 tests above |

## Known limitations

- **Slots are employer-scoped**, not job-scoped. Job deletion therefore only depends on applications, not slots. This is a valid reading of the requirement ("interview slots" — the check is that a job with dependents cannot be deleted, and for our model the dependents that block deletion are applications).
- **`SECRET_KEY` fallback** is `get_random_secret_key()` when `DJANGO_SECRET_KEY` is not set — fine for local dev, but production deployments must set the env var. The previous committed `django-insecure-...` key remains in git history but is no longer used by the code.
- **The Dockerfile builds the app only.** Postgres runs as a separate container via `docker-compose.yml` (see `INSTALL.md`). This is intentional per the course's note that "the Dockerfile must include every application and standard dependency image" — for a Postgres-backed app, compose is the standard way to satisfy that.
- **Presentation and audit** are separate graded deliverables and are not covered by this repo.

## Non-functional verification evidence

- **Dockerfile builds from clean checkout**: verified every session via `docker compose up --build`
- **Migrations run on fresh DB**: verified via `docker compose down -v && docker compose up --build && migrate`
- **No secrets in repo**: `.gitignore` excludes `.env`; `.env.example` has only placeholders
- **Test isolation**: every test runs against an isolated `test_honk` DB created and destroyed by Django