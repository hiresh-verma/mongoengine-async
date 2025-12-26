"""
Async QuerySet for MongoEngine.

This module provides async versions of QuerySet that use async I/O operations
for all database interactions.
"""

from mongoengine.context_managers import set_write_concern, set_read_write_concern
from mongoengine.errors import OperationError, NotUniqueError
from mongoengine.io.aio.connection import _get_async_session
from mongoengine.io.aio.operations import AsyncIOOperations
from mongoengine.queryset.base import BaseQuerySet
from pymongo.collection import ReturnDocument
import pymongo.errors


class AsyncQuerySet(BaseQuerySet):
    """
    Async version of QuerySet.

    This class inherits query building logic from BaseQuerySet and provides
    async versions of all I/O operations.

    Usage:
        # Async iteration
        async for user in AsyncUser.objects.filter(active=True):
            print(user.name)

        # Async list materialization
        users = await AsyncUser.objects.filter(active=True).to_list()

        # Async operations
        count = await AsyncUser.objects.count()
        await AsyncUser.objects.filter(active=False).delete()
        await AsyncUser.objects.filter(email='old@example.com').update(email='new@example.com')
    """

    # I/O operations layer - uses async operations
    _io = AsyncIOOperations

    async def _ensure_collection(self):
        """
        Ensure that the collection is loaded.

        For async querysets, the collection may not be available at init time,
        so we lazy-load it on first use.
        """
        if self._collection_obj is None:
            self._collection_obj = await self._document._get_async_collection()
        return self._collection_obj

    @property
    def _collection(self):
        """
        Property that returns the collection object.

        For AsyncQuerySet, if the collection is not yet loaded, we need to
        call await _ensure_collection() before accessing it.
        """
        if self._collection_obj is None:
            raise RuntimeError(
                "Collection not loaded. Call 'await queryset._ensure_collection()' first "
                "or use async methods that handle this automatically."
            )
        return self._collection_obj

    def __aiter__(self):
        """
        Async iteration support.

        Returns an async iterator over the queryset results.
        """
        return self._async_iter()

    async def _get_cursor(self):
        """
        Get or create the async cursor for this queryset.

        This method ensures the collection is loaded before creating the cursor.
        """
        # Ensure collection is loaded first
        collection = await self._ensure_collection()

        # If _cursor_obj already exists, return it
        if self._cursor_obj is not None:
            return self._cursor_obj

        # Create a new PyMongo async cursor
        if self._read_preference is not None or self._read_concern is not None:
            collection = collection.with_options(
                read_preference=self._read_preference, read_concern=self._read_concern
            )
            self._cursor_obj = self._io.find(
                collection, self._query, session=_get_async_session(), **self._cursor_args
            )
        else:
            self._cursor_obj = self._io.find(
                collection, self._query, session=_get_async_session(), **self._cursor_args
            )

        # Apply ordering
        if self._ordering:
            self._cursor_obj.sort(self._ordering)

        # Apply limit
        if self._limit is not None:
            self._cursor_obj.limit(self._limit)

        # Apply skip
        if self._skip:
            self._cursor_obj.skip(self._skip)

        return self._cursor_obj

    async def _async_iter(self):
        """Internal async iterator implementation."""
        cursor = await self._get_cursor()
        async for raw_doc in cursor:
            if self._as_pymongo:
                yield raw_doc
            elif self._scalar:
                yield self._get_scalar(self._document._from_son(raw_doc))
            else:
                doc = self._document._from_son(
                    raw_doc,
                    _auto_dereference=self._auto_dereference,
                )
                yield doc

    async def to_list(self, length=None):
        """
        Convert queryset to a list asynchronously.

        This is the async equivalent of list(queryset).

        Args:
            length: Maximum number of documents to return

        Returns:
            List of documents
        """
        results = []
        count = 0
        async for doc in self:
            results.append(doc)
            count += 1
            if length is not None and count >= length:
                break
        return results

    async def first(self):
        """
        Get the first document matching the query asynchronously.

        Returns:
            First document or None
        """
        queryset = self.clone()
        queryset = queryset.limit(1)
        async for doc in queryset:
            return doc
        return None

    async def get(self, *q_objs, **query):
        """
        Get a single document matching the query asynchronously.

        Raises DoesNotExist if no document found.
        Raises MultipleObjectsReturned if multiple documents found.

        Args:
            *q_objs: Q objects for complex queries
            **query: Query filters

        Returns:
            Document matching the query
        """
        queryset = self.clone()
        if q_objs or query:
            queryset = queryset.filter(*q_objs, **query)

        count = 0
        result = None
        async for doc in queryset.limit(2):
            count += 1
            if count == 1:
                result = doc
            else:
                break

        if count == 0:
            from mongoengine.errors import DoesNotExist
            msg = "%s matching query does not exist." % queryset._document._class_name
            raise queryset._document.DoesNotExist(msg)
        elif count > 1:
            from mongoengine.errors import MultipleObjectsReturned
            msg = "%d items returned, only one expected" % count
            raise queryset._document.MultipleObjectsReturned(msg)

        return result

    async def count(self, with_limit_and_skip=False):
        """
        Count documents matching the query asynchronously.

        Args:
            with_limit_and_skip: Include limit/skip in count

        Returns:
            int: Number of matching documents
        """
        if (
            self._limit == 0
            and with_limit_and_skip is False
            or self._none
            or self._empty
        ):
            return 0

        kwargs = (
            {"limit": self._limit, "skip": self._skip} if with_limit_and_skip else {}
        )

        if self._limit == 0:
            kwargs.pop("limit", None)

        if self._hint not in (-1, None):
            kwargs["hint"] = self._hint

        if self._collation:
            kwargs["collation"] = self._collation

        # Ensure collection is loaded
        collection = await self._ensure_collection()

        # Use async count_documents
        count = await self._io.count_documents(
            collection=collection,
            filter=self._query,
            session=_get_async_session(),
            **kwargs,
        )

        self._cursor_obj = None
        return count

    async def delete(self, write_concern=None, _from_doc_delete=False, cascade_refs=None):
        """
        Delete all documents matching the query asynchronously.

        Args:
            write_concern: Write concern options
            _from_doc_delete: Internal flag
            cascade_refs: Cascade delete to references

        Returns:
            int: Number of deleted documents (if acknowledged)
        """
        if write_concern is None:
            write_concern = {}

        queryset = self.clone()
        if queryset._none or queryset._empty:
            return 0

        # Handle cascade deletes if needed
        # (simplified for now - full implementation would handle all cascade rules)

        kwargs = {}
        if self._hint not in (-1, None):
            kwargs["hint"] = self._hint
        if self._collation:
            kwargs["collation"] = self._collation
        if self._comment:
            kwargs["comment"] = self._comment

        # Ensure collection is loaded
        collection = await queryset._ensure_collection()

        with set_write_concern(collection, write_concern) as collection:
            result = await self._io.delete_many(
                collection,
                queryset._query,
                session=_get_async_session(),
                **kwargs,
            )

            if result.acknowledged:
                return result.deleted_count

    async def update(
        self,
        upsert=False,
        multi=True,
        write_concern=None,
        read_concern=None,
        full_result=False,
        array_filters=None,
        **update,
    ):
        """
        Update all documents matching the query asynchronously.

        Args:
            upsert: Insert if no documents match
            multi: Update multiple documents
            write_concern: Write concern options
            read_concern: Read concern options
            full_result: Return full UpdateResult
            array_filters: Array filters for update
            **update: Update operations

        Returns:
            Number of updated documents (or UpdateResult if full_result=True)
        """
        if not update and not upsert:
            raise OperationError("No update parameters, would remove data")

        if write_concern is None:
            write_concern = {}
        if self._none or self._empty:
            return 0

        queryset = self.clone()
        query = queryset._query

        from mongoengine.queryset import transform

        if "__raw__" in update and isinstance(update["__raw__"], list):
            update = [
                transform.update(queryset._document, **{"__raw__": u})
                for u in update["__raw__"]
            ]
        else:
            update = transform.update(queryset._document, **update)

        if upsert and "_cls" in query:
            if "$set" in update:
                update["$set"]["_cls"] = queryset._document._class_name
            else:
                update["$set"] = {"_cls": queryset._document._class_name}

        kwargs = {}
        if self._hint not in (-1, None):
            kwargs["hint"] = self._hint
        if self._collation:
            kwargs["collation"] = self._collation
        if self._comment:
            kwargs["comment"] = self._comment

        # Ensure collection is loaded
        collection = await queryset._ensure_collection()

        try:
            with set_read_write_concern(
                collection, write_concern, read_concern
            ) as collection:
                if multi:
                    result = await self._io.update_many(
                        collection,
                        query,
                        update,
                        upsert=upsert,
                        session=_get_async_session(),
                        array_filters=array_filters,
                        **kwargs,
                    )
                else:
                    result = await self._io.update_one(
                        collection,
                        query,
                        update,
                        upsert=upsert,
                        session=_get_async_session(),
                        array_filters=array_filters,
                        **kwargs,
                    )
            if full_result:
                return result
            elif result.raw_result:
                return result.raw_result["n"]
        except pymongo.errors.DuplicateKeyError as err:
            raise NotUniqueError("Update failed (%s)" % err)
        except pymongo.errors.OperationFailure as err:
            if str(err) == "multi not coded yet":
                message = "update() method requires MongoDB 1.1.3+"
                raise OperationError(message)
            raise OperationError("Update failed (%s)" % err)

    async def modify(
        self,
        upsert=False,
        remove=False,
        new=False,
        array_filters=None,
        **update,
    ):
        """
        Atomically find and modify a document asynchronously.

        Args:
            upsert: Insert if no document matches
            remove: Remove instead of update
            new: Return updated document (vs original)
            array_filters: Array filters for update
            **update: Update operations

        Returns:
            Modified document or None
        """
        if remove and new:
            raise OperationError("Conflicting parameters: remove and new")

        if not update and not upsert and not remove:
            raise OperationError("No update parameters, must either update or remove")

        if self._none or self._empty:
            return None

        queryset = self.clone()
        query = queryset._query

        if self._where_clause:
            where_clause = self._sub_js_fields(self._where_clause)
            query["$where"] = where_clause

        if not remove:
            from mongoengine.queryset import transform
            update = transform.update(queryset._document, **update)

        sort = queryset._ordering

        # Ensure collection is loaded
        collection = await queryset._ensure_collection()

        try:
            if remove:
                result = await self._io.find_one_and_delete(
                    collection,
                    query,
                    sort=sort,
                    session=_get_async_session(),
                    **self._cursor_args,
                )
            else:
                if new:
                    return_doc = ReturnDocument.AFTER
                else:
                    return_doc = ReturnDocument.BEFORE
                result = await self._io.find_one_and_update(
                    collection,
                    query,
                    update,
                    upsert=upsert,
                    sort=sort,
                    return_document=return_doc,
                    session=_get_async_session(),
                    array_filters=array_filters,
                    **self._cursor_args,
                )
        except pymongo.errors.DuplicateKeyError as err:
            raise NotUniqueError("Update failed (%s)" % err)
        except pymongo.errors.OperationFailure as err:
            raise OperationError("Update failed (%s)" % err)

        if result is not None:
            result = self._document._from_son(result)

        return result

    async def distinct(self, field):
        """
        Get distinct values for a field asynchronously.

        Args:
            field: Field name

        Returns:
            List of distinct values
        """
        queryset = self.clone()

        try:
            field = self._fields_to_dbfields([field]).pop()
        except:
            pass

        # Ensure collection is loaded
        collection = await queryset._ensure_collection()

        raw_values = await self._io.distinct(
            collection,
            field,
            filter=queryset._query,
            session=_get_async_session(),
        )

        if not self._auto_dereference:
            return raw_values

        # Handle dereferencing if needed
        return raw_values

    async def sum(self, field):
        """
        Sum values of a field asynchronously.

        Args:
            field: Field name

        Returns:
            Sum of field values
        """
        db_field = self._fields_to_dbfields([field]).pop()
        pipeline = [
            {"$match": self._query},
            {"$group": {"_id": "sum", "total": {"$sum": "$" + db_field}}},
        ]

        # Ensure collection is loaded
        collection = await self._ensure_collection()

        result = []
        cursor = self._io.aggregate(
            collection,
            pipeline,
            session=_get_async_session(),
        )
        async for doc in cursor:
            result.append(doc)

        if result:
            return result[0]["total"]
        return 0

    async def average(self, field):
        """
        Average values of a field asynchronously.

        Args:
            field: Field name

        Returns:
            Average of field values
        """
        db_field = self._fields_to_dbfields([field]).pop()
        pipeline = [
            {"$match": self._query},
            {"$group": {"_id": "avg", "total": {"$avg": "$" + db_field}}},
        ]

        # Ensure collection is loaded
        collection = await self._ensure_collection()

        result = []
        cursor = self._io.aggregate(
            collection,
            pipeline,
            session=_get_async_session(),
        )
        async for doc in cursor:
            result.append(doc)

        if result:
            return result[0]["total"]
        return 0

    async def select_related(self, max_depth=1):
        """
        Bulk dereference referenced documents to avoid N+1 queries.

        This method fetches all referenced documents in a single batch of
        queries, significantly improving performance when accessing references.

        Args:
            max_depth: Maximum depth to recursively dereference (default: 1)

        Returns:
            List of documents with references pre-loaded

        Example:
            # Without select_related (N+1 queries):
            posts = await Post.objects.to_list()
            for post in posts:
                author = await Post.author.fetch(post)  # N queries!

            # With select_related (2 queries):
            posts = await Post.objects.select_related().to_list()
            for post in posts:
                print(post.author.name)  # No additional queries!

            # Nested dereferencing:
            posts = await Post.objects.select_related(max_depth=2).to_list()
        """
        from mongoengine.async_dereference import AsyncDeReference

        # Get all documents first
        docs = await self.to_list()

        if not docs:
            return docs

        # Bulk dereference
        dereferencer = AsyncDeReference()
        await dereferencer(docs, max_depth=max_depth + 1)

        return docs


__all__ = ['AsyncQuerySet']
