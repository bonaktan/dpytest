import asyncio

import discord
import pytest
from discord.ext import commands

from discord.ext.test.session import Session, UnsupportedOperation


@pytest.mark.asyncio
async def test_factory_setup_and_owned_event_lifecycle():
    order = []
    started = asyncio.Event()

    class Bot(commands.Bot):
        async def setup_hook(self):
            order.append("setup")
            assert self.tree.get_command("factory") is not None

        async def on_message(self, message):
            started.set()
            await asyncio.Event().wait()

    def factory():
        bot = Bot(command_prefix="!", intents=discord.Intents.none())

        @bot.tree.command()
        async def factory(interaction: discord.Interaction):
            pass

        return bot

    async with Session(factory, configure=lambda session: order.append("configure")) as session:
        assert order == ["configure", "setup"]
        assert session.bot.is_ready()
        await session.bot.wait_until_ready()
        session.bot.dispatch("message", object())
        await asyncio.wait_for(started.wait(), 1)
        assert len(session.runtime.pending) == 1
        with pytest.raises(UnsupportedOperation, match="GET /users/@me"):
            await session.bot.http.request(discord.http.Route("GET", "/users/@me"))
        assert session.transcript.query(kind="request_rejected")
    assert not session.runtime.pending
    assert session.bot.is_closed()


@pytest.mark.asyncio
async def test_startup_failure_closes_client():
    class Bot(commands.Bot):
        async def setup_hook(self):
            raise ValueError("setup failed")

    bot = Bot(command_prefix="!", intents=discord.Intents.none())
    with pytest.raises(ValueError, match="setup failed"):
        async with Session(lambda: bot):
            pass
    assert bot.is_closed()


@pytest.mark.asyncio
async def test_teardown_stops_factory_and_setup_views_and_owned_tasks():
    class Persistent(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            self.add_item(discord.ui.Button(label='Persistent', custom_id='persistent'))

    persistent = Persistent()
    timed = discord.ui.View(timeout=60)
    timed.add_item(discord.ui.Button(label='Timed', custom_id='timed'))
    started = asyncio.Event()
    stopped = asyncio.Event()

    class Bot(commands.Bot):
        async def setup_hook(self):
            await self.get_partial_messageable(123).send('view', view=timed)

    def factory():
        bot = Bot(command_prefix='!', intents=discord.Intents.none())
        bot.add_view(persistent)
        return bot

    async def background():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async with Session(factory) as session:
        session.create_task(background())
        await started.wait()
        assert not persistent.is_finished() and not timed.is_finished()
    assert persistent.is_finished() and timed.is_finished()
    assert stopped.is_set()
