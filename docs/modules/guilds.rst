Guild setup
===========

``session.create_guild(name)`` returns a setup object. ``text_channel(name)``
and ``member(name)`` create or return named entities. Configure them before
``setup_hook`` when the bot needs them at startup. This facility is experimental:
roles, permission enforcement and cache-independent guild state are incomplete.

.. autoclass:: discord.ext.test.guilds.GuildSetup
   :members: text_channel, member
   :undoc-members:
