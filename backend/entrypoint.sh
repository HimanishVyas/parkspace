#!/bin/sh
# Applies migrations, then starts the API. Used as the container command in
# docker-compose so a clean `docker-compose up` yields a working database.
set -e

echo "Waiting for database..."
python - <<'PY'
import asyncio, sys
import asyncpg
from app.core.config import settings

async def wait():
    dsn = settings.database_url.replace("+asyncpg", "")
    for attempt in range(60):
        try:
            conn = await asyncpg.connect(dsn)
            await conn.close()
            return
        except Exception as exc:
            if attempt % 5 == 0:
                print(f"  ...not ready ({exc.__class__.__name__})")
            await asyncio.sleep(1)
    print("Database did not become ready in time", file=sys.stderr)
    sys.exit(1)

asyncio.run(wait())
PY

echo "Running migrations..."
alembic upgrade head

echo "Seeding platform defaults..."
python -m app.cli seed

exec "$@"
