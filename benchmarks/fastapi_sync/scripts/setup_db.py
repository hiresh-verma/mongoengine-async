#!/usr/bin/env python3
"""
Seed database with test data for benchmarking.
"""

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mongoengine import connect
from app.models import User, Post, Analytics
from shared.data_generators import (
    generate_user_data,
    generate_post_data,
    generate_analytics_event
)

def setup_database(num_users=1000, posts_per_user=5, events_per_user=10):
    """
    Seed database with test data.

    Args:
        num_users: Number of users to create
        posts_per_user: Number of posts per user
        events_per_user: Number of analytics events per user
    """
    print(f"Seeding database with {num_users} users...")

    # Connect to database
    connect(
        db="mongoengine_benchmark",
        host="localhost",
        port=27017
    )

    # Clear existing data
    print("Clearing existing data...")
    User.drop_collection()
    Post.drop_collection()
    Analytics.drop_collection()

    # Create users
    print(f"Creating {num_users} users...")
    created_users = []
    for i in range(num_users):
        user_data = generate_user_data(i)
        user = User(**user_data)
        user.save()
        created_users.append(user)

        if (i + 1) % 100 == 0:
            print(f"  Created {i + 1} users...")

    print(f"✓ Created {len(created_users)} users")

    # Create posts
    print(f"Creating {num_users * posts_per_user} posts...")
    created_posts = 0
    for i, user in enumerate(created_users):
        for j in range(posts_per_user):
            post_data = generate_post_data(str(user.id), i * posts_per_user + j)
            # Remove author_id since we're setting author directly
            post_data.pop('author_id', None)
            post = Post(author=user, **post_data)
            post.save()
            created_posts += 1

        if (i + 1) % 100 == 0:
            print(f"  Created {created_posts} posts...")

    print(f"✓ Created {created_posts} posts")

    # Create analytics events
    print(f"Creating {num_users * events_per_user} analytics events...")
    created_events = 0
    for i, user in enumerate(created_users):
        for j in range(events_per_user):
            event_data = generate_analytics_event(str(user.id))
            event = Analytics(**event_data)
            event.save()
            created_events += 1

        if (i + 1) % 100 == 0:
            print(f"  Created {created_events} events...")

    print(f"✓ Created {created_events} analytics events")

    # Print summary
    print("\n" + "="*60)
    print("Database seeding complete!")
    print("="*60)
    print(f"Users:     {User.objects.count():,}")
    print(f"Posts:     {Post.objects.count():,}")
    print(f"Analytics: {Analytics.objects.count():,}")
    print("="*60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed database with test data")
    parser.add_argument("--users", type=int, default=1000, help="Number of users")
    parser.add_argument("--posts-per-user", type=int, default=5, help="Posts per user")
    parser.add_argument("--events-per-user", type=int, default=10, help="Events per user")

    args = parser.parse_args()

    setup_database(
        num_users=args.users,
        posts_per_user=args.posts_per_user,
        events_per_user=args.events_per_user
    )
