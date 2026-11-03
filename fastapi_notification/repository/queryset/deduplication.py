"""Atomic claiming and reuse of notification idempotency keys."""

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.base import utcnow
from fastapi_notification.models.deduplication import NotificationDeduplication
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.state import insert_if_absent
from fastapi_notification.utils.sqlalchemy import execute_dml


async def _get_key_record(
    session: AsyncSession, scope: str, key: str
) -> Optional[NotificationDeduplication]:
    """Read a key record, using a locking/current read where supported."""
    statement = (
        select(NotificationDeduplication)
        .where(
            NotificationDeduplication.scope == scope,
            NotificationDeduplication.deduplication_key == key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _get_linked_notification(
    session: AsyncSession, notification_id: int
) -> Optional[Notification]:
    """Read the linked notification as a current row on locking-read dialects.

    MySQL's default REPEATABLE READ isolation can hide a concurrently committed
    notification from a plain ``Session.get`` after the ledger row was observed through
    ``SELECT FOR UPDATE``. Using the same current-read semantics avoids treating a valid
    key as orphaned.
    """
    statement = (
        select(Notification)
        .where(Notification.id == notification_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def claim_deduplication_key(
    session: AsyncSession,
    notification: Notification,
    *,
    scope: str,
    key: str,
    expires_at: Optional[datetime],
) -> Tuple[Notification, bool]:
    """Claim a scoped key or return the notification already associated with it.

    The unique ``(scope, key)`` constraint is the concurrency arbiter. SQLite
    and PostgreSQL use the shared native-upsert helper; other dialects use its
    savepoint-backed fallback. Expired records are reclaimed with a conditional
    UPDATE, so concurrent retries cannot both replace the same expired key.

    Returns:
        Tuple[Notification, bool]: The notification to return and whether the
        supplied notification successfully claimed the key.
    """
    now = utcnow()
    if expires_at is not None:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("Deduplication key expiry must be timezone-aware.")
        if expires_at <= now:
            raise ValueError("Deduplication key expiry must be in the future.")
    values = {
        "scope": scope,
        "deduplication_key": key,
        "notification_id": notification.id,
        "expires_at": expires_at,
        "created_at": now,
    }

    # A bounded retry handles the rare case where a key is deleted between a
    # conflicting insert and the subsequent current read.
    for _ in range(5):
        record = await _get_key_record(session, scope, key)
        if record is not None:
            is_active = record.expires_at is None or record.expires_at > now
            if is_active:
                existing = await _get_linked_notification(
                    session, record.notification_id
                )
                if existing is not None:
                    return existing, False

                # Recover safely from an orphan left by a database that had
                # foreign-key enforcement disabled during an external deletion.
                await session.delete(record)
                await session.flush()
                continue

            # Only a finite, elapsed expiry can be reclaimed. NULL represents
            # an indefinitely retained key and is never eligible for reuse.
            result = await execute_dml(
                session,
                update(NotificationDeduplication)
                .where(
                    NotificationDeduplication.id == record.id,
                    NotificationDeduplication.expires_at.is_not(None),
                    NotificationDeduplication.expires_at <= now,
                )
                .values(
                    notification_id=notification.id,
                    expires_at=expires_at,
                    created_at=now,
                )
                .execution_options(synchronize_session=False),
            )
            if result.rowcount == 1:
                # Keep a previously loaded ledger object coherent when the
                # expired key is reclaimed inside the same session.
                record.notification_id = notification.id
                record.expires_at = expires_at
                record.created_at = now
                await session.flush()
                return notification, True
            continue

        _, inserted = await insert_if_absent(
            session,
            NotificationDeduplication,
            values,
            ("scope", "deduplication_key"),
        )
        if inserted:
            return notification, True

    raise RuntimeError(
        "Could not claim notification deduplication key after concurrent retries."
    )


__all__ = ["claim_deduplication_key"]
