import pytest
import pytest_asyncio

from mongoengine import *
from mongoengine.async_document import AsyncDocument
from mongoengine.async_pymongo_support import async_list_collection_names
from mongoengine.io.aio.connection import (
    async_connect,
    async_disconnect_all,
    async_get_db,
)
from mongoengine.queryset import NULLIFY, PULL


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    await async_disconnect_all()
    await async_connect(db="mongoenginetest_async_class_methods")
    db = await async_get_db()

    yield db

    # Cleanup
    await async_disconnect_all()


@pytest.fixture
def Person():
    """Fixture providing Person class for tests that need it."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        non_field = True
        meta = {"allow_inheritance": True}

    return Person


@pytest.mark.asyncio
async def test_definition(async_db):
    """Ensure that document may be defined using fields."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        non_field = True
        meta = {"allow_inheritance": True}

    assert ["_cls", "age", "id", "name"] == sorted(Person._fields.keys())
    assert ["IntField", "ObjectIdField", "StringField", "StringField"] == sorted(
        x.__class__.__name__ for x in Person._fields.values()
    )


@pytest.mark.asyncio
async def test_get_db(async_db):
    """Ensure that get_db returns the expected db."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        meta = {"allow_inheritance": True}

    db = await Person._get_async_db()
    assert async_db.name == db.name


@pytest.mark.asyncio
async def test_get_collection_name(async_db):
    """Ensure that get_collection_name returns the expected collection name."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        meta = {"allow_inheritance": True}

    collection_name = "person"
    assert collection_name == Person._get_collection_name()


@pytest.mark.asyncio
async def test_get_collection(async_db):
    """Ensure that get_collection returns the expected collection."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        meta = {"allow_inheritance": True}

    collection_name = "person"
    collection = await Person._get_async_collection()
    assert async_db[collection_name].name == collection.name


@pytest.mark.asyncio
async def test_drop_collection(async_db):
    """Ensure that the collection may be dropped from the database."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        meta = {"allow_inheritance": True}

    collection_name = "person"
    await Person(name="Test").save()
    collections = await async_list_collection_names(async_db)
    assert collection_name in collections

    await Person.drop_collection()
    collections = await async_list_collection_names(async_db)
    assert collection_name not in collections


@pytest.mark.asyncio
async def test_register_delete_rule(async_db):
    """Ensure that register delete rule adds a delete rule to the document meta."""

    class Person(AsyncDocument):
        name = StringField()
        age = IntField()
        meta = {"allow_inheritance": True}

    class Job(AsyncDocument):
        employee = ReferenceField("Person")

    assert Person._meta.get("delete_rules") is None

    Person.register_delete_rule(Job, "employee", NULLIFY)
    assert Person._meta["delete_rules"] == {(Job, "employee"): NULLIFY}


@pytest.mark.asyncio
async def test_compare_indexes(async_db):
    """Ensure that the indexes are properly created and that
    compare_indexes identifies the missing/extra indexes
    """

    class BlogPost(AsyncDocument):
        author = StringField()
        title = StringField()
        description = StringField()
        tags = StringField()
        meta = {"indexes": [("author", "title")]}

    await BlogPost.drop_collection()

    await BlogPost.ensure_indexes()
    result = await BlogPost.compare_indexes()
    assert result == {"missing": [], "extra": []}

    await BlogPost.create_index(["author", "description"])
    result = await BlogPost.compare_indexes()
    assert result == {
        "missing": [],
        "extra": [[("author", 1), ("description", 1)]],
    }

    collection = await BlogPost._get_async_collection()
    await collection.drop_index("author_1_description_1")
    result = await BlogPost.compare_indexes()
    assert result == {"missing": [], "extra": []}

    await collection.drop_index("author_1_title_1")
    result = await BlogPost.compare_indexes()
    assert result == {
        "missing": [[("author", 1), ("title", 1)]],
        "extra": [],
    }


@pytest.mark.asyncio
async def test_compare_indexes_inheritance(async_db):
    """Ensure that the indexes are properly created and that
    compare_indexes identifies the missing/extra indexes for subclassed
    documents (_cls included)
    """

    class BlogPost(AsyncDocument):
        author = StringField()
        title = StringField()
        description = StringField()
        meta = {"allow_inheritance": True}

    class BlogPostWithTags(BlogPost):
        tags = StringField()
        tag_list = ListField(StringField())
        meta = {"indexes": [("author", "tags")]}

    await BlogPost.drop_collection()

    await BlogPost.ensure_indexes()
    await BlogPostWithTags.ensure_indexes()
    result = await BlogPost.compare_indexes()
    assert result == {"missing": [], "extra": []}

    await BlogPostWithTags.create_index(["author", "tag_list"])
    result = await BlogPost.compare_indexes()
    assert result == {
        "missing": [],
        "extra": [[("_cls", 1), ("author", 1), ("tag_list", 1)]],
    }

    collection = await BlogPostWithTags._get_async_collection()
    await collection.drop_index("_cls_1_author_1_tag_list_1")
    result = await BlogPost.compare_indexes()
    assert result == {"missing": [], "extra": []}

    await collection.drop_index("_cls_1_author_1_tags_1")
    result = await BlogPost.compare_indexes()
    assert result == {
        "missing": [[("_cls", 1), ("author", 1), ("tags", 1)]],
        "extra": [],
    }


@pytest.mark.asyncio
async def test_compare_indexes_multiple_subclasses(async_db):
    """Ensure that compare_indexes behaves correctly if called from a
    class, which base class has multiple subclasses
    """

    class BlogPost(AsyncDocument):
        author = StringField()
        title = StringField()
        description = StringField()
        meta = {"allow_inheritance": True}

    class BlogPostWithTags(BlogPost):
        tags = StringField()
        tag_list = ListField(StringField())
        meta = {"indexes": [("author", "tags")]}

    class BlogPostWithCustomField(BlogPost):
        custom = DictField()
        meta = {"indexes": [("author", "custom")]}

    await BlogPost.ensure_indexes()
    await BlogPostWithTags.ensure_indexes()
    await BlogPostWithCustomField.ensure_indexes()

    assert (await BlogPost.compare_indexes()) == {"missing": [], "extra": []}
    assert (await BlogPostWithTags.compare_indexes()) == {"missing": [], "extra": []}
    assert (await BlogPostWithCustomField.compare_indexes()) == {
        "missing": [],
        "extra": [],
    }


@pytest.mark.asyncio
async def test_compare_indexes_for_text_indexes(async_db):
    """Ensure that compare_indexes behaves correctly for text indexes"""

    class Doc(AsyncDocument):
        a = StringField()
        b = StringField()
        meta = {
            "indexes": [
                {
                    "fields": ["$a", "$b"],
                    "default_language": "english",
                    "weights": {"a": 10, "b": 2},
                }
            ]
        }

    await Doc.drop_collection()
    await Doc.ensure_indexes()
    actual = await Doc.compare_indexes()
    expected = {"missing": [], "extra": []}
    assert actual == expected


@pytest.mark.asyncio
async def test_list_indexes_inheritance(async_db):
    """ensure that all of the indexes are listed regardless of the super-
    or sub-class that we call it from
    """

    class BlogPost(AsyncDocument):
        author = StringField()
        title = StringField()
        description = StringField()
        meta = {"allow_inheritance": True}

    class BlogPostWithTags(BlogPost):
        tags = StringField()
        meta = {"indexes": [("author", "tags")]}

    class BlogPostWithTagsAndExtraText(BlogPostWithTags):
        extra_text = StringField()
        meta = {"indexes": [("author", "tags", "extra_text")]}

    await BlogPost.drop_collection()

    await BlogPost.ensure_indexes()
    await BlogPostWithTags.ensure_indexes()
    await BlogPostWithTagsAndExtraText.ensure_indexes()

    assert await BlogPost.list_indexes() == await BlogPostWithTags.list_indexes()
    assert await BlogPost.list_indexes() == await BlogPostWithTagsAndExtraText.list_indexes()
    assert await BlogPost.list_indexes() == [
        [("_cls", 1), ("author", 1), ("tags", 1)],
        [("_cls", 1), ("author", 1), ("tags", 1), ("extra_text", 1)],
        [("_id", 1)],
        [("_cls", 1)],
    ]


@pytest.mark.asyncio
async def test_register_delete_rule_inherited(async_db):
    class Vaccine(AsyncDocument):
        name = StringField(required=True)
        meta = {"indexes": ["name"]}

    class Animal(AsyncDocument):
        family = StringField(required=True)
        vaccine_made = ListField(ReferenceField("Vaccine", reverse_delete_rule=PULL))
        meta = {"allow_inheritance": True, "indexes": ["family"]}

    class Cat(Animal):
        name = StringField(required=True)

    assert Vaccine._meta["delete_rules"][(Animal, "vaccine_made")] == PULL
    assert Vaccine._meta["delete_rules"][(Cat, "vaccine_made")] == PULL


@pytest.mark.asyncio
async def test_collection_naming(async_db):
    """Ensure that a collection with a specified name may be used."""

    class DefaultNamingTest(AsyncDocument):
        pass

    assert "default_naming_test" == DefaultNamingTest._get_collection_name()

    class CustomNamingTest(AsyncDocument):
        meta = {"collection": "pimp_my_collection"}

    assert "pimp_my_collection" == CustomNamingTest._get_collection_name()

    class DynamicNamingTest(AsyncDocument):
        meta = {"collection": lambda c: "DYNAMO"}

    assert "DYNAMO" == DynamicNamingTest._get_collection_name()

    # Use Abstract class to handle backwards compatibility
    class BaseDocument(AsyncDocument):
        meta = {"abstract": True, "collection": lambda c: c.__name__.lower()}

    class OldNamingConvention(BaseDocument):
        pass

    assert "oldnamingconvention" == OldNamingConvention._get_collection_name()

    class InheritedAbstractNamingTest(BaseDocument):
        meta = {"collection": "wibble"}

    assert "wibble" == InheritedAbstractNamingTest._get_collection_name()

    # Mixin tests
    class BaseMixin:
        meta = {"collection": lambda c: c.__name__.lower()}

    class OldMixinNamingConvention(AsyncDocument, BaseMixin):
        pass

    assert "oldmixinnamingconvention" == OldMixinNamingConvention._get_collection_name()

    class BaseMixin:
        meta = {"collection": lambda c: c.__name__.lower()}

    class BaseDocument(AsyncDocument, BaseMixin):
        meta = {"allow_inheritance": True}

    class MyDocument(BaseDocument):
        pass

    assert "basedocument" == MyDocument._get_collection_name()


@pytest.mark.asyncio
async def test_custom_collection_name_operations(async_db):
    """Ensure that a collection with a specified name is used as expected."""
    collection_name = "personCollTest"

    class Person(AsyncDocument):
        name = StringField()
        meta = {"collection": collection_name}

    await Person(name="Test User").save()
    collections = await async_list_collection_names(async_db)
    assert collection_name in collections

    user_obj = await async_db[collection_name].find_one()
    assert user_obj["name"] == "Test User"

    user_obj = await Person.objects.first()
    assert user_obj.name == "Test User"

    await Person.drop_collection()
    collections = await async_list_collection_names(async_db)
    assert collection_name not in collections


@pytest.mark.asyncio
async def test_collection_name_and_primary(async_db):
    """Ensure that a collection with a specified name may be used."""

    class Person(AsyncDocument):
        name = StringField(primary_key=True)
        meta = {"collection": "app"}

    await Person(name="Test User").save()

    user_obj = await Person.objects.first()
    assert user_obj.name == "Test User"

    await Person.drop_collection()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
