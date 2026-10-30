Actors and interaction handles
==============================

Create actors with ``session.actor(id)`` or ``guild.member(name)``. Their async
actions dispatch input and return without waiting for all bot work. Handles are
bound to their session; message results expose immutable snapshots and
``visible_to(actor)``. The supported types and current gaps are listed in the
:doc:`session tutorial <../tutorials/session>`.

.. autoclass:: discord.ext.test.actors.Actor
   :members: message, edit_message, delete_message, slash, autocomplete, user_command, message_command, click, select, submit, react, remove_reaction
   :undoc-members:

.. autoclass:: discord.ext.test.actors.InteractionHandle
   :members: expect_response, expect_modal, expect_deferred, expect_original, expect_followup, expect_choices
   :undoc-members:

.. autoclass:: discord.ext.test.actors.MessageResult
   :members: id, channel_id, content, visible_to

.. autoclass:: discord.ext.test.actors.ModalResult
