Experimental session API
========================

``Session`` owns a fresh bot, a local server, observations, and tracked tasks.
The bot factory can be synchronous or asynchronous and must return an unstarted
client. The session initializes it without Discord login, calls ``setup_hook``
once, then marks it ready. An optional ``configure(session)`` callback runs
before ``setup_hook``. Application services remain the factory's responsibility.

The following example is run as part of the test suite. Numeric channel and user
IDs without a configured guild represent a simulated DM context.

.. literalinclude:: ../../tests/test_session_example.py
   :language: python

For guild-aware commands, create the guild, channel and members in the
``configure`` callback. Configuration runs before bot setup, so a bot's
``setup_hook`` can use the configured channels. Calling ``text_channel`` or
``member`` again with the same name returns the existing object.

.. literalinclude:: ../../tests/test_session_guild_example.py
   :language: python

Interaction conversation
------------------------

The next executable test sends a registered view, clicks its button, submits the
modal actually opened by that click, and checks the deferred original and
followup. No protocol payloads or private discord.py attributes are needed.

.. literalinclude:: ../../tests/test_actor_conversation.py
   :language: python

Waiting for reactions
---------------------

An action does not wait for a bot handler to become idle. This lets a test send
a second action while a handler is waiting. This example uses the fixture above,
which enables intents so discord.py can resolve the reacting user:

.. literalinclude:: ../../tests/test_session_example.py
   :language: python
   :pyobject: test_reaction_wait

``session.evict_message(message.id)`` removes the client cache projection while
leaving the server's message available for a fetch. Subsequent reaction inputs
can exercise discord.py's raw event path.

Expectations and visibility
---------------------------

Actions return once the input is dispatched. The returned interaction handle's
``expect_response``, ``expect_modal``, ``expect_deferred``, ``expect_original``,
``expect_followup``, and ``expect_choices`` methods wait for matching observations
with a real-time timeout. They do not consume transcript history or wait for all
bot tasks. ``expect_response`` means an initial message response;
``expect_original`` addresses the original response, including a deferred edit.

``session.transcript.checkpoint()`` records a position for later queries.
Unfiltered ``query`` is an administrative view, including ephemeral records;
pass ``visible_to=<user ID>`` to restrict results to public records and records
visible to that actor. ``expect_none(predicate, after=checkpoint, timeout=...)``
checks a bounded observation window, not all future execution. Register
application background coroutines with ``session.create_task`` so teardown can
cancel them and report failures. ``await session.expect_error(ExceptionType)``
acknowledges a deliberately expected callback error.

Current capability and migration status
---------------------------------------

The session API is experimental and does not replace the existing global
``configure``, message queue, or ``verify`` helpers. Existing tests can keep
using those helpers; new session tests should use actors and transcript queries.
The legacy helpers still use global state and do not select a session; calls to
them fail while multiple sessions overlap. Their queue assertions consume messages,
while transcript queries do not. A compatibility-session wrapper is still pending.

* Supported in the current tests: DM-like text messages and basic attachments;
  normal reactions; slash commands with primitive and actor-user options;
  grouped subcommands, autocomplete, user and message context menus; buttons,
  string selects and text-input modals; initial responses, deferred responses,
  original edits and followups. The server intentionally rejects operations it
  does not implement.
* Experimental guild setup is available through ``session.create_guild(name)``,
  ``guild.text_channel(name)`` and ``guild.member(name)``. Configuration may run
  from the session's ``configure`` callback before bot setup. Roles, permissions,
  cache-independent guild state and broad guild operations are incomplete.
* Incomplete: resolved role/channel and attachment options, entity selects,
  full reaction types, interaction error
  transitions and permissions, comprehensive callback diagnostics, and legacy
  compatibility sessions. The local simulator is not a complete Discord API.
  Guild roles currently grant broad permissions, so this setup is not suitable
  for testing Discord permission enforcement.
* Tested combinations are currently Python 3.14.7 with discord.py 2.7.1 and a
  2.8.0 development build. The project's broader declared Python and discord.py
  ranges have not yet been verified for this API.

The simulator clock can be supplied as ``Session(..., clock=callable)`` to
control interaction deadlines. It does not control arbitrary application clocks
or replace the real-time safety timeout used by expectations.
