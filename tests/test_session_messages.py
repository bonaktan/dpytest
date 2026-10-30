import io
import asyncio

import discord
import pytest

from discord.ext.test.session import Session


@pytest.mark.asyncio
async def test_real_channel_message_round_trip_and_snapshot_history():
    async with Session(lambda: discord.Client(intents=discord.Intents.none())) as session:
        channel = session.bot.get_partial_messageable(123)
        message = await channel.send("before")
        fetched = await channel.fetch_message(message.id)
        assert fetched.content == "before"
        edited = await message.edit(content="after")
        assert edited.id == message.id
        assert (await channel.fetch_message(message.id)).content == "after"
        assert session.transcript.query(kind="message_created")[0].payload["content"] == "before"
        await edited.delete()
        with pytest.raises(discord.NotFound):
            await channel.fetch_message(message.id)


@pytest.mark.asyncio
async def test_message_stores_are_isolated():
    async with Session(lambda: discord.Client(intents=discord.Intents.none())) as first:
        async with Session(lambda: discord.Client(intents=discord.Intents.none())) as second:
            message = await first.bot.get_partial_messageable(123).send("first")
            with pytest.raises(discord.NotFound):
                await second.bot.get_partial_messageable(123).fetch_message(message.id)
            assert not second.transcript.query(kind="message_created")


@pytest.mark.asyncio
async def test_file_round_trip_and_session_owned_storage():
    async with Session(lambda: discord.Client(intents=discord.Intents.none())) as session:
        channel = session.bot.get_partial_messageable(123)
        message = await channel.send('file', file=discord.File(io.BytesIO(b'hello'), filename='hello.txt'))
        attachment = message.attachments[0]
        assert attachment.filename == 'hello.txt'
        assert await attachment.read() == b'hello'
        fetched = await channel.fetch_message(message.id)
        assert await fetched.attachments[0].read() == b'hello'
        edited = await fetched.edit(attachments=[])
        assert edited.attachments == []
        with pytest.raises(discord.NotFound):
            await session.bot.http.get_from_cdn('https://example.com/unknown')
    assert not session.server.attachments


@pytest.mark.asyncio
async def test_bot_edit_and_delete_emit_gateway_events():
    async with Session(lambda: discord.Client(intents=discord.Intents.all())) as session:
        channel = session.bot.get_partial_messageable(123)
        message = await channel.send('before')
        edit_waiter = asyncio.create_task(session.bot.wait_for('message_edit', timeout=1))
        await asyncio.sleep(0)
        edited = await message.edit(content='after')
        before, after = await edit_waiter
        assert (before.content, after.content) == ('before', 'after')
        assert (await channel.fetch_message(message.id)).content == 'after'
        delete_waiter = asyncio.create_task(session.bot.wait_for('message_delete', timeout=1))
        await asyncio.sleep(0)
        await edited.delete()
        assert (await delete_waiter).id == message.id
        assert not session.bot.cached_messages
