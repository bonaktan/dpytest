import asyncio

import discord
import pytest
from discord.ext import commands

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_actor_message_dispatches_real_prefix_command():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

        @bot.command()
        async def greet(ctx, name: str):
            await ctx.send(f'Hello {name}')

        return bot

    async with Session(factory) as session:
        alice = session.actor(456)
        checkpoint = session.transcript.checkpoint()
        incoming = await alice.message('!greet Alice', channel_id=123)
        reply = await session.transcript.expect(
            lambda item: item.kind == 'message_created' and item.direction == 'out'
            and item.payload['content'] == 'Hello Alice', after=checkpoint)
        assert incoming.observation.direction == 'in'
        assert incoming.observation.payload['author']['id'] == '456'
        assert reply.payload['channel_id'] == '123'
        assert reply.sequence > incoming.observation.sequence
        fetched = await session.bot.get_partial_messageable(123).fetch_message(incoming.id)
        assert fetched.content == '!greet Alice'


@pytest.mark.asyncio
async def test_actor_edits_and_deletes_dispatch_gateway_events():
    async with Session(lambda: discord.Client(intents=discord.Intents.all())) as session:
        alice, bob = session.actor(456), session.actor(789)
        message = await alice.message('before', channel_id=123)
        edit_waiter = asyncio.create_task(session.bot.wait_for('message_edit', timeout=1))
        await asyncio.sleep(0)
        edited = await alice.edit_message(message, content='after')
        before, after = await edit_waiter
        assert (before.content, after.content) == ('before', 'after')
        assert edited.id == message.id and message.content == 'before'
        with pytest.raises(ValueError, match='not owned'):
            await bob.delete_message(message)
        delete_waiter = asyncio.create_task(session.bot.wait_for('message_delete', timeout=1))
        await asyncio.sleep(0)
        await alice.delete_message(message)
        assert (await delete_waiter).id == message.id
        with pytest.raises(discord.NotFound):
            await session.bot.get_partial_messageable(123).fetch_message(message.id)
