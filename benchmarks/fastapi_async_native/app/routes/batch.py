"""
Batch operation endpoints for stress testing.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from typing import List
from fastapi import APIRouter, HTTPException

from app.models import user_repo, post_repo, analytics_repo
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
async def batch_create_users(batch_data: BatchUserCreate):
    """Batch create users."""
    try:
        created_users = []

        for user_data in batch_data.users:
            if await user_repo.find_by_username(user_data.username):
                continue

            user_dict = user_data.model_dump()
            user_dict["login_count"] = 0
            user = await user_repo.create(user_dict)

            user["_id"] = str(user["_id"])
            created_users.append(UserResponse(**user))

        return {
            "created": len(created_users),
            "total": len(batch_data.users),
            "users": created_users
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/posts", status_code=201)
async def batch_create_posts(batch_data: BatchPostCreate):
    """Batch create posts."""
    try:
        created_posts = []

        for post_data in batch_data.posts:
            author = await user_repo.find_by_id(post_data.author_id)
            if not author:
                continue

            post_dict = post_data.model_dump()
            post_dict["view_count"] = 0
            post_dict["like_count"] = 0
            post = await post_repo.create(post_dict)

            post["_id"] = str(post["_id"])
            post["author_id"] = str(post["author"])
            del post["author"]
            created_posts.append(PostResponse(**post))

        return {
            "created": len(created_posts),
            "total": len(batch_data.posts),
            "posts": created_posts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analytics", status_code=201)
async def batch_create_analytics(batch_data: BatchAnalyticsCreate):
    """Batch create analytics events."""
    try:
        events_data = [event.model_dump() for event in batch_data.events]
        created_events = await analytics_repo.create_many(events_data)

        result = []
        for event in created_events:
            event["_id"] = str(event["_id"])
            result.append(AnalyticsResponse(**event))

        return {
            "created": len(result),
            "total": len(batch_data.events),
            "events": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
