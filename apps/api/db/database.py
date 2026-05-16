from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.models.incident import Base


DATABASE_URL = "sqlite+aiosqlite:///./data/sentinal.db"

Path("data").mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_incident_workflow_columns(conn)


async def _ensure_incident_workflow_columns(conn) -> None:
    """Add Stage 2.5 columns to existing SQLite databases.

    SQLAlchemy create_all creates missing tables but intentionally does not alter
    existing ones. This keeps local development smooth until formal migrations
    are introduced.
    """

    result = await conn.execute(text("PRAGMA table_info(incident_workflows)"))
    existing_columns = {row[1] for row in result.fetchall()}
    columns = {
        "findings": "JSON NOT NULL DEFAULT '{}'",
        "fix_proposal": "TEXT",
        "validation_passed": "BOOLEAN NOT NULL DEFAULT 0",
        "max_retries": "INTEGER NOT NULL DEFAULT 2",
        "error": "TEXT",
        "pr_url": "VARCHAR(2048)",
        "trace_id": "VARCHAR(64)",
        "dedupe_key": "VARCHAR(255)",
    }

    for column_name, column_definition in columns.items():
        if column_name not in existing_columns:
            await conn.execute(
                text(
                    f"ALTER TABLE incident_workflows "
                    f"ADD COLUMN {column_name} {column_definition}"
                )
            )

    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_incident_workflows_dedupe_key "
            "ON incident_workflows (dedupe_key) "
            "WHERE dedupe_key IS NOT NULL"
        )
    )
