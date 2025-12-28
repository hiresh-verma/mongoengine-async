from mongoengine.errors import OperationError
from mongoengine.queryset.aio.base import (
    CASCADE,
    DENY,
    DO_NOTHING,
    NULLIFY,
    PULL,
    AsyncBaseQuerySet,
)

__all__ = (
    "AsyncQuerySet",
    "AsyncQuerySetNoCache",
    "DO_NOTHING",
    "NULLIFY",
    "CASCADE",
    "DENY",
    "PULL",
)

# The maximum number of items to display in a QuerySet.__repr__
REPR_OUTPUT_SIZE = 20
ITER_CHUNK_SIZE = 100


class AsyncQuerySet(AsyncBaseQuerySet):
    """The default async queryset, that builds queries and handles a set of results
    returned from a query.

    Wraps a MongoDB async cursor, providing :class:`~mongoengine.Document` objects
    as the results. This queryset implements result caching for efficient iteration.

    Usage Examples::

        # Async iteration
        async for user in User.objects.filter(is_active=True):
            print(user.name)

        # Get count
        count = await User.objects.count()

        # Get first result
        user = await User.objects.first()

        # Get specific result
        user = await User.objects.get(email="user@example.com")

        # Convert to list (loads all results into memory)
        users = await User.objects.filter(age__gte=18).to_list()

        # Chain queries (lazy evaluation until iteration)
        queryset = User.objects.filter(is_active=True).order_by('-created_at')
        async for user in queryset.limit(10):
            print(user.name)

    Note:
        - All database operations require ``await`` or ``async for``
        - ``len(queryset)`` only works if results are already cached
        - Use ``await queryset.count()`` to get count from database
        - The queryset uses result caching by default for efficient re-iteration
    """

    _has_more = True
    _len = None
    _result_cache = None

    def __aiter__(self):
        """Async iteration utilises a results cache which iterates the cursor
        in batches of ``ITER_CHUNK_SIZE``.

        If ``self._has_more`` the cursor hasn't been exhausted so cache then
        batch. Otherwise iterate the result_cache.
        """
        self._iter = True

        if self._has_more:
            return self._iter_results()

        # iterating over the cache.
        async def _cache_iterator():
            for item in self._result_cache:
                yield item
        return _cache_iterator()

    def __len__(self):
        """Returns the cached length if available.

        Note: For async querysets, you cannot use len() to trigger a database query.
        Use `await queryset.count()` instead to get the count from the database.
        This method only returns the cached length if it's already been computed.
        """
        if self._len is not None:
            return self._len

        # For async querysets, we can't automatically fetch from the database
        # because __len__ cannot be async
        if self._result_cache is not None and not self._has_more:
            self._len = len(self._result_cache)
            return self._len

        raise TypeError(
            "Cannot determine length of async queryset. "
            "Use 'await queryset.count()' to get the count from the database."
        )

    def __repr__(self):
        """Provide a string representation of the QuerySet.

        Note: Only shows cached results. For async querysets, you need to
        iterate the queryset first (using 'async for') to populate the cache.
        """
        if self._iter:
            return ".. queryset mid-iteration .."

        if self._result_cache is None or len(self._result_cache) == 0:
            return "[] (queryset not yet fetched - use 'async for' to iterate)"

        data = self._result_cache[: REPR_OUTPUT_SIZE + 1]
        if len(data) > REPR_OUTPUT_SIZE:
            data[-1] = "...(remaining elements truncated)..."
        return repr(data)

    async def _iter_results(self):
        """An async generator for iterating over the result cache.

        Also populates the cache if there are more possible results to
        yield. Raises StopAsyncIteration when there are no more results.
        """
        if self._result_cache is None:
            self._result_cache = []

        pos = 0
        while True:
            # For all positions lower than the length of the current result
            # cache, serve the docs straight from the cache w/o hitting the
            # database.
            # XXX it's VERY important to compute the len within the `while`
            # condition because the result cache might expand mid-iteration
            # (e.g. if we call len(qs) inside a loop that iterates over the
            # queryset). Fortunately len(list) is O(1) in Python, so this
            # doesn't cause performance issues.
            while pos < len(self._result_cache):
                yield self._result_cache[pos]
                pos += 1

            # return if we already established there were no more
            # docs in the db cursor.
            if not self._has_more:
                return

            # Otherwise, populate more of the cache and repeat.
            if len(self._result_cache) <= pos:
                await self._populate_cache()

    async def _populate_cache(self):
        """
        Populates the result cache with ``ITER_CHUNK_SIZE`` more entries
        (until the cursor is exhausted).
        """
        if self._result_cache is None:
            self._result_cache = []

        # Skip populating the cache if we already established there are no
        # more docs to pull from the database.
        if not self._has_more:
            return

        # Pull in ITER_CHUNK_SIZE docs from the database and store them in
        # the result cache.
        try:
            for _ in range(ITER_CHUNK_SIZE):
                self._result_cache.append(await self.__anext__())
        except StopAsyncIteration:
            # Getting this exception means there are no more docs in the
            # db cursor. Set _has_more to False so that we can use that
            # information in other places.
            self._has_more = False

    async def count(self, with_limit_and_skip=False):
        """Count the selected elements in the query.

        Args:
            with_limit_and_skip: If True, take any :meth:`limit` or :meth:`skip`
                that has been applied to this cursor into account when getting
                the count. Defaults to False.

        Returns:
            int: The count of documents matching the query.

        Example::

            # Count all users
            total = await User.objects.count()

            # Count with limit/skip applied
            limited_count = await User.objects.limit(10).count(with_limit_and_skip=True)
        """
        if with_limit_and_skip is False:
            return await super().count(with_limit_and_skip)

        if self._len is None:
            # cache the length
            self._len = await super().count(with_limit_and_skip)

        return self._len

    async def to_list(self, length=None):
        """Fetch all results and return them as a list.

        This is a convenience method that iterates through the entire queryset
        and returns all documents as a Python list. The results are cached for
        future iterations.

        Args:
            length: Optional maximum number of results to return. If None,
                returns all results.

        Returns:
            list: A list of Document instances.

        Warning:
            Be careful with large result sets as this loads all documents into
            memory at once. Consider using async iteration for large datasets.

        Example::

            # Get all active users as a list
            users = await User.objects.filter(is_active=True).to_list()

            # Get first 100 users
            users = await User.objects.to_list(length=100)
        """
        results = []
        count = 0
        async for item in self:
            results.append(item)
            count += 1
            if length is not None and count >= length:
                break
        return results

    def no_cache(self):
        """Convert to a non-caching queryset.

        Returns an AsyncQuerySetNoCache instance that doesn't cache results. Useful
        for large result sets where you don't need to re-iterate.

        Returns:
            AsyncQuerySetNoCache: A non-caching version of this queryset.

        Raises:
            OperationError: If the queryset has already been cached.

        Example::

            # Iterate without caching (saves memory for large datasets)
            async for user in User.objects.no_cache():
                process(user)
        """
        if self._result_cache is not None:
            raise OperationError("AsyncQuerySet already cached")

        return self._clone_into(AsyncQuerySetNoCache(self._document, self._collection))


class AsyncQuerySetNoCache(AsyncBaseQuerySet):
    """A non-caching async QuerySet for memory-efficient iteration.

    This queryset does not cache results, making it ideal for processing
    large datasets where you only need to iterate once and don't need to
    re-iterate over the results.

    Usage Examples::

        # Process large dataset without caching
        async for user in User.objects.no_cache():
            await process_user(user)
            # Each user is processed and then garbage collected

        # Convert back to caching queryset if needed
        cached_qs = User.objects.no_cache().limit(10).cache()
        async for user in cached_qs:
            print(user.name)

    Note:
        - Results are not cached, so you cannot re-iterate
        - More memory efficient for large datasets
        - Cannot use ``len()`` on this queryset
        - Use ``.cache()`` to convert back to a caching queryset
    """

    def cache(self):
        """Convert to a caching queryset.

        Returns:
            AsyncQuerySet: A caching version of this queryset.

        Example::

            # Start with no-cache, convert to cached
            qs = User.objects.no_cache().limit(100).cache()
            async for user in qs:
                print(user.name)
            # Can re-iterate because it's now cached
            async for user in qs:
                print(user.email)
        """
        return self._clone_into(AsyncQuerySet(self._document, self._collection))

    def __repr__(self):
        """Provides the string representation of the QuerySet.

        Note: Cannot show results for async no-cache queryset.
        Use 'async for' to iterate over results.
        """
        if self._iter:
            return ".. queryset mid-iteration .."

        return "<QuerySetNoCache: use 'async for' to iterate>"

    def __aiter__(self):
        """Return an async iterator for the queryset.

        Returns:
            AsyncBaseQuerySet: An async iterator for this queryset.
        """
        queryset = self
        if queryset._iter:
            queryset = self.clone()
        queryset.rewind()
        return queryset
