"""
I/O operations layer for mongoengine.

This module provides a clean abstraction over PyMongo I/O operations,
separating business logic from database I/O. Both sync and async
implementations share the same interface.
"""

from mongoengine.io.sync.operations import SyncIOOperations

__all__ = ['SyncIOOperations']
