Getting started
===============

Install dpytest in the environment used for your bot and tests::

    python -m pip install dpytest pytest pytest-asyncio

Import it as ``discord.ext.test``. A session creates a simulated Discord
environment without a token or Discord connection; it does not mock other
services used by your bot. Provide those dependencies in your bot factory or
fixtures. The experimental API requires a fresh, unstarted client for each session.

The :doc:`session tutorial <session>` contains executable DM and guild examples,
describes the async lifecycle, and lists current capabilities and limitations.
For fixture placement and running tests, continue with :doc:`using_pytest`.

Existing projects using the global ``configure`` and ``verify`` API can keep
using it. That API has a shared message queue; the session API has independent,
non-consuming transcripts. See :doc:`../modules/runner` and
:doc:`../modules/verify` for the legacy reference.
