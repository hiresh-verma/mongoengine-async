"""
Asynchronous I/O operations - thin wrapper around PyMongo 4.0+ native async calls.

This class provides a clean abstraction over all PyMongo async database operations.
All methods are static and use async/await to delegate to PyMongo's native asynchronous API
(PyMongo 4.0+ AsyncMongoClient).
"""


class AsyncIOOperations:
    """
    Asynchronous I/O operations layer.

    This class contains all async PyMongo operations used by MongoEngine.
    Each method is a thin wrapper that directly calls PyMongo's async API.
    """

    # ========================================================================
    # Document-level operations (used by Document class)
    # ========================================================================

    @staticmethod
    async def insert_one(collection, document, session=None):
        """
        Insert a single document into the collection.

        Args:
            collection: PyMongo async collection object
            document: Document dict to insert
            session: Optional session for transactions

        Returns:
            InsertOneResult with inserted_id
        """
        return await collection.insert_one(document, session=session)

    @staticmethod
    async def find_one_and_replace(collection, filter, replacement, session=None, **kwargs):
        """
        Find a document and replace it atomically.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            replacement: Replacement document dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            The original document (before replacement) or None
        """
        return await collection.find_one_and_replace(filter, replacement, session=session, **kwargs)

    @staticmethod
    async def update_one(collection, filter, update, upsert=False, session=None, **kwargs):
        """
        Update a single document.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            update: Update operations dict
            upsert: Whether to insert if not found
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            UpdateResult
        """
        return await collection.update_one(filter, update, upsert=upsert, session=session, **kwargs)

    # ========================================================================
    # QuerySet read operations
    # ========================================================================

    @staticmethod
    def find(collection, filter, session=None, **kwargs):
        """
        Find documents matching a query.

        Note: This returns a cursor synchronously. The cursor itself is async-iterable.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments (projection, sort, limit, etc.)

        Returns:
            AsyncCursor object (PyMongo 4.0+ async cursor, async iterable)
        """
        return collection.find(filter, session=session, **kwargs)

    @staticmethod
    async def find_one(collection, filter, session=None, **kwargs):
        """
        Find a single document.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            Document dict or None
        """
        return await collection.find_one(filter, session=session, **kwargs)

    @staticmethod
    async def count_documents(collection, filter, session=None, **kwargs):
        """
        Count documents matching a query.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments (skip, limit, hint, etc.)

        Returns:
            int: Number of matching documents
        """
        return await collection.count_documents(filter, session=session, **kwargs)

    @staticmethod
    async def estimated_document_count(collection, **kwargs):
        """
        Get estimated document count (faster, less accurate).

        Args:
            collection: PyMongo async collection object
            **kwargs: Additional PyMongo arguments

        Returns:
            int: Estimated number of documents
        """
        return await collection.estimated_document_count(**kwargs)

    @staticmethod
    async def distinct(collection, key, filter=None, session=None, **kwargs):
        """
        Get distinct values for a field.

        Args:
            collection: PyMongo async collection object
            key: Field name
            filter: Optional query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            list: Distinct values
        """
        return await collection.distinct(key, filter=filter, session=session, **kwargs)

    @staticmethod
    def aggregate(collection, pipeline, session=None, **kwargs):
        """
        Run an aggregation pipeline.

        Note: This returns a cursor synchronously. The cursor itself is async-iterable.

        Args:
            collection: PyMongo async collection object
            pipeline: Aggregation pipeline list
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            AsyncCommandCursor (async iterable)
        """
        return collection.aggregate(pipeline, session=session, **kwargs)

    # ========================================================================
    # QuerySet write operations
    # ========================================================================

    @staticmethod
    async def insert_many(collection, documents, ordered=True, session=None):
        """
        Insert multiple documents.

        Args:
            collection: PyMongo async collection object
            documents: List of document dicts
            ordered: Whether to stop on first error
            session: Optional session for transactions

        Returns:
            InsertManyResult with inserted_ids
        """
        return await collection.insert_many(documents, ordered=ordered, session=session)

    @staticmethod
    async def update_many(collection, filter, update, upsert=False, session=None, **kwargs):
        """
        Update multiple documents.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            update: Update operations dict
            upsert: Whether to insert if not found
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            UpdateResult
        """
        return await collection.update_many(filter, update, upsert=upsert, session=session, **kwargs)

    @staticmethod
    async def delete_one(collection, filter, session=None, **kwargs):
        """
        Delete a single document.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            DeleteResult
        """
        return await collection.delete_one(filter, session=session, **kwargs)

    @staticmethod
    async def delete_many(collection, filter, session=None, **kwargs):
        """
        Delete multiple documents.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            DeleteResult
        """
        return await collection.delete_many(filter, session=session, **kwargs)

    @staticmethod
    async def find_one_and_update(collection, filter, update, session=None, return_document=None, **kwargs):
        """
        Find a document and update it atomically.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            update: Update operations dict
            session: Optional session for transactions
            return_document: Whether to return before or after update
            **kwargs: Additional PyMongo arguments (upsert, sort, etc.)

        Returns:
            The document (before or after update) or None
        """
        return await collection.find_one_and_update(
            filter, update, session=session, return_document=return_document, **kwargs
        )

    @staticmethod
    async def find_one_and_delete(collection, filter, session=None, **kwargs):
        """
        Find a document and delete it atomically.

        Args:
            collection: PyMongo async collection object
            filter: Query filter dict
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments (sort, etc.)

        Returns:
            The deleted document or None
        """
        return await collection.find_one_and_delete(filter, session=session, **kwargs)

    # ========================================================================
    # Index operations
    # ========================================================================

    @staticmethod
    async def create_index(collection, keys, session=None, **kwargs):
        """
        Create an index on the collection.

        Args:
            collection: PyMongo async collection object
            keys: Index specification
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments (unique, background, etc.)

        Returns:
            str: Index name
        """
        return await collection.create_index(keys, session=session, **kwargs)

    @staticmethod
    async def drop_index(collection, index_or_name, session=None):
        """
        Drop an index from the collection.

        Args:
            collection: PyMongo async collection object
            index_or_name: Index name or specification
            session: Optional session for transactions
        """
        return await collection.drop_index(index_or_name, session=session)

    @staticmethod
    async def index_information(collection, session=None):
        """
        Get information about collection indexes.

        Args:
            collection: PyMongo async collection object
            session: Optional session for transactions

        Returns:
            dict: Index information
        """
        return await collection.index_information(session=session)

    # ========================================================================
    # Database operations
    # ========================================================================

    @staticmethod
    async def list_collection_names(database, session=None, **kwargs):
        """
        List all collection names in the database.

        Args:
            database: PyMongo async database object
            session: Optional session for transactions
            **kwargs: Additional PyMongo arguments

        Returns:
            list: Collection names
        """
        return await database.list_collection_names(session=session, **kwargs)

    @staticmethod
    async def drop_collection(database, name_or_collection, session=None):
        """
        Drop a collection from the database.

        Args:
            database: PyMongo async database object
            name_or_collection: Collection name or object
            session: Optional session for transactions
        """
        return await database.drop_collection(name_or_collection, session=session)

    @staticmethod
    async def create_collection(database, name, session=None, **kwargs):
        """
        Create a new collection.

        Args:
            database: PyMongo async database object
            name: Collection name
            session: Optional session for transactions
            **kwargs: Collection options (capped, size, etc.)

        Returns:
            Collection object
        """
        return await database.create_collection(name, session=session, **kwargs)

    @staticmethod
    async def command(database, command, session=None, **kwargs):
        """
        Execute a database command.

        Args:
            database: PyMongo async database object
            command: Command dict or name
            session: Optional session for transactions
            **kwargs: Additional arguments

        Returns:
            Command result
        """
        return await database.command(command, session=session, **kwargs)

    @staticmethod
    async def dereference(database, dbref, session=None):
        """
        Dereference a DBRef.

        Args:
            database: PyMongo async database object
            dbref: DBRef object
            session: Optional session for transactions

        Returns:
            Document dict or None
        """
        return await database.dereference(dbref, session=session)
