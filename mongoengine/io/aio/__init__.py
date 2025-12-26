"""
Asynchronous I/O operations using PyMongo 4.0+ native async API.
"""

from mongoengine.io.aio.connection import (
    async_connect,
    async_disconnect,
    async_disconnect_all,
    async_get_connection,
    async_get_db,
    async_register_connection,
    _get_async_session,
    _set_async_session,
    _clear_async_session,
)
from mongoengine.io.aio.operations import AsyncIOOperations

__all__ = [
    'AsyncIOOperations',
    'async_connect',
    'async_disconnect',
    'async_disconnect_all',
    'async_get_connection',
    'async_get_db',
    'async_register_connection',
]
