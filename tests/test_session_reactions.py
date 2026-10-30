import asyncio

import discord
import pytest

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_cached_reaction_wait_and_uncached_raw_event():
    async with Session(lambda: discord.Client(intents=discord.Intents.all())) as session:
        alice = session.actor(456)
        channel = session.bot.get_partial_messageable(123)
        message = await channel.send('React here')
        waiter = session.runtime.create_task(session.bot.wait_for('reaction_add', timeout=1))
        await asyncio.sleep(0)
        await alice.react(message, '👍')
        reaction, user = await waiter
        assert reaction.message.id == message.id
        assert str(reaction.emoji) == '👍'
        assert user.id == alice.id
        await alice.react(message, '👍')
        assert len(session.transcript.query(kind='reaction_added')) == 1

        session.evict_message(message.id)
        raw_waiter = session.runtime.create_task(session.bot.wait_for('raw_reaction_add', timeout=1))
        cached_waiter = session.runtime.create_task(session.bot.wait_for('reaction_add', timeout=0.05))
        await asyncio.sleep(0)
        await alice.react(message, '👀')
        raw = await raw_waiter
        assert raw.message_id == message.id
        with pytest.raises(asyncio.TimeoutError):
            await cached_waiter
        assert (await channel.fetch_message(message.id)).content == 'React here'


@pytest.mark.asyncio
async def test_user_removal_and_bot_reaction_operations():
    async with Session(lambda: discord.Client(intents=discord.Intents.all())) as session:
        alice = session.actor(456)
        message = await session.bot.get_partial_messageable(123).send('React')
        await alice.remove_reaction(message, 'missing')
        await alice.react(message, '👍')
        await message.add_reaction('👍')
        await alice.remove_reaction(message, '👍')
        cached = session.bot.cached_messages[-1]
        assert cached.reactions[0].count == 1
        assert cached.reactions[0].me
        fetched = await session.bot.get_partial_messageable(123).fetch_message(message.id)
        assert fetched.reactions[0].count == 1 and fetched.reactions[0].me
        await message.remove_reaction('👍', session.bot.user)
        assert not cached.reactions
        await alice.react(message, '👍')
        await alice.react(message, '👀')
        await message.clear_reaction('👍')
        assert [str(reaction.emoji) for reaction in cached.reactions] == ['👀']
        await message.clear_reactions()
        assert not cached.reactions
        records = session.transcript.query()
        assert any(item.kind == 'reaction_added' and item.direction == 'out' for item in records)
        assert len(session.transcript.query(kind='reaction_removed')) == 2
        assert len(session.transcript.query(kind='reaction_cleared')) == 2


@pytest.mark.asyncio
async def test_custom_emoji_identity_and_deletion_cleanup():
    async with Session(lambda: discord.Client(intents=discord.Intents.all())) as session:
        alice, bob = session.actor(456), session.actor(789)
        channel = session.bot.get_partial_messageable(123)
        message = await channel.send('custom')
        emoji_id = 123456789012345678
        await alice.react(message, discord.PartialEmoji(name='old', id=emoji_id))
        await alice.react(message, f'<:renamed:{emoji_id}>')
        await bob.react(message, f'<:renamed:{emoji_id}>')
        fetched = await channel.fetch_message(message.id)
        assert len(fetched.reactions) == 1 and fetched.reactions[0].count == 2
        await alice.remove_reaction(message, f'<:different:{emoji_id}>')
        assert (await channel.fetch_message(message.id)).reactions[0].count == 1
        await message.delete()
        assert not session.server.reactions
        assert not session.server.reaction_emoji
