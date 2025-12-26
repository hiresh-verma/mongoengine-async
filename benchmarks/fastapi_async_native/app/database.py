"""
MongoDB connection management using PyMongo native async (AsyncMongoClient).
"""

import logging
from pymongo import AsyncMongoClient
from pymongo.errors import ConnectionFailure

from app.config import settings

logger = logging.getLogger(__name__)

# Global database instances
client = None
db = None


async def init_db():
    """Initialize MongoDB async connection."""
    global client, db

    try:
        logger.info(f"Connecting to MongoDB at {settings.MONGODB_HOST}:{settings.MONGODB_PORT}")

        # Create async MongoDB client using PyMongo's native async support
        connection_string = f"mongodb://{settings.MONGODB_HOST}:{settings.MONGODB_PORT}"

        if settings.MONGODB_USERNAME and settings.MONGODB_PASSWORD:
            connection_string = (
                f"mongodb://{settings.MONGODB_USERNAME}:{settings.MONGODB_PASSWORD}@"
                f"{settings.MONGODB_HOST}:{settings.MONGODB_PORT}"
            )

        # PyMongo 4.0+ native async client
        client = AsyncMongoClient(
            connection_string,
            maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
            minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
        )

        db = client[settings.MONGODB_DB]

        # Test connection
        await client.admin.command("ping")

        # Create indexes
        await create_indexes()

        logger.info("Successfully connected to MongoDB (async)")
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during MongoDB connection: {e}")
        raise


async def create_indexes():
    """Create database indexes."""
    try:
        # User indexes
        await db.benchmark_users.create_index("email", unique=True)
        await db.benchmark_users.create_index("username", unique=True)
        await db.benchmark_users.create_index("created_at")
        await db.benchmark_users.create_index([("username", 1), ("email", 1)])
        await db.benchmark_users.create_index("is_active")

        # Post indexes
        await db.benchmark_posts.create_index("author_id")
        await db.benchmark_posts.create_index("created_at")
        await db.benchmark_posts.create_index("is_published")
        await db.benchmark_posts.create_index([("author_id", 1), ("created_at", -1)])
        await db.benchmark_posts.create_index("tags")

        # Comment indexes
        await db.benchmark_comments.create_index("post_id")
        await db.benchmark_comments.create_index("author_id")
        await db.benchmark_comments.create_index("created_at")
        await db.benchmark_comments.create_index([("post_id", 1), ("created_at", -1)])

        # Analytics indexes
        await db.benchmark_analytics.create_index("event_type")
        await db.benchmark_analytics.create_index("timestamp")
        await db.benchmark_analytics.create_index([("user_id", 1), ("timestamp", -1)])
        await db.benchmark_analytics.create_index("user_id")

        logger.info("Database indexes created successfully")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise


async def close_db():
    """Close MongoDB async connection."""
    global client

    if client:
        client.close()
        logger.info("MongoDB connection closed")


def get_db():
    """Get database instance."""
    if db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db
