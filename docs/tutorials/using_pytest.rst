Using pytest
============

Install ``pytest`` and ``pytest-asyncio``, put test modules in ``tests/``, and
run::

    python -m pytest tests/

Async tests use ``@pytest.mark.asyncio``. An async fixture can create a fresh bot
and yield a session; exiting the fixture closes it. This complete example is
also run by the project's test suite:

.. literalinclude:: ../../tests/test_session_example.py
   :language: python

Place a shared fixture in ``tests/conftest.py`` to use it in other test modules.
Keep external service fakes and configuration in the bot factory or separate
fixtures. A session does not control arbitrary application clocks or network
dependencies. See :doc:`session` for guild setup, actions, expectations,
visibility, and the experimental API's current limits.

Troubleshooting
---------------

* If pytest cannot find a fixture, check the name of the test argument and the
  location of ``conftest.py``.
* If an expectation times out, inspect its action ID, recent observations,
  callback errors and pending owned tasks. Register application background tasks
  with ``session.create_task`` and acknowledge deliberate failures with
  ``session.expect_error``.
* Legacy ``verify().message()`` consumes the global sent queue. Use its peek
  option to leave an item queued, or use a session transcript for non-consuming
  observations. Legacy helpers cannot be used while multiple sessions overlap.
