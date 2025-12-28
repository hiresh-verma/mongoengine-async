import unittest

from bson import SON

from mongoengine import (
    StringField,
    IntField,
    DictField,
    ListField,
    EmbeddedDocument,
    DynamicEmbeddedDocument,
    EmbeddedDocumentField,
    MapField,
)
from mongoengine.async_document import AsyncDocument, AsyncDynamicDocument
from mongoengine.async_fields import AsyncReferenceField
from mongoengine.async_pymongo_support import async_list_collection_names
from tests.utils import MongoDBTestCase, get_as_pymongo


class TestDelta(MongoDBTestCase):
    def setUp(self):
        super().setUp()

        class Person(AsyncDocument):
            name = StringField()
            age = IntField()

            non_field = True

            meta = {"allow_inheritance": True}

        self.Person = Person

    async def tearDown(self):
        for collection in await async_list_collection_names(self.db):
            await self.db.drop_collection(collection)

    def test_delta(self):
        self.delta(AsyncDocument)
        self.delta(AsyncDynamicDocument)

    @staticmethod
    async def delta(DocClass):
        class Doc(DocClass):
            string_field = StringField()
            int_field = IntField()
            dict_field = DictField()
            list_field = ListField()

        await Doc.drop_collection()
        doc = Doc()
        await doc.save()

        doc = Doc.objects.first()
        assert doc._get_changed_fields() == []
        assert doc._delta() == ({}, {})

        doc.string_field = "hello"
        assert doc._get_changed_fields() == ["string_field"]
        assert doc._delta() == ({"string_field": "hello"}, {})

        doc._changed_fields = []
        doc.int_field = 1
        assert doc._get_changed_fields() == ["int_field"]
        assert doc._delta() == ({"int_field": 1}, {})

        doc._changed_fields = []
        dict_value = {"hello": "world", "ping": "pong"}
        doc.dict_field = dict_value
        assert doc._get_changed_fields() == ["dict_field"]
        assert doc._delta() == ({"dict_field": dict_value}, {})

        doc._changed_fields = []
        list_value = ["1", 2, {"hello": "world"}]
        doc.list_field = list_value
        assert doc._get_changed_fields() == ["list_field"]
        assert doc._delta() == ({"list_field": list_value}, {})

        # Test unsetting
        doc._changed_fields = []
        doc.dict_field = {}
        assert doc._get_changed_fields() == ["dict_field"]
        assert doc._delta() == ({}, {"dict_field": 1})

        doc._changed_fields = []
        doc.list_field = []
        assert doc._get_changed_fields() == ["list_field"]
        assert doc._delta() == ({}, {"list_field": 1})

    def test_delta_recursive(self):
        self.delta_recursive(AsyncDocument, EmbeddedDocument)
        self.delta_recursive(AsyncDynamicDocument, EmbeddedDocument)
        self.delta_recursive(AsyncDocument, DynamicEmbeddedDocument)
        self.delta_recursive(AsyncDynamicDocument, DynamicEmbeddedDocument)

    async def delta_recursive(self, DocClass, EmbeddedClass):
        class Embedded(EmbeddedClass):
            id = StringField()
            string_field = StringField()
            int_field = IntField()
            dict_field = DictField()
            list_field = ListField()

        class Doc(DocClass):
            string_field = StringField()
            int_field = IntField()
            dict_field = DictField()
            list_field = ListField()
            embedded_field = EmbeddedDocumentField(Embedded)

        await Doc.drop_collection()
        doc = Doc()
        await doc.save()

        doc = Doc.objects.first()
        assert doc._get_changed_fields() == []
        assert doc._delta() == ({}, {})

        embedded_1 = Embedded()
        embedded_1.id = "010101"
        embedded_1.string_field = "hello"
        embedded_1.int_field = 1
        embedded_1.dict_field = {"hello": "world"}
        embedded_1.list_field = ["1", 2, {"hello": "world"}]
        doc.embedded_field = embedded_1

        assert doc._get_changed_fields() == ["embedded_field"]

        embedded_delta = {
            "id": "010101",
            "string_field": "hello",
            "int_field": 1,
            "dict_field": {"hello": "world"},
            "list_field": ["1", 2, {"hello": "world"}],
        }
        assert doc.embedded_field._delta() == (embedded_delta, {})
        assert doc._delta() == ({"embedded_field": embedded_delta}, {})

        await doc.save()
        doc = doc.reload(10)

        doc.embedded_field.dict_field = {}
        assert doc._get_changed_fields() == ["embedded_field.dict_field"]
        assert doc.embedded_field._delta() == ({}, {"dict_field": 1})
        assert doc._delta() == ({}, {"embedded_field.dict_field": 1})
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.dict_field == {}

        doc.embedded_field.list_field = []
        assert doc._get_changed_fields() == ["embedded_field.list_field"]
        assert doc.embedded_field._delta() == ({}, {"list_field": 1})
        assert doc._delta() == ({}, {"embedded_field.list_field": 1})
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field == []

        embedded_2 = Embedded()
        embedded_2.string_field = "hello"
        embedded_2.int_field = 1
        embedded_2.dict_field = {"hello": "world"}
        embedded_2.list_field = ["1", 2, {"hello": "world"}]

        doc.embedded_field.list_field = ["1", 2, embedded_2]
        assert doc._get_changed_fields() == ["embedded_field.list_field"]

        assert doc.embedded_field._delta() == (
            {
                "list_field": [
                    "1",
                    2,
                    {
                        "_cls": "Embedded",
                        "string_field": "hello",
                        "dict_field": {"hello": "world"},
                        "int_field": 1,
                        "list_field": ["1", 2, {"hello": "world"}],
                    },
                ]
            },
            {},
        )

        assert doc._delta() == (
            {
                "embedded_field.list_field": [
                    "1",
                    2,
                    {
                        "_cls": "Embedded",
                        "string_field": "hello",
                        "dict_field": {"hello": "world"},
                        "int_field": 1,
                        "list_field": ["1", 2, {"hello": "world"}],
                    },
                ]
            },
            {},
        )
        await doc.save()
        doc = doc.reload(10)

        assert doc.embedded_field.list_field[0] == "1"
        assert doc.embedded_field.list_field[1] == 2
        for k in doc.embedded_field.list_field[2]._fields:
            assert doc.embedded_field.list_field[2][k] == embedded_2[k]

        doc.embedded_field.list_field[2].string_field = "world"
        assert doc._get_changed_fields() == ["embedded_field.list_field.2.string_field"]
        assert doc.embedded_field._delta() == (
            {"list_field.2.string_field": "world"},
            {},
        )
        assert doc._delta() == (
            {"embedded_field.list_field.2.string_field": "world"},
            {},
        )
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].string_field == "world"

        # Test multiple assignments
        doc.embedded_field.list_field[2].string_field = "hello world"
        doc.embedded_field.list_field[2] = doc.embedded_field.list_field[2]
        assert doc._get_changed_fields() == ["embedded_field.list_field.2"]
        assert doc.embedded_field._delta() == (
            {
                "list_field.2": {
                    "_cls": "Embedded",
                    "string_field": "hello world",
                    "int_field": 1,
                    "list_field": ["1", 2, {"hello": "world"}],
                    "dict_field": {"hello": "world"},
                }
            },
            {},
        )
        assert doc._delta() == (
            {
                "embedded_field.list_field.2": {
                    "_cls": "Embedded",
                    "string_field": "hello world",
                    "int_field": 1,
                    "list_field": ["1", 2, {"hello": "world"}],
                    "dict_field": {"hello": "world"},
                }
            },
            {},
        )
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].string_field == "hello world"

        # Test list native methods
        doc.embedded_field.list_field[2].list_field.pop(0)
        assert doc._delta() == (
            {"embedded_field.list_field.2.list_field": [2, {"hello": "world"}]},
            {},
        )
        await doc.save()
        doc = doc.reload(10)

        doc.embedded_field.list_field[2].list_field.append(1)
        assert doc._delta() == (
            {"embedded_field.list_field.2.list_field": [2, {"hello": "world"}, 1]},
            {},
        )
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].list_field == [2, {"hello": "world"}, 1]

        doc.embedded_field.list_field[2].list_field.sort(key=str)
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].list_field == [1, 2, {"hello": "world"}]

        del doc.embedded_field.list_field[2].list_field[2]["hello"]
        assert doc._delta() == (
            {},
            {"embedded_field.list_field.2.list_field.2.hello": 1},
        )
        await doc.save()
        doc = doc.reload(10)

        del doc.embedded_field.list_field[2].list_field
        assert doc._delta() == ({}, {"embedded_field.list_field.2.list_field": 1})

        await doc.save()
        doc = doc.reload(10)

        doc.dict_field["Embedded"] = embedded_1
        await doc.save()
        doc = doc.reload(10)

        doc.dict_field["Embedded"].string_field = "Hello World"
        assert doc._get_changed_fields() == ["dict_field.Embedded.string_field"]
        assert doc._delta() == ({"dict_field.Embedded.string_field": "Hello World"}, {})

    def test_circular_reference_deltas(self):
        self.circular_reference_deltas(AsyncDocument, AsyncDocument)
        self.circular_reference_deltas(AsyncDocument, AsyncDynamicDocument)
        self.circular_reference_deltas(AsyncDynamicDocument, AsyncDocument)
        self.circular_reference_deltas(AsyncDynamicDocument, AsyncDynamicDocument)

    async def circular_reference_deltas(self, DocClass1, DocClass2):
        class Person(DocClass1):
            name = StringField()
            owns = ListField(AsyncReferenceField("Organization"))

        class Organization(DocClass2):
            name = StringField()
            owner = AsyncReferenceField("Person")

        await Person.drop_collection()
        await Organization.drop_collection()

        person = await Person(name="owner").save()
        organization = await Organization(name="company").save()

        person.owns.append(organization)
        organization.owner = person

        await person.save()
        await organization.save()

        p = Person.objects[0].select_related()
        o = Organization.objects.first()
        assert p.owns[0] == o
        assert o.owner == p

    def test_circular_reference_deltas_2(self):
        self.circular_reference_deltas_2(AsyncDocument, AsyncDocument)
        self.circular_reference_deltas_2(AsyncDocument, AsyncDynamicDocument)
        self.circular_reference_deltas_2(AsyncDynamicDocument, AsyncDocument)
        self.circular_reference_deltas_2(AsyncDynamicDocument, AsyncDynamicDocument)

    async def circular_reference_deltas_2(self, DocClass1, DocClass2, dbref=True):
        class Person(DocClass1):
            name = StringField()
            owns = ListField(AsyncReferenceField("Organization", dbref=dbref))
            employer = AsyncReferenceField("Organization", dbref=dbref)

        class Organization(DocClass2):
            name = StringField()
            owner = AsyncReferenceField("Person", dbref=dbref)
            employees = ListField(AsyncReferenceField("Person", dbref=dbref))

        await Person.drop_collection()
        await Organization.drop_collection()

        person = await Person(name="owner").save()
        employee = await Person(name="employee").save()
        organization = await Organization(name="company").save()

        person.owns.append(organization)
        organization.owner = person

        organization.employees.append(employee)
        employee.employer = organization

        await person.save()
        await organization.save()
        await employee.save()

        p = Person.objects.get(name="owner")
        e = Person.objects.get(name="employee")
        o = Organization.objects.first()

        assert p.owns[0] == o
        assert o.owner == p
        assert e.employer == o

        return person, organization, employee

    def test_delta_db_field(self):
        self.delta_db_field(AsyncDocument)
        self.delta_db_field(AsyncDynamicDocument)

    async def delta_db_field(self, DocClass):
        class Doc(DocClass):
            string_field = StringField(db_field="db_string_field")
            int_field = IntField(db_field="db_int_field")
            dict_field = DictField(db_field="db_dict_field")
            list_field = ListField(db_field="db_list_field")

        await Doc.drop_collection()
        doc = Doc()
        await doc.save()

        doc = Doc.objects.first()
        assert doc._get_changed_fields() == []
        assert doc._delta() == ({}, {})

        doc.string_field = "hello"
        assert doc._get_changed_fields() == ["db_string_field"]
        assert doc._delta() == ({"db_string_field": "hello"}, {})

        doc._changed_fields = []
        doc.int_field = 1
        assert doc._get_changed_fields() == ["db_int_field"]
        assert doc._delta() == ({"db_int_field": 1}, {})

        doc._changed_fields = []
        dict_value = {"hello": "world", "ping": "pong"}
        doc.dict_field = dict_value
        assert doc._get_changed_fields() == ["db_dict_field"]
        assert doc._delta() == ({"db_dict_field": dict_value}, {})

        doc._changed_fields = []
        list_value = ["1", 2, {"hello": "world"}]
        doc.list_field = list_value
        assert doc._get_changed_fields() == ["db_list_field"]
        assert doc._delta() == ({"db_list_field": list_value}, {})

        # Test unsetting
        doc._changed_fields = []
        doc.dict_field = {}
        assert doc._get_changed_fields() == ["db_dict_field"]
        assert doc._delta() == ({}, {"db_dict_field": 1})

        doc._changed_fields = []
        doc.list_field = []
        assert doc._get_changed_fields() == ["db_list_field"]
        assert doc._delta() == ({}, {"db_list_field": 1})

        # Test it saves that data
        doc = Doc()
        await doc.save()

        doc.string_field = "hello"
        doc.int_field = 1
        doc.dict_field = {"hello": "world"}
        doc.list_field = ["1", 2, {"hello": "world"}]
        await doc.save()
        doc = doc.reload(10)

        assert doc.string_field == "hello"
        assert doc.int_field == 1
        assert doc.dict_field == {"hello": "world"}
        assert doc.list_field == ["1", 2, {"hello": "world"}]

    def test_delta_recursive_db_field_on_doc_and_embeddeddoc(self):
        self.delta_recursive_db_field(AsyncDocument, EmbeddedDocument)

    def test_delta_recursive_db_field_on_doc_and_dynamicembeddeddoc(self):
        self.delta_recursive_db_field(AsyncDocument, DynamicEmbeddedDocument)

    def test_delta_recursive_db_field_on_dynamicdoc_and_embeddeddoc(self):
        self.delta_recursive_db_field(AsyncDynamicDocument, EmbeddedDocument)

    def test_delta_recursive_db_field_on_dynamicdoc_and_dynamicembeddeddoc(self):
        self.delta_recursive_db_field(AsyncDynamicDocument, DynamicEmbeddedDocument)

    @staticmethod
    async def delta_recursive_db_field(DocClass, EmbeddedClass):
        class Embedded(EmbeddedClass):
            string_field = StringField(db_field="db_string_field")
            int_field = IntField(db_field="db_int_field")
            dict_field = DictField(db_field="db_dict_field")
            list_field = ListField(db_field="db_list_field")

        class Doc(DocClass):
            string_field = StringField(db_field="db_string_field")
            int_field = IntField(db_field="db_int_field")
            dict_field = DictField(db_field="db_dict_field")
            list_field = ListField(db_field="db_list_field")
            embedded_field = EmbeddedDocumentField(
                Embedded, db_field="db_embedded_field"
            )

        await Doc.drop_collection()
        doc = Doc()
        await doc.save()

        doc = Doc.objects.first()
        assert doc._get_changed_fields() == []
        assert doc._delta() == ({}, {})

        embedded_1 = Embedded()
        embedded_1.string_field = "hello"
        embedded_1.int_field = 1
        embedded_1.dict_field = {"hello": "world"}
        embedded_1.list_field = ["1", 2, {"hello": "world"}]
        doc.embedded_field = embedded_1

        assert doc._get_changed_fields() == ["db_embedded_field"]

        embedded_delta = {
            "db_string_field": "hello",
            "db_int_field": 1,
            "db_dict_field": {"hello": "world"},
            "db_list_field": ["1", 2, {"hello": "world"}],
        }
        assert doc.embedded_field._delta() == (embedded_delta, {})
        assert doc._delta() == ({"db_embedded_field": embedded_delta}, {})

        await doc.save()
        doc = doc.reload(10)

        doc.embedded_field.dict_field = {}
        assert doc._get_changed_fields() == ["db_embedded_field.db_dict_field"]
        assert doc.embedded_field._delta() == ({}, {"db_dict_field": 1})
        assert doc._delta() == ({}, {"db_embedded_field.db_dict_field": 1})
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.dict_field == {}

        assert doc._get_changed_fields() == []
        doc.embedded_field.list_field = []
        assert doc._get_changed_fields() == ["db_embedded_field.db_list_field"]
        assert doc.embedded_field._delta() == ({}, {"db_list_field": 1})
        assert doc._delta() == ({}, {"db_embedded_field.db_list_field": 1})
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field == []

        embedded_2 = Embedded()
        embedded_2.string_field = "hello"
        embedded_2.int_field = 1
        embedded_2.dict_field = {"hello": "world"}
        embedded_2.list_field = ["1", 2, {"hello": "world"}]

        doc.embedded_field.list_field = ["1", 2, embedded_2]
        assert doc._get_changed_fields() == ["db_embedded_field.db_list_field"]
        assert doc.embedded_field._delta() == (
            {
                "db_list_field": [
                    "1",
                    2,
                    {
                        "_cls": "Embedded",
                        "db_string_field": "hello",
                        "db_dict_field": {"hello": "world"},
                        "db_int_field": 1,
                        "db_list_field": ["1", 2, {"hello": "world"}],
                    },
                ]
            },
            {},
        )

        assert doc._delta() == (
            {
                "db_embedded_field.db_list_field": [
                    "1",
                    2,
                    {
                        "_cls": "Embedded",
                        "db_string_field": "hello",
                        "db_dict_field": {"hello": "world"},
                        "db_int_field": 1,
                        "db_list_field": ["1", 2, {"hello": "world"}],
                    },
                ]
            },
            {},
        )
        await doc.save()
        assert doc._get_changed_fields() == []
        doc = doc.reload(10)

        assert doc.embedded_field.list_field[0] == "1"
        assert doc.embedded_field.list_field[1] == 2
        for k in doc.embedded_field.list_field[2]._fields:
            assert doc.embedded_field.list_field[2][k] == embedded_2[k]

        doc.embedded_field.list_field[2].string_field = "world"
        assert doc._get_changed_fields() == [
            "db_embedded_field.db_list_field.2.db_string_field"
        ]
        assert doc.embedded_field._delta() == (
            {"db_list_field.2.db_string_field": "world"},
            {},
        )
        assert doc._delta() == (
            {"db_embedded_field.db_list_field.2.db_string_field": "world"},
            {},
        )
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].string_field == "world"

        # Test multiple assignments
        doc.embedded_field.list_field[2].string_field = "hello world"
        doc.embedded_field.list_field[2] = doc.embedded_field.list_field[2]
        assert doc._get_changed_fields() == ["db_embedded_field.db_list_field.2"]
        assert doc.embedded_field._delta() == (
            {
                "db_list_field.2": {
                    "_cls": "Embedded",
                    "db_string_field": "hello world",
                    "db_int_field": 1,
                    "db_list_field": ["1", 2, {"hello": "world"}],
                    "db_dict_field": {"hello": "world"},
                }
            },
            {},
        )
        assert doc._delta() == (
            {
                "db_embedded_field.db_list_field.2": {
                    "_cls": "Embedded",
                    "db_string_field": "hello world",
                    "db_int_field": 1,
                    "db_list_field": ["1", 2, {"hello": "world"}],
                    "db_dict_field": {"hello": "world"},
                }
            },
            {},
        )
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].string_field == "hello world"

        # Test list native methods
        doc.embedded_field.list_field[2].list_field.pop(0)
        assert doc._delta() == (
            {
                "db_embedded_field.db_list_field.2.db_list_field": [
                    2,
                    {"hello": "world"},
                ]
            },
            {},
        )
        await doc.save()
        doc = doc.reload(10)

        doc.embedded_field.list_field[2].list_field.append(1)
        assert doc._delta() == (
            {
                "db_embedded_field.db_list_field.2.db_list_field": [
                    2,
                    {"hello": "world"},
                    1,
                ]
            },
            {},
        )
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].list_field == [2, {"hello": "world"}, 1]

        doc.embedded_field.list_field[2].list_field.sort(key=str)
        await doc.save()
        doc = doc.reload(10)
        assert doc.embedded_field.list_field[2].list_field == [1, 2, {"hello": "world"}]

        del doc.embedded_field.list_field[2].list_field[2]["hello"]
        assert doc._delta() == (
            {},
            {"db_embedded_field.db_list_field.2.db_list_field.2.hello": 1},
        )
        await doc.save()
        doc = doc.reload(10)

        assert doc._delta() == (
            {},
            {},
        )
        del doc.embedded_field.list_field[2].list_field
        assert doc._delta() == (
            {},
            {"db_embedded_field.db_list_field.2.db_list_field": 1},
        )

    async def test_delta_for_dynamic_documents(self):
        class Person(AsyncDynamicDocument):
            name = StringField()
            meta = {"allow_inheritance": True}

        await Person.drop_collection()

        p = Person(name="James", age=34)
        assert p._delta() == (
            SON([("_cls", "Person"), ("name", "James"), ("age", 34)]),
            {},
        )

        p.doc = 123
        del p.doc
        assert p._delta() == (
            SON([("_cls", "Person"), ("name", "James"), ("age", 34)]),
            {},
        )

        p = Person()
        p.name = "Dean"
        p.age = 22
        await p.save()

        p.age = 24
        assert p.age == 24
        assert p._get_changed_fields() == ["age"]
        assert p._delta() == ({"age": 24}, {})

        p = Person.objects(age=22).get()
        p.age = 24
        assert p.age == 24
        assert p._get_changed_fields() == ["age"]
        assert p._delta() == ({"age": 24}, {})

        await p.save()
        assert 1 == Person.objects(age=24).count()

    async def test_dynamic_delta(self):
        class Doc(AsyncDynamicDocument):
            pass

        await Doc.drop_collection()
        doc = Doc()
        await doc.save()

        doc = Doc.objects.first()
        assert doc._get_changed_fields() == []
        assert doc._delta() == ({}, {})

        doc.string_field = "hello"
        assert doc._get_changed_fields() == ["string_field"]
        assert doc._delta() == ({"string_field": "hello"}, {})

        doc._changed_fields = []
        doc.int_field = 1
        assert doc._get_changed_fields() == ["int_field"]
        assert doc._delta() == ({"int_field": 1}, {})

        doc._changed_fields = []
        dict_value = {"hello": "world", "ping": "pong"}
        doc.dict_field = dict_value
        assert doc._get_changed_fields() == ["dict_field"]
        assert doc._delta() == ({"dict_field": dict_value}, {})

        doc._changed_fields = []
        list_value = ["1", 2, {"hello": "world"}]
        doc.list_field = list_value
        assert doc._get_changed_fields() == ["list_field"]
        assert doc._delta() == ({"list_field": list_value}, {})

        # Test unsetting
        doc._changed_fields = []
        doc.dict_field = {}
        assert doc._get_changed_fields() == ["dict_field"]
        assert doc._delta() == ({}, {"dict_field": 1})

        doc._changed_fields = []
        doc.list_field = []
        assert doc._get_changed_fields() == ["list_field"]
        assert doc._delta() == ({}, {"list_field": 1})

    async def test_delta_with_dbref_true(self):
        person, organization, employee = await self.circular_reference_deltas_2(
            AsyncDocument, AsyncDocument, True
        )
        employee.name = "test"

        assert organization._get_changed_fields() == []

        updates, removals = organization._delta()
        assert removals == {}
        assert updates == {}

        organization.employees.append(person)
        updates, removals = organization._delta()
        assert removals == {}
        assert "employees" in updates

    async def test_delta_with_dbref_false(self):
        person, organization, employee = await self.circular_reference_deltas_2(
            AsyncDocument, AsyncDocument, False
        )
        employee.name = "test"

        assert organization._get_changed_fields() == []

        updates, removals = organization._delta()
        assert removals == {}
        assert updates == {}

        organization.employees.append(person)
        updates, removals = organization._delta()
        assert removals == {}
        assert "employees" in updates

    async def test_nested_nested_fields_mark_as_changed(self):
        class EmbeddedDoc(EmbeddedDocument):
            name = StringField()

        class MyDoc(AsyncDocument):
            subs = MapField(MapField(EmbeddedDocumentField(EmbeddedDoc)))
            name = StringField()

        await MyDoc.drop_collection()

        await MyDoc(name="testcase1", subs={"a": {"b": EmbeddedDoc(name="foo")}}).save()

        mydoc = MyDoc.objects.first()
        subdoc = mydoc.subs["a"]["b"]
        subdoc.name = "bar"

        assert subdoc._get_changed_fields() == ["name"]
        assert mydoc._get_changed_fields() == ["subs.a.b.name"]

        mydoc._clear_changed_fields()
        assert mydoc._get_changed_fields() == []

    async def test_nested_nested_fields_db_field_set__gets_mark_as_changed_and_cleaned(
        self,
    ):
        class EmbeddedDoc(EmbeddedDocument):
            name = StringField(db_field="db_name")

        class MyDoc(AsyncDocument):
            embed = EmbeddedDocumentField(EmbeddedDoc, db_field="db_embed")
            name = StringField(db_field="db_name")

        await MyDoc.drop_collection()

        await MyDoc(name="testcase1", embed=EmbeddedDoc(name="foo")).save()

        mydoc = MyDoc.objects.first()
        mydoc.embed.name = "foo1"

        assert mydoc.embed._get_changed_fields() == ["db_name"]
        assert mydoc._get_changed_fields() == ["db_embed.db_name"]

        mydoc = MyDoc.objects.first()
        embed = EmbeddedDoc(name="foo2")
        embed.name = "bar"
        mydoc.embed = embed

        assert embed._get_changed_fields() == ["db_name"]
        assert mydoc._get_changed_fields() == ["db_embed"]

        mydoc._clear_changed_fields()
        assert mydoc._get_changed_fields() == []

    async def test_lower_level_mark_as_changed(self):
        class EmbeddedDoc(EmbeddedDocument):
            name = StringField()

        class MyDoc(AsyncDocument):
            subs = MapField(EmbeddedDocumentField(EmbeddedDoc))

        await MyDoc.drop_collection()

        await MyDoc().save()

        mydoc = MyDoc.objects.first()
        mydoc.subs["a"] = EmbeddedDoc()
        assert mydoc._get_changed_fields() == ["subs.a"]

        subdoc = mydoc.subs["a"]
        subdoc.name = "bar"

        assert subdoc._get_changed_fields() == ["name"]
        assert mydoc._get_changed_fields() == ["subs.a"]
        await mydoc.save()

        mydoc._clear_changed_fields()
        assert mydoc._get_changed_fields() == []

    async def test_upper_level_mark_as_changed(self):
        class EmbeddedDoc(EmbeddedDocument):
            name = StringField()

        class MyDoc(AsyncDocument):
            subs = MapField(EmbeddedDocumentField(EmbeddedDoc))

        await MyDoc.drop_collection()

        await MyDoc(subs={"a": EmbeddedDoc(name="foo")}).save()

        mydoc = MyDoc.objects.first()
        subdoc = mydoc.subs["a"]
        subdoc.name = "bar"

        assert subdoc._get_changed_fields() == ["name"]
        assert mydoc._get_changed_fields() == ["subs.a.name"]

        mydoc.subs["a"] = EmbeddedDoc()
        assert mydoc._get_changed_fields() == ["subs.a"]
        await mydoc.save()

        mydoc._clear_changed_fields()
        assert mydoc._get_changed_fields() == []

    async def test_referenced_object_changed_attributes(self):
        """Ensures that when you save a new reference to a field, the referenced object isn't altered"""

        class Organization(AsyncDocument):
            name = StringField()

        class User(AsyncDocument):
            name = StringField()
            org = AsyncReferenceField("Organization", required=True)

        await Organization.drop_collection()
        await User.drop_collection()

        org1 = Organization(name="Org 1")
        await org1.save()

        org2 = Organization(name="Org 2")
        await org2.save()

        user = User(name="Fred", org=org1)
        await user.save()

        await org1.reload()
        await org2.reload()
        await user.reload()
        assert org1.name == "Org 1"
        assert org2.name == "Org 2"
        assert user.name == "Fred"

        user.name = "Harold"
        user.org = org2

        org2.name = "New Org 2"
        assert org2.name == "New Org 2"

        await user.save()
        await org2.save()

        assert org2.name == "New Org 2"
        await org2.reload()
        assert org2.name == "New Org 2"

    async def test_delta_for_nested_map_fields(self):
        class UInfoDocument(AsyncDocument):
            phone = StringField()

        class EmbeddedRole(EmbeddedDocument):
            type = StringField()

        class EmbeddedUser(EmbeddedDocument):
            name = StringField()
            roles = MapField(field=EmbeddedDocumentField(EmbeddedRole))
            rolist = ListField(field=EmbeddedDocumentField(EmbeddedRole))
            info = AsyncReferenceField(UInfoDocument)

        class Doc(AsyncDocument):
            users = MapField(field=EmbeddedDocumentField(EmbeddedUser))
            num = IntField(default=-1)

        await Doc.drop_collection()

        doc = Doc(num=1)
        doc.users["007"] = EmbeddedUser(name="Agent007")
        await doc.save()

        uinfo = UInfoDocument(phone="79089269066")
        await uinfo.save()

        d = Doc.objects(num=1).first()
        d.users["007"]["roles"]["666"] = EmbeddedRole(type="superadmin")
        d.users["007"]["rolist"].append(EmbeddedRole(type="oops"))
        d.users["007"]["info"] = uinfo
        delta = d._delta()
        assert True == ("users.007.roles.666" in delta[0])
        assert True == ("users.007.rolist" in delta[0])
        assert True == ("users.007.info" in delta[0])
        assert "superadmin" == delta[0]["users.007.roles.666"]["type"]
        assert "oops" == delta[0]["users.007.rolist"][0]["type"]
        assert uinfo.id == delta[0]["users.007.info"]

    async def test_delta_on_dict(self):
        class MyDoc(AsyncDocument):
            dico = DictField()

        await MyDoc.drop_collection()

        await MyDoc(dico={"a": {"b": 0}}).save()

        mydoc = MyDoc.objects.first()
        assert mydoc._get_changed_fields() == []
        mydoc.dico["a"]["b"] = 0
        assert mydoc._get_changed_fields() == []
        mydoc.dico["a"] = {"b": 0}
        assert mydoc._get_changed_fields() == []
        mydoc.dico = {"a": {"b": 0}}
        assert mydoc._get_changed_fields() == []
        mydoc.dico["a"]["c"] = 1
        assert mydoc._get_changed_fields() == ["dico.a.c"]
        mydoc.dico["a"]["b"] = 2
        mydoc.dico["d"] = 3
        assert mydoc._get_changed_fields() == ["dico.a.c", "dico.a.b", "dico.d"]

        mydoc._clear_changed_fields()
        assert mydoc._get_changed_fields() == []

    async def test_delta_on_dict_empty_key_triggers_full_change(self):
        """more of a bug (harmless) but empty key changes aren't managed perfectly"""

        class MyDoc(AsyncDocument):
            dico = DictField()

        await MyDoc.drop_collection()

        await MyDoc(dico={"a": {"b": 0}}).save()

        mydoc = MyDoc.objects.first()
        assert mydoc._get_changed_fields() == []
        mydoc.dico[""] = 3
        assert mydoc._get_changed_fields() == ["dico"]
        await mydoc.save()
        raw_doc = get_as_pymongo(mydoc)
        assert raw_doc == {"_id": mydoc.id, "dico": {"": 3, "a": {"b": 0}}}


if __name__ == "__main__":
    unittest.main()
