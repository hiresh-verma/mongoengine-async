"""
MongoEngine document models for sync benchmark.
These models mirror realistic production usage patterns.
"""

from datetime import datetime
from mongoengine import (
    Document,
    EmbeddedDocument,
    StringField,
    IntField,
    EmailField,
    DateTimeField,
    ListField,
    ReferenceField,
    EmbeddedDocumentField,
    DictField,
    BooleanField,
)


class Address(EmbeddedDocument):
    """Embedded document for testing nested structures."""
    street = StringField(max_length=200)
    city = StringField(max_length=100)
    state = StringField(max_length=50)
    zip_code = StringField(max_length=20)
    country = StringField(max_length=50, default="USA")


class User(Document):
    """Primary document for testing - represents a typical user entity."""
    meta = {
        'collection': 'benchmark_users',
        'indexes': [
            'email',
            'username',
            'created_at',
            ('username', 'email'),  # Compound index
            'is_active'
        ]
    }

    username = StringField(required=True, unique=True, max_length=50)
    email = EmailField(required=True, unique=True)
    full_name = StringField(max_length=100)
    age = IntField(min_value=0, max_value=150)
    bio = StringField(max_length=500)
    address = EmbeddedDocumentField(Address)
    tags = ListField(StringField(max_length=50))
    metadata = DictField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)
    login_count = IntField(default=0)

    def save(self, *args, **kwargs):
        """Override save to update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)


class Post(Document):
    """Secondary document for testing references and relationships."""
    meta = {
        'collection': 'benchmark_posts',
        'indexes': [
            'author',
            'created_at',
            'is_published',
            ('author', '-created_at'),
            'tags'
        ]
    }

    title = StringField(required=True, max_length=200)
    content = StringField(required=True)
    author = ReferenceField(User, required=True)
    tags = ListField(StringField(max_length=50))
    view_count = IntField(default=0)
    like_count = IntField(default=0)
    is_published = BooleanField(default=False)
    metadata = DictField()
    created_at = DateTimeField(default=datetime.utcnow)
    updated_at = DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        """Override save to update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        return super().save(*args, **kwargs)


class Comment(Document):
    """Tertiary document for complex queries and nested relationships."""
    meta = {
        'collection': 'benchmark_comments',
        'indexes': [
            'post',
            'author',
            'created_at',
            ('post', '-created_at')
        ]
    }

    post = ReferenceField(Post, required=True)
    author = ReferenceField(User, required=True)
    content = StringField(required=True, max_length=1000)
    parent_comment = ReferenceField('self')  # For nested comments
    created_at = DateTimeField(default=datetime.utcnow)


class Analytics(Document):
    """Document for write-heavy scenarios and event tracking."""
    meta = {
        'collection': 'benchmark_analytics',
        'indexes': [
            'event_type',
            'timestamp',
            ('user_id', '-timestamp'),
            'user_id'
        ]
    }

    user_id = StringField(required=True)
    event_type = StringField(required=True)
    event_data = DictField()
    timestamp = DateTimeField(default=datetime.utcnow)
    session_id = StringField()
    page_url = StringField()
    duration_ms = IntField()
