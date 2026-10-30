"""Executable guild example included in the session tutorial."""
import discord
import pytest
import pytest_asyncio
from discord.ext import commands

import discord.ext.test as dpytest


def create_bot():
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

    @bot.tree.command()
    async def where(interaction: discord.Interaction):
        await interaction.response.send_message(f'{interaction.guild.name}: {interaction.user.name}')

    return bot


def configure(session):
    guild = session.create_guild('Support')
    guild.text_channel('help')
    guild.member('Alice')


@pytest_asyncio.fixture
async def discord_session():
    async with dpytest.Session(bot_factory=create_bot, configure=configure) as session:
        yield session


@pytest.mark.asyncio
async def test_guild_command(discord_session):
    guild = discord_session.guild('Support')
    channel = guild.text_channel('help')
    alice = guild.member('Alice')
    command = await alice.slash('where', channel_id=channel.id)
    assert (await command.expect_response()).content == 'Support: Alice'
