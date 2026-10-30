import asyncio

import pytest

from discord.ext.test.observations import Transcript


def test_snapshots_and_checkpoints_are_independent():
    transcript = Transcript(clock=lambda: 42.0)
    payload = {"embeds": [{"title": "before"}]}
    first = transcript.record("out", "message_created", payload)
    checkpoint = transcript.checkpoint()
    payload["embeds"][0]["title"] = "after"
    transcript.record("out", "message_edited", payload)
    assert first.payload["embeds"][0]["title"] == "before"
    assert first.timestamp == 42.0
    assert [item.kind for item in transcript.query(after=checkpoint)] == ["message_edited"]
    with pytest.raises(TypeError):
        first.payload["new"] = 1


@pytest.mark.asyncio
async def test_wait_is_bounded_and_does_not_consume_or_wait_for_other_tasks():
    transcript = Transcript()
    pending = asyncio.create_task(asyncio.Event().wait())
    waiter = asyncio.create_task(transcript.expect(lambda item: item.kind == "reply"))
    await asyncio.sleep(0)
    record = transcript.record("out", "reply", {"content": "ok"})
    assert await waiter is record
    assert transcript.query() == (record,)
    assert not pending.done()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(TimeoutError, match="recent observations"):
        await transcript.expect(lambda item: False, timeout=0.01)


@pytest.mark.asyncio
async def test_scoped_visibility_filters_and_bounded_no_output():
    transcript = Transcript()
    checkpoint = transcript.checkpoint()
    public = transcript.record('out', 'message_created', {
        'id': '1', 'channel_id': '10', 'author': {'id': '5'}, 'content': 'public'}, visibility='public')
    secret = transcript.record('out', 'message_created', {
        'id': '2', 'channel_id': '10', 'author': {'id': '5'}, 'content': 'secret'}, visibility='user:7')
    transcript.record('internal', 'callback_failure', {'interaction_id': '20'}, action_id=20)
    assert transcript.query(visible_to=8) == (public,)
    assert transcript.query(visible_to=7, channel_id=10, author_id=5, message_id=2) == (secret,)
    assert len(transcript.query(interaction_id=20)) == 1
    assert len(transcript.query(after=checkpoint, kind='message_created')) == 2
    await transcript.expect_none(lambda item: item.kind == 'reaction_added', after=checkpoint, timeout=0.01)
    with pytest.raises(AssertionError, match='Unexpected observation'):
        await transcript.expect_none(lambda item: item is secret, after=checkpoint, timeout=0.1)
    later = transcript.checkpoint()
    task = asyncio.create_task(transcript.expect_none(lambda item: item.kind == 'reply', after=later, timeout=1))
    await asyncio.sleep(0)
    transcript.record('out', 'reply', {})
    with pytest.raises(AssertionError, match='Unexpected observation'):
        await task
