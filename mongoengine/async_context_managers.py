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

from mongoengine.async_pymongo_support import async_count_documents
from mongoengine.base.fields import _no_dereference_for_fields
from mongoengine.common import _import_class
from mongoengine.connection import DEFAULT_CONNECTION_NAME
from mongoengine.io.aio.connection import (
    async_get_connection,
    async_get_db,
    _set_async_session,
    _clear_async_session,
    _get_async_session
)

__all__ = (
    "async_switch_db",
    "async_switch_collection",
    "async_run_in_transaction",
    "async_no_dereference",
    "async_no_sub_classes",
    "async_query_counter",
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
        self._original_collection = getattr(self.cls, "_collection", None)
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
        self._original_collection = getattr(self.cls, "_collection", None)
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


@asynccontextmanager
async def async_no_dereference(cls: Type) -> AsyncGenerator[None, None]:
    """Async no_dereference context manager.

    Turns off all dereferencing in Documents for the duration of the context.

    Args:
        cls: The document class to disable dereferencing for.

    Yields:
        None

    Example:
        async with async_no_dereference(AsyncGroup):
            groups = await AsyncGroup.objects.to_list()
            # References are not dereferenced
    """
    try:
        ReferenceField = _import_class("ReferenceField")
        GenericReferenceField = _import_class("GenericReferenceField")
        ComplexBaseField = _import_class("ComplexBaseField")

        deref_fields = [
            field
            for name, field in cls._fields.items()
            if isinstance(
                field, (ReferenceField, GenericReferenceField, ComplexBaseField)
            )
        ]

        with _no_dereference_for_fields(*deref_fields):
            yield None
    finally:
        pass


class async_no_sub_classes:
    """Async no_sub_classes context manager.

    Only returns instances of this class and no sub (inherited) classes.

    Example:
        async with async_no_sub_classes(AsyncGroup) as Group:
            groups = await Group.objects.to_list()
            # Only AsyncGroup instances, not subclasses
    """

    def __init__(self, cls: Type) -> None:
        """Construct the async_no_sub_classes context manager.

        Args:
            cls: The class to turn querying subclasses off for.
        """
        self.cls = cls
        self.cls_initial_subclasses: Optional[tuple] = None

    async def __aenter__(self) -> Type:
        """Change the _subclasses to exclude subclasses.

        Returns:
            The document class.
        """
        self.cls_initial_subclasses = self.cls._subclasses
        self.cls._subclasses = (self.cls._class_name,)
        return self.cls

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Reset the _subclasses.

        Returns:
            False to not suppress exceptions.
        """
        self.cls._subclasses = self.cls_initial_subclasses
        return False


class async_query_counter:
    """Async query_counter context manager to count database queries.

    This works by updating the profiling_level of the database so that all queries
    get logged, resetting the db.system.profile collection at the beginning of the
    context and counting the new entries.

    Note: This is a global counter so queries issued by other threads/processes
    can interfere with it. Designed for debugging purposes.

    Example:
        class AsyncUser(AsyncDocument):
            name = StringField()

        async with async_query_counter() as q:
            user = AsyncUser(name='Bob')
            assert await q.get_count() == 0  # no query fired yet
            await user.save()
            assert await q.get_count() == 1  # 1 query was fired, an 'insert'
            user_bis = await AsyncUser.objects.first()
            assert await q.get_count() == 2  # a 2nd query was fired, a 'find_one'
    """

    def __init__(self, alias: str = DEFAULT_CONNECTION_NAME) -> None:
        """Initialize the async query counter.

        Args:
            alias: The database connection alias to use.
        """
        self.alias = alias
        self.db: Optional[Any] = None
        self.initial_profiling_level: Optional[int] = None
        self._ctx_query_counter = 0

        self._ignored_query = {
            "op": {"$ne": "killcursors"},
            "command.killCursors": {"$exists": False},
        }

    async def _turn_on_profiling(self) -> None:
        """Turn on database profiling."""
        self.db = await async_get_db(alias=self.alias)

        # Get current profiling level
        profile_update_res = await self.db.command(
            {"profile": 0}, session=_get_async_session()
        )
        self.initial_profiling_level = profile_update_res["was"]

        # Drop existing profile collection and start profiling
        await self.db.system.profile.drop()
        await self.db.command({"profile": 2}, session=_get_async_session())

        # Update ignored query to exclude system.indexes
        self._ignored_query["ns"] = {"$ne": f"{self.db.name}.system.indexes"}

    async def _reset_profiling(self) -> None:
        """Reset database profiling to original level."""
        if self.db is not None and self.initial_profiling_level is not None:
            await self.db.command({"profile": self.initial_profiling_level})

    async def __aenter__(self) -> "async_query_counter":
        """Enter the context manager.

        Returns:
            Self for query counting.
        """
        await self._turn_on_profiling()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Exit the context manager.

        Returns:
            False to not suppress exceptions.
        """
        await self._reset_profiling()
        return False

    async def get_count(self) -> int:
        """Get the number of queries issued so far.

        Returns:
            Number of queries issued.

        Example:
            async with async_query_counter() as q:
                await user.save()
                count = await q.get_count()
                assert count == 1
        """
        if self.db is None:
            return 0

        count = (
            await async_count_documents(self.db.system.profile, self._ignored_query)
            - self._ctx_query_counter
        )
        self._ctx_query_counter += 1
        return count

    def __repr__(self) -> str:
        """Represent query counter as string.

        Returns:
            String representation.
        """
        return "async_query_counter()"
