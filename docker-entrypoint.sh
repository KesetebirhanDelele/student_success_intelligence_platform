#!/bin/sh
set -e

# If the database has tables from a legacy init_db() startup (before Alembic was
# introduced as the schema manager), stamp the Alembic version at head first so
# that upgrade head becomes a no-op instead of a fatal DDL conflict.
python - <<'PYEOF'
import asyncio, os, subprocess
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    e = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with e.connect() as c:
            alembic_exists = (await c.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name='alembic_version' AND table_schema='public')"
            ))).scalar()
            tables_exist = (await c.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name='ai_chatbot_triggerdata' AND table_schema='public')"
            ))).scalar()
    finally:
        await e.dispose()

    if tables_exist and not alembic_exists:
        # Stamp at 0001 (not head) — init_db() only created the Phase 1 baseline
        # tables. Stamping at head would skip warehouse/config migrations 0002-0003.
        print("Legacy init_db database detected — stamping Alembic at 0001")
        subprocess.run(["alembic", "stamp", "0001"], check=True)

asyncio.run(main())
PYEOF

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --log-level info
