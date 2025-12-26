"""
Basic tests for AsyncQuerySet functionality.
"""

import pytest
import pytest_asyncio
from mongoengine.fields import StringField, IntField
from mongoengine.async_document import AsyncDocument
from mongoengine.io.aio.connection import async_connect, async_disconnect_all


class AsyncPerson(AsyncDocument):
    """Test person model."""
    name = StringField(required=True)
    age = IntField()

    meta = {
        'collection': 'async_test_persons'
    }


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    # Disconnect any existing connections first
    await async_disconnect_all()

    # Connect to test database
    await async_connect('mongoenginetest_async', host='localhost', port=27017)

    # Clean up collection before tests
    collection = await AsyncPerson._get_async_collection()
    await collection.delete_many({})

    yield

    # Clean up - disconnect after test
    await async_disconnect_all()


@pytest.mark.asyncio
async def test_queryset_objects_exists(async_db):
    """Test that .objects property exists and returns AsyncQuerySet."""
    from mongoengine.async_queryset import AsyncQuerySet

    # Check that objects is an AsyncQuerySet
    qs = AsyncPerson.objects
    assert isinstance(qs, AsyncQuerySet)


@pytest.mark.asyncio
async def test_queryset_filter(async_db):
    """Test that queryset can be filtered."""
    # Create some test data
    person1 = AsyncPerson(name='Alice', age=30)
    await person1.save()

    person2 = AsyncPerson(name='Bob', age=25)
    await person2.save()

    # Test filter - chainable method (sync)
    qs = AsyncPerson.objects.filter(name='Alice')
    assert qs is not None

    # Test count - async method
    count = await qs.count()
    assert count == 1

    # Test iteration
    result = None
    async for person in qs:
        result = person
        break

    assert result is not None
    assert result.name == 'Alice'
    assert result.age == 30


@pytest.mark.asyncio
async def test_queryset_get(async_db):
    """Test queryset get() method."""
    # Create test data
    person = AsyncPerson(name='Charlie', age=35)
    await person.save()

    # Test get
    fetched = await AsyncPerson.objects.get(name='Charlie')
    assert fetched.name == 'Charlie'
    assert fetched.age == 35


@pytest.mark.asyncio
async def test_queryset_first(async_db):
    """Test queryset first() method."""
    # Create test data
    person1 = AsyncPerson(name='David', age=40)
    await person1.save()

    person2 = AsyncPerson(name='Eve', age=28)
    await person2.save()

    # Test first
    first = await AsyncPerson.objects.filter(age__gte=30).first()
    assert first is not None
    assert first.name == 'David'


@pytest.mark.asyncio
async def test_queryset_to_list(async_db):
    """Test queryset to_list() method."""
    # Create test data
    person1 = AsyncPerson(name='Frank', age=22)
    await person1.save()

    person2 = AsyncPerson(name='Grace', age=26)
    await person2.save()

    # Test to_list
    persons = await AsyncPerson.objects.to_list()
    assert len(persons) >= 2
    names = {p.name for p in persons}
    assert 'Frank' in names
    assert 'Grace' in names


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
