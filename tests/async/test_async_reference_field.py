"""
Tests for AsyncReferenceField functionality.
"""

import pytest
import pytest_asyncio
from bson import ObjectId
from mongoengine.fields import StringField, IntField
from mongoengine.async_document import AsyncDocument
from mongoengine.async_fields import AsyncReferenceField
from mongoengine.io.aio.connection import async_connect, async_disconnect_all


class AsyncAuthor(AsyncDocument):
    """Test author model."""
    name = StringField(required=True)
    email = StringField()

    meta = {
        'collection': 'async_test_authors'
    }


class AsyncPost(AsyncDocument):
    """Test post model with reference."""
    title = StringField(required=True)
    content = StringField()
    author = AsyncReferenceField(AsyncAuthor)

    meta = {
        'collection': 'async_test_posts'
    }


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    # Disconnect any existing connections first
    await async_disconnect_all()

    # Connect to test database
    await async_connect('mongoenginetest_async', host='localhost', port=27017)

    # Clean up collections before tests
    author_collection = await AsyncAuthor._get_async_collection()
    await author_collection.delete_many({})

    post_collection = await AsyncPost._get_async_collection()
    await post_collection.delete_many({})

    yield

    # Clean up - disconnect after test
    await async_disconnect_all()


@pytest.mark.asyncio
async def test_reference_field_raw_access(async_db):
    """Test that accessing a reference field returns raw ObjectId."""
    # Create author
    author = AsyncAuthor(name='Alice', email='alice@example.com')
    await author.save()

    # Create post with reference
    post = AsyncPost(title='Test Post', content='Hello', author=author)
    await post.save()

    # Reload post
    await post.reload()

    # Accessing reference should return ObjectId (raw reference)
    assert isinstance(post.author, ObjectId)
    assert post.author == author.pk


@pytest.mark.asyncio
async def test_reference_field_fetch(async_db):
    """Test explicit async dereferencing with fetch()."""
    # Create author
    author = AsyncAuthor(name='Bob', email='bob@example.com')
    await author.save()

    # Create post with reference
    post = AsyncPost(title='My Post', content='Content', author=author)
    await post.save()

    # Reload post to get fresh data
    await post.reload()

    # Fetch should dereference the author
    fetched_author = await AsyncPost.author.fetch(post)

    assert fetched_author is not None
    assert isinstance(fetched_author, AsyncAuthor)
    assert fetched_author.name == 'Bob'
    assert fetched_author.email == 'bob@example.com'
    assert fetched_author.pk == author.pk


@pytest.mark.asyncio
async def test_reference_field_caching(async_db):
    """Test that fetch() caches the dereferenced document."""
    # Create author
    author = AsyncAuthor(name='Charlie', email='charlie@example.com')
    await author.save()

    # Create post
    post = AsyncPost(title='Cached Post', author=author)
    await post.save()
    await post.reload()

    # First fetch
    author1 = await AsyncPost.author.fetch(post)

    # Second fetch should return cached value
    author2 = await AsyncPost.author.fetch(post)

    assert author1 is author2  # Same object reference (cached)


@pytest.mark.asyncio
async def test_reference_field_none(async_db):
    """Test reference field with None value."""
    # Create post without author
    post = AsyncPost(title='No Author Post', content='Solo')
    await post.save()
    await post.reload()

    # Accessing None reference
    assert post.author is None

    # Fetching None reference
    author = await AsyncPost.author.fetch(post)
    assert author is None


@pytest.mark.asyncio
async def test_reference_field_query_and_fetch(async_db):
    """Test querying for posts and fetching references."""
    # Create multiple authors and posts
    author1 = AsyncAuthor(name='David', email='david@example.com')
    await author1.save()

    author2 = AsyncAuthor(name='Eve', email='eve@example.com')
    await author2.save()

    post1 = AsyncPost(title='Post 1', author=author1)
    await post1.save()

    post2 = AsyncPost(title='Post 2', author=author2)
    await post2.save()

    # Query all posts
    posts = await AsyncPost.objects.to_list()

    assert len(posts) == 2

    # Fetch authors for each post
    for post in posts:
        author = await AsyncPost.author.fetch(post)
        assert author is not None
        assert isinstance(author, AsyncAuthor)


@pytest.mark.asyncio
async def test_reference_field_assignment(async_db):
    """Test assigning different types to reference field."""
    author = AsyncAuthor(name='Frank', email='frank@example.com')
    await author.save()

    # Test assigning Document instance
    post = AsyncPost(title='Test', author=author)
    await post.save()
    await post.reload()

    assert isinstance(post.author, ObjectId)

    # Test that we can fetch it
    fetched = await AsyncPost.author.fetch(post)
    assert fetched.name == 'Frank'


@pytest.mark.asyncio
async def test_reference_field_validation(async_db):
    """Test reference field validation."""
    # Test that we can't save a reference to unsaved document
    author = AsyncAuthor(name='Grace')  # Not saved yet

    post = AsyncPost(title='Test', author=author)

    # Should raise error when trying to save
    with pytest.raises(Exception):  # ValidationError
        await post.save()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
