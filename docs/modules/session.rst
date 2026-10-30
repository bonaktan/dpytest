Session
=======

The experimental session owns one bot and its simulator state. Enter it in an
async context; the factory returns a fresh, unstarted client. ``configure`` runs
before ``setup_hook``. The session then marks the client ready without login.
Close cancels owned tasks, stops tracked views and releases attachment storage.

Use :meth:`~discord.ext.test.session.Session.actor` for actions,
:meth:`~discord.ext.test.session.Session.create_guild` for basic guild setup,
and :meth:`~discord.ext.test.session.Session.create_task` for application work
that should be cancelled and reported with the session. The ``clock`` callable
controls simulator deadlines; expectation timeouts use real time.

.. autoclass:: discord.ext.test.session.Session
   :members: actor, create_guild, guild, create_task, expect_error, evict_message, close
   :undoc-members:

.. autoexception:: discord.ext.test.session.UnsupportedOperation
