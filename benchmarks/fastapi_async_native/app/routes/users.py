"""
User CRUD endpoints for async native benchmark.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from bson import ObjectId
from bson.errors import InvalidId

from app.models import user_repo, post_repo
from shared.models_schema import UserCreate, UserUpdate, UserResponse, PostResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(user_data: UserCreate):
    """Create a new user."""
    try:
        if await user_repo.find_by_username(user_data.username):
            raise HTTPException(status_code=400, detail="Username already exists")
        if await user_repo.find_by_email(user_data.email):
            raise HTTPException(status_code=400, detail="Email already exists")

        user_dict = user_data.model_dump()
        user_dict["login_count"] = 0
        user = await user_repo.create(user_dict)

        user["_id"] = str(user["_id"])
        return UserResponse(**user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    """Get user by ID."""
    try:
        user = await user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user["_id"] = str(user["_id"])
        return UserResponse(**user)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    email_filter: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List users with pagination and optional filtering."""
    try:
        filters = {}
        if email_filter:
            filters["email"] = {"$regex": email_filter, "$options": "i"}
        if is_active is not None:
            filters["is_active"] = is_active

        users = await user_repo.find_all(skip=skip, limit=limit, filters=filters)

        result = []
        for user in users:
            user["_id"] = str(user["_id"])
            result.append(UserResponse(**user))

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate):
    """Update user by ID."""
    try:
        # Check if user exists
        existing_user = await user_repo.find_by_id(user_id)
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update fields
        update_dict = user_data.model_dump(exclude_unset=True)
        user = await user_repo.update_one(user_id, update_dict)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user["_id"] = str(user["_id"])
        return UserResponse(**user)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{user_id}/increment-login", response_model=UserResponse)
async def increment_login_count(user_id: str):
    """Increment user's login count (atomic operation)."""
    try:
        user = await user_repo.increment_login(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user["_id"] = str(user["_id"])
        return UserResponse(**user)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: str):
    """Delete user by ID."""
    try:
        deleted = await user_repo.delete_one(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        return None
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/posts", response_model=List[PostResponse])
async def get_user_posts(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get all posts by a user."""
    try:
        # Verify user exists
        user = await user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        posts = await post_repo.find_by_author(user_id, skip=skip, limit=limit)

        result = []
        for post in posts:
            post["_id"] = str(post["_id"])
            post["author_id"] = str(post["author_id"])
            result.append(PostResponse(**post))

        return result
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
