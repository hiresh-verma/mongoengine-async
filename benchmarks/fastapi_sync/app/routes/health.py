"""
Health check and metrics endpoints.
"""

import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from mongoengine import connection

from app.models import User, Post, Analytics

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        db = connection.get_db()
        db.command("ping")

        return {
            "status": "healthy",
            "database": "connected",
            "type": "sync"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@router.get("/stats")
def get_stats():
    """Get database and collection statistics."""
    try:
        db = connection.get_db()

        # Get collection counts
        user_count = User.objects.count()
        post_count = Post.objects.count()
        analytics_count = Analytics.objects.count()

        # Get database stats
        db_stats = db.command("dbStats")

        # Get server status (connection pool info)
        server_status = db.command("serverStatus")

        return {
            "collections": {
                "users": user_count,
                "posts": post_count,
                "analytics": analytics_count,
            },
            "database": {
                "name": db.name,
                "size_bytes": db_stats.get("dataSize", 0),
                "storage_size_bytes": db_stats.get("storageSize", 0),
                "index_size_bytes": db_stats.get("indexSize", 0),
                "collections": db_stats.get("collections", 0),
            },
            "connections": server_status.get("connections", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
def get_metrics():
    """Get application metrics."""
    try:
        return {
            "type": "sync",
            "framework": "fastapi",
            "orm": "mongoengine",
            "driver": "pymongo"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
