# CHANGELOG

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
