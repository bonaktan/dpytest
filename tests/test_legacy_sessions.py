import discord
import pytest

import discord.ext.test as dpytest
from discord.ext.test.legacy import require_unambiguous


@pytest.mark.asyncio
async def test_overlapping_sessions_reject_ambiguous_legacy_calls():
    factory = lambda: discord.Client(intents=discord.Intents.none())  # noqa: E731
    async with dpytest.Session(factory) as first:
        async with dpytest.Session(factory):
            with pytest.raises(RuntimeError, match='multiple Sessions'):
                dpytest.get_message()
            with pytest.raises(RuntimeError, match='multiple Sessions'):
                dpytest.get_config()
            with pytest.raises(RuntimeError, match='multiple Sessions'):
                dpytest.configure(first.bot)
            with pytest.raises(RuntimeError, match='multiple Sessions'):
                await dpytest.run_all_events()
        # Once overlap ends, the guard no longer intercepts normal legacy behavior.
        require_unambiguous()


@pytest.mark.asyncio
async def test_failed_startup_unregisters_session():
    class Failing(discord.Client):
        async def setup_hook(self):
            raise ValueError('startup')

    async with dpytest.Session(lambda: discord.Client(intents=discord.Intents.none())):
        with pytest.raises(ValueError, match='startup'):
            async with dpytest.Session(lambda: Failing(intents=discord.Intents.none())):
                pass
        require_unambiguous()
