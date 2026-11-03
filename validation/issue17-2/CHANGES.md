# Issue 17.2 changes

- Digest batch ownership is now represented by a per-claim UUID token.
- All digest batch completion transitions require the current token.
- Stale workers cannot finalize a batch reclaimed by another worker.
- Claim tokens are invalidated when a batch leaves `processing`.
- Provider failure persistence now accepts only validated non-sensitive error codes.
- Existing raw failure text is mapped to `delivery_failed` and removed by the reference migration.
- Existing in-flight batches are reset to `pending` during the migration so old workers cannot finalize them after the protocol upgrade.
- Added same-session, independent-session, error-validation, schema and migration regression tests.
