"""
Async context managers for MongoEngine.

This module provides async versions of context managers for:
- Database switching
- Collection switching
- Transactions
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional, Type

from pymongo.errors import ConnectionFailure, OperationFailure

from mongoengine.connection import DEFAULT_CONNECTION_NAME
from mongoengine.io.aio.connection import (
    _clear_async_session,
    _set_async_session,
    async_get_connection,
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

    def __init__(self, cls: Type, db_alias: str) -> None:
        """Construct the async_switch_db context manager.

        Args:
            cls: The document class to change the registered db.
            db_alias: The name of the specific database to use.
        """
        self.cls = cls
        self.db_alias = db_alias
        self.ori_db_alias = cls._meta.get("db_alias", DEFAULT_CONNECTION_NAME)
        self._original_collection = None

    async def __aenter__(self) -> Type:
        """Change the db_alias and clear the cached collection.

        Returns:
            The document class.
        """
        self._original_collection = getattr(self.cls, '_collection', None)
        self.cls._meta["db_alias"] = self.db_alias
        self.cls._collection = None
        return self.cls

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Reset the db_alias and collection.

        Returns:
            False to not suppress exceptions.
        """
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

    def __init__(self, cls: Type, collection_name: str) -> None:
        """Construct the async_switch_collection context manager.

        Args:
            cls: The document class to change the collection.
            collection_name: The name of the collection to use.
        """
        self.cls = cls
        self.collection_name = collection_name
        self.ori_collection_name = cls._meta.get("collection")
        self._original_collection = None

    async def __aenter__(self) -> Type:
        """Change the collection name and clear the cached collection.

        Returns:
            The document class.
        """
        self._original_collection = getattr(self.cls, '_collection', None)
        self.cls._meta["collection"] = self.collection_name
        self.cls._collection = None
        return self.cls

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Reset the collection name and collection object.

        Returns:
            False to not suppress exceptions.
        """
        self.cls._meta["collection"] = self.ori_collection_name
        self.cls._collection = self._original_collection
        return False


async def _async_commit_with_retry(session: Any) -> None:
    """Commit a transaction with retry logic for transient errors.

    Args:
        session: The async client session.
    """
    while True:
        try:
            await session.commit_transaction()
            break
        except (ConnectionFailure, OperationFailure) as exc:
            if exc.has_error_label("UnknownTransactionCommitResult"):
                logging.warning(
                    "UnknownTransactionCommitResult, retrying commit operation ..."
                )
                continue
            else:
                raise


@asynccontextmanager
async def async_run_in_transaction(
    alias: str = DEFAULT_CONNECTION_NAME,
    session_kwargs: Optional[Dict[str, Any]] = None,
    transaction_kwargs: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Any, None]:
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
        - MongoDB transactions run inside a session bound to a connection.
        - Transactions cannot span different connection aliases.
        - Multiple transactions can be nested within the same session.
        - Requires MongoDB 4.0+ with replica set or sharded cluster.

    Args:
        alias: The connection alias to use (default: 'default').
        session_kwargs: Optional kwargs for start_session().
        transaction_kwargs: Optional kwargs for start_transaction().

    Yields:
        The async client session.
    """
    conn = await async_get_connection(alias)
    session_kwargs = session_kwargs or {}

    async with conn.start_session(**session_kwargs) as session:
        transaction_kwargs = transaction_kwargs or {}
        await session.start_transaction(**transaction_kwargs)

        try:
            _set_async_session(session)
            yield session
            await _async_commit_with_retry(session)
        except Exception:
            await session.abort_transaction()
            raise
        finally:
            _clear_async_session()
