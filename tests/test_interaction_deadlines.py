import asyncio

import discord
import pytest
from discord.ext import commands

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_deadline_and_expiry_with_simulator_clock():
    now = [0.0]

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def waiting(interaction: discord.Interaction):
            await asyncio.Event().wait()

        return bot

    async with Session(factory, clock=lambda: now[0]) as session:
        late = session.inject_slash('waiting', channel_id=123, user_id=456)
        callback = discord.webhook.async_.Route('POST', '/interactions/{webhook_id}/{webhook_token}/callback',
                                                webhook_id=late, webhook_token=session._interactions[late]['token'])
        now[0] = 3.0
        with pytest.raises(discord.NotFound):
            await session._webhook.request(callback, payload={'type': 4, 'data': {'content': 'late'}})
        assert not session.transcript.query(kind='message_created')

        timely = session.inject_slash('waiting', channel_id=123, user_id=456)
        callback = discord.webhook.async_.Route('POST', '/interactions/{webhook_id}/{webhook_token}/callback',
                                                webhook_id=timely, webhook_token=session._interactions[timely]['token'])
        await session._webhook.request(callback, payload={'type': 5})
        followup = discord.webhook.async_.Route('POST', '/webhooks/{webhook_id}/{webhook_token}',
                                                webhook_id=1, webhook_token=session._interactions[timely]['token'])
        now[0] += 900
        with pytest.raises(discord.NotFound):
            await session._webhook.request(followup, payload={'content': 'expired'})
        assert not session.transcript.query(kind='followup_sent')
        assert len(session.transcript.query(kind='request_rejected')) == 2


@pytest.mark.asyncio
async def test_tokens_cannot_cross_sessions_with_identical_interaction_ids():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def waiting(interaction: discord.Interaction):
            await asyncio.Event().wait()

        return bot

    async with Session(factory) as first:
        async with Session(factory) as second:
            first_id = first.inject_slash('waiting', channel_id=123, user_id=456)
            second_id = second.inject_slash('waiting', channel_id=123, user_id=456)
            assert first_id == second_id
            first_token = first._interactions[first_id]['token']
            assert first_token != second._interactions[second_id]['token']
            callback = discord.http.Route('POST', '/interactions/{webhook_id}/{webhook_token}/callback',
                                          webhook_id=second_id, webhook_token=first_token)
            with pytest.raises(discord.NotFound):
                await second._webhook.request(callback, payload={'type': 4, 'data': {'content': 'wrong'}})
            assert not second.transcript.query(kind='message_created')
            assert first_token not in repr(second.transcript.query())
        with pytest.raises(RuntimeError, match='closed'):
            await second._webhook.request(callback, payload={'type': 4, 'data': {'content': 'late'}})


@pytest.mark.asyncio
async def test_invalid_and_duplicate_acknowledgements_are_http_errors():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def waiting(interaction: discord.Interaction):
            await asyncio.Event().wait()

        return bot

    async with Session(factory) as session:
        interaction_id = session.inject_slash('waiting', channel_id=123, user_id=456)
        route = discord.http.Route('POST', '/interactions/{webhook_id}/{webhook_token}/callback',
                                   webhook_id=interaction_id,
                                   webhook_token=session._interactions[interaction_id]['token'])
        for payload in ({'type': 7, 'data': {'content': 'invalid'}}, {'type': 5, 'data': {'flags': 4}}):
            with pytest.raises(discord.HTTPException) as exc:
                await session._webhook.request(route, payload=payload)
            assert exc.value.status == 400 and exc.value.code == 50035
        await session._webhook.request(route, payload={'type': 4, 'data': {'content': 'accepted'}})
        with pytest.raises(discord.HTTPException) as exc:
            await session._webhook.request(route, payload={'type': 4, 'data': {'content': 'duplicate'}})
        assert exc.value.status == 400 and exc.value.code == 40060
        assert len(session.transcript.query(kind='message_created')) == 1
        assert len(session.transcript.query(kind='request_rejected', action_id=interaction_id)) == 3
