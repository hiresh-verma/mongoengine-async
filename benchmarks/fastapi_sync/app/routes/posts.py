"""
Post CRUD endpoints for sync benchmark.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from bson.errors import InvalidId

from app.models import User, Post
from shared.models_schema import PostCreate, PostUpdate, PostResponse, UserResponse

router = APIRouter(prefix="/posts", tags=["posts"])


@router.post("", response_model=PostResponse, status_code=201)
def create_post(post_data: PostCreate):
    """Create a new post."""
    try:
        author = User.objects(id=post_data.author_id).first()
        if not author:
            raise HTTPException(status_code=404, detail="Author not found")

        post_dict = post_data.model_dump()
        author_id = post_dict.pop("author_id")
        post = Post(author=author, **post_dict)
        post.save()

        response_dict = post.to_mongo().to_dict()
        response_dict["_id"] = str(response_dict["_id"])
        response_dict["author_id"] = str(post.author.id)
        del response_dict["author"]

        return PostResponse(**response_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid author ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{post_id}", response_model=PostResponse)
def get_post(post_id: str, include_author: bool = False):
    """Get post by ID, optionally include author details."""
    try:
        post = Post.objects(id=post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        response_dict = post.to_mongo().to_dict()
        response_dict["_id"] = str(response_dict["_id"])
        response_dict["author_id"] = str(post.author.id)
        del response_dict["author"]

        if include_author:
            # Dereference author
            author_dict = post.author.to_mongo().to_dict()
            author_dict["_id"] = str(author_dict["_id"])
            if post.author.address:
                author_dict["address"] = post.author.address.to_mongo().to_dict()
            response_dict["author"] = UserResponse(**author_dict)

        return PostResponse(**response_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[PostResponse])
def list_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    author_id: Optional[str] = None,
    is_published: Optional[bool] = None,
):
    """List posts with pagination and filtering."""
    try:
        query = Post.objects()

        if author_id:
            author = User.objects(id=author_id).first()
            if not author:
                raise HTTPException(status_code=404, detail="Author not found")
            query = query.filter(author=author)

        if is_published is not None:
            query = query.filter(is_published=is_published)

        posts = query.skip(skip).limit(limit)

        result = []
        for post in posts:
            post_dict = post.to_mongo().to_dict()
            post_dict["_id"] = str(post_dict["_id"])
            post_dict["author_id"] = str(post.author.id)
            del post_dict["author"]
            result.append(PostResponse(**post_dict))

        return result
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{post_id}", response_model=PostResponse)
def update_post(post_id: str, post_data: PostUpdate):
    """Update post by ID."""
    try:
        post = Post.objects(id=post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Update fields
        update_dict = post_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(post, key, value)

        post.save()

        response_dict = post.to_mongo().to_dict()
        response_dict["_id"] = str(response_dict["_id"])
        response_dict["author_id"] = str(post.author.id)
        del response_dict["author"]

        return PostResponse(**response_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{post_id}/view", response_model=PostResponse)
def increment_view_count(post_id: str):
    """Increment post view count (atomic operation)."""
    try:
        post = Post.objects(id=post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Atomic increment
        post.update(inc__view_count=1)
        post.reload()

        response_dict = post.to_mongo().to_dict()
        response_dict["_id"] = str(response_dict["_id"])
        response_dict["author_id"] = str(post.author.id)
        del response_dict["author"]

        return PostResponse(**response_dict)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{post_id}", status_code=204)
def delete_post(post_id: str):
    """Delete post by ID."""
    try:
        post = Post.objects(id=post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        post.delete()
        return None
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
