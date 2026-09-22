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

# Migrations and seeding are a deploy step, not a start-up step: several
# replicas starting together would otherwise race each other through them.
# Compose runs a single api container, so the default keeps `docker-compose up`
# working end to end; set RUN_MIGRATIONS=false everywhere else and run
# `alembic upgrade head` once, before the new version starts rolling out.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Running migrations..."
    alembic upgrade head

    echo "Seeding platform defaults..."
    python -m app.cli seed
else
    echo "Skipping migrations (RUN_MIGRATIONS=false)"
fi

exec "$@"
