"""
Tests for concurrent async operations.
"""

import asyncio
import pytest
import pytest_asyncio
from mongoengine.fields import StringField, IntField, ListField
from mongoengine.async_document import AsyncDocument
from mongoengine.async_fields import AsyncReferenceField
from mongoengine.io.aio.connection import async_connect, async_disconnect_all


class AsyncCounter(AsyncDocument):
    """Test document for concurrent operations."""

    name = StringField(required=True)
    count = IntField(default=0)

    meta = {"collection": "async_test_concurrent_counters"}


class AsyncTask(AsyncDocument):
    """Test document for task tracking."""

    name = StringField(required=True)
    status = StringField(default="pending")
    result = IntField()

    meta = {"collection": "async_test_concurrent_tasks"}


class AsyncBulkDoc(AsyncDocument):
    """Test document for bulk operations."""

    value = IntField()
    tags = ListField(StringField())

    meta = {"collection": "async_test_concurrent_bulk"}


class AsyncAuthor(AsyncDocument):
    """Author for reference testing."""

    name = StringField(required=True)

    meta = {"collection": "async_test_concurrent_authors"}


class AsyncArticle(AsyncDocument):
    """Article with reference."""

    title = StringField(required=True)
    author = AsyncReferenceField(AsyncAuthor)

    meta = {"collection": "async_test_concurrent_articles"}


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    await async_disconnect_all()
    await async_connect("mongoenginetest_async", host="localhost", port=27017)

    # Clean up collections
    try:
        db = await AsyncCounter._get_async_db()
        await db["async_test_concurrent_counters"].delete_many({})
        await db["async_test_concurrent_tasks"].delete_many({})
        await db["async_test_concurrent_bulk"].delete_many({})
        await db["async_test_concurrent_authors"].delete_many({})
        await db["async_test_concurrent_articles"].delete_many({})
    except Exception as e:
        print(e)

    yield

    await async_disconnect_all()


# Concurrent save operations


@pytest.mark.asyncio
async def test_concurrent_saves(async_db):
    """Test multiple concurrent save operations."""

    async def save_task(i):
        task = AsyncTask(name=f"Task {i}", status="running")
        await task.save()
        return task

    # Create 100 tasks concurrently
    tasks = await asyncio.gather(*[save_task(i) for i in range(100)])

    # Verify all were saved
    assert len(tasks) == 100
    count = await AsyncTask.objects.count()
    assert count == 100


@pytest.mark.asyncio
async def test_concurrent_updates(async_db):
    """Test multiple concurrent update operations."""
    # Create initial documents
    counters = []
    for i in range(10):
        counter = AsyncCounter(name=f"Counter {i}", count=0)
        await counter.save()
        counters.append(counter)

    async def increment_counter(counter):
        # Reload to get latest
        await counter.reload()
        counter.count += 1
        await counter.save()

    # Increment each counter 10 times concurrently
    for counter in counters:
        await asyncio.gather(*[increment_counter(counter) for _ in range(10)])

    # Verify counts (may not be exactly 10 due to race conditions)
    for counter in counters:
        await counter.reload()
        # Due to race conditions, final count might be less than 10
        assert counter.count > 0


@pytest.mark.asyncio
async def test_concurrent_reads(async_db):
    """Test multiple concurrent read operations."""
    # Create some documents
    for i in range(10):
        await AsyncTask(name=f"Task {i}", status="completed", result=i).save()

    async def read_task(i):
        task = await AsyncTask.objects.get(name=f"Task {i}")
        return task.result

    # Read all concurrently
    results = await asyncio.gather(*[read_task(i) for i in range(10)])

    assert results == list(range(10))


@pytest.mark.asyncio
async def test_concurrent_queries(async_db):
    """Test multiple concurrent query operations."""
    # Create documents
    for i in range(50):
        await AsyncTask(name=f"Task {i}", status="completed" if i % 2 == 0 else "pending").save()

    async def query_by_status(status):
        return await AsyncTask.objects.filter(status=status).count()

    # Query concurrently
    completed_count, pending_count = await asyncio.gather(
        query_by_status("completed"), query_by_status("pending")
    )

    assert completed_count == 25
    assert pending_count == 25


# Concurrent deletes


@pytest.mark.asyncio
async def test_concurrent_deletes(async_db):
    """Test multiple concurrent delete operations."""
    # Create documents
    tasks = []
    for i in range(20):
        task = AsyncTask(name=f"Task {i}", status="pending")
        await task.save()
        tasks.append(task)

    async def delete_task(task):
        await task.delete()

    # Delete all concurrently
    await asyncio.gather(*[delete_task(task) for task in tasks])

    # Verify all deleted
    count = await AsyncTask.objects.count()
    assert count == 0


@pytest.mark.asyncio
async def test_concurrent_bulk_insert(async_db):
    """Test concurrent bulk insert operations."""

    async def bulk_insert(batch_num):
        docs = []
        for i in range(10):
            doc = AsyncBulkDoc(value=batch_num * 10 + i)
            await doc.save()
            docs.append(doc)
        return docs

    # Insert 10 batches of 10 documents concurrently
    batches = await asyncio.gather(*[bulk_insert(i) for i in range(10)])

    # Verify all inserted
    count = await AsyncBulkDoc.objects.count()
    assert count == 100


@pytest.mark.asyncio
async def test_concurrent_iteration(async_db):
    """Test concurrent iteration over querysets."""
    # Create documents
    for i in range(50):
        await AsyncTask(name=f"Task {i}", status="completed", result=i).save()

    async def iterate_and_sum():
        total = 0
        async for task in AsyncTask.objects:
            total += task.result or 0
        return total

    # Iterate concurrently in multiple tasks
    sums = await asyncio.gather(*[iterate_and_sum() for _ in range(5)])

    # All should have the same sum
    expected_sum = sum(range(50))
    assert all(s == expected_sum for s in sums)


# Concurrent reference operations


@pytest.mark.asyncio
async def test_concurrent_reference_fetch(async_db):
    """Test concurrent fetching of references."""
    # Create author
    author = AsyncAuthor(name="Test Author")
    await author.save()

    # Create articles
    articles = []
    for i in range(20):
        article = AsyncArticle(title=f"Article {i}", author=author)
        await article.save()
        articles.append(article)

    async def fetch_author(article):
        return await AsyncArticle.author.fetch(article)

    # Fetch all authors concurrently
    authors = await asyncio.gather(*[fetch_author(article) for article in articles])

    # All should be the same author
    assert all(a.pk == author.pk for a in authors)
    assert all(a.name == "Test Author" for a in authors)


@pytest.mark.asyncio
async def test_concurrent_select_related(async_db):
    """Test concurrent select_related operations."""
    # Create authors
    for i in range(5):
        author = AsyncAuthor(name=f"Author {i}")
        await author.save()

        # Create articles for each author
        for j in range(4):
            article = AsyncArticle(title=f"Article {i}-{j}", author=author)
            await article.save()

    async def get_articles_with_authors():
        return await AsyncArticle.objects.select_related()

    # Run select_related concurrently
    results = await asyncio.gather(*[get_articles_with_authors() for _ in range(5)])

    # All should return same number of articles with authors loaded
    for articles in results:
        assert len(articles) == 20
        for article in articles:
            assert isinstance(article.author, AsyncAuthor)


# Mixed concurrent operations


@pytest.mark.asyncio
async def test_mixed_concurrent_operations(async_db):
    """Test mix of read, write, update, delete operations concurrently."""

    async def create_task(i):
        task = AsyncTask(name=f"Task {i}", status="created")
        await task.save()
        return task

    async def update_task(task):
        await task.reload()
        task.status = "updated"
        await task.save()

    async def read_task(name):
        try:
            return await AsyncTask.objects.get(name=name)
        except:
            return None

    async def delete_task(task):
        try:
            await task.delete()
        except:
            pass

    # Create 20 tasks
    tasks = await asyncio.gather(*[create_task(i) for i in range(20)])

    # Mix operations: update some, read some, delete some
    operations = []

    # Update first 10
    operations.extend([update_task(task) for task in tasks[:10]])

    # Read middle 10
    operations.extend([read_task(f"Task {i}") for i in range(5, 15)])

    # Delete last 10
    operations.extend([delete_task(task) for task in tasks[10:]])

    # Run all concurrently
    await asyncio.gather(*operations)

    # Verify state
    remaining = await AsyncTask.objects.count()
    assert remaining == 10  # Only first 10 should remain (last 10 deleted)


# Stress test


@pytest.mark.asyncio
async def test_concurrent_stress(async_db):
    """Stress test with many concurrent operations."""

    async def worker(worker_id):
        # Each worker creates, reads, updates, deletes
        doc = AsyncCounter(name=f"Worker {worker_id}", count=0)
        await doc.save()

        # Update multiple times
        for _ in range(5):
            await doc.reload()
            doc.count += 1
            await doc.save()

        # Read
        fetched = await AsyncCounter.objects.get(pk=doc.pk)
        assert fetched.count == doc.count

        # Delete
        await doc.delete()

    # Run 50 workers concurrently
    await asyncio.gather(*[worker(i) for i in range(50)])

    # All should be deleted
    count = await AsyncCounter.objects.count()
    assert count == 0


# Timeout and cancellation


@pytest.mark.asyncio
async def test_task_cancellation(async_db):
    """Test cancellation of async operations."""

    async def long_running_operation():
        # Simulate long operation
        await asyncio.sleep(5)
        doc = AsyncTask(name="Long Task", status="completed")
        await doc.save()

    # Create task and cancel it
    task = asyncio.create_task(long_running_operation())
    await asyncio.sleep(0.1)  # Let it start
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass  # Expected

    # Verify document wasn't created
    count = await AsyncTask.objects.filter(name="Long Task").count()
    assert count == 0


@pytest.mark.asyncio
async def test_concurrent_with_timeout(async_db):
    """Test concurrent operations with timeout."""

    async def slow_save(i):
        await asyncio.sleep(0.1)  # Simulate slow operation
        doc = AsyncTask(name=f"Task {i}", status="completed")
        await doc.save()

    # Run with timeout
    try:
        await asyncio.wait_for(
            asyncio.gather(*[slow_save(i) for i in range(100)]), timeout=5.0
        )
    except asyncio.TimeoutError:
        pytest.fail("Operations timed out")

    # Verify all completed
    count = await AsyncTask.objects.count()
    assert count == 100


# Connection pooling


@pytest.mark.asyncio
async def test_connection_pooling(async_db):
    """Test that connection pooling works under concurrent load."""

    async def use_connection(i):
        # Multiple operations using same connection
        doc = AsyncTask(name=f"Task {i}", status="pending")
        await doc.save()
        await doc.reload()
        doc.status = "completed"
        await doc.save()
        await doc.delete()

    # Run many concurrent operations
    await asyncio.gather(*[use_connection(i) for i in range(100)])

    # Verify all completed (and deleted)
    count = await AsyncTask.objects.count()
    assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
