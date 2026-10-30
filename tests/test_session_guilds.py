import asyncio

import discord
import pytest
from discord.ext import commands

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_guild_configured_before_setup_routes_member_commands():
    configured = {}

    def configure(session):
        guild = session.create_guild('Support')
        configured['channel'] = guild.text_channel('help')
        configured['alice'] = guild.member('Alice')
        configured['bob'] = guild.member('Bob')

    class Bot(commands.Bot):
        async def setup_hook(self):
            assert self.get_channel(configured['channel'].id).name == 'help'

    def factory():
        bot = Bot(command_prefix='!', intents=discord.Intents.all())

        @bot.command()
        async def where(ctx):
            await ctx.send(f'{ctx.guild.name}:{ctx.author.name}')

        @bot.tree.command()
        async def inspect(interaction: discord.Interaction):
            await interaction.response.send_message(f'{interaction.guild.name}:{interaction.user.name}')

        @bot.tree.command()
        async def target(interaction: discord.Interaction, member: discord.Member):
            await interaction.response.send_message(f'member:{member.name}')

        return bot

    async with Session(factory, configure=configure) as session:
        alice = configured['alice']
        channel = configured['channel']
        checkpoint = session.transcript.checkpoint()
        await alice.message('!where', channel_id=channel.id)
        prefix_reply = await session.transcript.expect(
            lambda item: item.kind == 'message_created' and item.direction == 'out'
            and item.payload['content'] == 'Support:Alice', after=checkpoint)
        assert prefix_reply.payload['guild_id'] == str(channel.guild.id)
        action = await alice.slash('inspect', channel_id=channel.id)
        assert (await action.expect_response()).content == 'Support:Alice'
        target = await alice.slash('target', channel_id=channel.id, options={'member': configured['bob']})
        assert (await target.expect_response()).content == 'member:Bob'
        with pytest.raises(ValueError, match='not a member'):
            await session.actor(999).message('hello', channel_id=channel.id)


@pytest.mark.asyncio
async def test_guild_reactions_report_member_and_raw_guild_after_eviction():
    async with Session(lambda: discord.Client(intents=discord.Intents.all())) as session:
        guild = session.create_guild('Support')
        channel = guild.text_channel('help')
        alice = guild.member('Alice')
        message = await channel.send('react')
        cached = asyncio.create_task(session.bot.wait_for('reaction_add', timeout=1))
        raw = asyncio.create_task(session.bot.wait_for('raw_reaction_add', timeout=1))
        await asyncio.sleep(0)
        await alice.react(message, '👍')
        reaction, member = await cached
        raw_event = await raw
        assert reaction.message.id == message.id
        assert isinstance(member, discord.Member) and member.name == 'Alice'
        assert raw_event.guild_id == guild.id and raw_event.member.id == alice.id
        session.evict_message(message.id)
        raw = asyncio.create_task(session.bot.wait_for('raw_reaction_add', timeout=1))
        await asyncio.sleep(0)
        await alice.react(message, '👀')
        assert (await raw).guild_id == guild.id
        assert (await channel.fetch_message(message.id)).id == message.id
        with pytest.raises(ValueError, match='not a member'):
            await session.actor(999).react(message, '🎉')
