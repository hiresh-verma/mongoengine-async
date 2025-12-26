"""
Tests for async edge cases and boundary conditions.
"""

import pytest
import pytest_asyncio
from bson import ObjectId
from mongoengine.fields import (
    StringField,
    IntField,
    ListField,
    DictField,
    EmailField,
)
from mongoengine import DoesNotExist, MultipleObjectsReturned, EmbeddedDocument
from mongoengine.async_document import AsyncDocument
from mongoengine.io.aio.connection import async_connect, async_disconnect_all


class AsyncTestDoc(AsyncDocument):
    """Test document for edge cases."""

    name = StringField()
    value = IntField()
    tags = ListField(StringField())
    metadata = DictField()
    email = EmailField()

    meta = {"collection": "async_test_edge_cases"}


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    await async_disconnect_all()
    await async_connect("mongoenginetest_async", host="localhost", port=27017)

    # Clean up collections
    try:
        db = await AsyncTestDoc._get_async_db()
        await db["async_test_edge_cases"].delete_many({})
    except Exception as e:
        print(e)

    yield

    await async_disconnect_all()


# Empty and None value tests


@pytest.mark.asyncio
async def test_save_with_none_values(async_db):
    """Test saving document with None values."""
    doc = AsyncTestDoc(name=None, value=None)
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.name is None
    assert fetched.value is None


@pytest.mark.asyncio
async def test_save_with_empty_strings(async_db):
    """Test saving document with empty strings."""
    doc = AsyncTestDoc(name="")
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.name == ""


@pytest.mark.asyncio
async def test_save_with_empty_list(async_db):
    """Test saving document with empty list."""
    doc = AsyncTestDoc(name="test", tags=[])
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.tags == []


@pytest.mark.asyncio
async def test_save_with_empty_dict(async_db):
    """Test saving document with empty dict."""
    doc = AsyncTestDoc(name="test", metadata={})
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.metadata == {}


@pytest.mark.asyncio
async def test_query_empty_collection(async_db):
    """Test querying empty collection."""
    results = await AsyncTestDoc.objects.to_list()
    assert results == []

    count = await AsyncTestDoc.objects.count()
    assert count == 0


@pytest.mark.asyncio
async def test_first_on_empty_collection(async_db):
    """Test first() on empty collection."""
    result = await AsyncTestDoc.objects.first()
    assert result is None


# ObjectId edge cases


@pytest.mark.asyncio
async def test_get_with_invalid_objectid(async_db):
    """Test get() with invalid ObjectId."""
    with pytest.raises(DoesNotExist):
        await AsyncTestDoc.objects.get(pk=ObjectId())


@pytest.mark.asyncio
async def test_filter_with_invalid_objectid(async_db):
    """Test filter with invalid ObjectId."""
    results = await AsyncTestDoc.objects.filter(pk=ObjectId()).to_list()
    assert results == []


@pytest.mark.asyncio
async def test_get_with_string_objectid(async_db):
    """Test get() with string representation of ObjectId."""
    doc = AsyncTestDoc(name="test")
    await doc.save()

    # Get with string ObjectId
    fetched = await AsyncTestDoc.objects.get(pk=str(doc.pk))
    assert fetched.pk == doc.pk


# Large data edge cases


@pytest.mark.asyncio
async def test_save_large_string(async_db):
    """Test saving document with large string."""
    large_string = "x" * 10000
    doc = AsyncTestDoc(name=large_string)
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert len(fetched.name) == 10000


@pytest.mark.asyncio
async def test_save_large_list(async_db):
    """Test saving document with large list."""
    large_list = [str(i) for i in range(1000)]
    doc = AsyncTestDoc(name="test", tags=large_list)
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert len(fetched.tags) == 1000


@pytest.mark.asyncio
async def test_save_large_dict(async_db):
    """Test saving document with large dict."""
    large_dict = {f"key_{i}": f"value_{i}" for i in range(1000)}
    doc = AsyncTestDoc(name="test", metadata=large_dict)
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert len(fetched.metadata) == 1000


# Special characters


@pytest.mark.asyncio
async def test_save_with_special_characters(async_db):
    """Test saving document with special characters."""
    special_chars = "!@#$%^&*()_+-=[]{}|;:'\",.<>?/~`"
    doc = AsyncTestDoc(name=special_chars)
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.name == special_chars


@pytest.mark.asyncio
async def test_save_with_unicode(async_db):
    """Test saving document with unicode characters."""
    unicode_text = "こんにちは 世界 🌍 Привет мир"
    doc = AsyncTestDoc(name=unicode_text)
    await doc.save()

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.name == unicode_text


# Query edge cases


@pytest.mark.asyncio
async def test_multiple_objects_returned(async_db):
    """Test get() when multiple objects match."""
    await AsyncTestDoc(name="duplicate").save()
    await AsyncTestDoc(name="duplicate").save()

    with pytest.raises(MultipleObjectsReturned):
        await AsyncTestDoc.objects.get(name="duplicate")


@pytest.mark.asyncio
async def test_filter_with_none(async_db):
    """Test filter with None value."""
    await AsyncTestDoc(name="test", value=None).save()
    await AsyncTestDoc(name="test2", value=10).save()

    results = await AsyncTestDoc.objects.filter(value=None).to_list()
    assert len(results) == 1
    assert results[0].name == "test"


@pytest.mark.asyncio
async def test_filter_with_empty_query(async_db):
    """Test filter with no query parameters."""
    await AsyncTestDoc(name="test1").save()
    await AsyncTestDoc(name="test2").save()

    results = await AsyncTestDoc.objects.filter().to_list()
    assert len(results) == 2


@pytest.mark.asyncio
async def test_filter_with_not_operator(async_db):
    """Test filter with $ne (not equal) operator."""
    await AsyncTestDoc(name="test1").save()
    await AsyncTestDoc(name="test2").save()

    results = await AsyncTestDoc.objects.filter(name__ne="test1").to_list()
    assert len(results) == 1
    assert results[0].name == "test2"


# Update edge cases


@pytest.mark.asyncio
async def test_update_to_none(async_db):
    """Test updating field to None using unset."""
    doc = AsyncTestDoc(name="test", value=10)
    await doc.save()

    # Use update with unset to remove field
    await AsyncTestDoc.objects.filter(pk=doc.pk).update(unset__value=1)

    fetched = await AsyncTestDoc.objects.get(pk=doc.pk)
    assert fetched.value is None


@pytest.mark.asyncio
async def test_update_nonexistent_document(async_db):
    """Test updating document that doesn't exist."""
    result = await AsyncTestDoc.objects.filter(pk=ObjectId()).update(name="updated")
    assert result == 0


# Delete edge cases


@pytest.mark.asyncio
async def test_delete_nonexistent_document(async_db):
    """Test deleting document that doesn't exist."""
    doc = AsyncTestDoc(name="test")
    doc.pk = ObjectId()  # Set invalid ID

    # Delete should not raise error
    result = await AsyncTestDoc.objects.filter(pk=doc.pk).delete()
    assert result == 0


@pytest.mark.asyncio
async def test_delete_empty_filter(async_db):
    """Test delete with empty filter (deletes all)."""
    await AsyncTestDoc(name="test1").save()
    await AsyncTestDoc(name="test2").save()

    count = await AsyncTestDoc.objects.delete()
    assert count == 2

    remaining = await AsyncTestDoc.objects.count()
    assert remaining == 0


# Reload edge cases


@pytest.mark.asyncio
async def test_reload_deleted_document(async_db):
    """Test reloading document that was deleted."""
    doc = AsyncTestDoc(name="test")
    await doc.save()
    pk = doc.pk

    # Delete from another query
    await AsyncTestDoc.objects.filter(pk=pk).delete()

    # Reload should raise DoesNotExist
    with pytest.raises(DoesNotExist):
        await doc.reload()


@pytest.mark.asyncio
async def test_reload_unsaved_document(async_db):
    """Test reloading document that was never saved."""
    doc = AsyncTestDoc(name="test")

    # Reloading unsaved document (pk is None) raises DoesNotExist
    with pytest.raises(DoesNotExist):
        await doc.reload()


# Limit and skip edge cases


@pytest.mark.asyncio
async def test_limit_zero(async_db):
    """Test limit(0) returns all documents (MongoDB behavior)."""
    await AsyncTestDoc(name="test1").save()
    await AsyncTestDoc(name="test2").save()

    # limit(0) in MongoDB means no limit (returns all)
    results = await AsyncTestDoc.objects.limit(0).to_list()
    assert len(results) == 2


@pytest.mark.asyncio
async def test_skip_beyond_count(async_db):
    """Test skip beyond document count."""
    await AsyncTestDoc(name="test1").save()

    results = await AsyncTestDoc.objects.skip(10).to_list()
    assert results == []


@pytest.mark.asyncio
async def test_limit_larger_than_count(async_db):
    """Test limit larger than document count."""
    await AsyncTestDoc(name="test1").save()

    results = await AsyncTestDoc.objects.limit(100).to_list()
    assert len(results) == 1


# Ordering edge cases


@pytest.mark.asyncio
async def test_order_by_none_values(async_db):
    """Test ordering when some values are None."""
    await AsyncTestDoc(name="a", value=None).save()
    await AsyncTestDoc(name="b", value=10).save()
    await AsyncTestDoc(name="c", value=5).save()

    results = await AsyncTestDoc.objects.order_by("value").to_list()
    assert len(results) == 3
    # None should come first
    assert results[0].value is None


@pytest.mark.asyncio
async def test_order_by_descending(async_db):
    """Test descending order."""
    await AsyncTestDoc(name="a", value=1).save()
    await AsyncTestDoc(name="b", value=3).save()
    await AsyncTestDoc(name="c", value=2).save()

    results = await AsyncTestDoc.objects.order_by("-value").to_list()
    assert results[0].value == 3
    assert results[1].value == 2
    assert results[2].value == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
