"""Executable example included in the session tutorial."""
import asyncio

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

import discord.ext.test as dpytest


def create_bot():
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

    @bot.tree.command()
    async def greet(interaction: discord.Interaction, name: str):
        await interaction.response.send_message(f'Hello, {name}!', ephemeral=True)

    return bot


@pytest_asyncio.fixture
async def discord_session():
    async with dpytest.Session(bot_factory=create_bot) as session:
        yield session


@pytest.mark.asyncio
async def test_greeting(discord_session):
    alice = discord_session.actor(123)
    bob = discord_session.actor(456)
    command = await alice.slash('greet', channel_id=789, options={'name': 'Alice'})
    reply = await command.expect_response()
    assert reply.content == 'Hello, Alice!'
    assert reply.visible_to(alice)
    assert not reply.visible_to(bob)


@pytest.mark.asyncio
async def test_reaction_wait(discord_session):
    alice = discord_session.actor(123)
    bob = discord_session.actor(456)
    message = await alice.message('React here', channel_id=789)
    waiter = asyncio.create_task(discord_session.bot.wait_for('reaction_add', timeout=1))
    await asyncio.sleep(0)  # Let discord.py register the waiter.
    await bob.react(message, '👍')
    reaction, user = await waiter
    assert reaction.message.id == message.id
    assert user.id == bob.id
