Runtime
=======

The runtime tracks explicitly registered tasks, retains task exceptions and
cancels owned work with a bounded wait. Application tests should normally use
``session.create_task`` rather than interact with this internal class directly.

.. autoclass:: discord.ext.test.runtime.Runtime
   :members: track, create_task, pending, close
