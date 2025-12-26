"""
Tests for async transactions and context managers.
"""

import pytest
import pytest_asyncio
from pymongo.errors import OperationFailure

from mongoengine.async_context_managers import (
    async_run_in_transaction,
    async_switch_db,
    async_switch_collection,
)
from mongoengine.async_document import AsyncDocument
from mongoengine.fields import StringField, IntField
from mongoengine.io.aio.connection import (
    async_connect,
    async_disconnect_all,
    async_register_connection,
)


class AsyncUser(AsyncDocument):
    """Test user model."""

    name = StringField(required=True)
    email = StringField()
    age = IntField()

    meta = {"collection": "async_test_transaction_users"}


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection.

    Note: Transactions require MongoDB replica set or sharded cluster.
    Tests will skip gracefully on standalone MongoDB.
    """
    await async_disconnect_all()
    await async_connect("mongoenginetest_async", host="localhost", port=27017, port=27017)

    # Clean up collections (both default and any alternate collections)
    try:
        db = await AsyncUser._get_async_db()
        # Clean default collection
        await db["async_test_transaction_users"].delete_many({})
        # Clean alternate collection used in tests
        await db["users_alt"].delete_many({})
    except Exception as e:
        print(e)

    yield

    await async_disconnect_all()


@pytest_asyncio.fixture
async def async_multi_db():
    """Set up multiple async database connections."""
    await async_disconnect_all()

    # Actually connect to both databases (not just register)
    try:
        # Connect to default database
        await async_connect(
            "mongoenginetest_async",
            alias="default",
            host="localhost", port=27017,
            port=27017,
        )

        # Connect to testdb2 database
        await async_connect(
            "mongoenginetest_async2",
            alias="testdb2",
            host="localhost", port=27017,
            port=27017,
        )

        # Clean up collections in default db
        db = await AsyncUser._get_async_db()
        await db["async_test_transaction_users"].delete_many({})
    except Exception as e:
        print(f"Setup error: {e}")

    yield

    await async_disconnect_all()


# Transaction Tests


@pytest.mark.asyncio
async def test_transaction_commit(async_db):
    """Test successful transaction commit.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        async with async_run_in_transaction():
            user1 = AsyncUser(name="Alice", email="alice@example.com")
            await user1.save()

            user2 = AsyncUser(name="Bob", email="bob@example.com")
            await user2.save()

        # Verify both users were saved
        users = await AsyncUser.objects.to_list()
        assert len(users) == 2
        assert {u.name for u in users} == {"Alice", "Bob"}
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_rollback(async_db):
    """Test transaction rollback on exception.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        with pytest.raises(ValueError):
            async with async_run_in_transaction():
                user1 = AsyncUser(name="Charlie", email="charlie@example.com")
                await user1.save()

                # Verify user exists within transaction
                count = await AsyncUser.objects.count()
                assert count == 1

                # Raise exception to trigger rollback
                raise ValueError("Test error")

        # Verify user was rolled back
        users = await AsyncUser.objects.to_list()
        assert len(users) == 0
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_update(async_db):
    """Test updates within transaction.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        # Create user outside transaction
        user = AsyncUser(name="David", email="david@example.com", age=25)
        await user.save()
        user_id = user.pk

        # Update in transaction
        async with async_run_in_transaction():
            user_to_update = await AsyncUser.objects.get(pk=user_id)
            user_to_update.age = 30
            await user_to_update.save()

        # Verify update persisted
        updated_user = await AsyncUser.objects.get(pk=user_id)
        assert updated_user.age == 30
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_delete(async_db):
    """Test deletes within transaction.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        # Create users outside transaction
        user1 = AsyncUser(name="Eve", email="eve@example.com")
        await user1.save()

        user2 = AsyncUser(name="Frank", email="frank@example.com")
        await user2.save()

        # Delete in transaction
        async with async_run_in_transaction():
            await AsyncUser.objects.filter(name="Eve").delete()

        # Verify only Eve was deleted
        users = await AsyncUser.objects.to_list()
        assert len(users) == 1
        assert users[0].name == "Frank"
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


# Switch DB Tests


@pytest.mark.asyncio
async def test_switch_db(async_multi_db):
    """Test switching database alias."""
    # Save to default db
    user1 = AsyncUser(name="Grace", email="grace@example.com")
    await user1.save()

    # Switch to testdb2 and save
    async with async_switch_db(AsyncUser, "testdb2"):
        user2 = AsyncUser(name="Henry", email="henry@example.com")
        await user2.save()

        # Verify user2 is in testdb2
        users_in_db2 = await AsyncUser.objects.to_list()
        assert len(users_in_db2) == 1
        assert users_in_db2[0].name == "Henry"

    # Back to default db - should only see user1
    users_in_default = await AsyncUser.objects.to_list()
    assert len(users_in_default) == 1
    assert users_in_default[0].name == "Grace"


@pytest.mark.asyncio
async def test_switch_db_restores_original(async_multi_db):
    """Test that switch_db properly restores original db alias."""
    original_alias = AsyncUser._meta.get("db_alias", "default")

    async with async_switch_db(AsyncUser, "testdb2"):
        assert AsyncUser._meta["db_alias"] == "testdb2"

    # Verify restored
    assert AsyncUser._meta.get("db_alias", "default") == original_alias


# Switch Collection Tests


@pytest.mark.asyncio
async def test_switch_collection(async_db):
    """Test switching collection name."""
    # Save to default collection
    user1 = AsyncUser(name="Ivan", email="ivan@example.com")
    await user1.save()

    # Switch to different collection and save
    async with async_switch_collection(AsyncUser, "users_alt"):
        user2 = AsyncUser(name="Jane", email="jane@example.com")
        await user2.save()

        # Verify user2 is in users_alt collection
        users_in_alt = await AsyncUser.objects.to_list()
        assert len(users_in_alt) == 1
        assert users_in_alt[0].name == "Jane"

    # Back to default collection - should only see user1
    users_in_default = await AsyncUser.objects.to_list()
    assert len(users_in_default) == 1
    assert users_in_default[0].name == "Ivan"


@pytest.mark.asyncio
async def test_switch_collection_restores_original(async_db):
    """Test that switch_collection properly restores original collection name."""
    original_collection = AsyncUser._meta.get("collection")

    async with async_switch_collection(AsyncUser, "users_temp"):
        assert AsyncUser._meta["collection"] == "users_temp"

    # Verify restored
    assert AsyncUser._meta.get("collection") == original_collection


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
