import asyncio

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_command_errors_preserve_handler_and_can_be_acknowledged():
    handled = []

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.error
        async def on_tree_error(interaction, error):
            handled.append(error)

        @bot.tree.command()
        async def fail(interaction: discord.Interaction):
            raise ValueError('failure')

        return bot

    async with Session(factory) as session:
        await session.actor(123).slash('fail', channel_id=456)
        error = await session.expect_error(app_commands.CommandInvokeError)
        await asyncio.sleep(0)
        assert isinstance(error.original, ValueError)
        assert handled == [error]


@pytest.mark.asyncio
async def test_unexpected_event_failure_is_reported_on_exit():
    fired = asyncio.Event()

    class Bot(discord.Client):
        async def on_message(self, message):
            raise ValueError('event failure')

        async def on_error(self, event, *args, **kwargs):
            fired.set()

    with pytest.raises(RuntimeError, match='unexpected callback failure') as exc:
        async with Session(lambda: Bot(intents=discord.Intents.none())) as session:
            session.bot.dispatch('message', object())
            await asyncio.wait_for(fired.wait(), 1)
    assert isinstance(exc.value.__cause__, ValueError)


@pytest.mark.asyncio
async def test_view_error_remains_visible_to_application_handler():
    handled = asyncio.Event()

    class View(discord.ui.View):
        @discord.ui.button(label='Fail', custom_id='fail')
        async def fail(self, interaction, button):
            raise ValueError('view failure')

        async def on_error(self, interaction, error, item):
            handled.set()

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def show(interaction: discord.Interaction):
            await interaction.response.send_message('click', view=View())

        return bot

    async with Session(factory) as session:
        alice = session.actor(123)
        response = await (await alice.slash('show', channel_id=456)).expect_response()
        await alice.click(response, custom_id='fail')
        error = await session.expect_error(ValueError)
        await asyncio.wait_for(handled.wait(), 1)
        assert str(error) == 'view failure'


@pytest.mark.asyncio
async def test_registered_background_failure_is_reported_and_acknowledged():
    async def fail():
        raise ValueError('background failed')

    async with Session(lambda: discord.Client(intents=discord.Intents.none())) as session:
        session.create_task(fail())
        error = await session.expect_error(ValueError)
        assert str(error) == 'background failed'
        assert session.transcript.query(kind='callback_failure')[-1].payload['source'] == 'background_task'


@pytest.mark.asyncio
async def test_expectation_timeout_reports_relevant_error_and_pending_work():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def fail(interaction: discord.Interaction):
            raise ValueError('failure')

        return bot

    async with Session(factory) as session:
        session.create_task(asyncio.Event().wait(), name='waiting-background')
        action = await session.actor(123).slash('fail', channel_id=456)
        with pytest.raises(TimeoutError, match='CommandInvokeError.*waiting-background') as exc:
            await action.expect_response(timeout=0.01)
        assert str(action.id) in str(exc.value)
        assert isinstance(exc.value.__cause__, app_commands.CommandInvokeError)
        await session.expect_error(app_commands.CommandInvokeError)
