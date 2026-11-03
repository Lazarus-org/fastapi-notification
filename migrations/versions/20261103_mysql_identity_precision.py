"""Reference MySQL 8.4 migration; attach to the host application's revision chain.

Run with writers stopped and a verified backup: MySQL DDL implicitly commits.
No automatic migration is performed by package import or installation.
"""

from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects import mysql

revision = "notification_mysql_841"
down_revision = None
branch_labels = ("notification_mysql",)
depends_on = None

IDENTIFIERS = {
    "notification_recipient": ("recipient_id",),
    "notification_seen": ("user_id",),
    "deleted_notifications": ("user_id",),
    "notification_group": ("group_id",),
    "notification_preference": ("user_id",),
    "notification_quiet_hours": ("user_id",),
    "notification_digest_schedule": ("user_id",),
    "notification_digest_batch": ("user_id",),
    "notification_deduplication": ("scope", "deduplication_key"),
}
DATETIMES = {
    "notification_digest_schedule": (
        "next_run_at",
        "last_run_at",
        "created_at",
        "updated_at",
    ),
    "notification_preference": ("updated_at",),
    "notification_quiet_hours": ("updated_at",),
    "notification_template": ("updated_at",),
    "notification": ("expires_at",),
    "notification_digest_batch": (
        "scheduled_for",
        "period_start",
        "period_end",
        "claimed_at",
        "available_at",
        "created_at",
        "sent_at",
    ),
    "notification_deduplication": ("expires_at", "created_at"),
}
TIMES = {
    "notification_digest_schedule": ("local_time",),
    "notification_quiet_hours": ("start_time", "end_time"),
}
BASELINE = "utf8mb4_0900_ai_ci"
TARGET = "utf8mb4_0900_bin"


def _preflight(downgrade):
    connection = op.get_bind()
    if connection.dialect.name != "mysql":
        return []
    version = connection.scalar(text("SELECT VERSION()"))
    if not version.startswith("8.4."):
        raise RuntimeError("This reference revision supports MySQL 8.4 only.")
    inspector = inspect(connection)
    changes = []
    for mapping, kind in (
        (IDENTIFIERS, "identity"),
        (DATETIMES, "datetime"),
        (TIMES, "time"),
    ):
        for table, names in mapping.items():
            columns = {
                column["name"]: column for column in inspector.get_columns(table)
            }
            for name in names:
                column = columns[name]
                current = column["type"]
                if kind == "identity":
                    collation = connection.scalar(
                        text(
                            "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:table AND COLUMN_NAME=:name"
                        ),
                        {"table": table, "name": name},
                    )
                    if current.length != 255 or collation not in (BASELINE, TARGET):
                        raise RuntimeError(
                            f"Customized identifier column: {table}.{name}"
                        )
                    target = mysql.VARCHAR(
                        255,
                        charset="utf8mb4",
                        collation=BASELINE if downgrade else TARGET,
                    )
                    if downgrade and connection.scalar(
                        text(
                            f"SELECT COUNT(*) FROM (SELECT `{name}` COLLATE {BASELINE} "
                            f"FROM `{table}` GROUP BY `{name}` COLLATE {BASELINE} "
                            f"HAVING COUNT(DISTINCT `{name}` COLLATE {TARGET}) > 1) AS collisions"
                        )
                    ):
                        raise RuntimeError(
                            f"Rollback would alias identifiers: {table}.{name}"
                        )
                else:
                    factory = mysql.DATETIME if kind == "datetime" else mysql.TIME
                    if not isinstance(current, factory) or (current.fsp or 0) not in (
                        0,
                        6,
                    ):
                        raise RuntimeError(
                            f"Customized temporal column: {table}.{name}"
                        )
                    target = factory(fsp=0 if downgrade else 6)
                    if downgrade and connection.scalar(
                        text(
                            f"SELECT COUNT(*) FROM `{table}` WHERE MICROSECOND(`{name}`) <> 0"
                        )
                    ):
                        raise RuntimeError(
                            f"Rollback would lose microseconds: {table}.{name}"
                        )
                changes.append((table, name, column, target))
    return changes


def _apply(downgrade):
    # All compatibility and data-loss checks finish before the first implicit commit.
    for table, name, column, target in _preflight(downgrade):
        op.alter_column(
            table,
            name,
            type_=target,
            existing_type=column["type"],
            existing_nullable=column["nullable"],
            existing_server_default=column["default"],
            existing_comment=column.get("comment"),
        )


def upgrade():
    _apply(False)


def downgrade():
    _apply(True)
