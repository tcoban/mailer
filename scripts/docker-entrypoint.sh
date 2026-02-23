#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for database to be ready..."
# Use PG connection vars from environment
MAX_RETRIES=30
COUNT=0
until pg_isready -h "$POSTGRES_SERVER" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" || [ $COUNT -eq $MAX_RETRIES ]; do
  echo "Database not ready, waiting..."
  sleep 2
  COUNT=$((COUNT + 1))
done

if [ $COUNT -eq $MAX_RETRIES ]; then
  echo "Database failed to become ready in time."
  exit 1
fi

echo "Running migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"

