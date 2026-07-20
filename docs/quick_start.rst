Quick Start
===========

This guide takes you from an empty project to a working notification API.

1. Install the Package
----------------------

**Option 1: Using ``pip`` (Recommended)**

.. code-block:: bash

   $ pip install fastapi-notification

**Option 2: Using ``Poetry``**

.. code-block:: bash

   $ poetry add fastapi-notification

**Option 3: Using ``pipenv``**

.. code-block:: bash

   $ pipenv install fastapi-notification

You will also need an async database driver. For PostgreSQL:

.. code-block:: bash

   $ pip install asyncpg

For SQLite, which is enough to try the package out:

.. code-block:: bash

   $ pip install aiosqlite


2. Create the Tables
--------------------

The package ships its own SQLAlchemy models on a declarative ``Base``. Create
the tables from that metadata, or point Alembic at it if you manage migrations.

.. code-block:: python

   from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

   from fastapi_notification import Base

   engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/app")
   Session = async_sessionmaker(engine, expire_on_commit=False)


   async def create_tables() -> None:
       async with engine.begin() as connection:
           await connection.run_sync(Base.metadata.create_all)

If your application already has a declarative base, the package's tables can
live alongside it: ``Base.metadata`` is ordinary SQLAlchemy metadata.


3. Supply the Two Dependencies
------------------------------

The package does not own your database session or your authentication, so it
asks for both. Supply them when you build the router.

.. code-block:: python

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

The user object you return needs an ``id``, an ``is_staff`` flag, and a
``groups`` collection. The packaged :class:`~fastapi_notification.models.auth.User`
model provides all three, but any object will do.

Instead of passing the dependencies, you may override the package's
placeholders through FastAPI's ``dependency_overrides``:

.. code-block:: python

   from fastapi_notification.api.dependencies import get_session, get_current_user

   app.dependency_overrides[get_session] = my_session_dependency
   app.dependency_overrides[get_current_user] = my_user_dependency


4. (Optional) Configure the Package
-----------------------------------

Every setting has a working default, so this step is optional. Settings can be
registered from Python:

.. code-block:: python

   from fastapi_notification import configure

   configure(
       API_INCLUDE_HARD_DELETE=True,
       AUTHENTICATED_USER_THROTTLE_RATE="60/minute",
   )

or supplied through the environment:

.. code-block:: bash

   export FASTAPI_NOTIFICATION_API_INCLUDE_HARD_DELETE=true
   export FASTAPI_NOTIFICATION_AUTHENTICATED_USER_THROTTLE_RATE="60/minute"

Configure the package **before** building the router: the router reads its
settings when it is created, and a route disabled in settings is never
registered.

Settings are validated when the router is built, so a mistake surfaces at
startup rather than on the first request. See :doc:`settings` for the full
reference.


5. Create Notifications
-----------------------

Notifications are created through the data access layer.

.. code-block:: python

   from fastapi_notification import NotificationDataAccessLayer

   async with Session() as session:
       dal = NotificationDataAccessLayer(session)

       await dal.create_notification(
           verb="liked your post",
           actor=user,
           recipients=[other_user],
           groups=[moderators],
           status="INFO",
           public=True,
           target=post,
           link="https://example.com/posts/123",
           is_sent=True,
           data={"post_id": 123},
       )

       await session.commit()

Only ``verb`` and ``actor`` are required. With no ``description``, one is
generated from the actor, the verb, and the target or action object — the
example above describes itself as ``"alice liked your post my-first-post"``.

A notification is only visible to its recipients once ``is_sent`` is true.
Create it unsent and call ``mark_all_as_sent()`` later if you want to stage
delivery.

Any object can be the ``actor``, ``target`` or ``action_object``, as long as
its model is registered:

.. code-block:: python

   from fastapi_notification import register_content_model


   @register_content_model
   class Post(Base):
       __tablename__ = "posts"
       ...


6. Verify
---------

Start your application and call the API as an authenticated user:

.. code-block:: bash

   $ curl -H "Authorization: Bearer <token>" http://localhost:8000/notifications/

.. code-block:: json

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
         "link": "https://example.com/posts/123",
         "timestamp": "2026-07-20T12:00:00Z"
       }
     ]
   }

The interactive documentation at ``/docs`` lists every route the package
registered, which is a quick way to confirm your settings took effect.
