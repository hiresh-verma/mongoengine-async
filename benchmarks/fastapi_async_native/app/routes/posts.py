"""
Post CRUD endpoints for async native benchmark.
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
from shared.models_schema import PostCreate, PostUpdate, PostResponse, UserResponse

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=PostResponse, status_code=201)
async def create_post(post_data: PostCreate):
    """Create a new post."""
    try:
        author = await user_repo.find_by_id(post_data.author_id)
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")

        post_dict = post_data.model_dump()
        post_dict["view_count"] = 0
        post_dict["like_count"] = 0
        post = await post_repo.create(post_dict)

        post["_id"] = str(post["_id"])
        post["author_id"] = str(post["author"])
        del post["author"]
        return PostResponse(**post)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid author ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: str, include_author: bool = False):
    """Get post by ID, optionally include author details."""
    try:
        post = await post_repo.find_by_id(post_id, include_author=include_author)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        post["_id"] = str(post["_id"])
        post["author_id"] = str(post["author"])

        if include_author and "author_details" in post:
            post["author_details"]["_id"] = str(post["author_details"]["_id"])
            post["author"] = UserResponse(**post["author_details"])
            del post["author_details"]
        else:
            del post["author"]

        return PostResponse(**post)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[PostResponse])
async def list_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    author_id: Optional[str] = None,
    is_published: Optional[bool] = None,
):
    """List posts with pagination and filtering."""
    try:
        filters = {}
        if author_id:
            author = await user_repo.find_by_id(author_id)
            if not author:
                raise HTTPException(status_code=404, detail="Author not found")
            filters["author"] = ObjectId(author_id)

        if is_published is not None:
            filters["is_published"] = is_published

        posts = await post_repo.find_all(skip=skip, limit=limit, filters=filters)

        result = []
        for post in posts:
            post["_id"] = str(post["_id"])
            post["author_id"] = str(post.pop("author"))
            result.append(PostResponse(**post))

        return result
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    except HTTPException:
        raise
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"Missing required field: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing posts: {str(e)}")


@router.put("/{post_id}", response_model=PostResponse)
async def update_post(post_id: str, post_data: PostUpdate):
    """Update post by ID."""
    try:
        update_dict = post_data.model_dump(exclude_unset=True)
        post = await post_repo.update_one(post_id, update_dict)

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        post["_id"] = str(post["_id"])
        post["author_id"] = str(post["author"])
        del post["author"]
        return PostResponse(**post)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{post_id}/view", response_model=PostResponse)
async def increment_view_count(post_id: str):
    """Increment post view count (atomic operation)."""
    try:
        post = await post_repo.increment_view_count(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        post["_id"] = str(post["_id"])
        post["author_id"] = str(post["author"])
        del post["author"]
        return PostResponse(**post)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{post_id}", status_code=204)
async def delete_post(post_id: str):
    """Delete post by ID."""
    try:
        deleted = await post_repo.delete_one(post_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Post not found")
        return None
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
