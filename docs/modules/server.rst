Message server
==============

The experimental session uses an in-memory message server for supported routes.
It stores messages, attachments and reaction membership independently of the
client message cache. This is an internal interface; actor actions and real
discord.py methods are the supported entry points for tests.

.. autoclass:: discord.ext.test.server.MessageServer
   :members: request
