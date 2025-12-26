"""
Data access layer using PyMongo async.
Repository pattern for database operations.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId
from pymongo import ReturnDocument

from app.database import get_db


class UserRepository:
    """Repository for User collection operations."""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """Lazy-load collection when accessed."""
        if self._collection is None:
            self._collection = get_db().benchmark_users
        return self._collection

    async def create(self, user_data: dict) -> dict:
        """Create a new user."""
        user_data["created_at"] = datetime.utcnow()
        user_data["updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(user_data)
        user_data["_id"] = result.inserted_id
        return user_data

    async def find_by_id(self, user_id: str) -> Optional[dict]:
        """Find user by ID."""
        return await self.collection.find_one({"_id": ObjectId(user_id)})

    async def find_by_username(self, username: str) -> Optional[dict]:
        """Find user by username."""
        return await self.collection.find_one({"username": username})

    async def find_by_email(self, email: str) -> Optional[dict]:
        """Find user by email."""
        return await self.collection.find_one({"email": email})

    async def find_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None
    ) -> List[dict]:
        """Find all users with optional filters and pagination."""
        query = filters if filters else {}
        cursor = self.collection.find(query).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def update_one(self, user_id: str, update_data: dict) -> Optional[dict]:
        """Update user by ID."""
        update_data["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER
        )
        return result

    async def increment_login(self, user_id: str) -> Optional[dict]:
        """Increment user's login count atomically."""
        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {
                "$inc": {"login_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            },
            return_document=ReturnDocument.AFTER
        )
        return result

    async def delete_one(self, user_id: str) -> bool:
        """Delete user by ID."""
        result = await self.collection.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0

    async def count(self, filters: Optional[dict] = None) -> int:
        """Count users matching filters."""
        query = filters if filters else {}
        return await self.collection.count_documents(query)


class PostRepository:
    """Repository for Post collection operations."""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """Lazy-load collection when accessed."""
        if self._collection is None:
            self._collection = get_db().benchmark_posts
        return self._collection

    async def create(self, post_data: dict) -> dict:
        """Create a new post (stores as 'author' like MongoEngine)."""
        post_data["created_at"] = datetime.utcnow()
        post_data["updated_at"] = datetime.utcnow()

        if "author_id" in post_data:
            author_id = post_data.pop("author_id")
            if isinstance(author_id, str):
                post_data["author"] = ObjectId(author_id)
            else:
                post_data["author"] = author_id

        result = await self.collection.insert_one(post_data)
        post_data["_id"] = result.inserted_id
        return post_data

    async def find_by_id(self, post_id: str, include_author: bool = False) -> Optional[dict]:
        """Find post by ID, optionally with author details."""
        if include_author:
            pipeline = [
                {"$match": {"_id": ObjectId(post_id)}},
                {
                    "$lookup": {
                        "from": "benchmark_users",
                        "localField": "author",
                        "foreignField": "_id",
                        "as": "author_data"
                    }
                },
                {"$unwind": "$author_data"},
                {
                    "$addFields": {
                        "author_details": "$author_data"
                    }
                },
                {"$project": {"author_data": 0}}
            ]
            cursor = self.collection.aggregate(pipeline)
            results = await cursor.to_list(length=1)
            return results[0] if results else None
        else:
            return await self.collection.find_one({"_id": ObjectId(post_id)})

    async def find_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict] = None
    ) -> List[dict]:
        """Find all posts with optional filters and pagination."""
        query = filters if filters else {}
        cursor = self.collection.find(query).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def find_by_author(
        self,
        author_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[dict]:
        """Find posts by author ID."""
        author_oid = ObjectId(author_id)
        cursor = self.collection.find({"author": author_oid}).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def update_one(self, post_id: str, update_data: dict) -> Optional[dict]:
        """Update post by ID."""
        update_data["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(post_id)},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER
        )
        return result

    async def increment_view_count(self, post_id: str) -> Optional[dict]:
        """Increment post view count atomically."""
        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(post_id)},
            {
                "$inc": {"view_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            },
            return_document=ReturnDocument.AFTER
        )
        return result

    async def delete_one(self, post_id: str) -> bool:
        """Delete post by ID."""
        result = await self.collection.delete_one({"_id": ObjectId(post_id)})
        return result.deleted_count > 0

    async def count(self, filters: Optional[dict] = None) -> int:
        """Count posts matching filters."""
        query = filters if filters else {}
        return await self.collection.count_documents(query)


class AnalyticsRepository:
    """Repository for Analytics collection operations."""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """Lazy-load collection when accessed."""
        if self._collection is None:
            self._collection = get_db().benchmark_analytics
        return self._collection

    async def create(self, event_data: dict) -> dict:
        """Create a new analytics event."""
        event_data["timestamp"] = datetime.utcnow()

        result = await self.collection.insert_one(event_data)
        event_data["_id"] = result.inserted_id
        return event_data

    async def create_many(self, events_data: List[dict]) -> List[dict]:
        """Create multiple analytics events."""
        for event in events_data:
            event["timestamp"] = datetime.utcnow()

        result = await self.collection.insert_many(events_data)

        for i, inserted_id in enumerate(result.inserted_ids):
            events_data[i]["_id"] = inserted_id

        return events_data

    async def find_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[dict]:
        """Find analytics events by user ID."""
        cursor = self.collection.find(
            {"user_id": user_id}
        ).skip(skip).limit(limit).sort("timestamp", -1)
        return await cursor.to_list(length=limit)

    async def count(self, filters: Optional[dict] = None) -> int:
        """Count analytics events matching filters."""
        query = filters if filters else {}
        return await self.collection.count_documents(query)


user_repo = UserRepository()
post_repo = PostRepository()
analytics_repo = AnalyticsRepository()
