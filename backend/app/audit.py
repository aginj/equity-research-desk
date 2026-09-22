"""Admin audit log helpers."""

from __future__ import annotations

import json
import uuid

from sqlmodel import Session, col, select

from app.db import AuditLogRow
from app.store import get_engine


def write_audit(
    actor_id: str,
    action: str,
    target: str = "",
    detail: dict | None = None,
) -> None:
    with Session(get_engine()) as session:
        session.add(
            AuditLogRow(
                id=uuid.uuid4().hex[:16],
                actor_id=actor_id[:64],
                action=action[:64],
                target=(target or "")[:200],
                detail_json=json.dumps(detail, separators=(",", ":")) if detail else None,
            )
        )
        session.commit()


def list_audit(limit: int = 100) -> list[AuditLogRow]:
    with Session(get_engine()) as session:
        return list(
            session.exec(
                select(AuditLogRow).order_by(col(AuditLogRow.at).desc()).limit(limit)
            ).all()
        )


def serialize_audit(row: AuditLogRow) -> dict:
    detail = None
    if row.detail_json:
        try:
            detail = json.loads(row.detail_json)
        except json.JSONDecodeError:
            detail = row.detail_json
    return {
        "id": row.id,
        "at": row.at.isoformat() if row.at else None,
        "actor_id": row.actor_id,
        "action": row.action,
        "target": row.target,
        "detail": detail,
    }
