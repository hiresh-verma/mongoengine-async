#!/usr/bin/env python3
"""
Clean up benchmark database.
"""

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mongoengine import connect
from app.models import User, Post, Analytics, Comment


def cleanup_database():
    """Drop all benchmark collections."""
    print("Cleaning up benchmark database...")

    # Connect to database
    connect(
        db="mongoengine_benchmark",
        host="localhost",
        port=27017
    )

    # Drop collections
    print("Dropping collections...")
    User.drop_collection()
    Post.drop_collection()
    Analytics.drop_collection()
    Comment.drop_collection()

    print("✓ Database cleaned up")


if __name__ == "__main__":
    cleanup_database()
