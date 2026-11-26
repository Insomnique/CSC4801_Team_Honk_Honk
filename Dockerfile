FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_NAME=honk \
    DB_USER=honk \
    DB_PASSWORD=honk_local_dev \
    DB_HOST=localhost \
    DB_PORT=5432 \
    PGDATA=/var/lib/postgresql/data

# PostgreSQL runs inside this same container, so `docker build` + `docker run` is the whole environment
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Strip Windows line endings in case the script was checked out with CRLF
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "--insecure", "0.0.0.0:8000"]
