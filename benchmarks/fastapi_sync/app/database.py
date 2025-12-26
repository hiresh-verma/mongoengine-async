"""
MongoDB connection management using MongoEngine (sync).
"""

import logging
from mongoengine import connect, disconnect
from app.config import settings

logger = logging.getLogger(__name__)


def init_db():
    """Initialize MongoDB connection with MongoEngine."""
    try:
        logger.info(f"Connecting to MongoDB at {settings.MONGODB_HOST}:{settings.MONGODB_PORT}")

        connection_params = {
            "db": settings.MONGODB_DB,
            "host": settings.MONGODB_HOST,
            "port": settings.MONGODB_PORT,
            "maxPoolSize": settings.MONGODB_MAX_POOL_SIZE,
            "minPoolSize": settings.MONGODB_MIN_POOL_SIZE,
            "serverSelectionTimeoutMS": settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
            "connectTimeoutMS": settings.MONGODB_CONNECT_TIMEOUT_MS,
        }

        if settings.MONGODB_USERNAME and settings.MONGODB_PASSWORD:
            connection_params["username"] = settings.MONGODB_USERNAME
            connection_params["password"] = settings.MONGODB_PASSWORD
            connection_params["authentication_source"] = "admin"

        connect(**connection_params)

        logger.info("Successfully connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


def close_db():
    """Close MongoDB connection."""
    try:
        disconnect()
        logger.info("MongoDB connection closed")
    except Exception as e:
        logger.error(f"Error closing MongoDB connection: {e}")


def get_db_stats():
    """Get database connection statistics."""
    from mongoengine import connection
    from pymongo import monitoring

    try:
        db = connection.get_db()
        stats = db.command("serverStatus")
        return {
            "connections": stats.get("connections", {}),
            "network": stats.get("network", {}),
        }
    except Exception as e:
        logger.error(f"Error getting DB stats: {e}")
        return {}
