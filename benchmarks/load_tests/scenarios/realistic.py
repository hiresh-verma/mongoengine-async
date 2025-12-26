"""
Realistic production workload scenario for Locust load testing.
This mimics real-world usage patterns with 70% reads and 30% writes.
"""

from locust import HttpUser, task, between, events
import random
import json

# Shared state for all users
existing_post_ids = []
existing_user_ids = []


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Fetch existing data at test start."""
    print("Fetching existing posts and users for realistic testing...")

    # Get some existing posts
    import requests
    try:
        response = requests.get(f"{environment.host}/posts?limit=100")
        if response.status_code == 200:
            posts = response.json()
            existing_post_ids.extend([p["_id"] for p in posts])
            print(f"Loaded {len(existing_post_ids)} existing posts")

        # Get some existing users
        response = requests.get(f"{environment.host}/users?limit=100")
        if response.status_code == 200:
            users = response.json()
            existing_user_ids.extend([u["_id"] for u in users])
            print(f"Loaded {len(existing_user_ids)} existing users")
    except Exception as e:
        print(f"Warning: Could not fetch existing data: {e}")
        print("Tests will still work but may have some 404s")


class RealisticUser(HttpUser):
    """
    Realistic user behavior for production-like benchmarking.

    Task weights represent percentage of requests:
    - 35% browse posts (read-heavy)
    - 20% view user profiles (read)
    - 15% create posts (write)
    - 15% update profile (write)
    - 10% increment views (atomic write)
    - 5% search/filter (read with query)
    """

    wait_time = between(0.5, 2.0)  # Realistic think time

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created_post_ids = []  # Track posts created by this user

    def on_start(self):
        """Initialize user session with a created user."""
        import time
        import uuid

        # Use timestamp + random + UUID to ensure uniqueness
        unique_id = f"{int(time.time()*1000)}_{random.randint(1, 999999)}_{uuid.uuid4().hex[:8]}"

        response = self.client.post("/users", json={
            "username": f"user_{unique_id}",
            "email": f"user_{unique_id}@example.com",
            "full_name": "Test User",
            "age": random.randint(18, 70),
            "bio": "Load test user",
            "tags": ["test", "benchmark"],
            "metadata": {"source": "locust"},
            "is_active": True
        }, name="/users (create)")

        if response.status_code == 201:
            self.user_data = response.json()
            self.user_id = self.user_data["_id"]
        else:
            self.user_id = None

    @task(35)
    def browse_posts(self):
        """Browse and view posts (most common operation)."""
        # List posts
        self.client.get("/posts", params={
            "skip": random.randint(0, 50),
            "limit": 20
        })

        # Occasionally view a specific post (use existing post IDs)
        if random.random() < 0.3 and (existing_post_ids or self.created_post_ids):
            # Prefer posts we created, fallback to existing posts
            if self.created_post_ids and random.random() < 0.5:
                post_id = random.choice(self.created_post_ids)
            elif existing_post_ids:
                post_id = random.choice(existing_post_ids)
            else:
                post_id = random.choice(self.created_post_ids)

            self.client.get(f"/posts/{post_id}")

    @task(20)
    def view_user_profile(self):
        """View user profiles."""
        if self.user_id:
            self.client.get(f"/users/{self.user_id}")

    @task(15)
    def create_post(self):
        """Create new content."""
        if self.user_id:
            response = self.client.post("/posts", json={
                "title": f"Test Post {random.randint(1, 9999)}",
                "content": "This is a test post created during load testing.",
                "author_id": self.user_id,
                "tags": ["test", "benchmark"],
                "is_published": random.choice([True, False]),
                "metadata": {"source": "locust"}
            })

            # Track created post IDs
            if response.status_code == 201:
                post_data = response.json()
                self.created_post_ids.append(post_data["_id"])

    @task(15)
    def update_profile(self):
        """Update user profile."""
        if self.user_id:
            self.client.put(f"/users/{self.user_id}", json={
                "bio": f"Updated bio at {random.randint(1, 9999)}",
                "tags": ["updated", "test"]
            })

    @task(10)
    def increment_view(self):
        """Increment view counts (atomic operation)."""
        # Use existing or created post IDs
        if self.created_post_ids:
            post_id = random.choice(self.created_post_ids)
        elif existing_post_ids:
            post_id = random.choice(existing_post_ids)
        else:
            return  # Skip if no posts available

        self.client.patch(f"/posts/{post_id}/view")

    @task(5)
    def search_users(self):
        """Search and filter users."""
        self.client.get("/users", params={
            "skip": 0,
            "limit": 50,
            "is_active": True
        })
