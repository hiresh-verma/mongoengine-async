"""
Middleware for metrics collection and request timing.
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to capture request timing and basic metrics.
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and collect metrics."""
        start_time = time.perf_counter()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.perf_counter() - start_time
        duration_ms = duration * 1000

        # Log request metrics
        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"duration={duration_ms:.2f}ms"
        )

        # Add custom headers
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}"

        return response
