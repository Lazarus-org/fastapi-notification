# Issue 17.2 repository integration

The validated extracted source was subsequently copied into the repository root.
The four runtime-validation corrections were reapplied and each restored file
matched its recorded validated SHA-256 exactly. Unrelated CRLF-only differences
were normalized, and the existing generated-artifact ignore rules were retained.

Fresh execution from the repository root completed 726 cases: 724 passed and two
explicitly MySQL-only cases skipped. Statement coverage remained 100% (2,984
statements). Black, isort, docformatter, Pylint and mypy all exited zero; Pylint
reported 10.00/10 and mypy checked 166 files without errors. New `root-*` JSON/XML
and logs preserve these post-integration results without replacing earlier runs.

The earlier PostgreSQL/MySQL results remain applicable to the same source logic:
29 scheduling/session cases passed on each, and real Alembic upgrade/downgrade
passed against the complete Issue 17.1 schema on both backends. The new migration
uses revision `notification_digest_ownership`, distinct from its branch label and
within Alembic's default 32-character version column.

Reproduction runners now select either the extracted tree or the root. Full
legacy-schema migration reproduction loads immutable commit `ae79ca7`, rather
than assuming the current root still has the old schema. Its offline legacy
schema check passed after this adjustment. The seven validation controllers
were also formatted with the configured Black/isort settings.

The earlier REPORT.md is a historical checkpoint; its statements about an
unchanged committed root and no commits describe the state before integration.
Generated raw evidence and archives stay local and are ignored. No push or
publication is part of this integration.
