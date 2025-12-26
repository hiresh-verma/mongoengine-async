"""
Health check and metrics endpoints.
"""

import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.models import user_repo, post_repo, analytics_repo

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        db = get_db()
        await db.command("ping")

        return {
            "status": "healthy",
            "database": "connected",
            "type": "async_native"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@router.get("/stats")
async def get_stats():
    """Get database and collection statistics."""
    try:
        db = get_db()

        # Get collection counts
        user_count = await user_repo.count()
        post_count = await post_repo.count()
        analytics_count = await analytics_repo.count()

        # Get database stats
        db_stats = await db.command("dbStats")

        # Get server status
        server_status = await db.command("serverStatus")

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
async def get_metrics():
    """Get application metrics."""
    try:
        return {
            "type": "async_native",
            "framework": "fastapi",
            "orm": "none",
            "driver": "pymongo native async (4.0+)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
