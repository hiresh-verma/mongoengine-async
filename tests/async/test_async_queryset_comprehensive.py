"""
Comprehensive async queryset tests ported from sync tests.
"""

import pytest
import pytest_asyncio
from bson import ObjectId
from mongoengine.fields import (
    StringField,
    IntField,
    ListField,
    DictField,
    BooleanField,
)
from mongoengine import DoesNotExist, MultipleObjectsReturned
from mongoengine.async_document import AsyncDocument
from mongoengine.io.aio.connection import async_connect, async_disconnect_all
from mongoengine.queryset import Q


class AsyncBlogPost(AsyncDocument):
    """Test blog post model."""

    title = StringField(required=True)
    content = StringField()
    author = StringField()
    published = BooleanField(default=False)
    views = IntField(default=0)
    tags = ListField(StringField())
    metadata = DictField()

    meta = {"collection": "async_test_blog_posts"}


@pytest_asyncio.fixture
async def async_db():
    """Set up async database connection."""
    await async_disconnect_all()
    await async_connect("mongoenginetest_async", host="localhost", port=27017)

    # Clean up collections
    try:
        db = await AsyncBlogPost._get_async_db()
        await db["async_test_blog_posts"].delete_many({})
    except Exception as e:
        print(e)

    yield

    await async_disconnect_all()


# Basic Query Operations


@pytest.mark.asyncio
async def test_filter(async_db):
    """Test filter operation."""
    await AsyncBlogPost(title="Post 1", author="Alice", published=True).save()
    await AsyncBlogPost(title="Post 2", author="Bob", published=False).save()
    await AsyncBlogPost(title="Post 3", author="Alice", published=True).save()

    # Filter by author
    posts = await AsyncBlogPost.objects.filter(author="Alice").to_list()
    assert len(posts) == 2

    # Filter by published
    published_posts = await AsyncBlogPost.objects.filter(published=True).to_list()
    assert len(published_posts) == 2


@pytest.mark.asyncio
async def test_exclude_with_ne(async_db):
    """Test exclude using __ne operator."""
    await AsyncBlogPost(title="Post 1", author="Alice", published=True).save()
    await AsyncBlogPost(title="Post 2", author="Bob", published=False).save()
    await AsyncBlogPost(title="Post 3", author="Charlie", published=True).save()

    # Exclude Bob's posts using __ne
    posts = await AsyncBlogPost.objects.filter(author__ne="Bob").to_list()
    assert len(posts) == 2
    assert all(p.author != "Bob" for p in posts)


@pytest.mark.asyncio
async def test_filter_chaining(async_db):
    """Test chaining multiple filters."""
    await AsyncBlogPost(title="Post 1", author="Alice", published=True, views=10).save()
    await AsyncBlogPost(title="Post 2", author="Alice", published=False, views=5).save()
    await AsyncBlogPost(title="Post 3", author="Bob", published=True, views=20).save()

    # Chain filters
    posts = (
        await AsyncBlogPost.objects.filter(author="Alice")
        .filter(published=True)
        .to_list()
    )
    assert len(posts) == 1
    assert posts[0].title == "Post 1"


@pytest.mark.asyncio
async def test_get_single_document(async_db):
    """Test get() returns single document."""
    post = await AsyncBlogPost(title="Unique Post", author="Alice").save()

    fetched = await AsyncBlogPost.objects.get(pk=post.pk)
    assert fetched.title == "Unique Post"


@pytest.mark.asyncio
async def test_get_does_not_exist(async_db):
    """Test get() raises DoesNotExist."""
    with pytest.raises(DoesNotExist):
        await AsyncBlogPost.objects.get(title="NonExistent")


@pytest.mark.asyncio
async def test_get_multiple_objects_returned(async_db):
    """Test get() raises MultipleObjectsReturned."""
    await AsyncBlogPost(title="Duplicate", author="Alice").save()
    await AsyncBlogPost(title="Duplicate", author="Bob").save()

    with pytest.raises(MultipleObjectsReturned):
        await AsyncBlogPost.objects.get(title="Duplicate")


@pytest.mark.asyncio
async def test_first(async_db):
    """Test first() returns first document."""
    await AsyncBlogPost(title="Post 1", views=10).save()
    await AsyncBlogPost(title="Post 2", views=20).save()

    # First without filter
    first = await AsyncBlogPost.objects.first()
    assert first is not None

    # First with filter
    first_high_views = await AsyncBlogPost.objects.filter(views__gte=15).first()
    assert first_high_views.title == "Post 2"


@pytest.mark.asyncio
async def test_first_empty_queryset(async_db):
    """Test first() on empty queryset returns None."""
    result = await AsyncBlogPost.objects.first()
    assert result is None


@pytest.mark.asyncio
async def test_count(async_db):
    """Test count() operation."""
    await AsyncBlogPost(title="Post 1").save()
    await AsyncBlogPost(title="Post 2").save()
    await AsyncBlogPost(title="Post 3").save()

    count = await AsyncBlogPost.objects.count()
    assert count == 3

    # Count with filter
    await AsyncBlogPost(title="Post 4", published=True).save()
    published_count = await AsyncBlogPost.objects.filter(published=True).count()
    assert published_count == 1


# Slicing and Pagination


@pytest.mark.asyncio
async def test_limit(async_db):
    """Test limit operation."""
    for i in range(10):
        await AsyncBlogPost(title=f"Post {i}").save()

    limited = await AsyncBlogPost.objects.limit(5).to_list()
    assert len(limited) == 5


@pytest.mark.asyncio
async def test_skip(async_db):
    """Test skip operation."""
    for i in range(10):
        await AsyncBlogPost(title=f"Post {i}", views=i).save()

    skipped = await AsyncBlogPost.objects.order_by("views").skip(5).to_list()
    assert len(skipped) == 5


@pytest.mark.asyncio
async def test_limit_and_skip(async_db):
    """Test combining limit and skip (pagination)."""
    for i in range(20):
        await AsyncBlogPost(title=f"Post {i}", views=i).save()

    # Page 2, 5 items per page
    page_2 = await AsyncBlogPost.objects.order_by("views").skip(5).limit(5).to_list()
    assert len(page_2) == 5
    assert page_2[0].views == 5


@pytest.mark.asyncio
async def test_slicing_with_skip_limit(async_db):
    """Test slicing using skip and limit."""
    for i in range(10):
        await AsyncBlogPost(title=f"Post {i}", views=i).save()

    # Get items 2-5 using skip(2).limit(3)
    sliced = await AsyncBlogPost.objects.order_by("views").skip(2).limit(3).to_list()
    assert len(sliced) == 3
    assert sliced[0].views == 2


# Ordering


@pytest.mark.asyncio
async def test_order_by_ascending(async_db):
    """Test ascending order."""
    await AsyncBlogPost(title="C", views=30).save()
    await AsyncBlogPost(title="A", views=10).save()
    await AsyncBlogPost(title="B", views=20).save()

    ordered = await AsyncBlogPost.objects.order_by("views").to_list()
    assert ordered[0].views == 10
    assert ordered[1].views == 20
    assert ordered[2].views == 30


@pytest.mark.asyncio
async def test_order_by_descending(async_db):
    """Test descending order."""
    await AsyncBlogPost(title="C", views=30).save()
    await AsyncBlogPost(title="A", views=10).save()
    await AsyncBlogPost(title="B", views=20).save()

    ordered = await AsyncBlogPost.objects.order_by("-views").to_list()
    assert ordered[0].views == 30
    assert ordered[1].views == 20
    assert ordered[2].views == 10


@pytest.mark.asyncio
async def test_order_by_multiple_fields(async_db):
    """Test ordering by multiple fields."""
    await AsyncBlogPost(title="Post", author="Alice", views=10).save()
    await AsyncBlogPost(title="Post", author="Alice", views=20).save()
    await AsyncBlogPost(title="Post", author="Bob", views=15).save()

    ordered = await AsyncBlogPost.objects.order_by("author", "-views").to_list()
    assert ordered[0].author == "Alice" and ordered[0].views == 20
    assert ordered[1].author == "Alice" and ordered[1].views == 10
    assert ordered[2].author == "Bob"


# Update Operations


@pytest.mark.asyncio
async def test_update_single_field(async_db):
    """Test updating single field."""
    await AsyncBlogPost(title="Old Title", views=10).save()
    await AsyncBlogPost(title="Old Title", views=20).save()

    count = await AsyncBlogPost.objects.filter(title="Old Title").update(
        title="New Title"
    )
    assert count == 2

    updated = await AsyncBlogPost.objects.to_list()
    assert all(p.title == "New Title" for p in updated)


@pytest.mark.asyncio
async def test_update_multiple_fields(async_db):
    """Test updating multiple fields."""
    post = await AsyncBlogPost(title="Post", published=False, views=0).save()

    await AsyncBlogPost.objects.filter(pk=post.pk).update(published=True, views=100)

    updated = await AsyncBlogPost.objects.get(pk=post.pk)
    assert updated.published is True
    assert updated.views == 100


@pytest.mark.asyncio
async def test_update_inc(async_db):
    """Test increment operation."""
    post = await AsyncBlogPost(title="Post", views=10).save()

    await AsyncBlogPost.objects.filter(pk=post.pk).update(inc__views=5)

    updated = await AsyncBlogPost.objects.get(pk=post.pk)
    assert updated.views == 15


@pytest.mark.asyncio
async def test_update_push(async_db):
    """Test push to list field."""
    post = await AsyncBlogPost(title="Post", tags=["tag1"]).save()

    await AsyncBlogPost.objects.filter(pk=post.pk).update(push__tags="tag2")

    updated = await AsyncBlogPost.objects.get(pk=post.pk)
    assert "tag2" in updated.tags
    assert len(updated.tags) == 2


@pytest.mark.asyncio
async def test_update_pull(async_db):
    """Test pull from list field."""
    post = await AsyncBlogPost(title="Post", tags=["tag1", "tag2", "tag3"]).save()

    await AsyncBlogPost.objects.filter(pk=post.pk).update(pull__tags="tag2")

    updated = await AsyncBlogPost.objects.get(pk=post.pk)
    assert "tag2" not in updated.tags
    assert len(updated.tags) == 2


@pytest.mark.asyncio
async def test_update_set_dict_field(async_db):
    """Test setting dictionary field."""
    post = await AsyncBlogPost(title="Post", metadata={}).save()

    await AsyncBlogPost.objects.filter(pk=post.pk).update(
        set__metadata={"key": "value"}
    )

    updated = await AsyncBlogPost.objects.get(pk=post.pk)
    assert updated.metadata == {"key": "value"}


@pytest.mark.asyncio
async def test_upsert(async_db):
    """Test upsert operation."""
    # First upsert creates document
    result = await AsyncBlogPost.objects.filter(title="Unique").update(
        upsert=True, set__views=10
    )
    assert result == 1

    # Verify created
    doc = await AsyncBlogPost.objects.get(title="Unique")
    assert doc.views == 10

    # Second upsert updates existing
    await AsyncBlogPost.objects.filter(title="Unique").update(
        upsert=True, set__views=20
    )

    updated = await AsyncBlogPost.objects.get(title="Unique")
    assert updated.views == 20


@pytest.mark.asyncio
async def test_modify(async_db):
    """Test modify operation (update and return)."""
    post = await AsyncBlogPost(title="Post", views=10).save()

    modified = await AsyncBlogPost.objects.filter(pk=post.pk).modify(
        set__views=20, new=True
    )

    assert modified is not None
    assert modified.views == 20


@pytest.mark.asyncio
async def test_modify_nonexistent(async_db):
    """Test modify on nonexistent document."""
    result = await AsyncBlogPost.objects.filter(pk=ObjectId()).modify(set__views=20)
    assert result is None


# Delete Operations


@pytest.mark.asyncio
async def test_delete_filtered(async_db):
    """Test deleting filtered documents."""
    await AsyncBlogPost(title="Keep", published=True).save()
    await AsyncBlogPost(title="Delete 1", published=False).save()
    await AsyncBlogPost(title="Delete 2", published=False).save()

    count = await AsyncBlogPost.objects.filter(published=False).delete()
    assert count == 2

    remaining = await AsyncBlogPost.objects.count()
    assert remaining == 1


@pytest.mark.asyncio
async def test_delete_all(async_db):
    """Test deleting all documents."""
    for i in range(5):
        await AsyncBlogPost(title=f"Post {i}").save()

    count = await AsyncBlogPost.objects.delete()
    assert count == 5

    remaining = await AsyncBlogPost.objects.count()
    assert remaining == 0


# Query Operators


@pytest.mark.asyncio
async def test_q_objects_or(async_db):
    """Test Q objects with OR."""
    await AsyncBlogPost(title="Post 1", author="Alice").save()
    await AsyncBlogPost(title="Post 2", author="Bob").save()
    await AsyncBlogPost(title="Post 3", author="Charlie").save()

    posts = await AsyncBlogPost.objects.filter(
        Q(author="Alice") | Q(author="Bob")
    ).to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_q_objects_and(async_db):
    """Test Q objects with AND."""
    await AsyncBlogPost(title="Post 1", author="Alice", published=True).save()
    await AsyncBlogPost(title="Post 2", author="Alice", published=False).save()
    await AsyncBlogPost(title="Post 3", author="Bob", published=True).save()

    posts = await AsyncBlogPost.objects.filter(
        Q(author="Alice") & Q(published=True)
    ).to_list()
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_filter_with_ne_operator(async_db):
    """Test filtering with not equal operator."""
    await AsyncBlogPost(title="Post 1", author="Alice").save()
    await AsyncBlogPost(title="Post 2", author="Bob").save()

    # Use __ne instead of ~Q() for NOT logic
    posts = await AsyncBlogPost.objects.filter(author__ne="Alice").to_list()
    assert len(posts) == 1
    assert posts[0].author == "Bob"


# Field Queries


@pytest.mark.asyncio
async def test_contains_query(async_db):
    """Test __contains query operator."""
    await AsyncBlogPost(title="Hello World").save()
    await AsyncBlogPost(title="Goodbye World").save()
    await AsyncBlogPost(title="Test Post").save()

    posts = await AsyncBlogPost.objects.filter(title__contains="World").to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_icontains_query(async_db):
    """Test case-insensitive contains."""
    await AsyncBlogPost(title="Hello WORLD").save()
    await AsyncBlogPost(title="Goodbye world").save()

    posts = await AsyncBlogPost.objects.filter(title__icontains="world").to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_startswith_query(async_db):
    """Test __startswith query operator."""
    await AsyncBlogPost(title="Post: News").save()
    await AsyncBlogPost(title="Post: Update").save()
    await AsyncBlogPost(title="Article: Tech").save()

    posts = await AsyncBlogPost.objects.filter(title__startswith="Post:").to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_endswith_query(async_db):
    """Test __endswith query operator."""
    await AsyncBlogPost(title="News Report").save()
    await AsyncBlogPost(title="Tech Report").save()
    await AsyncBlogPost(title="Daily Update").save()

    posts = await AsyncBlogPost.objects.filter(title__endswith="Report").to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_gt_query(async_db):
    """Test greater than query."""
    await AsyncBlogPost(title="Post 1", views=10).save()
    await AsyncBlogPost(title="Post 2", views=20).save()
    await AsyncBlogPost(title="Post 3", views=30).save()

    posts = await AsyncBlogPost.objects.filter(views__gt=15).to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_gte_query(async_db):
    """Test greater than or equal query."""
    await AsyncBlogPost(title="Post 1", views=10).save()
    await AsyncBlogPost(title="Post 2", views=20).save()
    await AsyncBlogPost(title="Post 3", views=30).save()

    posts = await AsyncBlogPost.objects.filter(views__gte=20).to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_lt_query(async_db):
    """Test less than query."""
    await AsyncBlogPost(title="Post 1", views=10).save()
    await AsyncBlogPost(title="Post 2", views=20).save()
    await AsyncBlogPost(title="Post 3", views=30).save()

    posts = await AsyncBlogPost.objects.filter(views__lt=25).to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_lte_query(async_db):
    """Test less than or equal query."""
    await AsyncBlogPost(title="Post 1", views=10).save()
    await AsyncBlogPost(title="Post 2", views=20).save()
    await AsyncBlogPost(title="Post 3", views=30).save()

    posts = await AsyncBlogPost.objects.filter(views__lte=20).to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_in_query(async_db):
    """Test __in query operator."""
    await AsyncBlogPost(title="Post", author="Alice").save()
    await AsyncBlogPost(title="Post", author="Bob").save()
    await AsyncBlogPost(title="Post", author="Charlie").save()

    posts = await AsyncBlogPost.objects.filter(author__in=["Alice", "Bob"]).to_list()
    assert len(posts) == 2


@pytest.mark.asyncio
async def test_nin_query(async_db):
    """Test __nin (not in) query operator."""
    await AsyncBlogPost(title="Post", author="Alice").save()
    await AsyncBlogPost(title="Post", author="Bob").save()
    await AsyncBlogPost(title="Post", author="Charlie").save()

    posts = await AsyncBlogPost.objects.filter(author__nin=["Alice", "Bob"]).to_list()
    assert len(posts) == 1
    assert posts[0].author == "Charlie"


@pytest.mark.asyncio
async def test_exists_query(async_db):
    """Test __exists query operator."""
    await AsyncBlogPost(title="Post", content="Some content").save()
    await AsyncBlogPost(title="Post").save()

    posts_with_content = await AsyncBlogPost.objects.filter(
        content__exists=True
    ).to_list()
    assert len(posts_with_content) == 1


# Bulk Operations


@pytest.mark.asyncio
async def test_bulk_insert(async_db):
    """Test bulk insert via save."""
    docs = [AsyncBlogPost(title=f"Post {i}", views=i) for i in range(10)]

    for doc in docs:
        await doc.save()

    count = await AsyncBlogPost.objects.count()
    assert count == 10


# Iteration


@pytest.mark.asyncio
async def test_async_iteration(async_db):
    """Test async for iteration."""
    for i in range(5):
        await AsyncBlogPost(title=f"Post {i}", views=i).save()

    collected = []
    async for post in AsyncBlogPost.objects.order_by("views"):
        collected.append(post.views)

    assert collected == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_to_list(async_db):
    """Test to_list() helper."""
    for i in range(5):
        await AsyncBlogPost(title=f"Post {i}").save()

    posts = await AsyncBlogPost.objects.to_list()
    assert len(posts) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
