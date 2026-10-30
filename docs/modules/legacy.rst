Legacy coordination
===================

The legacy helpers use a single global configuration and queue. Calls through
those helpers reject ambiguous use while more than one session is active. This
guard does not convert global helpers into session-scoped APIs; use actors and
the transcript for independent sessions.

.. autofunction:: discord.ext.test.legacy.require_unambiguous
