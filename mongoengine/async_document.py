"""
Async Document classes for MongoEngine.

This module provides async versions of MongoEngine document classes that use
async I/O operations for all database interactions.
"""

from typing import Any, Dict, List, Optional, Tuple

from mongoengine.async_queryset_manager import AsyncQuerySetManager
from mongoengine.base.document import BaseDocument
from mongoengine.connection import DEFAULT_CONNECTION_NAME
from mongoengine.context_managers import set_write_concern
from mongoengine.document import TopLevelDocumentMetaclass
from mongoengine.io.aio.connection import async_get_db, _get_async_session
from mongoengine.io.aio.operations import AsyncIOOperations


class AsyncDocument(BaseDocument, metaclass=TopLevelDocumentMetaclass):
    """
    Async version of Document class.

    This class inherits all business logic from BaseDocument and provides
    async versions of I/O methods (save, delete, reload, etc.).

    Usage:
        class User(AsyncDocument):
            name = StringField()
            email = EmailField()

        # Async operations
        user = User(name='Alice', email='alice@example.com')
        await user.save()

        user = await User.objects.get(name='Alice')
        await user.delete()
    """

    my_metaclass = TopLevelDocumentMetaclass
    __slots__ = ("__objects",)

    # I/O operations layer - uses async operations
    _io = AsyncIOOperations

    # QuerySet manager for async operations
    objects = AsyncQuerySetManager()

    @property
    def pk(self) -> Optional[Any]:
        """Get the primary key.

        Returns:
            The primary key value or None if not set.
        """
        if "id_field" not in self._meta:
            return None
        return getattr(self, self._meta["id_field"])

    @pk.setter
    def pk(self, value: Any) -> None:
        """Set the primary key.

        Args:
            value: The primary key value to set.
        """
        return setattr(self, self._meta["id_field"], value)

    @classmethod
    async def _get_async_db(cls) -> Any:
        """Get the async database for this document.

        Returns:
            AsyncDatabase instance.
        """
        return await async_get_db(cls._meta.get("db_alias", DEFAULT_CONNECTION_NAME))

    @classmethod
    async def _get_async_collection(cls) -> Any:
        """Get the async collection for this document.

        Returns:
            AsyncCollection instance.
        """
        if not hasattr(cls, "_collection") or cls._collection is None:
            db = await cls._get_async_db()
            collection_name = cls._get_collection_name()

            if "capped" in cls._meta:
                cls._collection = await cls._io.create_collection(
                    db,
                    collection_name,
                    size=cls._meta.get("max_size"),
                    max=cls._meta.get("max_documents"),
                    capped=True,
                )
            else:
                cls._collection = db[collection_name]

        return cls._collection

    async def save(
        self,
        force_insert: bool = False,
        validate: bool = True,
        clean: bool = True,
        write_concern: Optional[Dict[str, Any]] = None,
        cascade: Optional[bool] = None,
        cascade_kwargs: Optional[Dict[str, Any]] = None,
        _refs: Optional[List] = None,
        save_condition: Optional[Dict[str, Any]] = None,
        signal_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "AsyncDocument":
        """Save the document to the database asynchronously.

        Args:
            force_insert: If True, forces an insert operation.
            validate: If True, validates the document before saving.
            clean: If True, calls the clean() method before validation.
            write_concern: Write concern options.
            cascade: Cascade save to referenced documents.
            cascade_kwargs: Kwargs to pass to cascaded saves.
            save_condition: Conditional save based on query.
            signal_kwargs: Kwargs to pass to signals.
            **kwargs: Additional keyword arguments.

        Returns:
            The saved document instance.
        """
        from mongoengine import signals

        if validate:
            self.validate(clean=clean)

        if write_concern is None:
            write_concern = {}

        doc = self.to_mongo()

        signal_kwargs = signal_kwargs or {}
        signals.pre_save.send(self.__class__, document=self, **signal_kwargs)

        if self._created or force_insert:
            object_id = await self._save_create(doc, force_insert, write_concern)
            created = True
        else:
            object_id, created = await self._save_update(
                doc, save_condition, write_concern
            )

        if created:
            self._created = False
        id_field = self._meta["id_field"]
        self._data[id_field] = self._fields[id_field].to_python(object_id)

        signals.post_save.send(
            self.__class__, document=self, created=created, **signal_kwargs
        )

        return self

    def _integrate_shard_key(
        self, doc: Dict[str, Any], select_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Integrate the collection's shard key to the select_dict.

        Args:
            doc: The document dict.
            select_dict: The selection dict to update.

        Returns:
            The updated select_dict.
        """
        shard_key = self._meta.get("shard_key", tuple())
        for k in shard_key:
            path = self._lookup_field(k.split("."))
            actual_key = [p.db_field for p in path]
            val = doc
            for ak in actual_key:
                val = val[ak]
            select_dict[".".join(actual_key)] = val

        return select_dict

    def _get_update_doc(self) -> Dict[str, Any]:
        """Get the update document with $set and $unset operations.

        Returns:
            Dict containing $set and $unset operations based on document changes.
        """
        updates, removals = self._delta()

        update_doc = {}
        if updates:
            update_doc["$set"] = updates
        if removals:
            update_doc["$unset"] = removals

        return update_doc

    async def _save_create(
        self, doc: Dict[str, Any], force_insert: bool, write_concern: Dict[str, Any]
    ) -> Any:
        """Save a new document asynchronously.

        Args:
            doc: The document dict to save.
            force_insert: Whether to force an insert.
            write_concern: Write concern options.

        Returns:
            The inserted document ID.
        """
        collection = await self._get_async_collection()

        with set_write_concern(collection, write_concern) as wc_collection:
            if force_insert:
                result = await self._io.insert_one(
                    wc_collection, doc, session=_get_async_session()
                )
                return result.inserted_id

            if "_id" in doc and doc["_id"] is not None:
                select_dict = {"_id": doc["_id"]}
                select_dict = self._integrate_shard_key(doc, select_dict)
                raw_object = await self._io.find_one_and_replace(
                    wc_collection, select_dict, doc, session=_get_async_session()
                )
                if raw_object:
                    return doc["_id"]

            if "_id" in doc and doc["_id"] is None:
                doc = doc.copy()
                del doc["_id"]

            result = await self._io.insert_one(
                wc_collection, doc, session=_get_async_session()
            )
            object_id = result.inserted_id

        return object_id

    async def _save_update(
        self,
        doc: Dict[str, Any],
        save_condition: Optional[Dict[str, Any]],
        write_concern: Dict[str, Any],
    ) -> Tuple[Any, bool]:
        """Update an existing document asynchronously.

        Args:
            doc: The document dict.
            save_condition: Optional save condition.
            write_concern: Write concern options.

        Returns:
            Tuple of (object_id, created) where created indicates if document was created.
        """
        collection = await self._get_async_collection()
        object_id = doc["_id"]
        created = False

        select_dict = {}
        if save_condition is not None:
            from mongoengine.queryset import transform

            select_dict = transform.query(self.__class__, **save_condition)

        select_dict["_id"] = object_id
        select_dict = self._integrate_shard_key(doc, select_dict)

        update_doc = self._get_update_doc()
        if update_doc:
            upsert = save_condition is None
            with set_write_concern(collection, write_concern) as wc_collection:
                result = await self._io.update_one(
                    wc_collection,
                    select_dict,
                    update_doc,
                    upsert=upsert,
                    session=_get_async_session(),
                )
                last_error = result.raw_result

            if not upsert and last_error["n"] == 0:
                from mongoengine.errors import SaveConditionError

                raise SaveConditionError(
                    "Race condition preventing document update detected"
                )

            if last_error is not None:
                updated_existing = last_error.get("updatedExisting")
                if updated_existing is False:
                    created = True

        return object_id, created

    async def delete(
        self, signal_kwargs: Optional[Dict[str, Any]] = None, **write_concern: Any
    ) -> None:
        """Delete this document asynchronously.

        Args:
            signal_kwargs: Kwargs to pass to signals.
            **write_concern: Write concern options.
        """
        from mongoengine import signals

        signal_kwargs = signal_kwargs or {}
        signals.pre_delete.send(self.__class__, document=self, **signal_kwargs)

        collection = await self._get_async_collection()

        with set_write_concern(collection, write_concern) as wc_collection:
            await self._io.delete_one(
                wc_collection,
                {"_id": self.pk},
                session=_get_async_session(),
            )

        signals.post_delete.send(self.__class__, document=self, **signal_kwargs)

    async def reload(self, *fields: str, **kwargs: Any) -> "AsyncDocument":
        """Reload this document from the database asynchronously.

        Args:
            *fields: Specific fields to reload.
            **kwargs: Additional options.

        Returns:
            The reloaded document instance.

        Raises:
            DoesNotExist: If the document no longer exists in the database.
        """
        collection = await self._get_async_collection()

        projection = None
        if fields:
            projection = {field: 1 for field in fields}
            projection["_id"] = 1

        obj = await self._io.find_one(
            collection,
            {"_id": self.pk},
            projection=projection,
            session=_get_async_session(),
        )

        if obj is None:
            from mongoengine.errors import DoesNotExist

            raise DoesNotExist(f"{self.__class__.__name__} object does not exist")

        for field_name in self._fields_ordered:
            if fields and field_name not in fields:
                continue
            if field_name in obj:
                setattr(
                    self,
                    field_name,
                    self._fields[field_name].to_python(obj[field_name]),
                )

        self._changed_fields = []
        return self

    async def modify(
        self, query: Optional[Dict[str, Any]] = None, **update: Any
    ) -> Optional["AsyncDocument"]:
        """Modify and return the updated document asynchronously.

        This performs an atomic find-and-modify operation.

        Args:
            query: Additional query filters.
            **update: Update operations.

        Returns:
            Updated document or None if no document matched.
        """
        if query:
            for key, value in query.items():
                if getattr(self, key, None) != value:
                    return None

        from mongoengine.queryset import transform

        update_doc = transform.update(self.__class__, **update)

        collection = await self._get_async_collection()

        result = await self._io.find_one_and_update(
            collection,
            {"_id": self.pk},
            update_doc,
            return_document=True,
            session=_get_async_session(),
        )

        if result:
            for field_name in self._fields_ordered:
                if field_name in result:
                    setattr(
                        self,
                        field_name,
                        self._fields[field_name].to_python(result[field_name]),
                    )
            self._changed_fields = []

        return self


# Make it available at module level
__all__ = ["AsyncDocument"]
