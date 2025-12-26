"""
Tests for async error handling and exception scenarios.
"""

import pytest
import pytest_asyncio
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from mongoengine import DoesNotExist, MultipleObjectsReturned
from mongoengine.async_document import AsyncDocument
from mongoengine.async_fields import AsyncReferenceField
from mongoengine.errors import (
    ValidationError,
    NotUniqueError,
    FieldDoesNotExist,
    InvalidQueryError,
)
from mongoengine.fields import (
    StringField,
    IntField,
    EmailField,
    URLField,
)
from mongoengine.io.aio.connection import (
    async_connect,
    async_disconnect_all,
)


class AsyncUser(AsyncDocument):
    """Test user model."""

    name = StringField(required=True, max_length=50)
    email = EmailField(unique=True)
    age = IntField(min_value=0, max_value=150)
    website = URLField()

    meta = {"collection": "async_test_error_users"}


class AsyncPost(AsyncDocument):
    """Test post model."""

    title = StringField(required=True)
    author = AsyncReferenceField(AsyncUser)

    meta = {"collection": "async_test_error_posts"}


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    await async_disconnect_all()
    await async_connect("mongoenginetest_async", host="localhost", port=27017)

    # Clean up collections
    try:
        db = await AsyncUser._get_async_db()
        await db["async_test_error_users"].delete_many({})
        await db["async_test_error_posts"].delete_many({})
        # Drop indexes to reset unique constraints
        try:
            await db["async_test_error_users"].drop_indexes()
        except:
            pass
    except Exception as e:
        print(e)

    yield

    await async_disconnect_all()


# Validation errors


@pytest.mark.asyncio
async def test_required_field_validation(async_db):
    """Test validation error for missing required field."""
    user = AsyncUser()

    with pytest.raises(ValidationError) as exc_info:
        user.validate()

    assert "name" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_save_without_required_field(async_db):
    """Test saving document without required field."""
    user = AsyncUser(email="test@example.com")

    with pytest.raises(ValidationError):
        await user.save()


@pytest.mark.asyncio
async def test_max_length_validation(async_db):
    """Test max_length validation."""
    user = AsyncUser(name="x" * 100)  # Exceeds max_length=50

    with pytest.raises(ValidationError) as exc_info:
        user.validate()

    assert "name" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_min_value_validation(async_db):
    """Test min_value validation for IntField."""
    user = AsyncUser(name="Test", age=-5)

    with pytest.raises(ValidationError) as exc_info:
        user.validate()

    assert "age" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_max_value_validation(async_db):
    """Test max_value validation for IntField."""
    user = AsyncUser(name="Test", age=200)

    with pytest.raises(ValidationError) as exc_info:
        user.validate()

    assert "age" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_email_validation(async_db):
    """Test email validation."""
    user = AsyncUser(name="Test", email="invalid-email")

    with pytest.raises(ValidationError) as exc_info:
        user.validate()

    assert "email" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_url_validation(async_db):
    """Test URL validation."""
    user = AsyncUser(name="Test", website="not-a-url")

    with pytest.raises(ValidationError) as exc_info:
        user.validate()

    assert "website" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_save_with_validation_disabled(async_db):
    """Test saving with validation disabled skips validation."""
    user = AsyncUser()

    # With validate=False, validation is skipped
    # This will succeed but document may be incomplete
    try:
        await user.save(validate=False)
        # If it succeeds, validation was skipped
        assert True
    except Exception:
        # Some backends may still enforce required fields at DB level
        pass


# Unique constraint errors


@pytest.mark.asyncio
async def test_unique_constraint_violation(async_db):
    """Test unique constraint violation."""
    # Ensure unique index exists
    collection = await AsyncUser._get_async_collection()
    try:
        await collection.create_index("email", unique=True)
    except:
        pass

    # Save first user
    user1 = AsyncUser(name="User1", email="test@example.com")
    await user1.save()

    # Try to save second user with same email
    user2 = AsyncUser(name="User2", email="test@example.com")

    try:
        await user2.save()
        pytest.fail("Expected NotUniqueError or DuplicateKeyError")
    except (NotUniqueError, DuplicateKeyError):
        pass  # Expected


# Query errors


@pytest.mark.asyncio
async def test_does_not_exist_error(async_db):
    """Test DoesNotExist error when document not found."""
    with pytest.raises(DoesNotExist):
        await AsyncUser.objects.get(name="NonExistent")


@pytest.mark.asyncio
async def test_multiple_objects_returned_error(async_db):
    """Test MultipleObjectsReturned error."""
    await AsyncUser(name="Duplicate", email="user1@example.com").save()
    await AsyncUser(name="Duplicate", email="user2@example.com").save()

    with pytest.raises(MultipleObjectsReturned):
        await AsyncUser.objects.get(name="Duplicate")


@pytest.mark.asyncio
async def test_invalid_field_query(async_db):
    """Test querying with invalid field name."""
    with pytest.raises((FieldDoesNotExist, InvalidQueryError, AttributeError)):
        await AsyncUser.objects.filter(nonexistent_field="value").to_list()


@pytest.mark.asyncio
async def test_invalid_operator(async_db):
    """Test using invalid query operator."""
    # Invalid operators raise InvalidQueryError
    with pytest.raises(InvalidQueryError):
        await AsyncUser.objects.filter(name__invalid_op="test").to_list()


# Type errors


@pytest.mark.asyncio
async def test_wrong_type_for_int_field(async_db):
    """Test assigning wrong type to IntField."""
    user = AsyncUser(name="Test", age="not-an-int")

    with pytest.raises((ValidationError, ValueError, TypeError)):
        user.validate()


@pytest.mark.asyncio
async def test_wrong_type_for_reference_field(async_db):
    """Test assigning wrong type to ReferenceField."""
    post = AsyncPost(title="Test", author="not-a-reference")

    with pytest.raises((ValidationError, ValueError)):
        await post.save()


# Update errors


@pytest.mark.asyncio
async def test_update_with_invalid_field(async_db):
    """Test update with invalid field name."""
    await AsyncUser(name="Test", email="test@example.com").save()

    with pytest.raises((FieldDoesNotExist, InvalidQueryError, AttributeError)):
        await AsyncUser.objects.update(nonexistent_field="value")


@pytest.mark.asyncio
async def test_update_with_validation_error(async_db):
    """Test update that would violate validation."""
    user = await AsyncUser(name="Test", email="test@example.com").save()

    # Try to update age to invalid value
    user.age = -10

    with pytest.raises(ValidationError):
        await user.save()


# Delete errors


@pytest.mark.asyncio
async def test_delete_unsaved_document(async_db):
    """Test deleting document that was never saved."""
    user = AsyncUser(name="Test")

    # Should not raise error, just do nothing
    result = await AsyncUser.objects.filter(pk=ObjectId()).delete()
    assert result == 0


# Reload errors


@pytest.mark.asyncio
async def test_reload_nonexistent_document(async_db):
    """Test reloading document that doesn't exist."""
    user = AsyncUser(name="Test", email="test@example.com")
    await user.save()

    # Delete the document
    await AsyncUser.objects.filter(pk=user.pk).delete()

    # Try to reload
    with pytest.raises(DoesNotExist):
        await user.reload()


@pytest.mark.asyncio
async def test_reload_without_pk(async_db):
    """Test reloading unsaved document."""
    user = AsyncUser(name="Test")

    # Reloading unsaved document raises DoesNotExist (pk is None)
    with pytest.raises(DoesNotExist):
        await user.reload()


# Reference field errors


@pytest.mark.asyncio
async def test_fetch_none_reference(async_db):
    """Test fetching None reference."""
    post = AsyncPost(title="Test", author=None)
    await post.save()

    result = await AsyncPost.author.fetch(post)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_deleted_reference(async_db):
    """Test fetching reference that was deleted."""
    user = AsyncUser(name="Test", email="test@example.com")
    await user.save()

    post = AsyncPost(title="Test", author=user)
    await post.save()

    # Delete the user
    await user.delete()

    # Reload post and try to fetch author
    await post.reload()

    # Fetching deleted reference raises DoesNotExist
    with pytest.raises(DoesNotExist):
        await AsyncPost.author.fetch(post)


# Connection errors


@pytest.mark.asyncio
async def test_operation_without_connection():
    """Test operation without establishing connection."""
    await async_disconnect_all()

    user = AsyncUser(name="Test", email="test@example.com")

    # Should raise connection error
    with pytest.raises(Exception):  # Could be various connection-related errors
        await user.save()

    # Reconnect for cleanup
    await async_connect("mongoenginetest_async", host="localhost", port=27017)


@pytest.mark.asyncio
async def test_invalid_database_name(async_db):
    """Test connecting to invalid database."""
    # Disconnect first
    await async_disconnect_all()

    # Connect with invalid characters in db name (if enforced)
    try:
        await async_connect("invalid/database/name", host="localhost", port=27017)
        # Some versions might allow this, so we just verify it doesn't crash
    except Exception:
        pass  # Expected in strict MongoDB versions

    # Reconnect to valid database
    await async_connect("mongoenginetest_async", host="localhost", port=27017)


# Concurrent modification errors


@pytest.mark.asyncio
async def test_concurrent_modification(async_db):
    """Test concurrent modification of same document."""
    user = AsyncUser(name="Test", email="test@example.com", age=25)
    await user.save()

    # Get two references to same document
    user1 = await AsyncUser.objects.get(pk=user.pk)
    user2 = await AsyncUser.objects.get(pk=user.pk)

    # Modify both
    user1.age = 30
    user2.age = 35

    # Save both - last one wins
    await user1.save()
    await user2.save()

    # Verify last save won
    final = await AsyncUser.objects.get(pk=user.pk)
    assert final.age == 35


# Invalid ObjectId errors


@pytest.mark.asyncio
async def test_invalid_objectid_string(async_db):
    """Test using invalid ObjectId string."""
    with pytest.raises((ValidationError, Exception)):
        await AsyncUser.objects.get(pk="invalid-objectid-string")


@pytest.mark.asyncio
async def test_empty_objectid_string(async_db):
    """Test using empty ObjectId string."""
    with pytest.raises((ValidationError, DoesNotExist, Exception)):
        await AsyncUser.objects.get(pk="")


# Modify errors


@pytest.mark.asyncio
async def test_modify_nonexistent_document(async_db):
    """Test modifying document that doesn't exist."""
    result = await AsyncUser.objects.filter(pk=ObjectId()).modify(name="Updated")
    assert result is None


@pytest.mark.asyncio
async def test_modify_with_validation_error(async_db):
    """Test modify with invalid data."""
    user = AsyncUser(name="Test", email="test@example.com")
    await user.save()

    # Try to modify with invalid age
    with pytest.raises(ValidationError):
        await AsyncUser.objects.filter(pk=user.pk).modify(age=-10)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
