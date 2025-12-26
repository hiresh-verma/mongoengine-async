"""
Basic tests for AsyncDocument functionality.

These tests verify that the async document operations work correctly.
"""

import pytest
import pytest_asyncio
from mongoengine.fields import StringField, IntField, EmailField
from mongoengine.async_document import AsyncDocument
from mongoengine.io.aio.connection import async_connect, async_disconnect


class AsyncUser(AsyncDocument):
    """Test user model."""
    name = StringField(required=True)
    email = EmailField()
    age = IntField()

    meta = {
        'collection': 'async_test_users'
    }


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    # Disconnect any existing connections first
    from mongoengine.io.aio.connection import async_disconnect_all
    await async_disconnect_all()

    # Connect to test database
    await async_connect('mongoenginetest_async', host='localhost', port=27017)

    yield

    # Clean up - disconnect after test
    await async_disconnect_all()


@pytest.mark.asyncio
async def test_async_document_save(async_db):
    """Test saving a document asynchronously."""
    # Create a new user
    user = AsyncUser(name='Alice', email='alice@example.com', age=30)

    # Save asynchronously
    await user.save()

    # Verify it has an ID
    assert user.pk is not None
    assert user.name == 'Alice'
    assert user.email == 'alice@example.com'
    assert user.age == 30


@pytest.mark.asyncio
async def test_async_document_reload(async_db):
    """Test reloading a document asynchronously."""
    # Create and save a user
    user = AsyncUser(name='Bob', email='bob@example.com', age=25)
    await user.save()

    original_id = user.pk

    # Modify in memory
    user.age = 26

    # Reload from database
    await user.reload()

    # Should have original age
    assert user.pk == original_id
    assert user.age == 25


@pytest.mark.asyncio
async def test_async_document_delete(async_db):
    """Test deleting a document asynchronously."""
    # Create and save a user
    user = AsyncUser(name='Charlie', email='charlie@example.com')
    await user.save()

    user_id = user.pk
    assert user_id is not None

    # Delete asynchronously
    await user.delete()

    # Verify it's deleted (should raise DoesNotExist)
    with pytest.raises(Exception):  # DoesNotExist
        user2 = AsyncUser(id=user_id)
        await user2.reload()


@pytest.mark.asyncio
async def test_async_document_update(async_db):
    """Test updating a document asynchronously."""
    # Create and save a user
    user = AsyncUser(name='David', email='david@example.com', age=35)
    await user.save()

    # Modify and save
    user.age = 36
    await user.save()

    # Reload to verify
    await user.reload()
    assert user.age == 36


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
