"""Coordination between legacy global helpers and independent sessions."""
from weakref import WeakSet


_active_sessions = WeakSet()


def register(session):
    _active_sessions.add(session)


def unregister(session):
    _active_sessions.discard(session)


def require_unambiguous():
    if len(_active_sessions) > 1:
        raise RuntimeError('Legacy global helpers cannot be used while multiple Sessions are active; '
                           'use the desired session\'s actors and transcript instead')
