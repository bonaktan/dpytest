import discord
import pytest
from discord.ext import commands

from discord.ext.test import Session


@pytest.mark.asyncio
async def test_user_and_message_context_menu_resolve_real_discord_objects():
    seen = []

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.context_menu(name='Inspect user')
        async def inspect_user(interaction: discord.Interaction, user: discord.User):
            seen.append(user)
            await interaction.response.send_message(f'user:{user.id}')

        @bot.tree.context_menu(name='Inspect message')
        async def inspect_message(interaction: discord.Interaction, message: discord.Message):
            seen.append(message)
            await interaction.response.send_message(f'message:{message.content}')

        return bot

    async with Session(factory) as session:
        alice, bob = session.actor(123), session.actor(456)
        target = await bob.message('hello', channel_id=789)
        user_action = await alice.user_command('Inspect user', bob, channel_id=789)
        message_action = await alice.message_command('Inspect message', target)
        assert (await user_action.expect_response()).content == 'user:456'
        assert (await message_action.expect_response()).content == 'message:hello'
        assert isinstance(seen[0], discord.User)
        assert isinstance(seen[1], discord.Message)
        with pytest.raises(ValueError, match='Unknown context menu'):
            await alice.user_command('missing', bob, channel_id=789)


@pytest.mark.asyncio
async def test_cross_session_handles_do_not_resolve_to_local_entities():
    async with Session(lambda: discord.Client(intents=discord.Intents.none())) as first:
        async with Session(lambda: discord.Client(intents=discord.Intents.none())) as second:
            alice = first.actor(123)
            other = second.actor(123)
            message = await other.message('foreign', channel_id=789)
            await alice.message('local', channel_id=789)
            with pytest.raises(ValueError, match='another session'):
                await alice.message_command('anything', message)
            assert not message.visible_to(alice)
