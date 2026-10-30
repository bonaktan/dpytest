import asyncio
import io

import discord
import pytest
from discord.ext import commands

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_interaction_and_followup_multipart_attachments():
    finished = asyncio.Event()
    contents = []

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def upload(interaction: discord.Interaction):
            await interaction.response.send_message(
                'original', file=discord.File(io.BytesIO(b'original'), filename='one.txt'), ephemeral=True)
            original = await interaction.original_response()
            contents.append(await original.attachments[0].read())
            followup = await interaction.followup.send(
                'followup', file=discord.File(io.BytesIO(b'followup'), filename='two.txt'), wait=True)
            contents.append(await followup.attachments[0].read())
            edited = await interaction.followup.edit_message(
                followup.id, attachments=[discord.File(io.BytesIO(b'edited'), filename='three.txt')])
            contents.append(await edited.attachments[0].read())
            finished.set()

        return bot

    async with Session(factory) as session:
        action = await session.actor(123).slash('upload', channel_id=456)
        original = await action.expect_response()
        await asyncio.wait_for(finished.wait(), 1)
        assert original.visible_to(session.actor(123))
        assert contents == [b'original', b'followup', b'edited']
    assert not session.server.attachments


@pytest.mark.asyncio
async def test_original_and_followup_message_lifecycle():
    finished = asyncio.Event()
    results = []

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

        @bot.tree.command()
        async def manage(interaction: discord.Interaction):
            await interaction.response.send_message('original', ephemeral=True)
            original = await interaction.original_response()
            followup = await interaction.followup.send('followup', wait=True)
            fetched = await interaction.followup.fetch_message(followup.id)
            edited = await interaction.followup.edit_message(followup.id, content='changed')
            results.extend((original, fetched, edited))
            await interaction.followup.delete_message(followup.id)
            await interaction.delete_original_response()
            finished.set()

        return bot

    async with Session(factory) as session:
        await session.actor(123).slash('manage', channel_id=456)
        await asyncio.wait_for(finished.wait(), 1)
        original, fetched, edited = results
        assert original.content == 'original'
        assert fetched.id == edited.id and edited.content == 'changed'
        assert len(session.transcript.query(kind='message_deleted')) == 2
        with pytest.raises(discord.NotFound):
            await session.bot.get_partial_messageable(456).fetch_message(edited.id)


@pytest.mark.asyncio
async def test_followup_cannot_be_fetched_with_another_interaction_token():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def send(interaction: discord.Interaction):
            await interaction.response.send_message('ready')
            await interaction.followup.send('followup')

        return bot

    async with Session(factory) as session:
        alice = session.actor(123)
        first = await alice.slash('send', channel_id=456)
        second = await alice.slash('send', channel_id=456)
        followup = await first.expect_followup(content='followup')
        await second.expect_response()
        token = session._interactions[second.id]['token']
        route = discord.http.Route('GET', '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}',
                                   webhook_id=1, webhook_token=token, message_id=followup.id)
        with pytest.raises(discord.NotFound):
            await session._webhook.request(route)


@pytest.mark.asyncio
async def test_first_followup_after_defer_edits_original_and_preserves_visibility():
    finished = asyncio.Event()
    result = []

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def defer(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            result.append(await interaction.followup.send('completed', ephemeral=False, wait=True))
            finished.set()

        return bot

    async with Session(factory) as session:
        command = await session.actor(123).slash('defer', channel_id=456)
        deferred = await command.expect_deferred(ephemeral=True)
        await asyncio.wait_for(finished.wait(), 1)
        assert result[0].id == int(deferred.payload['message_id'])
        assert result[0].flags.ephemeral
        assert not session.transcript.query(kind='followup_sent')


@pytest.mark.asyncio
@pytest.mark.parametrize('via_followup', [False, True])
async def test_public_defer_emits_message_and_edit_events(via_followup):
    gate = asyncio.Event()

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

        @bot.tree.command()
        async def slow(interaction: discord.Interaction):
            await interaction.response.defer()
            await gate.wait()
            if via_followup:
                await interaction.followup.send('ready')
            else:
                await interaction.edit_original_response(content='ready')

        return bot

    async with Session(factory) as session:
        created = asyncio.create_task(session.bot.wait_for('message', timeout=1))
        await asyncio.sleep(0)
        action = await session.actor(123).slash('slow', channel_id=456)
        deferred = await action.expect_deferred(ephemeral=False)
        placeholder = await created
        assert placeholder.id == int(deferred.payload['message_id'])
        assert placeholder.flags.loading
        edited = asyncio.create_task(session.bot.wait_for('message_edit', timeout=1))
        await asyncio.sleep(0)
        gate.set()
        before, after = await edited
        assert before.id == after.id == placeholder.id
        assert before.flags.loading and not after.flags.loading
        assert after.content == 'ready'
