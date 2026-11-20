# INSTALL

## Prerequisites
- Docker Desktop (with Docker Compose v2)
- Ports 8000 and 5432 free on localhost

## Build and start
```bash
docker compose up --build
```

## Run migrations (in a second terminal)
```bash
docker compose exec web python manage.py migrate
```

## Run the app
Open http://127.0.0.1:8000

## Run tests
```bash
docker compose exec web python manage.py test
```

## Stop
```bash
docker compose down
```

## Reset the database (wipes all data)
```bash
docker compose down -v
docker compose up --build
docker compose exec web python manage.py migrate
```