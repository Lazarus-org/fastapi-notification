# fastapi-notification

[![License](https://img.shields.io/github/license/lazarus-org/fastapi-notification)](https://github.com/lazarus-org/fastapi-notification/blob/main/LICENCE)
[![PyPI release](https://img.shields.io/pypi/v/fastapi-notification)](https://pypi.org/project/fastapi-notification/)
[![Documentation](https://img.shields.io/readthedocs/fastapi-notification)](https://fastapi-notification.readthedocs.io/en/latest/)
[![Pylint](https://img.shields.io/badge/pylint-10/10-brightgreen?logo=python&logoColor=blue)](https://www.pylint.org/)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/lazarus-org/fastapi-notification)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/fastapi-notification)](https://pypi.org/project/fastapi-notification/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=yellow)](https://github.com/pre-commit/pre-commit)
[![Open Issues](https://img.shields.io/github/issues/lazarus-org/fastapi-notification)](https://github.com/lazarus-org/fastapi-notification/issues)
[![Last Commit](https://img.shields.io/github/last-commit/lazarus-org/fastapi-notification)](https://github.com/lazarus-org/fastapi-notification/commits/main)

`fastapi-notification` is a FastAPI package developed by Lazarus, designed to simplify and optimize the process of managing notifications through various APIs. Install it, supply a database session and a way to identify the current user, and you have a fully featured notification API that you can then tailor to your needs.

It is built on async SQLAlchemy 2.0 and Pydantic v2, and it is the FastAPI counterpart to Lazarus's [`dj-notification-api`](https://github.com/lazarus-org/dj-notification-api) package for Django.

## Highlights

- **Notification inbox and activity history** — unseen notifications, seen activity, aggregate read/unread counts, and a bounded recent preview.
- **Notification expiration** — optional timezone-aware expiry with explicit, retention-controlled cleanup.
- **Structured notification taxonomy** — independent status, category and priority fields; built-in categories can be extended with application-defined keys.
- **Idempotent notification creation** — optional scoped deduplication keys
  prevent duplicate notifications from retried jobs, callbacks and event
  consumers; expired keys can be safely reused.
- **Anything can be an actor** — notifications reference an actor, a target and an action object generically, so any of your own models can take those roles. Generic relations support integer, UUID and string primary keys.
- **Addressed to users or groups** — a notification reaches named recipients, every member of a group, or both.
- **Soft and hard deletion** — clearing a notification hides it for one user while leaving it intact for the others; permanent deletion is available to administrators and off by default.
- **Configurable throughout** — serializers, fields, pagination, throttling, filtering and permissions are all driven from settings, and routes you switch off are never registered at all.
- **Validated at startup** — a misconfiguration raises when the router is built, listing every problem at once, rather than failing on the first request.

## Supported Versions

| FastAPI | SQLAlchemy | Python                        |
|---------|------------|-------------------------------|
| 0.110+  | 2.0        | 3.9, 3.10, 3.11, 3.12, 3.13   |

Any database with an async SQLAlchemy driver works; PostgreSQL (`asyncpg`), MySQL (`aiomysql`) and SQLite (`aiosqlite`) are the common choices.

## Documentation

The full documentation is available at [fastapi-notification.readthedocs.io](https://fastapi-notification.readthedocs.io), organised into:

- [Quick Start](https://fastapi-notification.readthedocs.io/en/latest/quick_start.html)
- [API Guide](https://fastapi-notification.readthedocs.io/en/latest/api_guide.html)
- [Usage](https://fastapi-notification.readthedocs.io/en/latest/usage.html)
- [Settings](https://fastapi-notification.readthedocs.io/en/latest/settings.html)
- [Roles](https://fastapi-notification.readthedocs.io/en/latest/roles.html)
- [Contributing](https://fastapi-notification.readthedocs.io/en/latest/contributing.html)

---

# Quick Start

## 1. Install the Package

**Option 1: Using `pip` (Recommended)**

```bash
$ pip install fastapi-notification
```

**Option 2: Using `Poetry`**

```bash
$ poetry add fastapi-notification
```

**Option 3: Using `pipenv`**

```bash
$ pipenv install fastapi-notification
```

You will also need an async database driver, for example `asyncpg` for PostgreSQL or `aiosqlite` for SQLite.

## 2. Create the Tables

The core notification tables live on the package declarative `Base`. They do not reference or require a package-owned user or group table. Create the notification tables from that metadata, or point Alembic at it if you manage migrations.

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fastapi_notification import Base

engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/app")
Session = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
```

If you want to use the optional example `User`, `Group`, and `Permission` models, create their separate metadata as well:

```python
from fastapi_notification import AuthBase

async with engine.begin() as connection:
    await connection.run_sync(AuthBase.metadata.create_all)
```

Applications with their own identity models should omit `AuthBase.metadata.create_all`. The default `IdentityAdapter` does not query package-owned user or group tables. To use the optional example models, configure `IDENTITY_ADAPTER="fastapi_notification.identity.BuiltInIdentityAdapter"`. The notification tables can also be incorporated into an application's Alembic environment as ordinary SQLAlchemy metadata.

## 3. Supply the Database and Authentication Dependencies

The package does not own your database session or authentication. Supply both, then configure an identity adapter so the package can work with your application's user and group models.

```python
from typing import Any, AsyncIterator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification import create_router


async def get_session() -> AsyncIterator[AsyncSession]:
    async with Session() as session:
        yield session


async def get_current_user() -> Any:
    # Return the user making the request, however your application
    # authenticates. Returning None results in a 401.
    ...


app = FastAPI()
app.include_router(
    create_router(
        session_dependency=get_session,
        current_user_dependency=get_current_user,
    )
)
```

By default, the adapter expects the user object to expose `id`, `is_staff`, `is_superuser`, and `groups`. It returns ID-only identity references and does not query user or group tables. If your model uses different fields or stores memberships separately, configure an `IdentityAdapter` subclass. User and group identifiers are stored as opaque strings, so integer, UUID, and string primary keys are supported.

Instead of passing the dependencies, you may override the package's placeholders through FastAPI's `dependency_overrides`:

```python
from fastapi_notification.api.dependencies import get_current_user, get_session

app.dependency_overrides[get_session] = my_session_dependency
app.dependency_overrides[get_current_user] = my_user_dependency
```

## 4. Integrate Your User and Group Models

The package does not create foreign keys to your authentication tables. Recipient, seen-by, deleted-by, and group associations store normalized identity identifiers. The optional built-in auth models are kept on `AuthBase`; the core notification schema remains on `Base`. The default `IdentityAdapter` does not require or query the optional auth tables.

For a host application with non-standard identity fields, subclass `IdentityAdapter` and configure it before creating the router:

```python
from typing import Any, Mapping, Sequence

from sqlalchemy import String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification import IdentityAdapter, configure
from myapp.models import AppGroup, AppUser


class AppIdentityAdapter(IdentityAdapter):
    user_id_attribute = "uuid"
    group_id_attribute = "slug"
    user_groups_attribute = "groups"
    staff_attribute = "is_admin"
    superuser_attribute = "is_root"

    async def resolve_users(
        self, session: AsyncSession, user_ids: Sequence[str]
    ) -> Mapping[str, Any]:
        result = await session.scalars(
            select(AppUser).where(cast(AppUser.uuid, String).in_(list(user_ids)))
        )
        return {str(user.uuid): user for user in result.all()}

    async def resolve_groups(
        self, session: AsyncSession, group_ids: Sequence[str]
    ) -> Mapping[str, Any]:
        result = await session.scalars(
            select(AppGroup).where(AppGroup.slug.in_(list(group_ids)))
        )
        return {str(group.slug): group for group in result.all()}


configure(IDENTITY_ADAPTER=AppIdentityAdapter)
```

If your application stores group membership in a separate association model rather than `user.groups`, override `get_user_group_ids(session, user)` and return the normalized group IDs. If the base adapter's lightweight ID-only representation is sufficient, you do not need to override `resolve_users` or `resolve_groups`. Configure `USER_SERIALIZER_FIELDS` and `GROUP_SERIALIZER_CLASS` to control how resolved host objects appear in API responses.

## 5. (Optional) Configure the Package

Every setting has a working default, so this step is optional. Settings can be registered from Python:

```python
from fastapi_notification import configure

configure(
    API_INCLUDE_HARD_DELETE=True,
    AUTHENTICATED_USER_THROTTLE_RATE="60/minute",
)
```

or supplied through the environment:

```bash
export FASTAPI_NOTIFICATION_API_INCLUDE_HARD_DELETE=true
export FASTAPI_NOTIFICATION_AUTHENTICATED_USER_THROTTLE_RATE="60/minute"
```

Configure the package **before** building the router: the router reads its settings when it is created, and a route disabled in settings is never registered.

## 6. Create Notifications

```python
from datetime import datetime, timedelta, timezone

from fastapi_notification import NotificationDataAccessLayer

async with Session() as session:
    dal = NotificationDataAccessLayer(session)

    await dal.create_notification(
        verb="liked your post",
        actor=user,
        recipients=[other_user],
        groups=[moderators],
        status="INFO",
        category="orders",
        priority="high",
        public=True,
        target=post,
        link="https://example.com/posts/123",
        is_sent=True,
        data={"post_id": 123},
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    await session.commit()
```

Only `verb` and `actor` are required. With no `description`, one is generated from the actor, the verb, and the target or action object.

A notification is only visible to its recipients once `is_sent` is true. Create it unsent and call `mark_all_as_sent()` later if you want to stage delivery.

## Categories and Priorities

`status`, `category` and `priority` describe different things:

- `status` describes the notification's state or nature (`INFO`, `WARNING`, `ERROR`, etc.).
- `category` groups notifications by application domain. Built-in keys are `general`, `system`, `security`, `social`, `financial`, `orders` and `marketing`; custom lowercase keys such as `com.example.billing` are also supported. The default is `general`.
- `priority` describes urgency and accepts `low`, `normal`, `high` or `urgent`. The default is `normal`.

Priority is not inferred from status. For example, an `ERROR` notification can have `normal` priority, while an `INFO` notification can be `urgent` if the application requires immediate attention.

Filter inboxes with `category` and `priority`, for example `/notifications/?category=orders&priority=urgent`. To sort by urgency, use `ordering=-priority`; equal priorities are ordered newest first. The summary endpoint also returns `by_category` and `by_priority` breakdowns, each split into `total`, `unread` and `read` counts. Preview items include both fields.

Any object can be the `actor`, `target` or `action_object`, as long as its model is registered:

```python
from fastapi_notification import register_content_model


@register_content_model
class Post(Base):
    __tablename__ = "posts"
    ...
```

## Notification Delivery Preferences

Users can manage their own category/channel delivery rules through the API or
``NotificationPreferenceDataAccessLayer``. Rules support ``*`` wildcards and
are evaluated from most-specific to least-specific. If no rule matches, the
channel is enabled by default.

```python
from fastapi_notification import NotificationPreferenceDataAccessLayer

preferences = NotificationPreferenceDataAccessLayer(session)
await preferences.set_preference(
    user, category="*", channel="email", enabled=False
)
await preferences.set_preference(
    user, category="security", channel="email", enabled=True
)

allowed = await preferences.is_enabled(
    user, category="security", channel="email"
)  # True
await session.commit()
```

The authenticated API exposes ``GET /notifications/preferences/`` to list the
current user's rules, ``PUT`` on the same path to create/update one rule, and
``DELETE`` with ``category`` and ``channel`` query parameters to reset a rule.
When no stored override matches, the effective default is enabled; no synthetic
default row is written to the database.

Preferences are delivery policy, not inbox visibility: they do not delete, hide
or mutate notifications already stored in the inbox. Delivery integrations
should consult ``is_enabled`` before dispatching email, SMS, push, webhook or
other channel messages. The package provides the preference store and policy
resolver; it does not yet send those external messages itself.

## 7. Verify

```bash
$ curl -H "Authorization: Bearer <token>" http://localhost:8000/notifications/
```

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "title": "alice liked your post my-first-post 2 minutes ago",
      "id": 1,
      "description": "alice liked your post my-first-post",
      "status": "INFO",
      "category": "orders",
      "priority": "high",
      "link": "https://example.com/posts/123",
      "timestamp": "2026-07-20T12:00:00Z",
      "expires_at": null
    }
  ]
}
```

The interactive documentation at `/docs` lists every route the package registered, which is a quick way to confirm your settings took effect.

---

# API Overview

## Notifications API

| Method | Path                                      | Description                                    |
|--------|-------------------------------------------|------------------------------------------------|
| GET    | `/notifications/`                        | List the notifications you have not seen yet.  |
| GET    | `/notifications/summary/`                | Return total, unread and read notification counts. |
| GET    | `/notifications/preview/`                | Preview recent notifications, including read state. |
| POST   | `/notifications/mark_all_as_seen/`       | Mark every unseen notification as seen.        |
| GET    | `/notifications/{id}/`                   | Retrieve one unseen notification (read-only).  |
| POST   | `/notifications/{id}/mark_as_seen/`      | Mark one notification as seen.                 |
| POST   | `/notifications/{id}/mark_as_unseen/`    | Return one notification to the unseen inbox.   |
| GET    | `/notifications/preferences/`            | List the current user's delivery preferences.  |
| PUT    | `/notifications/preferences/`            | Create or update one delivery preference.      |
| DELETE | `/notifications/preferences/`            | Reset one preference to inherited defaults.    |

Retrieval, summary and preview are read-only. The summary counts sent
notifications addressed to the current user or their groups, excluding items
the user has cleared. It returns ``total``, ``unread`` and ``read`` counts plus
``by_category`` and ``by_priority`` breakdowns with the same three counts for
each key. The preview returns the most recent visible notifications (5 by
default, at most 20), including ``status``, ``category``, ``priority``, an
``is_seen`` flag and nullable ``expires_at`` for each item.
Both endpoints honor inbox
filter conditions; preview is always ordered newest first. Use the explicit
POST action to mark a notification as seen;
repeating the action is harmless. Use ``POST /notifications/{id}/mark_as_unseen/``
to remove only the current user's seen state and return the notification to
their unseen inbox. The operation is idempotent, does not affect other
recipients, and cannot restore an item that the user has cleared.

## Activities API

| Method | Path                                         | Description                                    |
|--------|----------------------------------------------|------------------------------------------------|
| GET    | `/activities/`                               | List the notifications you have already seen.  |
| DELETE | `/activities/clear_activities/`              | Soft-delete every activity.                    |
| DELETE | `/activities/delete_activities/`             | Permanently delete every activity. Admin only. |
| GET    | `/activities/{id}/`                           | Retrieve one activity (read-only).             |
| DELETE | `/activities/{id}/clear_notification/`       | Soft-delete one activity.                      |
| DELETE | `/activities/{id}/delete_notification/`      | Permanently delete one activity. Admin only.   |

Routes are registered only when their setting allows it. With `API_INCLUDE_HARD_DELETE` off, for instance, the two delete routes do not exist: they return 404 and never appear in the OpenAPI schema.

## Pagination

Listings are wrapped in an envelope and paged with `limit` and `offset`:

```json
{
  "count": 42,
  "next": "http://localhost:8000/notifications/?limit=10&offset=10",
  "previous": null,
  "results": []
}
```

`limit` defaults to 10 and is clamped between 1 and 100. A limit above the maximum is capped rather than rejected.

## Filtering, Ordering and Search

| Parameter          | Effect                                                           |
|--------------------|------------------------------------------------------------------|
| `group__id`        | Only notifications addressed to this group.                      |
| `recipient__id`    | Only notifications addressed to this recipient.                  |
| `status`           | Only notifications with this status.                             |
| `public`           | Only public, or only private, notifications.                     |
| `timestamp_after`  | Only notifications at or after this time.                        |
| `timestamp_before` | Only notifications at or before this time.                       |
| `search`           | Case-insensitive match across `API_SEARCH_FIELDS`.               |
| `category`         | Filter by a built-in or custom category key. |
| `priority`         | Filter by `low`, `normal`, `high` or `urgent`. |
| `ordering`         | Order by a field in `API_ORDERING_FIELDS`; prefix `-` to reverse. Use `-priority` for urgent-first ordering. |

Ordering is restricted to the configured fields, so a client cannot sort by an arbitrary column.

## Expiration and Retention

A notification may have an optional timezone-aware ``expires_at`` instant. At
``expires_at`` itself it is considered expired. Expired notifications are
excluded from recipient inboxes, activity history, summaries, previews, and
normal unsent delivery queries. Direct and group audiences follow the same rule.
Raw/all and deleted-history DAL queries can still include expired rows for audit.

Expiration does not delete historical rows. Cleanup is explicit and staff-only;
the caller chooses the retention cutoff and optional batch size:

```python
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
purged = await dal.purge_expired(
    expired_before=cutoff,
    limit=500,
    actor=staff_user,
)
await session.commit()
```

This example removes only notifications whose expiry instant is at least 30
days old. The DAL never commits the transaction. The package does not start a
scheduler; invoke the cleanup method from your application's scheduled task if
you want recurring retention cleanup.

The nullable ``notification.expires_at`` column is a pre-release schema addition.
``Base.metadata.create_all()`` does not alter an existing table; add the nullable column and its index
through your migration process or recreate development tables before upgrading.

## Throttling

Authenticated users are limited to `AUTHENTICATED_USER_THROTTLE_RATE` (30 a minute by default) and staff to `STAFF_USER_THROTTLE_RATE` (100 a minute). Exceeding the limit returns `429` with a `Retry-After` header. Setting `API_THROTTLE_CLASS` to `None` turns throttling off.

## Permissions

Every route requires an authenticated user; without one the response is `401`. All
users, including staff and superusers, see only notifications addressed to them
directly or through their groups. Staff status does not bypass model-level
recipient permissions. The two permanent-deletion routes are separate staff-only
administrative operations, disabled by default; a superuser must also be staff
to use them. An extra permission class can be applied to every route through
`API_EXTRA_PERMISSION_CLASS`.

---

# Usage

## The Data Access Layer

`NotificationDataAccessLayer` is the package's Python API. It is bound to a session, flushes its writes, and leaves the commit to you.

Permanent deletion is privileged at the DAL boundary as well as in the HTTP API.
Pass a staff identity as ``actor`` to ``delete_notification(..., soft_delete=False)``
or ``delete_many(..., actor=staff_user)``. Missing actors, regular users and
superusers who are not staff are rejected. The lower-level queryset functions
are internal persistence primitives; application code should use the DAL.

```python
dal = NotificationDataAccessLayer(session)
```

### Querying

```python
# Everything, ignoring who has seen what.
await dal.all_notifications(recipients=user, display_detail=True)

# By delivery state.
await dal.sent(recipients=user, display_detail=True)
await dal.unsent(recipients=user, display_detail=True)

# By read state.
await dal.seen(seen_by=user, display_detail=True)
await dal.unseen(unseen_by=user, groups=user.groups, display_detail=True)

# Soft-deleted.
await dal.deleted(deleted_by=user)
```

With `display_detail=False`, which is the default, each of these returns compact dictionaries carrying only `id`, `description`, `status`, `link` and `timestamp`. With `display_detail=True` they return whole `Notification` objects with their recipients, groups and content types loaded.

Every read method has a `*_statement` counterpart returning the SQLAlchemy `Select` rather than executing it, which is how the routes layer filtering and pagination on top:

```python
statement = dal.unseen_statement(unseen_by=user, display_detail=True)
total = await dal.count(statement)
```

### Marking and Clearing

```python
count = await dal.mark_all_as_seen(user)
count = await dal.mark_all_as_sent(recipients=user, groups=[moderators])
await dal.clear_all(user)
await session.commit()
```

`clear_all` soft-deletes everything the user has already seen: the notifications stay in the database and stay visible to their other recipients.

### Updating and Deleting

```python
await dal.update_notification(notification_id, is_sent=True, public=False, data={"k": "v"})

# Soft delete — hidden for this user only, and a recipient is required.
await dal.delete_notification(notification_id, recipient=user, soft_delete=True)

# Hard delete — the row is destroyed; a staff actor is required.
await dal.delete_notification(
    notification_id, soft_delete=False, actor=staff_user
)

await session.commit()
```

Fields left out of `update_notification` keep their previous value. Deleting something that does not exist, or that the given recipient cannot see, raises `LookupError`.

## Models

| Model                         | Purpose                                                       |
|-------------------------------|---------------------------------------------------------------|
| `Notification`                | The notification itself.                                      |
| `NotificationRecipient`       | Links a notification to each of its recipients.               |
| `NotificationSeen`            | Records that a user has seen a notification.                  |
| `DeletedNotification`         | Records that a user has soft-deleted a notification.          |
| `ContentType`                 | Identifies the model behind a generic actor/target reference. |
| `User`, `Group`, `Permission` | Optional auth examples on `AuthBase`, separate from core tables. |

`NotificationStatus` provides the available statuses: `ERROR`, `SUCCESS`, `WARNING`, `INFO`, `CRITICAL`, `SENSITIVE` and `INFRASTRUCTURE`.

---

# Settings

Settings resolve in order of precedence: values registered through `configure()`, then environment variables prefixed `FASTAPI_NOTIFICATION_`, then the packaged defaults. Environment values are coerced — booleans accept `1`/`true`/`yes`/`on` and their negatives, and list settings are read as JSON.

| Setting                            | Type        | Default                        | Purpose                                              |
|------------------------------------|-------------|--------------------------------|------------------------------------------------------|
| `IDENTITY_ADAPTER`                | class / instance / str | `IdentityAdapter`               | Integrate host user and group models.                |
| `API_INCLUDE_SOFT_DELETE`          | bool        | `True`                         | Register the clearing routes.                        |
| `API_INCLUDE_HARD_DELETE`          | bool        | `False`                        | Register the permanent-deletion routes.              |
| `API_ALLOW_LIST`                   | bool        | `True`                         | Register inbox, summary, preview and activity listing routes. |
| `API_ALLOW_RETRIEVE`               | bool        | `True`                         | Register retrieval and individual mark-as-seen routes. |
| `SERIALIZER_INCLUDE_FULL_DETAILS`  | bool        | `False`                        | Give every user the detailed representation.         |
| `SERIALIZER_EXCLUDE_NULL_FIELDS`   | bool        | `False`                        | Strip null fields from responses.                    |
| `SERIALIZER_FIELDS`                | list / None | `None`                         | Serve exactly these notification fields.             |
| `SERIALIZER_CLASS`                 | str / None  | `None`                         | Replace the notification serializer.                 |
| `USER_SERIALIZER_FIELDS`           | list        | `["id"]`                       | Fields included when a user is nested in a response. |
| `USER_SERIALIZER_CLASS`            | str / None  | `None`                         | Replace the user serializer.                         |
| `GROUP_SERIALIZER_CLASS`           | str / None  | `None`                         | Replace the group serializer.                        |
| `AUTHENTICATED_USER_THROTTLE_RATE` | str         | `"30/minute"`                  | Rate limit for regular users.                        |
| `STAFF_USER_THROTTLE_RATE`         | str         | `"100/minute"`                 | Rate limit for staff users.                          |
| `API_THROTTLE_CLASS`               | str / None  | `RoleBasedUserRateThrottle`    | Throttle implementation; `None` disables throttling. |
| `API_PAGINATION_CLASS`             | str / None  | `DefaultLimitOffSetPagination` | Paginator; `None` returns bare lists.                |
| `API_EXTRA_PERMISSION_CLASS`       | str / None  | `None`                         | Extra permission applied to every route.             |
| `API_FILTERSET_CLASS`              | str / None  | `None`                         | Replace the filter set.                              |
| `API_ORDERING_FIELDS`              | list        | `["id", "timestamp", "public", "category", "priority"]` | Fields a client may order by.                       |
| `API_SEARCH_FIELDS`                | list        | `["verb", "description"]`      | Fields the `search` parameter matches against.       |

Settings are validated when a router is built. Anything wrong raises `ImproperlyConfigured`, listing every problem at once:

```python
from fastapi_notification.settings.checks import check_notification_settings

for error in check_notification_settings():
    print(error)
```

---

# Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up the project, the coding standards, and how to run the checks.

```bash
$ poetry install
$ poetry run pre-commit install
$ poetry run pytest
```

The test suite runs at 100% coverage and the build enforces it.

# License

This project is licensed under the MIT License — see the [LICENCE](LICENCE) file for details.


## Concurrency and transactions

Per-user seen and soft-deletion transitions are idempotent and protected by
database uniqueness constraints. SQLite and PostgreSQL use atomic conflict-safe
inserts for single and bulk operations; other SQLAlchemy dialects use savepoint
fallbacks. The package flushes but never commits the host application's
session. The host application owns transaction commit and rollback. See the
[concurrency guide](docs/concurrency.rst) for details.
