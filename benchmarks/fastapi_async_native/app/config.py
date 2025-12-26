"""
Configuration settings for the async native benchmark FastAPI application.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # MongoDB Configuration
    MONGODB_HOST: str = "localhost"
    MONGODB_PORT: int = 27017
    MONGODB_DB: str = "mongoengine_benchmark"
    MONGODB_USERNAME: Optional[str] = None
    MONGODB_PASSWORD: Optional[str] = None
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_MIN_POOL_SIZE: int = 10
    MONGODB_CONNECT_TIMEOUT_MS: int = 5000
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000

    # FastAPI Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001  # Different port from sync
    DEBUG: bool = False
    API_TITLE: str = "PyMongo Async Native Benchmark"
    API_VERSION: str = "1.0.0"

    # Benchmark Configuration
    ENABLE_METRICS: bool = True
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
