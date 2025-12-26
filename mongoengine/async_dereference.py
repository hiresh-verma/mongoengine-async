"""
Async bulk dereferencing for MongoEngine.

This module provides async versions of bulk dereferencing operations to
efficiently load referenced documents and avoid N+1 queries.
"""

from typing import Any, Dict, List, Optional, Set, Type, Union

from bson import DBRef, ObjectId

from mongoengine.base.common import _DocumentRegistry
from mongoengine.base.document import BaseDocument
from mongoengine.io.aio.connection import _get_async_session

__all__ = ['AsyncDeReference']


class AsyncDeReference:
    """
    Async bulk dereferencing utility.

    This class efficiently dereferences multiple references in a single
    batch of database queries to avoid N+1 query problems.

    Usage:
        # Get documents with references
        posts = await AsyncPost.objects.to_list()

        # Bulk dereference
        dereferencer = AsyncDeReference()
        await dereferencer(posts, max_depth=1)

        # Now all references are loaded
        for post in posts:
            print(post.author.name)  # No additional queries!
    """

    async def __call__(self, items: Union[List[Any], Any, None], max_depth: int = 1) -> Union[List[Any], Any, None]:
        """Bulk dereference items to a specified depth.

        Args:
            items: List of documents to dereference.
            max_depth: Maximum depth to recurse (default: 1).

        Returns:
            The items with references dereferenced.
        """
        if items is None or isinstance(items, str):
            return items

        # Convert to list if needed
        if not isinstance(items, list):
            items = list(items)

        if not items:
            return items

        self.max_depth = max_depth
        self.reference_map = self._find_references(items)
        await self._fetch_objects_async()
        self._attach_objects(items, 0)

        return items

    def _find_references(self, items: List[Any], depth: int = 0) -> Dict[Type[BaseDocument], Set[Any]]:
        """Recursively find all DBRef references to be dereferenced.

        Args:
            items: The items to scan for references.
            depth: Current recursion depth.

        Returns:
            Dict mapping document classes to sets of ObjectIds.
        """
        reference_map = {}

        if not items or depth >= self.max_depth:
            return reference_map

        depth += 1

        for item in items:
            if isinstance(item, BaseDocument):
                # Scan all fields for references
                for field_name, field in item._fields.items():
                    value = item._data.get(field_name, None)

                    if value is None:
                        continue

                    # Handle DBRef
                    if isinstance(value, DBRef):
                        # Get the document class for this reference
                        doc_cls = self._get_reference_doc_class(field, item)
                        if doc_cls:
                            reference_map.setdefault(doc_cls, set()).add(value.id)

                    # Handle ObjectId (AsyncReferenceField stores ObjectId directly)
                    elif isinstance(value, ObjectId):
                        # Get the document class for this reference field
                        doc_cls = self._get_reference_doc_class(field, item)
                        if doc_cls:
                            reference_map.setdefault(doc_cls, set()).add(value)

                    # Handle GenericReferenceField (dict with _cls and _ref)
                    elif isinstance(value, dict) and "_cls" in value and "_ref" in value:
                        doc_cls = _DocumentRegistry.get(value["_cls"])
                        reference_map.setdefault(doc_cls, set()).add(value["_ref"].id)

                    # Recursively handle lists
                    elif isinstance(value, list) and depth < self.max_depth:
                        nested_refs = self._find_references(value, depth)
                        for key, refs in nested_refs.items():
                            reference_map.setdefault(key, set()).update(refs)

        return reference_map

    def _get_reference_doc_class(self, field: Any, item: BaseDocument) -> Optional[Type[BaseDocument]]:
        """Get the document class that a reference field points to.

        Args:
            field: The field object.
            item: The document instance.

        Returns:
            The referenced document class, or None.
        """
        # Import here to avoid circular imports
        from mongoengine.async_fields import (
            AsyncReferenceField,
            AsyncGenericReferenceField,
            AsyncCachedReferenceField
        )

        # Check if it's a reference field
        if isinstance(field, (AsyncReferenceField, AsyncCachedReferenceField)):
            return field.document_type
        elif isinstance(field, AsyncGenericReferenceField):
            # For generic references, we don't know the type yet
            return None

        # Handle ListField wrapping reference fields
        if hasattr(field, 'field'):
            return self._get_reference_doc_class(field.field, item)

        return None

    async def _fetch_objects_async(self) -> None:
        """Async bulk fetch all referenced documents.

        This performs one query per document type to load all references
        of that type.
        """
        self.object_map = {}

        for doc_cls, object_ids in self.reference_map.items():
            if not object_ids or doc_cls is None:
                continue

            try:
                # Get the collection for this document class
                collection = await doc_cls._get_async_collection()

                # Bulk query for all referenced documents
                cursor = collection.find(
                    {"_id": {"$in": list(object_ids)}},
                    session=_get_async_session()
                )

                # Convert to documents
                async for doc_dict in cursor:
                    doc = doc_cls._from_son(doc_dict)
                    # Store in object map by (collection_name, id)
                    self.object_map[(doc_cls._get_collection_name(), doc_dict["_id"])] = doc

            except Exception:
                # If we can't fetch, skip this document type
                continue

    def _attach_objects(self, items: List[Any], depth: int) -> None:
        """Attach fetched objects back to the original documents.

        Args:
            items: The items to attach objects to.
            depth: Current recursion depth.
        """
        if not items or depth >= self.max_depth:
            return

        depth += 1

        for item in items:
            if isinstance(item, BaseDocument):
                # Attach fetched objects to reference fields
                for field_name, field in item._fields.items():
                    value = item._data.get(field_name, None)

                    if value is None:
                        continue

                    # Handle DBRef
                    if isinstance(value, DBRef):
                        key = (value.collection, value.id)
                        if key in self.object_map:
                            item._data[field_name] = self.object_map[key]

                    # Handle ObjectId (AsyncReferenceField stores ObjectId directly)
                    elif isinstance(value, ObjectId):
                        # Get the document class for this reference field
                        doc_cls = self._get_reference_doc_class(field, item)
                        if doc_cls:
                            collection_name = doc_cls._get_collection_name()
                            key = (collection_name, value)
                            if key in self.object_map:
                                item._data[field_name] = self.object_map[key]

                    # Handle GenericReferenceField
                    elif isinstance(value, dict) and "_cls" in value and "_ref" in value:
                        ref = value["_ref"]
                        key = (ref.collection, ref.id)
                        if key in self.object_map:
                            item._data[field_name] = self.object_map[key]

                    # Recursively handle lists
                    elif isinstance(value, list) and depth < self.max_depth:
                        self._attach_objects(value, depth)
