# INSTALL

## Prerequisites
- Docker Desktop (with Docker Compose v2)
- Ports 8000 and 5432 free on localhost
- No additional Python or PostgreSQL install required on the host

## Build and start (terminal 1)

```bash
docker compose up --build
```

Wait until you see:
```
web-1  | Starting development server at http://0.0.0.0:8000/
```

First run downloads `python:3.12.8-slim` and `postgres:16` and takes 2–5 minutes. Subsequent runs are near-instant.

## Run migrations (terminal 2)

Open a second terminal in the same folder:

```bash
docker compose exec web python manage.py migrate
```

Expected: all migrations apply cleanly (`Applying accounts.0001_initial... OK`, `jobs.0001_initial... OK`, `jobs.0002_application_and_more... OK`, `jobs.0003_slot... OK`, `jobs.0004_booking... OK`).

## Seed deterministic demo data

```bash
docker compose exec web python manage.py seed
```

Expected output ends with:
```
Seed complete.

Demo accounts (password: demo12345):
  employer_techco   / demo12345  (Employer — TechCo)
  employer_datacorp / demo12345  (Employer — DataCorp)
  candidate_alice   / demo12345  (Candidate — Python, SQL)
  candidate_bob     / demo12345  (Candidate — Python)
  candidate_carol   / demo12345  (Candidate — Rust)
```

The seed command **wipes all existing data** before repopulating. Run it any time you want a clean demo state.

## Run the app

Open http://127.0.0.1:8000

You should see the login page (the root URL redirects there if not authenticated). Log in with any demo account above.

## Run tests

```bash
docker compose exec web python manage.py test accounts jobs -v 2
```

Expected: **89 tests, OK.** The first run creates a fresh `test_honk` database and destroys it afterward — your real data is untouched. Takes ~2 minutes (Django 5.2's PBKDF2 iteration count).

## Stop

```bash
docker compose down
```

This stops both containers but **keeps the database volume** (`project_pgdata`). Your users, jobs, applications, and bookings survive.

## Reset the database (wipes all data)

```bash
docker compose down -v
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed
```

The `-v` flag deletes the `project_pgdata` volume. **Only use this when you want a completely fresh DB.**

---

## First run after pulling this repo

If you have a `pgdata` volume from a previous version of this project — specifically one created **before** the custom `User` model was introduced — the migration will fail with `Dependency on app with no migrations: accounts` or similar. Wipe the volume once:

```bash
docker compose down -v
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed
```

This is required because `AUTH_USER_MODEL` was introduced after the first migrations ran. After that one-time reset, subsequent starts only need `docker compose up`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` | Docker Desktop isn't running. Open it and wait for "Engine running". |
| `port is already allocated` (8000 or 5432) | Something else uses the port. Stop it, or change the host port in `docker-compose.yml` under `ports:`. |
| `could not connect to server` on migrate | Postgres is still booting. Wait 5–10 seconds, retry. |
| `Dependency on app with no migrations: accounts` | Stale `pgdata` volume. Run "First run after pulling this repo" above. |
| `no such table: accounts_user` | You forgot to run `migrate`. Run it. |
| Tests take ~2 minutes | Normal — Django 5.2 uses a high PBKDF2 iteration count in tests. |
| `docker compose down -v` wiped my demo data | That's what `-v` does. Re-run `docker compose up --build && migrate && seed`. |
| `Cannot delete: job has applications or slots` (409) | This is correct behavior. Delete applications first, or use a fresh seed. |
| `Slot already booked` (409) | Another candidate booked first. Pick a different slot, or re-seed. |

---

## Default ports and volumes

| Service | Host port | Container port |
|---|---|---|
| Web (Django) | 127.0.0.1:8000 | 8000 |
| Database (Postgres) | 127.0.0.1:5432 | 5432 |

| Volume | Purpose |
|---|---|
| `project_pgdata` | PostgreSQL data directory — contains all user/job/application/booking rows |

---

## Environment variables

All defaults work for local development. To override, create a `.env` file in the project root (copy `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DB_NAME` | `honk` | Postgres database name |
| `DB_USER` | `honk` | Postgres username |
| `DB_PASSWORD` | `honk_local_dev` | Postgres password (local only) |
| `DB_HOST` | `db` | Postgres host (set by Docker Compose networking) |
| `DB_PORT` | `5432` | Postgres port |
| `DJANGO_SECRET_KEY` | random per start | Django secret key |
| `DJANGO_DEBUG` | `1` in compose | Set to `1` to enable DEBUG |

`.env` is in `.gitignore` and must never be committed. `.env.example` contains placeholders only.