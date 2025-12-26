"""
Tests for advanced async reference features:
- AsyncGenericReferenceField
- AsyncCachedReferenceField
- select_related() bulk dereferencing
"""

import pytest
import pytest_asyncio
from mongoengine.fields import StringField, IntField
from mongoengine.async_document import AsyncDocument
from mongoengine.async_fields import (
    AsyncReferenceField,
    AsyncGenericReferenceField,
    AsyncCachedReferenceField
)
from mongoengine.io.aio.connection import async_connect, async_disconnect_all


class AsyncUser(AsyncDocument):
    """Test user model."""
    name = StringField(required=True)
    email = StringField()
    age = IntField()

    meta = {
        'collection': 'async_test_advanced_users'
    }


class AsyncPost(AsyncDocument):
    """Test post model."""
    title = StringField(required=True)
    content = StringField()
    author = AsyncReferenceField(AsyncUser)

    meta = {
        'collection': 'async_test_advanced_posts'
    }


class AsyncComment(AsyncDocument):
    """Test comment model with generic reference."""
    text = StringField(required=True)
    # Can reference either Post or User
    target = AsyncGenericReferenceField()

    meta = {
        'collection': 'async_test_advanced_comments'
    }


class AsyncArticle(AsyncDocument):
    """Test article with cached reference."""
    title = StringField(required=True)
    # Cache name and email from author
    author = AsyncCachedReferenceField(AsyncUser, fields=['name', 'email'])

    meta = {
        'collection': 'async_test_advanced_articles'
    }


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    await async_disconnect_all()
    await async_connect('mongoenginetest_async', host='localhost', port=27017)

    # Clean up collections
    for collection_name in [
        'async_test_advanced_users',
        'async_test_advanced_posts',
        'async_test_advanced_comments',
        'async_test_advanced_articles'
    ]:
        try:
            coll = await AsyncUser._get_async_db()
            await coll[collection_name].delete_many({})
        except:
            pass

    yield

    await async_disconnect_all()


# AsyncGenericReferenceField Tests

@pytest.mark.asyncio
async def test_generic_reference_to_user(async_db):
    """Test generic reference pointing to a User."""
    user = AsyncUser(name='Alice', email='alice@example.com', age=30)
    await user.save()

    comment = AsyncComment(text='Great user!', target=user)
    await comment.save()
    await comment.reload()

    # Fetch the target
    target = await AsyncComment.target.fetch(comment)

    assert target is not None
    assert isinstance(target, AsyncUser)
    assert target.name == 'Alice'
    assert target.pk == user.pk


@pytest.mark.asyncio
async def test_generic_reference_to_post(async_db):
    """Test generic reference pointing to a Post."""
    user = AsyncUser(name='Bob', email='bob@example.com')
    await user.save()

    post = AsyncPost(title='My Post', content='Hello', author=user)
    await post.save()

    comment = AsyncComment(text='Nice post!', target=post)
    await comment.save()
    await comment.reload()

    # Fetch the target
    target = await AsyncComment.target.fetch(comment)

    assert target is not None
    assert isinstance(target, AsyncPost)
    assert target.title == 'My Post'
    assert target.pk == post.pk


@pytest.mark.asyncio
async def test_generic_reference_none(async_db):
    """Test generic reference with None value."""
    comment = AsyncComment(text='No target')
    await comment.save()
    await comment.reload()

    target = await AsyncComment.target.fetch(comment)
    assert target is None


# AsyncCachedReferenceField Tests

@pytest.mark.asyncio
async def test_cached_reference_save(async_db):
    """Test saving document with cached reference."""
    user = AsyncUser(name='Charlie', email='charlie@example.com', age=35)
    await user.save()

    article = AsyncArticle(title='Test Article', author=user)
    await article.save()

    # Reload and check cached fields
    await article.reload()

    # Access cached fields (should not require fetch)
    author_ref = article.author
    assert author_ref is not None
    assert author_ref.name == 'Charlie'
    assert author_ref.email == 'charlie@example.com'
    # The cached reference object wraps the data dict
    assert hasattr(author_ref, '_data')
    assert '_id' in author_ref._data
    assert author_ref._data['_id'] == user.pk


@pytest.mark.asyncio
async def test_cached_reference_fetch_full(async_db):
    """Test fetching full document from cached reference."""
    user = AsyncUser(name='David', email='david@example.com', age=40)
    await user.save()

    article = AsyncArticle(title='Another Article', author=user)
    await article.save()
    await article.reload()

    # Fetch full user document
    full_author = await AsyncArticle.author.fetch(article)

    assert full_author is not None
    assert isinstance(full_author, AsyncUser)
    assert full_author.name == 'David'
    assert full_author.email == 'david@example.com'
    assert full_author.age == 40  # This field is not cached
    assert full_author.pk == user.pk


# select_related() Tests

@pytest.mark.asyncio
async def test_select_related_basic(async_db):
    """Test basic select_related functionality."""
    # Create test data
    user1 = AsyncUser(name='Eve', email='eve@example.com')
    await user1.save()

    user2 = AsyncUser(name='Frank', email='frank@example.com')
    await user2.save()

    post1 = AsyncPost(title='Post 1', content='Content 1', author=user1)
    await post1.save()

    post2 = AsyncPost(title='Post 2', content='Content 2', author=user2)
    await post2.save()

    # Use select_related to prefetch authors
    posts = await AsyncPost.objects.select_related()

    assert len(posts) == 2

    # Authors should be dereferenced (no additional queries needed)
    for post in posts:
        assert isinstance(post.author, AsyncUser)
        assert post.author.name in ['Eve', 'Frank']


@pytest.mark.asyncio
async def test_select_related_filter(async_db):
    """Test select_related with query filters."""
    # Create test data
    user1 = AsyncUser(name='Grace', email='grace@example.com', age=25)
    await user1.save()

    user2 = AsyncUser(name='Henry', email='henry@example.com', age=30)
    await user2.save()

    post1 = AsyncPost(title='Young Post', author=user1)
    await post1.save()

    post2 = AsyncPost(title='Old Post', author=user2)
    await post2.save()

    # Filter and select_related
    posts = await AsyncPost.objects.filter(title__contains='Young').select_related()

    assert len(posts) == 1
    assert posts[0].title == 'Young Post'
    assert isinstance(posts[0].author, AsyncUser)
    assert posts[0].author.name == 'Grace'


@pytest.mark.asyncio
async def test_select_related_empty(async_db):
    """Test select_related with no results."""
    posts = await AsyncPost.objects.select_related()

    assert posts == []


@pytest.mark.asyncio
async def test_select_related_no_references(async_db):
    """Test select_related with documents that have no references."""
    user = AsyncUser(name='Ivan', email='ivan@example.com')
    await user.save()

    users = await AsyncUser.objects.select_related()

    assert len(users) == 1
    assert users[0].name == 'Ivan'


@pytest.mark.asyncio
async def test_select_related_multiple_posts_same_author(async_db):
    """Test select_related with multiple documents referencing same object."""
    user = AsyncUser(name='Jane', email='jane@example.com')
    await user.save()

    post1 = AsyncPost(title='Post A', author=user)
    await post1.save()

    post2 = AsyncPost(title='Post B', author=user)
    await post2.save()

    post3 = AsyncPost(title='Post C', author=user)
    await post3.save()

    # Should only fetch user once
    posts = await AsyncPost.objects.select_related()

    assert len(posts) == 3

    # All should have the same dereferenced author
    for post in posts:
        assert isinstance(post.author, AsyncUser)
        assert post.author.name == 'Jane'
        assert post.author.pk == user.pk


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
