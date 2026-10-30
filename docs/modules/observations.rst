Observations
============

Each session has a non-consuming transcript. ``checkpoint`` returns a position
that can be supplied as ``after`` to later queries. Unfiltered queries are
administrative and include private records; ``visible_to`` restricts results to
public records and records visible to that user. ``expect_none`` observes only
the specified bounded period and does not prove that an event can never occur.

.. autoclass:: discord.ext.test.observations.Observation
   :members:

.. autoclass:: discord.ext.test.observations.Transcript
   :members: checkpoint, record, query, expect, expect_none
