"""
Batch operation endpoints for stress testing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from typing import List
from fastapi import APIRouter, HTTPException

from app.models import User, Post, Analytics
from shared.models_schema import (
    BatchUserCreate,
    BatchPostCreate,
    BatchAnalyticsCreate,
    UserResponse,
    PostResponse,
    AnalyticsResponse,
)

router = APIRouter(prefix="/batch", tags=["batch"])


@router.post("/users", status_code=201)
def batch_create_users(batch_data: BatchUserCreate):
    """Batch create users."""
    try:
        created_users = []

        for user_data in batch_data.users:
            if User.objects(username=user_data.username).first():
                continue

            user = User(**user_data.model_dump())
            user.save()

            user_dict = user.to_mongo().to_dict()
            user_dict["_id"] = str(user_dict["_id"])
            if user.address:
                user_dict["address"] = user.address.to_mongo().to_dict()

            created_users.append(UserResponse(**user_dict))

        return {
            "created": len(created_users),
            "total": len(batch_data.users),
            "users": created_users
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/posts", status_code=201)
def batch_create_posts(batch_data: BatchPostCreate):
    """Batch create posts."""
    try:
        created_posts = []

        for post_data in batch_data.posts:
            # Verify author exists
            author = User.objects(id=post_data.author_id).first()
            if not author:
                continue  # Skip if author doesn't exist

            post_dict = post_data.model_dump()
            author_id = post_dict.pop("author_id")
            post = Post(author=author, **post_dict)
            post.save()

            response_dict = post.to_mongo().to_dict()
            response_dict["_id"] = str(response_dict["_id"])
            response_dict["author_id"] = str(post.author.id)
            del response_dict["author"]

            created_posts.append(PostResponse(**response_dict))

        return {
            "created": len(created_posts),
            "total": len(batch_data.posts),
            "posts": created_posts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics", status_code=201)
def batch_create_analytics(batch_data: BatchAnalyticsCreate):
    """Batch create analytics events."""
    try:
        created_events = []

        for event_data in batch_data.events:
            event = Analytics(**event_data.model_dump())
            event.save()

            event_dict = event.to_mongo().to_dict()
            event_dict["_id"] = str(event_dict["_id"])

            created_events.append(AnalyticsResponse(**event_dict))

        return {
            "created": len(created_events),
            "total": len(batch_data.events),
            "events": created_events
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
