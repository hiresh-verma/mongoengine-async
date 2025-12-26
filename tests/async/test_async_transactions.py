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
    await async_connect("mongoenginetest_async", host="localhost", port=27017)

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
            host="localhost",
            port=27017,
        )

        # Connect to testdb2 database
        await async_connect(
            "mongoenginetest_async2",
            alias="testdb2",
            host="localhost",
            port=27017,
        )

        # Clean up collections in both databases
        from mongoengine.io.aio.connection import async_get_db

        db_default = await async_get_db(alias="default")
        await db_default["async_test_transaction_users"].delete_many({})

        db_testdb2 = await async_get_db(alias="testdb2")
        await db_testdb2["async_test_transaction_users"].delete_many({})
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


# Transaction Edge Cases


@pytest.mark.asyncio
async def test_nested_transactions(async_db):
    """Test nested transactions (should use same session).

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        async with async_run_in_transaction():
            user1 = AsyncUser(name="Outer", email="outer@example.com")
            await user1.save()

            # Nested transaction - uses same session
            async with async_run_in_transaction():
                user2 = AsyncUser(name="Inner", email="inner@example.com")
                await user2.save()

            # Both should be in same transaction
            count = await AsyncUser.objects.count()
            assert count == 2

        # Verify both committed
        users = await AsyncUser.objects.to_list()
        assert len(users) == 2
        assert {u.name for u in users} == {"Outer", "Inner"}
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_nested_transaction_rollback(async_db):
    """Test nested transaction rollback rolls back everything.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        with pytest.raises(ValueError):
            async with async_run_in_transaction():
                user1 = AsyncUser(name="Outer", email="outer@example.com")
                await user1.save()

                async with async_run_in_transaction():
                    user2 = AsyncUser(name="Inner", email="inner@example.com")
                    await user2.save()

                    # Raise error in inner transaction
                    raise ValueError("Inner error")

        # Both should be rolled back
        users = await AsyncUser.objects.to_list()
        assert len(users) == 0
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_with_validation_error(async_db):
    """Test transaction rollback on validation error.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        with pytest.raises(Exception):  # ValidationError
            async with async_run_in_transaction():
                user1 = AsyncUser(name="Valid", email="valid@example.com")
                await user1.save()

                # This should fail validation (missing required name)
                user2 = AsyncUser(email="invalid@example.com")
                await user2.save()

        # First user should be rolled back due to second save failing
        users = await AsyncUser.objects.to_list()
        assert len(users) == 0
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_sequential_transactions(async_db):
    """Test multiple sequential transactions.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        # First transaction
        async with async_run_in_transaction():
            user1 = AsyncUser(name="Transaction1", email="tx1@example.com")
            await user1.save()

        # Second transaction
        async with async_run_in_transaction():
            user2 = AsyncUser(name="Transaction2", email="tx2@example.com")
            await user2.save()

        # Third transaction
        async with async_run_in_transaction():
            user3 = AsyncUser(name="Transaction3", email="tx3@example.com")
            await user3.save()

        # All should be committed
        users = await AsyncUser.objects.to_list()
        assert len(users) == 3
        assert {u.name for u in users} == {
            "Transaction1",
            "Transaction2",
            "Transaction3",
        }
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_with_custom_session_kwargs(async_db):
    """Test transaction with custom session kwargs.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        # Use custom session options
        session_kwargs = {"causal_consistency": True}

        async with async_run_in_transaction(session_kwargs=session_kwargs):
            user = AsyncUser(name="CustomSession", email="custom@example.com")
            await user.save()

        # Verify saved
        users = await AsyncUser.objects.to_list()
        assert len(users) == 1
        assert users[0].name == "CustomSession"
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_bulk_operations(async_db):
    """Test transaction with bulk operations.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        async with async_run_in_transaction():
            # Create multiple users
            for i in range(10):
                user = AsyncUser(name=f"BulkUser{i}", email=f"bulk{i}@example.com")
                await user.save()

        # Verify all saved
        count = await AsyncUser.objects.count()
        assert count == 10
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_rollback_bulk_operations(async_db):
    """Test transaction rollback with bulk operations.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        with pytest.raises(ValueError):
            async with async_run_in_transaction():
                # Create multiple users
                for i in range(10):
                    user = AsyncUser(name=f"BulkUser{i}", email=f"bulk{i}@example.com")
                    await user.save()

                # Raise error after creating all
                raise ValueError("Rollback bulk")

        # All should be rolled back
        count = await AsyncUser.objects.count()
        assert count == 0
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


@pytest.mark.asyncio
async def test_transaction_mixed_operations(async_db):
    """Test transaction with mixed create, update, delete operations.

    Note: Requires MongoDB replica set or sharded cluster.
    """
    try:
        # Create some users outside transaction
        user1 = AsyncUser(name="PreExisting1", email="pre1@example.com", age=20)
        await user1.save()
        user2 = AsyncUser(name="PreExisting2", email="pre2@example.com", age=30)
        await user2.save()

        async with async_run_in_transaction():
            # Create new user
            new_user = AsyncUser(name="New", email="new@example.com")
            await new_user.save()

            # Update existing user
            user1_update = await AsyncUser.objects.get(pk=user1.pk)
            user1_update.age = 25
            await user1_update.save()

            # Delete existing user
            await AsyncUser.objects.filter(pk=user2.pk).delete()

        # Verify all operations committed
        users = await AsyncUser.objects.to_list()
        assert len(users) == 2  # user1 (updated) + new_user, user2 deleted

        names = {u.name for u in users}
        assert names == {"PreExisting1", "New"}

        # Verify update
        user1_final = await AsyncUser.objects.get(pk=user1.pk)
        assert user1_final.age == 25
    except OperationFailure as e:
        if "Transaction numbers are only allowed" in str(e):
            pytest.skip("Transactions require MongoDB replica set or sharded cluster")
        raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
