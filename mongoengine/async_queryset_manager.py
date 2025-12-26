"""
Async QuerySet Manager for AsyncDocument.
"""

from mongoengine.async_queryset import AsyncQuerySet

__all__ = ("AsyncQuerySetManager",)


class AsyncQuerySetManager:
    """
    The default AsyncQuerySet Manager for AsyncDocument.

    This is a descriptor that returns an AsyncQuerySet when accessed from a class.
    """

    get_queryset = None
    default = AsyncQuerySet

    def __init__(self, queryset_func=None):
        if queryset_func:
            self.get_queryset = queryset_func

    def __get__(self, instance, owner):
        """
        Descriptor for instantiating a new AsyncQuerySet object when
        AsyncDocument.objects is accessed.
        """
        if instance is not None:
            # Document object being used rather than a document class
            return self

        # owner is the document that contains the AsyncQuerySetManager
        queryset_class = owner._meta.get("queryset_class", self.default)

        # For AsyncQuerySet, we need to handle collection access differently
        # The collection will be fetched asynchronously when needed
        queryset = queryset_class(owner, None)  # Collection will be set on first use

        if self.get_queryset:
            arg_count = self.get_queryset.__code__.co_argcount
            if arg_count == 1:
                queryset = self.get_queryset(queryset)
            elif arg_count == 2:
                queryset = self.get_queryset(owner, queryset)
            else:
                queryset = self.get_queryset(owner, queryset)

        return queryset
