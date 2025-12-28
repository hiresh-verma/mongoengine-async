"""
Async field types for MongoEngine.

This module provides async versions of fields that require I/O operations.
Only fields that perform database or GridFS operations need async versions.
"""

from inspect import isclass
from io import BytesIO
import asyncio

from bson import DBRef, ObjectId, SON
from pymongo import ReturnDocument

from mongoengine.base import BaseField
from mongoengine.base.common import _DocumentRegistry
from mongoengine.base.datastructures import LazyReference
from mongoengine.connection import DEFAULT_CONNECTION_NAME
from mongoengine.document import Document, EmbeddedDocument
from mongoengine.errors import DoesNotExist, ValidationError
from mongoengine.fields import (
    DO_NOTHING,
    RECURSIVE_REFERENCE_CONSTANT,
    GridFSError,
    ImproperlyConfigured,
)
from mongoengine.io.aio.connection import async_get_db, _get_async_session
import gridfs
import itertools
import inspect

try:
    from PIL import Image, ImageOps

    if hasattr(Image, "Resampling"):
        LANCZOS = Image.Resampling.LANCZOS
    else:
        LANCZOS = Image.LANCZOS
except ImportError:
    Image = None
    ImageOps = None


__all__ = [
    "AsyncReferenceField",
    "AsyncCachedReferenceField",
    "AsyncGenericReferenceField",
    "AsyncGridFSProxy",
    "AsyncFileField",
    "AsyncImageGridFsProxy",
    "AsyncImageField",
    "AsyncSequenceField",
]


def _unsaved_object_error(class_name):
    """Helper function for unsaved object error messages"""
    return f"You can only reference documents once they have been saved to the database ('{class_name}' instance has no 'id' yet)"


class AsyncReferenceField(BaseField):
    """A reference to a document that will be automatically dereferenced on
    access (lazily).

    Note this means you will get a database I/O access everytime you access
    this field. This is necessary because the field returns a :class:`~mongoengine.Document`
    which precise type can depend of the value of the `_cls` field present in the
    document in database.
    In short, using this type of field can lead to poor performances (especially
    if you access this field only to retrieve it `pk` field which is already
    known before dereference). To solve this you should consider using the
    :class:`~mongoengine.fields.LazyReferenceField`.

    Use the `reverse_delete_rule` to handle what should happen if the document
    the field is referencing is deleted.  EmbeddedDocuments, DictFields and
    MapFields does not support reverse_delete_rule and an `InvalidDocumentError`
    will be raised if trying to set on one of these Document / Field types.

    The options are:

      * DO_NOTHING (0)  - don't do anything (default).
      * NULLIFY    (1)  - Updates the reference to null.
      * CASCADE    (2)  - Deletes the documents associated with the reference.
      * DENY       (3)  - Prevent the deletion of the reference object.
      * PULL       (4)  - Pull the reference from a :class:`~mongoengine.fields.ListField` of references

    Alternative syntax for registering delete rules (useful when implementing
    bi-directional delete rules)

    .. code-block:: python

        class Org(Document):
            owner = ReferenceField('User')

        class User(Document):
            org = ReferenceField('Org', reverse_delete_rule=CASCADE)

        User.register_delete_rule(Org, 'owner', DENY)
    """

    def __init__(
        self, document_type, dbref=False, reverse_delete_rule=DO_NOTHING, **kwargs
    ):
        """Initialises the Reference Field.

        :param document_type: The type of Document that will be referenced
        :param dbref:  Store the reference as :class:`~pymongo.dbref.DBRef`
          or as the :class:`~pymongo.objectid.ObjectId`.
        :param reverse_delete_rule: Determines what to do when the referring
          object is deleted
        :param kwargs: Keyword arguments passed into the parent :class:`~mongoengine.BaseField`

        .. note ::
            A reference to an abstract document type is always stored as a
            :class:`~pymongo.dbref.DBRef`, regardless of the value of `dbref`.
        """
        # XXX ValidationError raised outside of the "validate" method.
        if not (
            isinstance(document_type, str)
            or (isclass(document_type) and issubclass(document_type, Document))
        ):
            self.error(
                "Argument to ReferenceField constructor must be a "
                "document class or a string"
            )

        self.dbref = dbref
        self.document_type_obj = document_type
        self.reverse_delete_rule = reverse_delete_rule
        super().__init__(**kwargs)

    @property
    def document_type(self):
        if isinstance(self.document_type_obj, str):
            if self.document_type_obj == RECURSIVE_REFERENCE_CONSTANT:
                self.document_type_obj = self.owner_document
            else:
                self.document_type_obj = _DocumentRegistry.get(self.document_type_obj)
        return self.document_type_obj

    @staticmethod
    async def _lazy_load_ref(ref_cls, dbref):
        """Async dereference a DBRef to a document"""
        db = await ref_cls._get_async_db()
        dereferenced_son = await db.dereference(dbref, session=_get_async_session())
        if dereferenced_son is None:
            raise DoesNotExist(f"Trying to dereference unknown document {dbref}")

        return ref_cls._from_son(dereferenced_son)

    def __get__(self, instance, owner):
        """Descriptor to return the reference value.

        Note: Async fields do not auto-dereference. Use fetch() method to dereference.
        """
        if instance is None:
            # Document class being used rather than a document object
            return self

        # Return the raw reference value (DBRef or ObjectId)
        # Auto-dereferencing is not supported for async fields
        # Users should call await field.fetch() to dereference
        return super().__get__(instance, owner)

    async def fetch(self, instance):
        """Async method to dereference the reference.

        Usage:
            user = await post.author.fetch(post)
        """
        ref_value = instance._data.get(self.name)
        if ref_value is None:
            return None

        if isinstance(ref_value, DBRef):
            if hasattr(ref_value, "cls"):
                # Dereference using the class type specified in the reference
                cls = _DocumentRegistry.get(ref_value.cls)
            else:
                cls = self.document_type

            dereferenced = await self._lazy_load_ref(cls, ref_value)
            instance._data[self.name] = dereferenced
            return dereferenced

        # Already dereferenced or is an ObjectId
        return ref_value

    def to_mongo(self, document):
        if isinstance(document, DBRef):
            if not self.dbref:
                return document.id
            return document

        if isinstance(document, Document):
            # We need the id from the saved object to create the DBRef
            id_ = document.pk

            # XXX ValidationError raised outside of the "validate" method.
            if id_ is None:
                self.error(_unsaved_object_error(document.__class__.__name__))

            # Use the attributes from the document instance, so that they
            # override the attributes of this field's document type
            cls = document
        else:
            id_ = document
            cls = self.document_type

        id_field_name = cls._meta["id_field"]
        id_field = cls._fields[id_field_name]

        id_ = id_field.to_mongo(id_)
        if self.document_type._meta.get("abstract"):
            collection = cls._get_collection_name()
            return DBRef(collection, id_, cls=cls._class_name)
        elif self.dbref:
            collection = cls._get_collection_name()
            return DBRef(collection, id_)

        return id_

    def to_python(self, value):
        """Convert a MongoDB-compatible type to a Python type."""
        if not self.dbref and not isinstance(
            value, (DBRef, Document, EmbeddedDocument)
        ):
            collection = self.document_type._get_collection_name()
            value = DBRef(collection, self.document_type.id.to_python(value))
        return value

    def prepare_query_value(self, op, value):
        if value is None:
            return None
        super().prepare_query_value(op, value)
        return self.to_mongo(value)

    def validate(self, value):
        if not isinstance(value, (self.document_type, LazyReference, DBRef, ObjectId)):
            self.error(
                "A ReferenceField only accepts DBRef, LazyReference, ObjectId or documents"
            )

        if isinstance(value, Document) and value.id is None:
            self.error(_unsaved_object_error(value.__class__.__name__))

    def lookup_member(self, member_name):
        return self.document_type._fields.get(member_name)


class AsyncCachedReferenceField(BaseField):
    """A referencefield with cache fields to purpose pseudo-joins"""

    def __init__(self, document_type, fields=None, auto_sync=True, **kwargs):
        """Initialises the Cached Reference Field.

        :param document_type: The type of Document that will be referenced
        :param fields:  A list of fields to be cached in document
        :param auto_sync: if True documents are auto updated
        :param kwargs: Keyword arguments passed into the parent :class:`~mongoengine.BaseField`
        """
        if fields is None:
            fields = []

        # XXX ValidationError raised outside of the "validate" method.
        if not isinstance(document_type, str) and not (
            inspect.isclass(document_type) and issubclass(document_type, Document)
        ):
            self.error(
                "Argument to CachedReferenceField constructor must be a"
                " document class or a string"
            )

        self.auto_sync = auto_sync
        self.document_type_obj = document_type
        self.fields = fields
        super().__init__(**kwargs)

    def start_listener(self):
        from mongoengine import signals

        signals.post_save.connect(self.on_document_pre_save, sender=self.document_type)

    def on_document_pre_save(self, sender, document, created, **kwargs):
        if created:
            return None

        update_kwargs = {
            f"set__{self.name}__{key}": val
            for key, val in document._delta()[0].items()
            if key in self.fields
        }
        if update_kwargs:
            filter_kwargs = {}
            filter_kwargs[self.name] = document

            self.owner_document.objects(**filter_kwargs).update(**update_kwargs)

    async def to_python_async(self, value):
        """Async version of to_python for dereferencing cached references"""
        if isinstance(value, dict):
            collection = self.document_type._get_collection_name()
            value = DBRef(collection, self.document_type.id.to_python(value["_id"]))
            db = await self.document_type._get_async_db()
            dereferenced = await db.dereference(value, session=_get_async_session())
            return self.document_type._from_son(dereferenced)

        return value

    def to_python(self, value):
        """Sync version - returns the value as-is. Use to_python_async for dereferencing."""
        return value

    @property
    def document_type(self):
        if isinstance(self.document_type_obj, str):
            if self.document_type_obj == RECURSIVE_REFERENCE_CONSTANT:
                self.document_type_obj = self.owner_document
            else:
                self.document_type_obj = _DocumentRegistry.get(self.document_type_obj)
        return self.document_type_obj

    @staticmethod
    async def _lazy_load_ref(ref_cls, dbref):
        """Async dereference a DBRef to a document"""
        db = await ref_cls._get_async_db()
        dereferenced_son = await db.dereference(dbref, session=_get_async_session())
        if dereferenced_son is None:
            raise DoesNotExist(f"Trying to dereference unknown document {dbref}")

        return ref_cls._from_son(dereferenced_son)

    def __get__(self, instance, owner):
        """Descriptor to return the reference value.

        Note: Async fields do not auto-dereference. Use fetch() method to dereference.
        """
        if instance is None:
            # Document class being used rather than a document object
            return self

        # Return the raw reference value without dereferencing
        return super().__get__(instance, owner)

    async def fetch(self, instance):
        """Async method to dereference the cached reference.

        Usage:
            user = await post.author.fetch(post)
        """
        value = instance._data.get(self.name)
        if value is None:
            return None

        if isinstance(value, DBRef):
            dereferenced = await self._lazy_load_ref(self.document_type, value)
            instance._data[self.name] = dereferenced
            return dereferenced

        return value

    def to_mongo(self, document, use_db_field=True, fields=None):
        id_field_name = self.document_type._meta["id_field"]
        id_field = self.document_type._fields[id_field_name]

        # XXX ValidationError raised outside of the "validate" method.
        if isinstance(document, Document):
            # We need the id from the saved object to create the DBRef
            id_ = document.pk
            if id_ is None:
                self.error(_unsaved_object_error(document.__class__.__name__))
        else:
            self.error("Only accept a document object")

        value = SON((("_id", id_field.to_mongo(id_)),))

        if fields:
            new_fields = [f for f in self.fields if f in fields]
        else:
            new_fields = self.fields

        value.update(dict(document.to_mongo(use_db_field, fields=new_fields)))
        return value

    def prepare_query_value(self, op, value):
        if value is None:
            return None

        # XXX ValidationError raised outside of the "validate" method.
        if isinstance(value, Document):
            if value.pk is None:
                self.error(_unsaved_object_error(value.__class__.__name__))
            value_dict = {"_id": value.pk}
            for field in self.fields:
                value_dict.update({field: value[field]})

            return value_dict

        raise NotImplementedError

    def validate(self, value):
        if not isinstance(value, self.document_type):
            self.error("A CachedReferenceField only accepts documents")

        if isinstance(value, Document) and value.id is None:
            self.error(_unsaved_object_error(value.__class__.__name__))

    def lookup_member(self, member_name):
        return self.document_type._fields.get(member_name)

    def sync_all(self):
        """
        Sync all cached fields on demand.
        Caution: this operation may be slower.
        """
        update_key = "set__%s" % self.name

        for doc in self.document_type.objects:
            filter_kwargs = {}
            filter_kwargs[self.name] = doc

            update_kwargs = {}
            update_kwargs[update_key] = doc

            self.owner_document.objects(**filter_kwargs).update(**update_kwargs)


class AsyncGenericReferenceField(BaseField):
    """A reference to *any* :class:`~mongoengine.document.Document` subclass
    that will be automatically dereferenced on access (lazily).

    Note this field works the same way as :class:`~mongoengine.document.ReferenceField`,
    doing database I/O access the first time it is accessed (even if it's to access
    it ``pk`` or ``id`` field).
    To solve this you should consider using the
    :class:`~mongoengine.fields.GenericLazyReferenceField`.

    .. note ::
        * Any documents used as a generic reference must be registered in the
          document registry.  Importing the model will automatically register
          it.

        * You can use the choices param to limit the acceptable Document types
    """

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop("choices", None)
        super().__init__(*args, **kwargs)
        self.choices = []
        # Keep the choices as a list of allowed Document class names
        if choices:
            for choice in choices:
                if isinstance(choice, str):
                    self.choices.append(choice)
                elif isinstance(choice, type) and issubclass(choice, Document):
                    self.choices.append(choice._class_name)
                else:
                    # XXX ValidationError raised outside of the "validate"
                    # method.
                    self.error(
                        "Invalid choices provided: must be a list of"
                        "Document subclasses and/or str"
                    )

    def _validate_choices(self, value):
        if isinstance(value, dict):
            # If the field has not been dereferenced, it is still a dict
            # of class and DBRef
            value = value.get("_cls")
        elif isinstance(value, Document):
            value = value._class_name
        super()._validate_choices(value)

    @staticmethod
    async def _lazy_load_ref(ref_cls, dbref):
        """Async dereference a DBRef to a document"""
        db = await ref_cls._get_async_db()
        dereferenced_son = await db.dereference(dbref, session=_get_async_session())
        if dereferenced_son is None:
            raise DoesNotExist(f"Trying to dereference unknown document {dbref}")

        return ref_cls._from_son(dereferenced_son)

    def __get__(self, instance, owner):
        """Descriptor to return the reference value.

        Note: Async fields do not auto-dereference. Use fetch() method to dereference.
        """
        if instance is None:
            return self

        # Return the raw reference value without dereferencing
        return super().__get__(instance, owner)

    async def fetch(self, instance):
        """Async method to dereference the generic reference.

        Usage:
            referenced_doc = await post.ref_field.fetch(post)
        """
        value = instance._data.get(self.name)
        if value is None:
            return None

        if isinstance(value, dict) and "_cls" in value and "_ref" in value:
            doc_cls = _DocumentRegistry.get(value["_cls"])
            dereferenced = await self._lazy_load_ref(doc_cls, value["_ref"])
            instance._data[self.name] = dereferenced
            return dereferenced

        return value

    def validate(self, value):
        if not isinstance(value, (Document, DBRef, dict, SON)):
            self.error("GenericReferences can only contain documents")

        if isinstance(value, (dict, SON)):
            if "_ref" not in value or "_cls" not in value:
                self.error("GenericReferences can only contain documents")

        # We need the id from the saved object to create the DBRef
        elif isinstance(value, Document) and value.id is None:
            self.error(_unsaved_object_error(value.__class__.__name__))

    def to_mongo(self, document):
        if document is None:
            return None

        if isinstance(document, (dict, SON, ObjectId, DBRef)):
            return document

        id_field_name = document.__class__._meta["id_field"]
        id_field = document.__class__._fields[id_field_name]

        if isinstance(document, Document):
            # We need the id from the saved object to create the DBRef
            id_ = document.id
            if id_ is None:
                # XXX ValidationError raised outside of the "validate" method.
                self.error(_unsaved_object_error(document.__class__.__name__))
        else:
            id_ = document

        id_ = id_field.to_mongo(id_)
        collection = document._get_collection_name()
        ref = DBRef(collection, id_)
        return SON((("_cls", document._class_name), ("_ref", ref)))

    def prepare_query_value(self, op, value):
        if value is None:
            return None

        return self.to_mongo(value)


class AsyncGridFSProxy:
    """Async proxy object to handle writing and reading of files to and from GridFS"""

    _fs = None

    def __init__(
        self,
        grid_id=None,
        key=None,
        instance=None,
        db_alias=DEFAULT_CONNECTION_NAME,
        collection_name="fs",
    ):
        self.grid_id = grid_id  # Store GridFS id for file
        self.key = key
        self.instance = instance
        self.db_alias = db_alias
        self.collection_name = collection_name
        self.newfile = None  # Used for partial writes
        self.gridout = None

    def __getattr__(self, name):
        """Note: __getattr__ cannot be async. For async access to gridout attributes, use await get() first."""
        attrs = (
            "_fs",
            "grid_id",
            "key",
            "instance",
            "db_alias",
            "collection_name",
            "newfile",
            "gridout",
        )
        if name in attrs:
            return self.__getattribute__(name)
        # Cannot call async get() from __getattr__, so raise AttributeError
        # Users should call: gridout = await proxy.get(); gridout.attribute
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'. Use 'await proxy.get()' to access gridout attributes."
        )

    def __get__(self, instance, value):
        return self

    def __bool__(self):
        return bool(self.grid_id)

    def __getstate__(self):
        self_dict = self.__dict__
        self_dict["_fs"] = None
        return self_dict

    def __copy__(self):
        copied = AsyncGridFSProxy()
        copied.__dict__.update(self.__getstate__())
        return copied

    def __deepcopy__(self, memo):
        return self.__copy__()

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.grid_id}>"

    def __str__(self):
        """Note: __str__ cannot be async."""
        return f"<{self.__class__.__name__}: {self.grid_id}>"

    def __eq__(self, other):
        if isinstance(other, AsyncGridFSProxy):
            return (
                (self.grid_id == other.grid_id)
                and (self.collection_name == other.collection_name)
                and (self.db_alias == other.db_alias)
            )
        else:
            return False

    def __ne__(self, other):
        return not self == other

    async def _get_fs(self):
        """Get or create GridFS instance asynchronously"""
        if not self._fs:
            # Get the sync database from the async db (PyMongo AsyncMongoClient provides both)
            from mongoengine.connection import get_db

            sync_db = get_db(self.db_alias)
            self._fs = gridfs.GridFS(sync_db, self.collection_name)
        return self._fs

    async def get(self, grid_id=None):
        """Async get file from GridFS"""
        if grid_id:
            self.grid_id = grid_id

        if self.grid_id is None:
            return None

        try:
            if self.gridout is None:
                fs = await self._get_fs()
                # Run GridFS get operation in thread pool to avoid blocking
                self.gridout = await asyncio.to_thread(
                    fs.get, self.grid_id, session=_get_async_session()
                )
            return self.gridout
        except Exception:
            # File has been deleted
            return None

    async def new_file(self, **kwargs):
        """Create new file asynchronously"""
        fs = await self._get_fs()
        self.newfile = await asyncio.to_thread(fs.new_file, **kwargs)
        self.grid_id = self.newfile._id
        self._mark_as_changed()

    async def put(self, file_obj, **kwargs):
        """Put file into GridFS asynchronously"""
        if self.grid_id:
            raise GridFSError(
                "This document already has a file. Either delete "
                "it or call replace to overwrite it"
            )
        fs = await self._get_fs()
        self.grid_id = await asyncio.to_thread(fs.put, file_obj, **kwargs)
        self._mark_as_changed()

    async def write(self, string):
        """Write string to file asynchronously"""
        if self.grid_id:
            if not self.newfile:
                raise GridFSError(
                    "This document already has a file. Either "
                    "delete it or call replace to overwrite it"
                )
        else:
            await self.new_file()
        await asyncio.to_thread(self.newfile.write, string)

    async def writelines(self, lines):
        """Write lines to file asynchronously"""
        if not self.newfile:
            await self.new_file()
            self.grid_id = self.newfile._id
        await asyncio.to_thread(self.newfile.writelines, lines)

    async def read(self, size=-1):
        """Read file content asynchronously"""
        gridout = await self.get()
        if gridout is None:
            return None
        else:
            try:
                return await asyncio.to_thread(gridout.read, size)
            except Exception:
                return ""

    async def delete(self):
        """Delete file from GridFS asynchronously"""
        fs = await self._get_fs()
        await asyncio.to_thread(fs.delete, self.grid_id, session=_get_async_session())
        self.grid_id = None
        self.gridout = None
        self._mark_as_changed()

    async def replace(self, file_obj, **kwargs):
        """Replace file asynchronously"""
        await self.delete()
        await self.put(file_obj, **kwargs)

    async def close(self):
        """Close file asynchronously"""
        if self.newfile:
            await asyncio.to_thread(self.newfile.close)

    def _mark_as_changed(self):
        """Inform the instance that `self.key` has been changed"""
        if self.instance:
            self.instance._mark_as_changed(self.key)


class AsyncFileField(BaseField):
    """An async GridFS storage field."""

    proxy_class = AsyncGridFSProxy

    def __init__(
        self, db_alias=DEFAULT_CONNECTION_NAME, collection_name="fs", **kwargs
    ):
        super().__init__(**kwargs)
        self.collection_name = collection_name
        self.db_alias = db_alias

    def __get__(self, instance, owner):
        if instance is None:
            return self

        # Check if a file already exists for this model
        grid_file = instance._data.get(self.name)
        if not isinstance(grid_file, self.proxy_class):
            grid_file = self.get_proxy_obj(key=self.name, instance=instance)
            instance._data[self.name] = grid_file

        if not grid_file.key:
            grid_file.key = self.name
            grid_file.instance = instance
        return grid_file

    async def __set_async__(self, instance, value):
        """Async version of __set__ for putting files"""
        key = self.name
        if (
            hasattr(value, "read") and not isinstance(value, AsyncGridFSProxy)
        ) or isinstance(value, (bytes, str)):
            # using "FileField() = file/string" notation
            grid_file = instance._data.get(self.name)
            # If a file already exists, delete it
            if grid_file:
                try:
                    await grid_file.delete()
                except Exception:
                    pass

            # Create a new proxy object as we don't already have one
            instance._data[key] = self.get_proxy_obj(key=key, instance=instance)
            await instance._data[key].put(value)
        else:
            instance._data[key] = value

        instance._mark_as_changed(key)

    def __set__(self, instance, value):
        """Sync version - sets the value without async operations"""
        key = self.name
        instance._data[key] = value
        instance._mark_as_changed(key)

    def get_proxy_obj(self, key, instance, db_alias=None, collection_name=None):
        if db_alias is None:
            db_alias = self.db_alias
        if collection_name is None:
            collection_name = self.collection_name

        return self.proxy_class(
            key=key,
            instance=instance,
            db_alias=db_alias,
            collection_name=collection_name,
        )

    def to_mongo(self, value):
        # Store the GridFS file id in MongoDB
        if isinstance(value, self.proxy_class) and value.grid_id is not None:
            return value.grid_id
        return None

    def to_python(self, value):
        if value is not None:
            return self.proxy_class(
                value, collection_name=self.collection_name, db_alias=self.db_alias
            )

    def validate(self, value):
        if value.grid_id is not None:
            if not isinstance(value, self.proxy_class):
                self.error("FileField only accepts AsyncGridFSProxy values")
            if not isinstance(value.grid_id, ObjectId):
                self.error("Invalid AsyncGridFSProxy value")


class AsyncImageGridFsProxy(AsyncGridFSProxy):
    """Async proxy for ImageField"""

    async def put(self, file_obj, **kwargs):
        """
        Insert an image in database asynchronously
        applying field properties (size, thumbnail_size)
        """
        field = self.instance._fields[self.key]
        # Handle nested fields
        if hasattr(field, "field") and isinstance(field.field, AsyncFileField):
            field = field.field

        try:
            # Image processing is CPU-bound, run in thread pool
            img = await asyncio.to_thread(Image.open, file_obj)
            img_format = img.format
        except Exception as e:
            raise ValidationError("Invalid image: %s" % e)

        # Progressive JPEG
        # TODO: fixme, at least unused, at worst bad implementation
        progressive = img.info.get("progressive") or False

        if (
            kwargs.get("progressive")
            and isinstance(kwargs.get("progressive"), bool)
            and img_format == "JPEG"
        ):
            progressive = True
        else:
            progressive = False

        if field.size and (
            img.size[0] > field.size["width"] or img.size[1] > field.size["height"]
        ):
            size = field.size

            if size["force"]:
                img = await asyncio.to_thread(
                    ImageOps.fit, img, (size["width"], size["height"]), LANCZOS
                )
            else:
                await asyncio.to_thread(
                    img.thumbnail, (size["width"], size["height"]), LANCZOS
                )

        thumbnail = None
        if field.thumbnail_size:
            size = field.thumbnail_size

            if size["force"]:
                thumbnail = await asyncio.to_thread(
                    ImageOps.fit, img, (size["width"], size["height"]), LANCZOS
                )
            else:
                thumbnail = await asyncio.to_thread(img.copy)
                await asyncio.to_thread(
                    thumbnail.thumbnail, (size["width"], size["height"]), LANCZOS
                )

        if thumbnail:
            thumb_id = await self._put_thumbnail(thumbnail, img_format, progressive)
        else:
            thumb_id = None

        w, h = img.size

        io = BytesIO()
        await asyncio.to_thread(img.save, io, img_format, progressive=progressive)
        io.seek(0)

        return await super().put(
            io, width=w, height=h, format=img_format, thumbnail_id=thumb_id, **kwargs
        )

    async def delete(self, *args, **kwargs):
        """Delete image and thumbnail asynchronously"""
        # deletes thumbnail
        out = await self.get()
        if out and out.thumbnail_id:
            fs = await self._get_fs()
            await asyncio.to_thread(
                fs.delete, out.thumbnail_id, session=_get_async_session()
            )

        return await super().delete()

    async def _put_thumbnail(self, thumbnail, format, progressive, **kwargs):
        """Put thumbnail asynchronously"""
        w, h = thumbnail.size

        io = BytesIO()
        await asyncio.to_thread(thumbnail.save, io, format, progressive=progressive)
        io.seek(0)

        fs = await self._get_fs()
        return await asyncio.to_thread(
            fs.put, io, width=w, height=h, format=format, **kwargs
        )

    async def get_size(self):
        """
        Return width, height of image asynchronously
        """
        out = await self.get()
        if out:
            return out.width, out.height

    async def get_format(self):
        """
        Return format of image asynchronously
        ex: PNG, JPEG, GIF, etc
        """
        out = await self.get()
        if out:
            return out.format

    async def get_thumbnail(self):
        """
        Return a gridfs.grid_file.GridOut
        representing a thumbnail of Image
        """
        out = await self.get()
        if out and out.thumbnail_id:
            fs = await self._get_fs()
            return await asyncio.to_thread(
                fs.get, out.thumbnail_id, session=_get_async_session()
            )

    def write(self, *args, **kwargs):
        raise RuntimeError('Please use "put" method instead')

    def writelines(self, *args, **kwargs):
        raise RuntimeError('Please use "put" method instead')


class AsyncImageField(AsyncFileField):
    """
    An async Image File storage field.

    :param size: max size to store images, provided as (width, height, force)
        if larger, it will be automatically resized (ex: size=(800, 600, True))
    :param thumbnail_size: size to generate a thumbnail, provided as (width, height, force)
    """

    proxy_class = AsyncImageGridFsProxy

    def __init__(
        self, size=None, thumbnail_size=None, collection_name="images", **kwargs
    ):
        if not Image:
            raise ImproperlyConfigured("PIL library was not found")

        params_size = ("width", "height", "force")
        extra_args = {"size": size, "thumbnail_size": thumbnail_size}
        for att_name, att in extra_args.items():
            value = None
            if isinstance(att, (tuple, list)):
                value = dict(itertools.zip_longest(params_size, att, fillvalue=None))

            setattr(self, att_name, value)

        super().__init__(collection_name=collection_name, **kwargs)


class AsyncSequenceField(BaseField):
    """Async version of SequenceField. Provides a sequential counter see:
     https://www.mongodb.com/docs/manual/reference/method/ObjectId/#ObjectIDs-SequenceNumbers

    .. note::

             Although traditional databases often use increasing sequence
             numbers for primary keys. In MongoDB, the preferred approach is to
             use Object IDs instead.  The concept is that in a very large
             cluster of machines, it is easier to create an object ID than have
             global, uniformly increasing sequence numbers.

    :param collection_name:  Name of the counter collection (default 'mongoengine.counters')
    :param sequence_name: Name of the sequence in the collection (default 'ClassName.counter')
    :param value_decorator: Any callable to use as a counter (default int)

    Use any callable as `value_decorator` to transform calculated counter into
    any value suitable for your needs, e.g. string or hexadecimal
    representation of the default integer counter value.

    .. note::

        In case the counter is defined in the abstract document, it will be
        common to all inherited documents and the default sequence name will
        be the class name of the abstract document.

    .. note::

        Unlike sync SequenceField, this does NOT auto-generate on __get__.
        You must call `await instance.field_name.generate(instance)` or
        `await document.save()` which will auto-generate.
    """

    _auto_gen = True
    COLLECTION_NAME = "mongoengine.counters"
    VALUE_DECORATOR = int

    def __init__(
        self,
        collection_name=None,
        db_alias=None,
        sequence_name=None,
        value_decorator=None,
        *args,
        **kwargs,
    ):
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.db_alias = db_alias or DEFAULT_CONNECTION_NAME
        self.sequence_name = sequence_name
        self.value_decorator = (
            value_decorator if callable(value_decorator) else self.VALUE_DECORATOR
        )
        super().__init__(*args, **kwargs)

    async def generate(self):
        """
        Generate and Increment the counter asynchronously
        """
        sequence_name = self.get_sequence_name()
        sequence_id = f"{sequence_name}.{self.name}"
        db = await async_get_db(alias=self.db_alias)
        collection = db[self.collection_name]

        counter = await collection.find_one_and_update(
            filter={"_id": sequence_id},
            update={"$inc": {"next": 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True,
            session=_get_async_session(),
        )
        return self.value_decorator(counter["next"])

    async def set_next_value(self, value):
        """Helper method to set the next sequence value asynchronously"""
        sequence_name = self.get_sequence_name()
        sequence_id = f"{sequence_name}.{self.name}"
        db = await async_get_db(alias=self.db_alias)
        collection = db[self.collection_name]
        counter = await collection.find_one_and_update(
            filter={"_id": sequence_id},
            update={"$set": {"next": value}},
            return_document=ReturnDocument.AFTER,
            upsert=True,
            session=_get_async_session(),
        )
        return self.value_decorator(counter["next"])

    async def get_next_value(self):
        """Helper method to get the next value for previewing asynchronously.

        .. warning:: There is no guarantee this will be the next value
        as it is only fixed on set.
        """
        sequence_name = self.get_sequence_name()
        sequence_id = f"{sequence_name}.{self.name}"
        db = await async_get_db(alias=self.db_alias)
        collection = db[self.collection_name]
        data = await collection.find_one(
            {"_id": sequence_id}, session=_get_async_session()
        )

        if data:
            return self.value_decorator(data["next"] + 1)

        return self.value_decorator(1)

    def get_sequence_name(self):
        if self.sequence_name:
            return self.sequence_name
        owner = self.owner_document
        if issubclass(owner, Document) and not owner._meta.get("abstract"):
            return owner._get_collection_name()
        else:
            return (
                "".join("_%s" % c if c.isupper() else c for c in owner._class_name)
                .strip("_")
                .lower()
            )

    def __get__(self, instance, owner):
        """Return the value without auto-generating.

        Note: Async fields do not auto-generate on access.
        Use await field.generate() or save the document to generate.
        """
        if instance is None:
            return self
        return super().__get__(instance, owner)

    def __set__(self, instance, value):
        """Set the value without auto-generating."""
        return super().__set__(instance, value)

    def prepare_query_value(self, op, value):
        """
        This method is overridden in order to convert the query value into to required
        type. We need to do this in order to be able to successfully compare query
        values passed as string, the base implementation returns the value as is.
        """
        return self.value_decorator(value)

    def to_python(self, value):
        """Convert value to Python type without auto-generating."""
        return value
