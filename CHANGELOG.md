# CHANGELOG

### Issue 17.1 release hardening

- Support Python 3.11–3.15; drop Python 3.9/3.10 by maintainer decision. Package, Commitizen and semantic-release remain aligned on intended version 1.0.0.
- Recover formatting, documentation, Pylint and mypy checks without lowering quality thresholds.
- Preserve compound SELECT sources in SQLite conflict-safe bulk inserts.
- Preserve opaque identity comparisons and microsecond precision on MySQL 8.4; provide a guarded reference schema migration.
- Serialize MySQL duplicate state insertion without shared-lock upgrade deadlocks at REPEATABLE READ, retaining caller transaction ownership.
- Add real database and migration regressions, optional database test dependencies, and reproducible validation evidence.


### Issue 17 validation fixes

- Clean recipient, group, seen, deleted-state and deduplication associations during single and bulk permanent deletion even when SQLite foreign keys are disabled.
- Validate PostgreSQL 17.5 runtime behavior with independent async sessions, schema/index inspection and foreign-key enforcement.

- Make direct notification filter construction use plain optional defaults while preserving FastAPI query validation.
- Load async ORM group memberships before accessing relationship descriptors.
- Preserve configuration errors for unsupported composite generic-relation keys.
- Keep quiet-hour end timestamps in the future during a repeated DST hour.
- Exclude the test suite from installable distributions and refresh the stale development lockfile.
- Recover regression fixtures and add scheduling API, timezone and independent-session digest tests.
- Extend CI and tox interpreter coverage through Python 3.15.


## [Unreleased]

### Added
- Per-user, channel-specific quiet hours with IANA timezone support, overnight windows, and configurable urgent-notification bypass.
- Daily and weekly digest schedules calculated in local wall-clock time.
- Scheduler-agnostic digest batches with atomic claiming, retries, stale-worker lease recovery, and quiet-hour deferral.
- Authenticated API endpoints for managing quiet-hour rules and digest schedules.

### Added

- Add database-backed localized notification templates identified by an event
  key and locale, with exact-locale, base-language and configured-default fallback.
- Add ``NotificationTemplateDataAccessLayer`` to register/update translations,
  resolve active templates, render safe variables and remove locale versions.
- Add restricted ``{variable}`` interpolation; attribute access, indexing,
  conversions and format expressions are rejected, and missing values fail clearly.
- Allow ``NotificationDataAccessLayer.create_notification`` to render a template
  using ``template_key``, ``locale`` and ``template_context`` while preserving
  manual notification creation unchanged.
- Persist the rendered verb and description as notification text snapshots, plus
  the source template key and resolved locale for provenance. Later template
  edits do not alter existing notifications.

- Add independent notification ``category`` and ``priority`` fields. Built-in
  categories are ``general``, ``system``, ``security``, ``social``, ``financial``,
  ``orders`` and ``marketing``; applications may use validated custom namespaced
  keys.
- Add the ``low``, ``normal``, ``high`` and ``urgent`` priority levels without
  changing existing notification status values or their semantics.
- Add category and priority filtering, priority-aware ordering, and include both
  fields in standard notification, dynamic serializer defaults and preview items.
- Extend ``GET /notifications/summary/`` with ``by_category`` and ``by_priority``
  breakdowns, each split into total, unread and read counts. The breakdowns are
  calculated in the same grouped SQL query as the top-level counts.
- Add optional scoped notification deduplication through
  ``NotificationDataAccessLayer.create_notification(deduplication_key=...)``.
  Active keys return the original notification unchanged; expired keys can be
  atomically reclaimed without modifying the original notification.
- Add the ``notification_deduplication`` ledger table with database-enforced
  uniqueness for scoped keys and explicit key-retention timestamps.
- Make generic content-type registration atomic under concurrent notification
  creation by using the shared conflict-safe insert helper.

- Add optional timezone-aware ``Notification.expires_at`` and apply expiration
  consistently to recipient inboxes, activities, summaries, previews and normal
  unsent-delivery queries.
- Add explicit staff-only ``NotificationDataAccessLayer.purge_expired()`` with a
  caller-selected retention cutoff and optional batch limit; expiration alone
  never deletes historical notification records.
- Include ``expires_at`` in standard notification and preview representations.
- Add ``POST /notifications/{notification_id}/mark_as_unseen/`` and
  ``Notification.mark_as_unseen()`` to return a visible notification to the
  current user's unseen inbox by removing only that user's seen record.
- Add ``GET /notifications/summary/`` with a single aggregate query returning
  total, unread and read counts for the authenticated user's visible sent
  notifications.
- Add ``GET /notifications/preview/`` to return a bounded set of recent sent
  notifications with per-user ``is_seen`` state without hydrating generic
  relations.
- Add a configurable identity adapter for host user/group identifiers,
  membership, role flags and API identity resolution; optional built-in auth
  examples use separate ``AuthBase`` metadata.
- Support integer, UUID and string primary keys for generic actor, target and
  action-object relations.

### Changed

- Keep notification status, category and priority independent: status describes
  the notification's nature, category its application domain, and priority its
  urgency. Priority ordering uses the explicit low-to-urgent rank.
- Exclude expired notifications from recipient inboxes, activities, summaries,
  previews and normal unsent-delivery queries. Keep raw/all and deleted-history
  queries capable of returning expired rows for audit.
- Normalize expiration timestamps to UTC on database writes and restore
  timezone-aware UTC values on reads, including SQLite.
- Reject seen/unseen state transitions after notification expiration.
- Make per-user seen and soft-deletion writes idempotent under concurrent requests.
- Use atomic conflict-safe insert-select operations for bulk seen and clear actions
  on SQLite and PostgreSQL, with savepoint fallback for other SQLAlchemy dialects.
- Preserve host application ownership of commit and rollback boundaries.
- Use a savepoint for keyed notification creation so the candidate notification,
  idempotency claim and recipient/group associations succeed or roll back together.
- Require an explicit staff ``actor`` for DAL permanent deletion and keep
  superuser status separate from staff authorization.
- Make notification and activity retrieval endpoints read-only; retrieving an
  unseen notification no longer marks it as seen.
- Expose individual and bulk mark-as-seen actions through POST endpoints, and
  activity soft deletion/permanent deletion through DELETE endpoints.
- Include group memberships when bulk-marking notifications as seen and clearing
  all seen activities.
- Store user/group and generic relation identifiers as normalized strings.
- Select notification detail level from serializer settings, not staff/superuser
  role flags.

### Fixed

- Enforce personal notification audience checks for staff and superusers across
  listings, retrieval, model permissions, seen records and soft deletion.
- Enforce staff-only administrative deletion in the DAL as well as HTTP routes;
  a superuser flag alone does not grant staff access.
- Make synchronous permission checks use the configured identity adapter and
  fail clearly when external group membership requires asynchronous resolution.
- Validate extra permission classes at router startup, including their
  no-argument construction and callable contract.
- Ensure generic relation resolution loads content-type references before
  accessing them through SQLAlchemy's async ORM.

### Compatibility

- Add the ``notification_deduplication`` table. Create it through the package
  ``Base.metadata`` or add it to the application's Alembic migration before
  enabling ``deduplication_key`` on notification creation.
- A deduplication key is unique within its scope. The default scope is
  ``"global"``; callers should supply a tenant/user/event scope where keys are
  only unique within that boundary. Reusing an active key returns the original
  notification and does not merge recipients or update its content. A NULL key
  expiry retains the key until its notification is permanently deleted.
- Permanently deleting or explicitly purging a notification also releases its
  deduplication key. Expiring a notification for inbox visibility does not by
  itself release the key.

- Clients must use POST for mark-as-seen actions and DELETE for activity
  clearing/deletion; GET retrieval no longer changes seen state.
- The identity and generic-relation changes are pre-release schema changes.
  Recreate development tables or migrate the affected columns before upgrading.
- The nullable ``notification.expires_at`` column is an additional pre-release
  schema change; add the nullable column and its index, or recreate development
  tables before upgrading.
- Add non-null ``notification.category`` and ``notification.priority`` columns
  with server defaults ``general`` and ``normal``, indexes and a priority check
  constraint. Add these through the application's Alembic migration, or
  recreate development tables before upgrading. Existing status values and
  stored status data are unchanged.

---

## v1.0.0 (2026-07-20)

### ✨ Features

- **models**: Add async SQLAlchemy 2.0 models for notifications, recipients, seen records and soft deletions.
- **models**: Add `ContentType` backed generic relations for `actor`, `target` and `action_object`.
- **repository**: Add `NotificationDataAccessLayer` exposing `sent`, `unsent`, `seen`, `unseen`, `deleted`, `clear_all`, `mark_all_as_seen` and `mark_all_as_sent`.
- **api**: Add configurable notification and activity routers with soft/hard delete support.
- **api**: Add role based throttling, limit/offset pagination, filtering, ordering and search.
- **settings**: Add environment driven `NotificationConfig` with startup validation checks.

### 📚 Documentation

- Add full Sphinx documentation covering quick start, API guide, usage, settings and roles.

### ✅ Tests

- Add a pytest suite covering the package at 100%.

### Notes
- No background scheduler or delivery provider is bundled; host applications integrate their own worker and transport.
- Digest delivery is at-least-once. Use the stable digest batch ID as a provider idempotency key where supported.
- Existing databases require creation of the quiet-hours, digest-schedule, and digest-batch tables.


## Unreleased

### Added

- Configurable group audience strategies for notification creation: dynamic
  membership (the default) or snapshot membership captured as individual
  recipient associations at creation time.
- `IdentityAdapter.get_group_user_ids()` extension point for applications that
  need snapshot group delivery. The base implementation fails explicitly when
  snapshot membership resolution is not configured.
- Add per-user notification delivery preferences, with category/channel-specific
  rules and wildcard overrides. Preferences are isolated by host identity and
  default to enabled when no matching rule exists.
- Add ``NotificationPreferenceDataAccessLayer`` to list, set, reset and resolve
  preferences, plus authenticated GET/PUT/DELETE ``/notifications/preferences/``
  endpoints. Preference rules affect delivery decisions only; they do not hide,
  delete or mutate notifications already stored in the inbox.

### Changed

- Resolve preference rules from most-specific to least-specific: exact
  category/channel, exact category/all channels, all categories/exact channel,
  then global defaults. Removing a rule restores inherited behavior.
