# Static analysis decisions

No configured message, naming rule, threshold, coverage scope or mypy check is disabled or reduced.

Pylint 3/Astroid 3 mis-infers SQLAlchemy 2.1 Mapped generics and func.count. Current Pylint 4/Astroid 4 resolves these without suppressing SQLAlchemy diagnostics. The dev range permits both releases so Python-dependent resolution can select a compatible checker. The removed suggestion-mode option is rejected by Pylint 4; it is not a disabled-message or threshold change.

Narrow source-level Pylint annotations are retained only for contracts that cannot be changed without violating API compatibility:

- NotificationFilter exposes ten explicit query fields and an explicit dependency constructor so FastAPI retains parameter names, metadata and validation. Collapsing them into arbitrary kwargs or an opaque options object changes OpenAPI and injection behavior. Only its attribute/argument-count diagnostics are annotated.
- Existing DAL creation, template registration and scheduling methods retain their public positional/keyword options. Only argument-count (and the DAL's argument-driven local count) diagnostics are annotated. Actual branch/statement complexity is reduced through tested private validation, audience and router-registration helpers.
- UTCDateTime necessarily inherits SQLAlchemy's TypeDecorator hierarchy (eight ancestors). TypeDecorator's process_literal_param is an optional customization hook: the framework's literal processor intentionally falls back to process_bind_param when it is not overridden. Overriding it merely to satisfy a checker changes SQL literal semantics. Only these two diagnostics on this specific class are annotated.
- The startup configuration validator intentionally collects arbitrary Exceptions from host-supplied adapter constructors along with other validation errors. Narrowing the exception tuple would change the public error-collection behavior. BaseException, cancellation and process-exit exceptions are still not caught. The annotation is confined to that except clause.

No production module is excluded. No broad Any annotation or type-ignore is added to hide typing failures. Runtime tests and unchanged 100% statement coverage are required after these changes.


The typed read-operation module carries the same public sent/unsent signatures
that previously lived under the DAL module's existing too-many-arguments
annotation. That pre-existing exception is now restricted to the affected
methods/overloads rather than applied to the whole new module. No new read
behavior or argument limit is introduced.

Typing bridges are narrow and explicit: non-returning SQLAlchemy DML is typed
as CursorResult; single-class configuration is viewed after startup validation
from the generic host import boundary; minimal existing unit transports are
cast only within test support, and intentional invalid values keep their exact
runtime values. No integration session is replaced. A typed zero-argument
factory adapts the unannotated PostgreSQL dialect constructor in its SQL
compilation unit test. Generic relation projections use a protocol and are
correctly declared as per-instance unmapped data rather than ClassVars.

MySQL VARCHAR/DATETIME/TIME constructors lack annotations in the installed SQLAlchemy distribution. models/column_types.py isolates their specific callable/protocol signatures; the implementation uses typed dialect variants without broad casts. The generic state helper retains its existing dynamic ORM-model/value boundary for arbitrary mapped model constructors.
