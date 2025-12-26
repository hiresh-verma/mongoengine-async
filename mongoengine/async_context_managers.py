"""
Async context managers for MongoEngine.

This module provides async versions of context managers for:
- Database switching
- Collection switching
- Transactions
- Write concerns
"""

import logging
from contextlib import asynccontextmanager

from pymongo.errors import ConnectionFailure, OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from mongoengine.connection import DEFAULT_CONNECTION_NAME
from mongoengine.io.aio.connection import (
    _clear_async_session,
    _get_async_session,
    _set_async_session,
    async_get_connection,
    async_get_db,
)

__all__ = (
    "async_switch_db",
    "async_switch_collection",
    "async_run_in_transaction",
)


class async_switch_db:
    """Async switch_db context manager.

    Switch the database alias for a document class within an async context.

    Example::

        # Register connections
        await async_register_connection('default', 'mongoenginetest')
        await async_register_connection('testdb-1', 'mongoenginetest2')

        class AsyncGroup(AsyncDocument):
            name = StringField()

        await AsyncGroup(name='test').save()  # Saves in the default db

        async with async_switch_db(AsyncGroup, 'testdb-1') as Group:
            await Group(name='hello testdb!').save()  # Saves in testdb-1
    """

    def __init__(self, cls, db_alias):
        """Construct the async_switch_db context manager.

        Args:
            cls: The document class to change the registered db
            db_alias: The name of the specific database to use
        """
        self.cls = cls
        self.db_alias = db_alias
        self.ori_db_alias = cls._meta.get("db_alias", DEFAULT_CONNECTION_NAME)
        self._original_collection = None

    async def __aenter__(self):
        """Change the db_alias and clear the cached collection."""
        # Store the original collection object (AsyncDocument uses _collection, not _collection_obj)
        self._original_collection = getattr(self.cls, '_collection', None)

        # Change the db_alias
        self.cls._meta["db_alias"] = self.db_alias

        # Clear the cached collection so it will be re-created with new db
        self.cls._collection = None

        return self.cls

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Reset the db_alias and collection."""
        self.cls._meta["db_alias"] = self.ori_db_alias
        self.cls._collection = self._original_collection
        return False


class async_switch_collection:
    """Async switch_collection context manager.

    Switch the collection for a document class within an async context.

    Example::

        class AsyncGroup(AsyncDocument):
            name = StringField()

        await AsyncGroup(name='test').save()  # Saves in default collection

        async with async_switch_collection(AsyncGroup, 'group2') as Group:
            await Group(name='hello group2!').save()  # Saves in group2 collection
    """

    def __init__(self, cls, collection_name):
        """Construct the async_switch_collection context manager.

        Args:
            cls: The document class to change the collection
            collection_name: The name of the collection to use
        """
        self.cls = cls
        self.collection_name = collection_name
        self.ori_collection_name = cls._meta.get("collection")
        self._original_collection = None

    async def __aenter__(self):
        """Change the collection name and clear the cached collection."""
        # Store the original collection object (AsyncDocument uses _collection, not _collection_obj)
        self._original_collection = getattr(self.cls, '_collection', None)

        # Change the collection name
        self.cls._meta["collection"] = self.collection_name

        # Clear the cached collection so it will be re-created with new name
        self.cls._collection = None

        return self.cls

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Reset the collection name and collection object."""
        self.cls._meta["collection"] = self.ori_collection_name
        self.cls._collection = self._original_collection
        return False


async def _async_commit_with_retry(session):
    """
    Commit a transaction with retry logic for transient errors.

    Args:
        session: The async client session
    """
    while True:
        try:
            # Commit uses write concern set at transaction start
            await session.commit_transaction()
            break
        except (ConnectionFailure, OperationFailure) as exc:
            # Can retry commit
            if exc.has_error_label("UnknownTransactionCommitResult"):
                logging.warning(
                    "UnknownTransactionCommitResult, retrying commit operation ..."
                )
                continue
            else:
                # Error during commit
                raise


@asynccontextmanager
async def async_run_in_transaction(
    alias=DEFAULT_CONNECTION_NAME, session_kwargs=None, transaction_kwargs=None
):
    """Async run_in_transaction context manager.

    Execute async queries within the context in a database transaction.

    Usage::

        class AsyncUser(AsyncDocument):
            name = StringField()

        async with async_run_in_transaction():
            user = AsyncUser(name='Alice')
            await user.save()
            await user.update(name='Bob')

    Notes:
        - MongoDB transactions run inside a session which is bound to a connection.
        - You cannot execute a transaction across different connection aliases.
        - Multiple transactions can be nested within the same session for a connection.
        - Requires MongoDB 4.0+ with replica set or sharded cluster.

    Args:
        alias: The connection alias to use (default: 'default')
        session_kwargs: Optional kwargs for start_session()
        transaction_kwargs: Optional kwargs for start_transaction()

    For more information: https://pymongo.readthedocs.io/en/stable/api/pymongo/client_session.html#transactions
    """
    conn = await async_get_connection(alias)
    session_kwargs = session_kwargs or {}

    async with conn.start_session(**session_kwargs) as session:
        transaction_kwargs = transaction_kwargs or {}

        # Start the transaction
        await session.start_transaction(**transaction_kwargs)

        try:
            _set_async_session(session)
            yield session
            # Commit the transaction with retry logic
            await _async_commit_with_retry(session)
        except Exception:
            # Abort the transaction on any exception
            await session.abort_transaction()
            raise
        finally:
            _clear_async_session()
