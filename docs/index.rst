Welcome to fastapi-notification Documentation!
==============================================


.. |br| raw:: html

   <br />


.. image:: https://img.shields.io/github/license/lazarus-org/fastapi-notification
    :target: https://github.com/lazarus-org/fastapi-notification/blob/main/LICENCE
    :alt: License

.. image:: https://img.shields.io/pypi/v/fastapi-notification
    :target: https://pypi.org/project/fastapi-notification/
    :alt: PyPI release

.. image:: https://img.shields.io/readthedocs/fastapi-notification
    :target: https://fastapi-notification.readthedocs.io/en/latest/
    :alt: Documentation

.. image:: https://img.shields.io/badge/pylint-10/10-brightgreen?logo=python&logoColor=blue
   :target: https://www.pylint.org/
   :alt: Pylint

.. image:: https://img.shields.io/badge/coverage-100%25-brightgreen
   :target: https://github.com/lazarus-org/fastapi-notification
   :alt: Coverage

.. image:: https://img.shields.io/pypi/pyversions/fastapi-notification
    :target: https://pypi.org/project/fastapi-notification/
    :alt: Supported Python versions

.. image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=yellow
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit

.. image:: https://img.shields.io/github/issues/lazarus-org/fastapi-notification
    :target: https://github.com/lazarus-org/fastapi-notification/issues
    :alt: Open Issues

.. image:: https://img.shields.io/github/last-commit/lazarus-org/fastapi-notification
    :target: https://github.com/lazarus-org/fastapi-notification/commits/main
    :alt: Last Commit

.. image:: https://img.shields.io/github/languages/top/lazarus-org/fastapi-notification
    :target: https://github.com/lazarus-org/fastapi-notification
    :alt: Languages


|br|

``fastapi-notification`` is a FastAPI package developed by Lazarus, designed to
simplify and optimize the process of managing notifications through various
APIs. Install it, supply a database session and a way to identify the current
user, and you have a fully featured notification API that you can then tailor
to your needs.

It is built on async SQLAlchemy 2.0 and Pydantic v2, and it is the FastAPI
counterpart to Lazarus's ``dj-notification-api`` package for Django.

Highlights
----------

- **Two endpoint groups**: unseen notifications, and the activity history of
  everything already seen.
- **Anything can be an actor**: notifications reference an actor, a target and
  an action object generically, so any of your own models can take those roles.
- **Addressed to users or groups**: a notification reaches named recipients,
  every member of a group, or both.
- **Soft and hard deletion**: clearing a notification hides it for one user
  while leaving it intact for the others; permanent deletion is available to
  administrators and off by default.
- **Configurable throughout**: serializers, fields, pagination, throttling,
  filtering and permissions are all driven from settings, and routes you switch
  off are never registered at all.
- **Validated at startup**: a misconfiguration raises when the router is built,
  listing every problem at once, rather than failing on the first request.

Supported Versions
------------------

``fastapi-notification`` supports the following combinations:

==========  ==============  ===========================
  FastAPI     SQLAlchemy    Python
==========  ==============  ===========================
0.110+      2.0            3.9, 3.10, 3.11, 3.12, 3.13
==========  ==============  ===========================

Any database with an async SQLAlchemy driver works; PostgreSQL (``asyncpg``),
MySQL (``aiomysql``) and SQLite (``aiosqlite``) are the common choices.

Documentation
-------------

The documentation is organized into the following sections:

.. toctree::
   :maxdepth: 2

   quick_start
   api_guide
   usage
   taxonomy
   preferences
   concurrency
   settings
   identity
   roles
   contributing

Need Help?
----------

If you have questions or have trouble using the app please file a bug report
at:

https://github.com/lazarus-org/fastapi-notification/issues


Indices and tables
==================

* :ref:`search`
* :ref:`genindex`
* :ref:`modindex`
