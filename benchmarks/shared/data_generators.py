"""
Test data generators for benchmark seeding.
"""

import random
import string
from datetime import datetime, timedelta
from typing import List, Dict, Any
from faker import Faker

fake = Faker()


def random_string(length: int = 10) -> str:
    """Generate a random string of specified length."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate_user_data(index: int = 0) -> Dict[str, Any]:
    """Generate realistic user data."""
    return {
        "username": f"user_{index}_{random_string(6)}",
        "email": f"user{index}_{random_string(4)}@example.com",
        "full_name": fake.name(),
        "age": random.randint(18, 80),
        "bio": fake.text(max_nb_chars=200),
        "address": {
            "street": fake.street_address(),
            "city": fake.city(),
            "state": fake.state(),
            "zip_code": fake.zipcode(),
            "country": "USA"
        },
        "tags": random.sample([
            "developer", "designer", "manager", "analyst", "writer",
            "artist", "musician", "photographer", "engineer", "scientist"
        ], k=random.randint(1, 4)),
        "metadata": {
            "source": "benchmark",
            "signup_method": random.choice(["email", "google", "github"]),
            "referral_code": random_string(8)
        },
        "is_active": random.choice([True, True, True, False]),  # 75% active
        "login_count": random.randint(0, 100)
    }


def generate_post_data(author_id: str, index: int = 0) -> Dict[str, Any]:
    """Generate realistic post data."""
    return {
        "title": fake.sentence(nb_words=6)[:-1],  # Remove trailing period
        "content": fake.text(max_nb_chars=1000),
        "author_id": author_id,
        "tags": random.sample([
            "python", "javascript", "mongodb", "fastapi", "async",
            "performance", "tutorial", "guide", "news", "announcement"
        ], k=random.randint(1, 4)),
        "view_count": random.randint(0, 1000),
        "like_count": random.randint(0, 100),
        "is_published": random.choice([True, True, False]),  # 66% published
        "metadata": {
            "source": "benchmark",
            "reading_time_minutes": random.randint(1, 15)
        }
    }


def generate_comment_data(post_id: str, author_id: str, parent_id: str = None) -> Dict[str, Any]:
    """Generate realistic comment data."""
    return {
        "post_id": post_id,
        "author_id": author_id,
        "content": fake.text(max_nb_chars=500),
        "parent_comment_id": parent_id
    }


def generate_analytics_event(user_id: str, event_type: str = None) -> Dict[str, Any]:
    """Generate realistic analytics event data."""
    if event_type is None:
        event_type = random.choice([
            "page_view", "click", "scroll", "form_submit",
            "search", "download", "share", "like"
        ])

    return {
        "user_id": user_id,
        "event_type": event_type,
        "event_data": {
            "browser": random.choice(["Chrome", "Firefox", "Safari", "Edge"]),
            "os": random.choice(["Windows", "macOS", "Linux", "iOS", "Android"]),
            "device_type": random.choice(["desktop", "mobile", "tablet"])
        },
        "session_id": random_string(16),
        "page_url": f"/{random.choice(['home', 'about', 'products', 'blog', 'contact'])}",
        "duration_ms": random.randint(100, 30000)
    }


def generate_batch_users(count: int, start_index: int = 0) -> List[Dict[str, Any]]:
    """Generate a batch of user data."""
    return [generate_user_data(start_index + i) for i in range(count)]


def generate_batch_posts(author_ids: List[str], posts_per_author: int = 5) -> List[Dict[str, Any]]:
    """Generate a batch of post data."""
    posts = []
    for i, author_id in enumerate(author_ids):
        for j in range(posts_per_author):
            posts.append(generate_post_data(author_id, i * posts_per_author + j))
    return posts


def generate_batch_analytics(user_ids: List[str], events_per_user: int = 10) -> List[Dict[str, Any]]:
    """Generate a batch of analytics events."""
    events = []
    for user_id in user_ids:
        for _ in range(events_per_user):
            events.append(generate_analytics_event(user_id))
    return events
