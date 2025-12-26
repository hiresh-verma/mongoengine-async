"""
Shared Pydantic schemas for API requests and responses.
These are used across both sync and async benchmarks.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field


# Address schemas
class AddressSchema(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: str = "USA"


# User schemas
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)
    age: Optional[int] = Field(None, ge=0, le=150)
    bio: Optional[str] = Field(None, max_length=500)
    address: Optional[AddressSchema] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)
    age: Optional[int] = Field(None, ge=0, le=150)
    bio: Optional[str] = Field(None, max_length=500)
    address: Optional[AddressSchema] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: str = Field(alias="_id")
    username: str
    email: str
    full_name: Optional[str] = None
    age: Optional[int] = None
    bio: Optional[str] = None
    address: Optional[AddressSchema] = None
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    is_active: bool
    created_at: datetime
    updated_at: datetime
    login_count: int = 0

    class Config:
        populate_by_name = True
        from_attributes = True


# Post schemas
class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    author_id: str
    tags: List[str] = Field(default_factory=list)
    is_published: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    tags: Optional[List[str]] = None
    is_published: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class PostResponse(BaseModel):
    id: str = Field(alias="_id")
    title: str
    content: str
    author_id: str
    author: Optional[UserResponse] = None
    tags: List[str] = []
    view_count: int = 0
    like_count: int = 0
    is_published: bool
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True


# Comment schemas
class CommentCreate(BaseModel):
    post_id: str
    author_id: str
    content: str = Field(..., min_length=1, max_length=1000)
    parent_comment_id: Optional[str] = None


class CommentResponse(BaseModel):
    id: str = Field(alias="_id")
    post_id: str
    author_id: str
    content: str
    parent_comment_id: Optional[str] = None
    created_at: datetime

    class Config:
        populate_by_name = True
        from_attributes = True


# Analytics schemas
class AnalyticsEvent(BaseModel):
    user_id: str
    event_type: str
    event_data: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    page_url: Optional[str] = None
    duration_ms: Optional[int] = None


class AnalyticsResponse(BaseModel):
    id: str = Field(alias="_id")
    user_id: str
    event_type: str
    event_data: Dict[str, Any] = {}
    timestamp: datetime
    session_id: Optional[str] = None
    page_url: Optional[str] = None
    duration_ms: Optional[int] = None

    class Config:
        populate_by_name = True
        from_attributes = True


# Batch operation schemas
class BatchUserCreate(BaseModel):
    users: List[UserCreate]


class BatchPostCreate(BaseModel):
    posts: List[PostCreate]


class BatchAnalyticsCreate(BaseModel):
    events: List[AnalyticsEvent]
