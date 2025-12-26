"""
Async field types for MongoEngine.

This module provides async versions of reference fields that require
explicit dereferencing instead of automatic lazy loading.
"""

from typing import Any, List, Optional, Type, Union
from inspect import isclass

from bson import DBRef, ObjectId
from mongoengine.base.fields import BaseField
from mongoengine.base.document import BaseDocument
from mongoengine.document import Document
from mongoengine.fields import DO_NOTHING, RECURSIVE_REFERENCE_CONSTANT
from mongoengine.base.common import _DocumentRegistry
from mongoengine.errors import DoesNotExist
from mongoengine.io.aio.connection import _get_async_session


__all__ = [
    "AsyncReferenceField",
    "AsyncCachedReferenceField",
    "AsyncGenericReferenceField",
]


class AsyncReferenceField(BaseField):
    """
    Async reference to a document that must be explicitly dereferenced.

    Unlike the sync ReferenceField which auto-dereferences on access,
    AsyncReferenceField requires explicit async dereferencing using the
    fetch() method.

    Usage:
        class Post(AsyncDocument):
            author = AsyncReferenceField(User)

        # Access raw reference (ObjectId or DBRef)
        post = await Post.objects.first()
        author_id = post.author  # Returns ObjectId/DBRef, no I/O

        # Explicit async dereferencing
        author = await post.author.fetch(post)  # Async I/O to load author

        # Or use select_related for bulk prefetching
        post = await Post.objects.select_related('author').first()
        author = post.author  # Already dereferenced

    The options for reverse_delete_rule are:
      * DO_NOTHING (0)  - don't do anything (default).
      * NULLIFY    (1)  - Updates the reference to null.
      * CASCADE    (2)  - Deletes the documents associated with the reference.
      * DENY       (3)  - Prevent the deletion of the reference object.
      * PULL       (4)  - Pull the reference from a ListField of references
    """

    def __init__(
        self,
        document_type: Union[str, Type[BaseDocument]],
        dbref: bool = False,
        reverse_delete_rule: int = DO_NOTHING,
        **kwargs: Any,
    ) -> None:
        """Initialize the Async Reference Field.

        Args:
            document_type: The type of Document that will be referenced.
            dbref: Store the reference as DBRef or as ObjectId.
            reverse_delete_rule: Determines what to do when the referring object is deleted.
            **kwargs: Keyword arguments passed to parent BaseField.
        """
        if not (
            isinstance(document_type, str)
            or (isclass(document_type) and issubclass(document_type, BaseDocument))
        ):
            self.error(
                "Argument to AsyncReferenceField constructor must be a "
                "document class or a string"
            )

        self.dbref = dbref
        self.document_type_obj = document_type
        self.reverse_delete_rule = reverse_delete_rule
        super().__init__(**kwargs)
        # Never auto-dereference for async
        self.set_auto_dereferencing(False)

    @property
    def document_type(self) -> Type[BaseDocument]:
        """Get the actual document class (resolve string references).

        Returns:
            The resolved document class.
        """
        if isinstance(self.document_type_obj, str):
            if self.document_type_obj == RECURSIVE_REFERENCE_CONSTANT:
                self.document_type_obj = self.owner_document
            else:
                self.document_type_obj = _DocumentRegistry.get(self.document_type_obj)
        return self.document_type_obj

    @staticmethod
    async def _async_lazy_load_ref(
        ref_cls: Type[BaseDocument], dbref: DBRef
    ) -> BaseDocument:
        """Async dereference a DBRef to get the referenced document.

        Args:
            ref_cls: The document class to dereference to.
            dbref: The DBRef to dereference.

        Returns:
            The dereferenced document instance.

        Raises:
            DoesNotExist: If the referenced document doesn't exist.
        """
        db = await ref_cls._get_async_db()

        collection = db[dbref.collection]
        dereferenced_son = await collection.find_one(
            {"_id": dbref.id}, session=_get_async_session()
        )

        if dereferenced_son is None:
            raise DoesNotExist(f"Trying to dereference unknown document {dbref}")

        return ref_cls._from_son(dereferenced_son)

    async def fetch(self, instance: BaseDocument) -> Optional[BaseDocument]:
        """Explicitly fetch the referenced document asynchronously.

        This method must be called to dereference the reference and get
        the actual document object.

        Args:
            instance: The document instance that owns this field.

        Returns:
            The dereferenced document, or None if the reference is None.

        Example:
            post = await Post.objects.first()
            author = await post.author.fetch(post)
            print(author.name)
        """
        # Get the raw reference value
        ref_value = instance._data.get(self.name)

        if ref_value is None:
            return None

        # If already dereferenced (e.g., via select_related), return it
        if isinstance(ref_value, BaseDocument):
            return ref_value

        # Dereference DBRef
        if isinstance(ref_value, DBRef):
            if hasattr(ref_value, "cls"):
                # Dereference using the class type specified in the reference
                cls = _DocumentRegistry.get(ref_value.cls)
            else:
                cls = self.document_type

            doc = await self._async_lazy_load_ref(cls, ref_value)
            # Cache the dereferenced document
            instance._data[self.name] = doc
            return doc

        # Handle ObjectId reference (need to create DBRef first)
        if isinstance(ref_value, ObjectId):
            dbref = DBRef(
                collection=self.document_type._get_collection_name(), id=ref_value
            )
            doc = await self._async_lazy_load_ref(self.document_type, dbref)
            # Cache the dereferenced document
            instance._data[self.name] = doc
            return doc

        # If it's already a document, return it
        if isinstance(ref_value, BaseDocument):
            return ref_value

        return None

    def __get__(self, instance: Optional[BaseDocument], owner: Type) -> Any:
        """Descriptor that returns the raw reference (ObjectId/DBRef).

        Unlike sync ReferenceField, this does NOT auto-dereference.
        Use await field.fetch(instance) to dereference.

        Args:
            instance: The document instance.
            owner: The document class.

        Returns:
            The field instance if called on class, otherwise the raw reference value.
        """
        if instance is None:
            return self

        return instance._data.get(self.name)

    def to_mongo(
        self, document: Union[BaseDocument, DBRef, ObjectId, None]
    ) -> Union[DBRef, ObjectId, None]:
        """Convert the document reference to MongoDB format.

        Args:
            document: The document to convert (can be a Document, DBRef, or ObjectId).

        Returns:
            DBRef or ObjectId suitable for MongoDB storage.
        """
        if isinstance(document, DBRef):
            if not self.dbref:
                return document.id
            return document

        if isinstance(document, BaseDocument):
            # We need the id from the saved object to create the DBRef
            id_ = document.pk

            if id_ is None:
                self.error(
                    "You can only reference documents once they have been saved to the database"
                )

            collection = document._get_collection_name()
            if self.dbref:
                # Store as DBRef
                if document._meta.get("allow_inheritance"):
                    return DBRef(
                        collection,
                        id_,
                        document._class_name,
                        database=document._get_db().name,
                    )
                else:
                    return DBRef(collection, id_, database=document._get_db().name)
            else:
                # Store as ObjectId
                return id_

        # Handle ObjectId
        if isinstance(document, ObjectId):
            return document

        return document

    def to_python(self, value: Any) -> Union[BaseDocument, DBRef, ObjectId, None]:
        """Convert MongoDB value to Python.

        Args:
            value: The value from MongoDB (ObjectId, DBRef, or dict).

        Returns:
            The Python representation (ObjectId, DBRef, or Document).
        """
        # If it's already a document, return it
        if isinstance(value, BaseDocument):
            return value

        # If it's a DBRef, return it as-is (will be dereferenced on fetch)
        if isinstance(value, DBRef):
            return value

        # If it's an ObjectId, return it as-is
        if isinstance(value, ObjectId):
            return value

        # If it's a dict (from MongoDB), might need to convert to DBRef
        if isinstance(value, dict):
            if "$ref" in value:
                # It's a DBRef in dict form
                return DBRef(value["$ref"], value["$id"], value.get("$db"))

        return value

    def validate(self, value: Any, clean: bool = True) -> None:
        """Validate the reference field value.

        Args:
            value: The value to validate.
            clean: Whether to call clean before validation.
        """
        if value is None:
            if self.required:
                self.error("Field is required")
            return

        # Allow ObjectId, DBRef, or BaseDocument instances
        if not isinstance(value, (ObjectId, DBRef, BaseDocument)):
            self.error(
                f"ReferenceField only accepts DBRef, ObjectId or Document instances, got {type(value)}"
            )

        # If it's a Document, check if it's saved
        if isinstance(value, BaseDocument):
            if value.pk is None:
                self.error("You can only reference documents once they have been saved")

            # Check document type
            if not isinstance(value, self.document_type):
                self.error(
                    f"ReferenceField only accepts instances of {self.document_type._class_name}, "
                    f"got {value._class_name}"
                )


class AsyncGenericReferenceField(BaseField):
    """
    Async reference to any Document subclass.

    Unlike sync GenericReferenceField, this requires explicit async dereferencing.

    Usage:
        class Comment(AsyncDocument):
            content = StringField()
            target = AsyncGenericReferenceField()  # Can reference any document

        # Create comment targeting different document types
        comment1 = Comment(content='Great!', target=some_post)
        comment2 = Comment(content='Nice!', target=some_user)

        # Explicit dereferencing
        target_doc = await Comment.target.fetch(comment1)
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Async Generic Reference Field.

        Args:
            choices: Optional list of allowed Document types.
            **kwargs: Keyword arguments passed to parent BaseField.
        """
        choices = kwargs.pop("choices", None)
        super().__init__(*args, **kwargs)
        self.set_auto_dereferencing(False)  # Never auto-dereference for async
        self.choices = []

        # Keep the choices as a list of allowed Document class names
        if choices:
            for choice in choices:
                if isinstance(choice, str):
                    self.choices.append(choice)
                elif isinstance(choice, type) and issubclass(choice, BaseDocument):
                    self.choices.append(choice._class_name)
                else:
                    self.error(
                        "Invalid choices provided: must be a list of "
                        "Document subclasses and/or str"
                    )

    def _validate_choices(self, value: Any) -> None:
        """Validate that the value is one of the allowed choices.

        Args:
            value: The value to validate.
        """
        if isinstance(value, dict):
            value = value.get("_cls")
        elif isinstance(value, BaseDocument):
            value = value._class_name
        super()._validate_choices(value)

    @staticmethod
    async def _async_lazy_load_ref(
        ref_cls: Type[BaseDocument], dbref: DBRef
    ) -> BaseDocument:
        """Async dereference a DBRef to get the referenced document.

        Args:
            ref_cls: The document class to dereference to.
            dbref: The DBRef to dereference.

        Returns:
            The dereferenced document instance.

        Raises:
            DoesNotExist: If the referenced document doesn't exist.
        """
        db = await ref_cls._get_async_db()
        collection = db[dbref.collection]

        dereferenced_son = await collection.find_one(
            {"_id": dbref.id}, session=_get_async_session()
        )

        if dereferenced_son is None:
            raise DoesNotExist(f"Trying to dereference unknown document {dbref}")

        return ref_cls._from_son(dereferenced_son)

    async def fetch(self, instance: BaseDocument) -> Optional[BaseDocument]:
        """Explicitly fetch the referenced document asynchronously.

        Args:
            instance: The document instance that owns this field.

        Returns:
            The dereferenced document of the appropriate type, or None.
        """
        value = instance._data.get(self.name)

        if value is None:
            return None

        # If already dereferenced, return it
        if isinstance(value, BaseDocument):
            return value

        # Dereference dict format: {"_cls": class_name, "_ref": DBRef}
        if isinstance(value, dict):
            if "_cls" in value and "_ref" in value:
                doc_cls = _DocumentRegistry.get(value["_cls"])
                doc = await self._async_lazy_load_ref(doc_cls, value["_ref"])
                # Cache the dereferenced document
                instance._data[self.name] = doc
                return doc

        return None

    def __get__(self, instance: Optional[BaseDocument], owner: Type) -> Any:
        """Return the raw reference value (dict with _cls and _ref).

        Args:
            instance: The document instance.
            owner: The document class.

        Returns:
            The field instance if called on class, otherwise the raw reference value.
        """
        if instance is None:
            return self

        return instance._data.get(self.name)

    def validate(self, value: Any) -> None:
        """Validate the generic reference field value.

        Args:
            value: The value to validate.
        """
        from bson.son import SON

        if not isinstance(value, (BaseDocument, DBRef, dict, SON)):
            self.error("GenericReferences can only contain documents")

        if isinstance(value, (dict, SON)):
            if "_ref" not in value or "_cls" not in value:
                self.error("GenericReferences can only contain documents")

        # Check if document is saved
        elif isinstance(value, BaseDocument) and value.id is None:
            self.error("You can only reference documents once they have been saved")

    def to_mongo(self, document: Any) -> Any:
        """Convert the document reference to MongoDB format.

        Args:
            document: The document to convert.

        Returns:
            Dict with "_cls" (class name) and "_ref" (DBRef).
        """
        from bson.son import SON

        if document is None:
            return None

        if isinstance(document, (dict, SON, ObjectId, DBRef)):
            return document

        id_field_name = document.__class__._meta["id_field"]
        id_field = document.__class__._fields[id_field_name]

        if isinstance(document, BaseDocument):
            # We need the id from the saved object to create the DBRef
            id_ = document.id
            if id_ is None:
                self.error("You can only reference documents once they have been saved")
        else:
            id_ = document

        id_ = id_field.to_mongo(id_)
        collection = document._get_collection_name()
        ref = DBRef(collection, id_)

        return SON((("_cls", document._class_name), ("_ref", ref)))

    def to_python(self, value: Any) -> Any:
        """Convert MongoDB value to Python.

        Args:
            value: The value from MongoDB.

        Returns:
            The Python representation.
        """
        if isinstance(value, BaseDocument):
            return value

        if isinstance(value, dict):
            return value

        return value

    def prepare_query_value(self, op: str, value: Any) -> Any:
        """Prepare value for query operations.

        Args:
            op: The query operation.
            value: The value to prepare.

        Returns:
            The prepared value for MongoDB query.
        """
        if value is None:
            return None

        return self.to_mongo(value)


class AsyncCachedReferenceField(BaseField):
    """
    Async reference field with cached denormalized fields.

    This field stores selected fields from the referenced document
    directly in the referencing document to avoid extra queries.

    Usage:
        class Post(AsyncDocument):
            title = StringField()
            author = AsyncCachedReferenceField(
                User,
                fields=['name', 'email']  # Cache these fields
            )

        # When you save a post, it stores author._id plus name and email
        post = Post(title='Hello', author=user)
        await post.save()

        # Accessing cached fields doesn't require I/O
        author_name = post.author.name  # No database query!

        # Full dereference still available
        full_author = await Post.author.fetch(post)
    """

    def __init__(
        self,
        document_type: Union[str, Type[BaseDocument]],
        fields: Optional[List[str]] = None,
        auto_sync: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize the Async Cached Reference Field.

        Args:
            document_type: The type of Document that will be referenced.
            fields: List of fields to cache from the referenced document.
            auto_sync: If True, automatically sync cached fields (NOT IMPLEMENTED for async).
            **kwargs: Keyword arguments passed to parent BaseField.
        """
        if fields is None:
            fields = []

        if not isinstance(document_type, str) and not (
            isclass(document_type) and issubclass(document_type, BaseDocument)
        ):
            self.error(
                "Argument to AsyncCachedReferenceField constructor must be a "
                "document class or a string"
            )

        if auto_sync:
            # Auto-sync is complex for async, not implementing initially
            import warnings

            warnings.warn(
                "auto_sync is not yet implemented for AsyncCachedReferenceField",
                UserWarning,
            )

        self.auto_sync = False  # Disabled for async
        self.document_type_obj = document_type
        self.fields = fields
        super().__init__(**kwargs)
        self.set_auto_dereferencing(False)

    @property
    def document_type(self) -> Type[BaseDocument]:
        """Get the actual document class (resolve string references).

        Returns:
            The resolved document class.
        """
        if isinstance(self.document_type_obj, str):
            if self.document_type_obj == RECURSIVE_REFERENCE_CONSTANT:
                self.document_type_obj = self.owner_document
            else:
                self.document_type_obj = _DocumentRegistry.get(self.document_type_obj)
        return self.document_type_obj

    @staticmethod
    async def _async_lazy_load_ref(
        ref_cls: Type[BaseDocument], dbref: DBRef
    ) -> BaseDocument:
        """Async dereference a DBRef.

        Args:
            ref_cls: The document class to dereference to.
            dbref: The DBRef to dereference.

        Returns:
            The dereferenced document instance.

        Raises:
            DoesNotExist: If the referenced document doesn't exist.
        """
        db = await ref_cls._get_async_db()
        collection = db[dbref.collection]

        dereferenced_son = await collection.find_one(
            {"_id": dbref.id}, session=_get_async_session()
        )

        if dereferenced_son is None:
            raise DoesNotExist(f"Trying to dereference unknown document {dbref}")

        return ref_cls._from_son(dereferenced_son)

    async def fetch(self, instance: BaseDocument) -> Optional[BaseDocument]:
        """Fetch the full referenced document.

        This loads all fields, not just the cached ones.

        Args:
            instance: The document instance that owns this field.

        Returns:
            The full dereferenced document.
        """
        value = instance._data.get(self.name)

        if value is None:
            return None

        # If already a full document, return it
        if isinstance(value, BaseDocument):
            return value

        # If it's a dict with cached fields, fetch the full document
        if isinstance(value, dict) and "_id" in value:
            collection = self.document_type._get_collection_name()
            dbref = DBRef(collection, value["_id"])
            doc = await self._async_lazy_load_ref(self.document_type, dbref)
            # Cache the full document
            instance._data[self.name] = doc
            return doc

        return None

    def __get__(self, instance: Optional[BaseDocument], owner: Type) -> Any:
        """Return the cached reference data.

        For AsyncCachedReferenceField, this returns a dict with _id and cached fields.

        Args:
            instance: The document instance.
            owner: The document class.

        Returns:
            The field instance if called on class, otherwise the cached reference value.
        """
        if instance is None:
            return self

        value = instance._data.get(self.name)

        if isinstance(value, dict) and not isinstance(value, BaseDocument):

            class CachedReference:
                def __init__(self, data: Any, field: Any) -> None:
                    self._data = data
                    self._field = field

                def __getattr__(self, name: str) -> Any:
                    if name in self._data:
                        return self._data[name]
                    raise AttributeError(f"Cached field '{name}' not available")

                def __repr__(self) -> str:
                    return f"<CachedReference: {self._data}>"

            return CachedReference(value, self)

        return value

    def to_mongo(
        self,
        document: BaseDocument,
        use_db_field: bool = True,
        fields: Optional[List[str]] = None,
    ) -> Any:
        """Convert to MongoDB format with cached fields.

        Args:
            document: The document to convert.
            use_db_field: Whether to use db_field names.
            fields: Optional list of fields to include.

        Returns:
            Dict with _id and specified cached fields.
        """
        from bson.son import SON

        id_field_name = self.document_type._meta["id_field"]
        id_field = self.document_type._fields[id_field_name]

        if isinstance(document, BaseDocument):
            # We need the id from the saved object
            id_ = document.pk
            if id_ is None:
                self.error("You can only reference documents once they have been saved")
        else:
            self.error("Only accept a document object")

        value = SON((("_id", id_field.to_mongo(id_)),))

        # Add cached fields manually to avoid conflicts with _id
        if fields:
            new_fields = [f for f in self.fields if f in fields]
        else:
            new_fields = self.fields

        # Manually extract cached field values
        for field_name in new_fields:
            if field_name in document._fields:
                field_obj = document._fields[field_name]
                field_value = document._data.get(field_name)
                if use_db_field:
                    db_field_name = field_obj.db_field or field_name
                else:
                    db_field_name = field_name
                value[db_field_name] = field_obj.to_mongo(field_value)

        return value

    def to_python(self, value: Any) -> Any:
        """Convert MongoDB value to Python.

        Args:
            value: The value from MongoDB.

        Returns:
            The Python representation.
        """
        if isinstance(value, BaseDocument):
            return value

        if isinstance(value, dict):
            return value

        return value

    def validate(self, value: Any) -> None:
        """Validate the cached reference field value.

        Args:
            value: The value to validate.
        """
        if not isinstance(value, self.document_type):
            self.error("An AsyncCachedReferenceField only accepts documents")

        if isinstance(value, BaseDocument) and value.id is None:
            self.error("You can only reference documents once they have been saved")

    def prepare_query_value(self, op: str, value: Any) -> Any:
        """Prepare value for query operations.

        Args:
            op: The query operation.
            value: The value to prepare.

        Returns:
            The prepared value for MongoDB query.

        Raises:
            NotImplementedError: For unsupported value types.
        """
        if value is None:
            return None

        if isinstance(value, BaseDocument):
            if value.pk is None:
                self.error("You can only reference documents once they have been saved")

            value_dict = {"_id": value.pk}
            for field in self.fields:
                value_dict.update({field: value[field]})

            return value_dict

        raise NotImplementedError
