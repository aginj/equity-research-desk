"""Alembic environment: reuse the application's engine so URL handling lives in one place."""

from __future__ import annotations

from sqlmodel import SQLModel

import app.db  # noqa: F401  (registers tables on SQLModel.metadata)
from alembic import context
from app.store import get_engine

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    engine = get_engine()
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # `init_db()` passes an open connection so startup migrations share the app engine.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = get_engine()
    with engine.connect() as conn:
        _run(conn)


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
