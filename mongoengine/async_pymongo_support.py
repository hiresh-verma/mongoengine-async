"""
Async helper functions for PyMongo async operations.
"""

from pymongo.errors import OperationFailure

from mongoengine.io.aio.connection import _get_async_session
from mongoengine.pymongo_support import PYMONGO_VERSION


async def async_count_documents(
    collection, filter, skip=None, limit=None, hint=None, collation=None, session=None
):
    """Async version of count_documents for pymongo async operations."""
    if limit == 0:
        return 0  # Pymongo raises an OperationFailure if called with limit=0

    kwargs = {}
    if skip is not None:
        kwargs["skip"] = skip
    if limit is not None:
        kwargs["limit"] = limit
    if hint not in (-1, None):
        kwargs["hint"] = hint
    if collation is not None:
        kwargs["collation"] = collation

    # Use session if provided, otherwise get from context
    if session is None:
        session = _get_async_session()

    # count_documents appeared in pymongo 3.7
    if PYMONGO_VERSION >= (3, 7):
        try:
            is_active_session = session is not None
            if not filter and set(kwargs) <= {"max_time_ms"} and not is_active_session:
                # when no filter is provided, estimated_document_count
                # is a lot faster as it uses the collection metadata
                return await collection.estimated_document_count(**kwargs)
            else:
                return await collection.count_documents(
                    filter=filter, session=session, **kwargs
                )
        except OperationFailure as err:
            if PYMONGO_VERSION >= (4,):
                raise
            # OperationFailure - accounts for some operators that used to work
            # with .count but are no longer working with count_documents (i.e $near, $nearSphere)
            # Fallback to aggregate
            pipeline = [{"$match": filter}]
            if skip is not None:
                pipeline.append({"$skip": skip})
            if limit is not None:
                pipeline.append({"$limit": limit})
            pipeline.append({"$group": {"_id": 1, "n": {"$sum": 1}}})

            result = []
            async for doc in collection.aggregate(pipeline, session=session, **kwargs):
                result.append(doc)

            return result[0]["n"] if result else 0
    else:
        # For pymongo < 3.7, use the old count method
        return await collection.count(filter, session=session, **kwargs)


async def async_list_collection_names(db, session=None):
    """
    Async version of list_collection_names.

    Returns list of collection names, filtering out system collections.
    """
    if session is None:
        session = _get_async_session()

    collections = await db.list_collection_names(session=session)
    return [c for c in collections if not c.startswith("system.")]
