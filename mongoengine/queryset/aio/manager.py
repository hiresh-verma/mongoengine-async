from functools import partial

from mongoengine.queryset.aio.queryset import AsyncQuerySet

__all__ = ("queryset_manager", "AsyncQuerySetManager")


class AsyncQuerySetManager:
    """
    The default Async QuerySet Manager.

    Custom QuerySet Manager functions can extend this class and users can
    add extra queryset functionality. Any custom manager methods must accept a
    :class:`~mongoengine.Document` class as its first argument, and an async
    :class:`~mongoengine.queryset.aio.QuerySet` as its second argument.

    The method function should return an async
    :class:`~mongoengine.queryset.aio.QuerySet`, probably the same one that
    was passed in, but modified in some way.

    Note: The manager descriptor itself is not async, but it returns async
    QuerySet instances. Custom queryset functions should be synchronous
    functions that return a queryset (the async operations happen when
    methods are called on the queryset).
    """

    get_queryset = None
    default = AsyncQuerySet

    def __init__(self, queryset_func=None):
        if queryset_func:
            self.get_queryset = queryset_func

    def __get__(self, instance, owner):
        """Descriptor for instantiating a new async QuerySet object when
        Document.objects is accessed.

        Args:
            instance: The Document instance (or None when accessed from class)
            owner: The Document class that owns this manager

        Returns:
            An async QuerySet instance configured for the Document class
        """
        if instance is not None:
            # Document object being used rather than a document class
            return self

        # owner is the document that contains the AsyncQuerySetManager
        queryset_class = owner._meta.get("queryset_class", self.default)
        queryset = queryset_class(owner, owner._get_collection())
        if self.get_queryset:
            arg_count = self.get_queryset.__code__.co_argcount
            if arg_count == 1:
                queryset = self.get_queryset(queryset)
            elif arg_count == 2:
                queryset = self.get_queryset(owner, queryset)
            else:
                queryset = partial(self.get_queryset, owner, queryset)
        return queryset


def queryset_manager(func):
    """Decorator that allows you to define custom async QuerySet managers on
    :class:`~mongoengine.Document` classes. The manager must be a function that
    accepts a :class:`~mongoengine.Document` class as its first argument, and an
    async :class:`~mongoengine.queryset.aio.QuerySet` as its second argument.
    The function should return an async :class:`~mongoengine.queryset.aio.QuerySet`,
    probably the same one that was passed in, but modified in some way.

    Example::

        class User(AsyncDocument):
            name = StringField()
            is_active = BooleanField(default=True)

            @queryset_manager
            def active_users(doc_cls, queryset):
                return queryset.filter(is_active=True)

        # Usage (all operations are async):
        active_users = await User.active_users.first()
        async for user in User.active_users:
            print(user.name)
    """
    return AsyncQuerySetManager(func)
