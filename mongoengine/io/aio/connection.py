"""
Async connection management for MongoEngine.

This module provides async versions of connection functions using:
- AsyncMongoClient from PyMongo 4.0+ (native async support)
- contextvars for async-safe session management (instead of threading.local)
"""

import collections
import contextvars
import warnings

from pymongo import AsyncMongoClient, ReadPreference
from pymongo.common import _UUID_REPRESENTATIONS

try:
    from pymongo.database_shared import _check_name
except ImportError:
    from pymongo.database import _check_name

# DriverInfo was added in PyMongo 3.7.
try:
    from pymongo.driver_info import DriverInfo
except ImportError:
    DriverInfo = None

import mongoengine
from mongoengine.pymongo_support import PYMONGO_VERSION

__all__ = [
    "DEFAULT_CONNECTION_NAME",
    "DEFAULT_DATABASE_NAME",
    "ConnectionFailure",
    "async_connect",
    "async_disconnect",
    "async_disconnect_all",
    "async_get_connection",
    "async_get_db",
    "async_register_connection",
]


DEFAULT_CONNECTION_NAME = "default"
DEFAULT_DATABASE_NAME = "test"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 27017

_async_connection_settings = {}
_async_connections = {}
_async_dbs = {}


READ_PREFERENCE = ReadPreference.PRIMARY


class ConnectionFailure(Exception):
    """Error raised when the database connection can't be established or
    when a connection with a requested alias can't be retrieved.
    """

    pass


def _check_db_name(name):
    """Check if a database name is valid.
    This functionality is copied from pymongo Database class constructor.
    """
    if not isinstance(name, str):
        raise TypeError("name must be an instance of %s" % str)
    elif name != "$external":
        _check_name(name)


def _get_async_connection_settings(
    db=None,
    name=None,
    host=None,
    port=None,
    read_preference=READ_PREFERENCE,
    username=None,
    password=None,
    authentication_source=None,
    authentication_mechanism=None,
    authmechanismproperties=None,
    **kwargs,
):
    """Get the async connection settings as a dict.

    Same parameters as the sync version, but used for async connections.
    """
    conn_settings = {
        "name": name or db or DEFAULT_DATABASE_NAME,
        "host": host or DEFAULT_HOST,
        "port": port or DEFAULT_PORT,
        "read_preference": read_preference,
        "username": username,
        "password": password,
        "authentication_source": authentication_source,
        "authentication_mechanism": authentication_mechanism,
        "authmechanismproperties": authmechanismproperties,
    }

    # Handle URI-based connections
    if "://" in conn_settings["host"]:
        # It's a URI, remove individual host/port settings
        conn_settings.pop("port", None)
        if username:
            warnings.warn(
                "Setting username and password in connect() is deprecated when using a URI. "
                "Please include credentials in the URI string instead.",
                DeprecationWarning,
                stacklevel=3,
            )

    # Add MongoDB client class option
    conn_settings["mongo_client_class"] = kwargs.pop("mongo_client_class", AsyncMongoClient)

    # Deprecated options
    kwargs.pop("is_slave", None)

    keys = {
        key.lower() for key in kwargs.keys()
    }  # pymongo options are case insensitive
    if "uuidrepresentation" not in keys and "uuidrepresentation" not in conn_settings:
        warnings.warn(
            "No uuidRepresentation is specified! Falling back to "
            "'pythonLegacy' which is the default for pymongo 3.x. "
            "For compatibility with other MongoDB drivers this should be "
            "specified as 'standard' or '{java,csharp}Legacy' to work with "
            "older drivers in those languages. This will be changed to "
            "'unspecified' in a future release.",
            DeprecationWarning,
            stacklevel=3,
        )
        kwargs["uuidRepresentation"] = "pythonLegacy"

    conn_settings.update(kwargs)
    return conn_settings


def async_register_connection(
    alias,
    db=None,
    name=None,
    host=None,
    port=None,
    read_preference=READ_PREFERENCE,
    username=None,
    password=None,
    authentication_source=None,
    authentication_mechanism=None,
    authmechanismproperties=None,
    **kwargs,
):
    """Register the async connection settings.

    Same parameters as sync register_connection(), but stores settings for async connections.
    """
    conn_settings = _get_async_connection_settings(
        db=db,
        name=name,
        host=host,
        port=port,
        read_preference=read_preference,
        username=username,
        password=password,
        authentication_source=authentication_source,
        authentication_mechanism=authentication_mechanism,
        authmechanismproperties=authmechanismproperties,
        **kwargs,
    )
    _async_connection_settings[alias] = conn_settings


async def async_disconnect(alias=DEFAULT_CONNECTION_NAME):
    """Close the async connection with a given alias."""
    connection = _async_connections.pop(alias, None)
    if connection:
        # Close connection if this is the last reference to it
        if all(connection is not c for c in _async_connections.values()):
            # PyMongo 4.0+ AsyncMongoClient.close() is a coroutine
            await connection.close()

    if alias in _async_dbs:
        # Clear cached collections from all Document classes using this db
        try:
            from mongoengine.base.common import _get_documents_by_db
            for doc_cls in _get_documents_by_db(alias, DEFAULT_CONNECTION_NAME):
                # Clear the collection cache
                if hasattr(doc_cls, '_collection'):
                    doc_cls._collection = None
        except ImportError:
            pass

        del _async_dbs[alias]

    if alias in _async_connection_settings:
        del _async_connection_settings[alias]


async def async_disconnect_all():
    """Close all async connections."""
    for alias in list(_async_connections.keys()):
        await async_disconnect(alias)


async def async_get_connection(alias=DEFAULT_CONNECTION_NAME, reconnect=False):
    """Return an async connection with a given alias."""

    # Reconnect if requested
    if reconnect:
        await async_disconnect(alias)

    # Return existing connection if available
    if alias in _async_connections:
        return _async_connections[alias]

    # Validate that the alias exists
    if alias not in _async_connection_settings:
        if alias == DEFAULT_CONNECTION_NAME:
            msg = "You have not defined a default async connection"
        else:
            msg = 'Async connection with alias "%s" has not been defined' % alias
        raise ConnectionFailure(msg)

    def _clean_settings(settings_dict):
        if PYMONGO_VERSION < (4,):
            irrelevant_fields_set = {
                "name",
                "username",
                "password",
                "authentication_source",
                "authentication_mechanism",
                "authmechanismproperties",
            }
            rename_fields = {}
        else:
            irrelevant_fields_set = {"name"}
            rename_fields = {
                "authentication_source": "authSource",
                "authentication_mechanism": "authMechanism",
            }
        return {
            rename_fields.get(k, k): v
            for k, v in settings_dict.items()
            if k not in irrelevant_fields_set and v is not None
        }

    raw_conn_settings = _async_connection_settings[alias].copy()
    conn_settings = _clean_settings(raw_conn_settings)

    # Get the connection class (defaults to AsyncMongoClient from PyMongo 4.0+)
    mongo_client_class = conn_settings.pop("mongo_client_class", AsyncMongoClient)

    # Try to reuse existing connection with same settings
    for conn_alias, connection in _async_connections.items():
        conn_settings_cmp = _clean_settings(_async_connection_settings[conn_alias])
        conn_settings_cmp.pop("mongo_client_class", None)
        if conn_settings == conn_settings_cmp:
            _async_connections[alias] = connection
            return connection

    # Create new connection
    if DriverInfo:
        driver = DriverInfo("MongoEngine-Async", mongoengine.__version__)
        conn_settings.setdefault("driver", driver)

    try:
        connection = mongo_client_class(**conn_settings)
    except Exception as e:
        raise ConnectionFailure(f"Cannot connect to database {alias}: {e}")

    _async_connections[alias] = connection
    return connection


async def async_get_db(alias=DEFAULT_CONNECTION_NAME, reconnect=False):
    """Return an async database with a given alias."""
    if reconnect:
        await async_disconnect(alias)

    if alias not in _async_dbs:
        conn = await async_get_connection(alias)
        _async_dbs[alias] = conn[_async_connection_settings[alias]["name"]]

    return _async_dbs[alias]


async def async_connect(
    db=None,
    alias=DEFAULT_CONNECTION_NAME,
    **kwargs,
):
    """Connect to async MongoDB using PyMongo 4.0+ native async support.

    Usage:
        await async_connect('mydb')
        await async_connect('mydb', host='mongodb://localhost:27017/')
        await async_connect('mydb', host='localhost', port=27017)

    Returns:
        AsyncMongoClient instance (PyMongo 4.0+ native async)
    """
    async_register_connection(alias, db, **kwargs)
    return await async_get_connection(alias)


# ========================================================================
# Async-safe session management using contextvars
# ========================================================================

class _AsyncContextSessions:
    """Async-safe session management using contextvars."""

    def __init__(self):
        # Use ContextVar for async-safe storage
        self._sessions_var: contextvars.ContextVar = contextvars.ContextVar(
            'async_sessions',
            default=collections.deque()
        )

    def append(self, session):
        """Add a session to the current context."""
        sessions = self._sessions_var.get().copy()
        sessions.append(session)
        self._sessions_var.set(sessions)

    def get_current(self):
        """Get the current session from the context."""
        sessions = self._sessions_var.get()
        if len(sessions):
            return sessions[-1]
        return None

    def clear_current(self):
        """Remove the current session from the context."""
        sessions = self._sessions_var.get()
        if len(sessions):
            sessions = sessions.copy()
            sessions.pop()
            self._sessions_var.set(sessions)

    def clear_all(self):
        """Clear all sessions from the context."""
        self._sessions_var.set(collections.deque())


_async_context_sessions = _AsyncContextSessions()


def _set_async_session(session):
    """Set the current async session."""
    _async_context_sessions.append(session)


def _get_async_session():
    """Get the current async session."""
    return _async_context_sessions.get_current()


def _clear_async_session():
    """Clear the current async session."""
    return _async_context_sessions.clear_current()
