"""
User CRUD endpoints for sync benchmark.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from bson import ObjectId
from bson.errors import InvalidId
from mongoengine.errors import NotUniqueError

from app.models import User, Post
from shared.models_schema import UserCreate, UserUpdate, UserResponse, PostResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
def create_user(user_data: UserCreate):
    """Create a new user."""
    try:
        user = User(**user_data.model_dump())
        user.save()

        user_dict = user.to_mongo().to_dict()
        user_dict["_id"] = str(user_dict["_id"])
        if user.address:
            user_dict["address"] = user.address.to_mongo().to_dict()

        return UserResponse(**user_dict)
    except NotUniqueError as e:
        error_msg = str(e).lower()
        if "username" in error_msg:
            raise HTTPException(status_code=409, detail="Username already exists")
        elif "email" in error_msg:
            raise HTTPException(status_code=409, detail="Email already exists")
        else:
            raise HTTPException(status_code=409, detail="Duplicate entry")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str):
    """Get user by ID."""
    try:
        user = User.objects(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_dict = user.to_mongo().to_dict()
        user_dict["_id"] = str(user_dict["_id"])
        if user.address:
            user_dict["address"] = user.address.to_mongo().to_dict()

        return UserResponse(**user_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[UserResponse])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    email_filter: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List users with pagination and optional filtering."""
    try:
        query = User.objects()

        if email_filter:
            query = query.filter(email__icontains=email_filter)
        if is_active is not None:
            query = query.filter(is_active=is_active)

        users = query.skip(skip).limit(limit)

        result = []
        for user in users:
            user_dict = user.to_mongo().to_dict()
            user_dict["_id"] = str(user_dict["_id"])
            if user.address:
                user_dict["address"] = user.address.to_mongo().to_dict()
            result.append(UserResponse(**user_dict))

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: str, user_data: UserUpdate):
    """Update user by ID."""
    try:
        user = User.objects(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update fields
        update_dict = user_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(user, key, value)

        user.save()

        user_dict = user.to_mongo().to_dict()
        user_dict["_id"] = str(user_dict["_id"])
        if user.address:
            user_dict["address"] = user.address.to_mongo().to_dict()

        return UserResponse(**user_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{user_id}/increment-login", response_model=UserResponse)
def increment_login_count(user_id: str):
    """Increment user's login count (atomic operation)."""
    try:
        user = User.objects(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Atomic increment
        user.update(inc__login_count=1)
        user.reload()

        user_dict = user.to_mongo().to_dict()
        user_dict["_id"] = str(user_dict["_id"])
        if user.address:
            user_dict["address"] = user.address.to_mongo().to_dict()

        return UserResponse(**user_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str):
    """Delete user by ID."""
    try:
        user = User.objects(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.delete()
        return None
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/posts", response_model=List[PostResponse])
def get_user_posts(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get all posts by a user."""
    try:
        user = User.objects(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        posts = Post.objects(author=user).skip(skip).limit(limit)

        result = []
        for post in posts:
            post_dict = post.to_mongo().to_dict()
            post_dict["_id"] = str(post_dict["_id"])
            post_dict["author_id"] = str(post.author.id)
            result.append(PostResponse(**post_dict))

        return result
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
