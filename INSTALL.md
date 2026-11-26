# INSTALL

The whole environment (Django app **and** its PostgreSQL database) is built from the repository's `Dockerfile`. No `docker compose`, no other image, and no secrets are needed.

## Prerequisites
- Docker Desktop (or Docker Engine) 24 or newer, running ("Engine running")
- Port 8000 free on localhost
- No Python or PostgreSQL install required on the host

## 1. Build the image

```bash
docker build -t team-honk .
```

The first build downloads `python:3.12.8-slim` and installs PostgreSQL inside the image; it takes 2–5 minutes. Later builds reuse the cache.

## 2. Start the container

```bash
docker run -d --name team-honk -p 127.0.0.1:8000:8000 -v honk_pgdata:/var/lib/postgresql/data team-honk
```

On start, `docker-entrypoint.sh` starts PostgreSQL inside the container, creates the `honk` database user and database if they don't exist yet, then starts Django. Wait until the log shows the server is up:

```bash
docker logs team-honk
```
```
Starting development server at http://0.0.0.0:8000/
```

The `-v honk_pgdata:...` part keeps your data in a Docker volume, so it survives stopping and removing the container. It is optional: without it, data lives inside the container and is lost when the container is removed.

## 3. Run migrations

```bash
docker exec team-honk python manage.py migrate
```

Expected: all migrations apply cleanly, ending with `Applying jobs.0005_slot_duration_constraints... OK`.

## 4. Seed deterministic demo data

```bash
docker exec team-honk python manage.py seed
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

## 5. Run the app

Open http://127.0.0.1:8000

You should see the home page (the root URL redirects to `/accounts/home/`). Click **Log in** and use any demo account above.

## 6. Run tests

```bash
docker exec team-honk python manage.py test accounts jobs -v 2
```

Expected: **107 tests, OK.** The command exits nonzero on failure. Tests create a separate `test_honk` database and destroy it afterward — your real data is untouched. Takes ~2 minutes (Django 5.2's PBKDF2 iteration count).

## Stop and start again

```bash
docker stop team-honk
docker start team-honk
```

Your users, jobs, applications and bookings are kept.

## After changing the code

The code is copied into the image at build time, so rebuild and recreate the container (data in `honk_pgdata` is kept):

```bash
docker rm -f team-honk
docker build -t team-honk .
docker run -d --name team-honk -p 127.0.0.1:8000:8000 -v honk_pgdata:/var/lib/postgresql/data team-honk
docker exec team-honk python manage.py migrate
```

## Reset the database (wipes all data)

```bash
docker rm -f team-honk
docker volume rm honk_pgdata
docker run -d --name team-honk -p 127.0.0.1:8000:8000 -v honk_pgdata:/var/lib/postgresql/data team-honk
docker exec team-honk python manage.py migrate
docker exec team-honk python manage.py seed
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` / `cannot connect to the Docker daemon` | Docker Desktop isn't running. Open it and wait for "Engine running". |
| `port is already allocated` (8000) | Something else uses port 8000. Stop it, or use `-p 127.0.0.1:8080:8000` and open http://127.0.0.1:8080 |
| `Conflict. The container name "/team-honk" is already in use` | A container from an earlier run exists. Run `docker rm -f team-honk`, then `docker run` again. |
| `connection refused` / `could not connect to server` on migrate | PostgreSQL is still starting. Wait until `docker logs team-honk` shows `Starting development server`, then retry. |
| `relation "jobs_booking" does not exist` | You skipped `migrate`. Run step 3, then step 4. |
| `docker-entrypoint.sh: not found` or `bad interpreter` | The script was saved with Windows line endings before `.gitattributes` existed. Rebuild with `docker build -t team-honk .` (the build strips them). |
| Tests take ~2 minutes | Normal — Django 5.2 uses a high PBKDF2 iteration count. |
| `Cannot delete: job has applications or slots` (409) | Correct behavior. Delete applications first, or re-seed. |
| `Slot already booked` (409) | Another candidate booked first. Pick a different slot, or re-seed. |

---

## Ports and volumes

| Service | Host | Container |
|---|---|---|
| Web (Django) | 127.0.0.1:8000 | 8000 |
| Database (PostgreSQL) | not exposed | `localhost:5432` inside the container |

| Volume | Purpose |
|---|---|
| `honk_pgdata` (optional) | PostgreSQL data directory, mounted at `/var/lib/postgresql/data` |

---

## Environment variables

The defaults are set in the `Dockerfile` and work as they are. To override one, pass `-e NAME=value` to `docker run`.

| Variable | Default | Purpose |
|---|---|---|
| `DB_NAME` | `honk` | PostgreSQL database name |
| `DB_USER` | `honk` | PostgreSQL user, created on first start |
| `DB_PASSWORD` | `honk_local_dev` | PostgreSQL password (local placeholder, not a real secret) |
| `DB_HOST` | `localhost` | PostgreSQL runs inside the same container |
| `DB_PORT` | `5432` | PostgreSQL port inside the container |
| `DJANGO_SECRET_KEY` | random per start | Django secret key. If unset, a new random key is generated each time the server starts, so restarting the container logs everyone out. |
| `DJANGO_DEBUG` | off | Set to `1` to enable Django's debug pages |

`.env` is in `.gitignore` and must never be committed. `.env.example` contains placeholders only.