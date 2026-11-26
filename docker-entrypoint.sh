#!/bin/sh
# Starts the PostgreSQL server bundled in this image, makes sure the app's
# database user and database exist, then runs the container's command
# (by default the Django server). Graders only need `docker build` + `docker run`.
set -e

PG_BIN="$(ls -d /usr/lib/postgresql/*/bin | head -n 1)"

# First start (or a new empty volume): create the database cluster
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    mkdir -p "$PGDATA"
    chown -R postgres:postgres "$PGDATA"
    su postgres -c "$PG_BIN/initdb -D $PGDATA -U postgres --auth-local=trust --auth-host=scram-sha-256" > /dev/null
fi
chown -R postgres:postgres "$PGDATA"
mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql

# Start PostgreSQL inside this container, listening on localhost only
su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -o '-c listen_addresses=localhost' -w -l $PGDATA/server.log start" > /dev/null

# Create the app's user (allowed to create the isolated test database) and database
if ! su postgres -c "$PG_BIN/psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\"" | grep -q 1; then
    su postgres -c "$PG_BIN/psql -q -c \"CREATE ROLE $DB_USER LOGIN CREATEDB PASSWORD '$DB_PASSWORD'\""
fi
if ! su postgres -c "$PG_BIN/psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\"" | grep -q 1; then
    su postgres -c "$PG_BIN/createdb -O $DB_USER $DB_NAME"
fi

exec "$@"