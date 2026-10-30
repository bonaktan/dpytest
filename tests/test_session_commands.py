import asyncio

import discord
import pytest
from discord.ext import commands
from discord import app_commands

from discord.ext.test.session import Session


@pytest.mark.asyncio
async def test_slash_group_routes_subcommand_with_options():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())
        group = app_commands.Group(name='tools', description='Tools')

        @group.command()
        async def echo(interaction: discord.Interaction, text: str):
            await interaction.response.send_message(text)

        bot.tree.add_command(group)
        return bot

    async with Session(factory) as session:
        alice = session.actor(123)
        action = await alice.slash('tools echo', channel_id=456, options={'text': 'nested'})
        assert (await action.expect_response()).content == 'nested'
        with pytest.raises(ValueError, match='requires a subcommand'):
            await alice.slash('tools', channel_id=456)


@pytest.mark.asyncio
async def test_slash_user_option_resolves_session_actor():
    seen = []

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def inspect(interaction: discord.Interaction, target: discord.User):
            seen.append(target)
            await interaction.response.send_message(f'target:{target.id}')

        return bot

    async with Session(factory) as session:
        alice, bob = session.actor(123), session.actor(456)
        action = await alice.slash('inspect', channel_id=789, options={'target': bob})
        assert (await action.expect_response()).content == 'target:456'
        assert len(seen) == 1 and isinstance(seen[0], discord.User) and seen[0].id == bob.id
        async with Session(factory) as other:
            with pytest.raises(ValueError, match='actor in this session'):
                await alice.slash('inspect', channel_id=789, options={'target': other.actor(456)})


@pytest.mark.asyncio
async def test_string_select_validates_and_routes_choices():
    class Controls(discord.ui.View):
        @discord.ui.select(custom_id='pick', min_values=1, max_values=2,
                           options=[discord.SelectOption(label='One', value='1'),
                                    discord.SelectOption(label='Two', value='2')])
        async def pick(self, interaction, select):
            await interaction.response.send_message(','.join(select.values), ephemeral=True)

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def show(interaction: discord.Interaction):
            await interaction.response.send_message('choose', view=Controls())

        return bot

    async with Session(factory) as session:
        alice = session.actor(123)
        message = await (await alice.slash('show', channel_id=456)).expect_response()
        for values in ([], ['unknown'], ['1', '1'], ['1', '2', '3']):
            with pytest.raises(ValueError, match='Invalid select values'):
                await alice.select(message, custom_id='pick', values=values)
        selection = await alice.select(message, custom_id='pick', values=['2', '1'])
        result = await selection.expect_response()
        assert result.content == '2,1'
        assert result.visible_to(alice)


@pytest.mark.asyncio
@pytest.mark.parametrize('deferred', [False, True])
async def test_component_update_preserves_original_identity(deferred):
    class Controls(discord.ui.View):
        @discord.ui.button(label='Update', custom_id='update')
        async def update(self, interaction, button):
            if deferred:
                await interaction.response.defer()
                await interaction.edit_original_response(content='updated')
            else:
                await interaction.response.edit_message(content='updated')

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

        @bot.tree.command()
        async def show(interaction: discord.Interaction):
            await interaction.response.send_message('before', view=Controls())

        return bot

    async with Session(factory) as session:
        alice = session.actor(123)
        original = await (await alice.slash('show', channel_id=456)).expect_response()
        waiter = asyncio.create_task(session.bot.wait_for('message_edit', timeout=1))
        await asyncio.sleep(0)
        click = await alice.click(original, custom_id='update')
        if deferred:
            await click.expect_deferred(ephemeral=False)
        edited = await click.expect_original(content='updated')
        before, after = await waiter
        assert edited.id == original.id == after.id
        assert (before.content, after.content) == ('before', 'updated')


@pytest.mark.asyncio
async def test_initial_ephemeral_response_is_private_and_not_dispatched():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

        @bot.tree.command()
        async def secret(interaction: discord.Interaction):
            await interaction.response.send_message('private', ephemeral=True)

        return bot

    async with Session(factory) as session:
        alice, bob = session.actor(123), session.actor(456)
        waiter = asyncio.create_task(session.bot.wait_for('message', timeout=0.05))
        await asyncio.sleep(0)
        command = await alice.slash('secret', channel_id=789)
        response = await command.expect_response()
        assert response.content == 'private'
        assert response.visible_to(alice) and not response.visible_to(bob)
        assert (await command.expect_original(content='private')).id == response.id
        with pytest.raises(asyncio.TimeoutError):
            await waiter
        with pytest.raises(discord.NotFound):
            await session.bot.get_partial_messageable(789).fetch_message(response.id)
        assert all(message.id != response.id for message in session.bot.cached_messages)


@pytest.mark.asyncio
async def test_autocomplete_uses_real_registered_handler():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def find(interaction: discord.Interaction, query: str, required: int):
            raise AssertionError('autocomplete must not invoke the command')

        @find.autocomplete('query')
        async def suggest(interaction: discord.Interaction, current: str):
            return [app_commands.Choice(name=current + ' result', value=current + '1')]

        return bot

    async with Session(factory) as session:
        alice = session.actor(123)
        interaction = await alice.autocomplete('find', channel_id=456, focused='query', options={'query': 'he'})
        choices = await interaction.expect_choices()
        assert choices[0]['name'] == 'he result'
        assert choices[0]['value'] == 'he1'
        with pytest.raises(ValueError, match='Focused option'):
            await alice.autocomplete('find', channel_id=456, focused='required', options={'required': 1})


@pytest.mark.asyncio
async def test_command_options_run_real_check_and_transformer():
    calls = []

    class Upper(app_commands.Transformer):
        async def transform(self, interaction, value: str):
            calls.append(('transform', value))
            return value.upper()

    async def check(interaction):
        calls.append(('check', interaction.user.id))
        return True

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        @app_commands.check(check)
        async def greet(interaction: discord.Interaction, name: app_commands.Transform[str, Upper], count: int):
            await interaction.response.send_message(name * count)

        return bot

    async with Session(factory) as session:
        alice = session.actor(456)
        with pytest.raises(ValueError, match='Missing required'):
            await alice.slash('greet', channel_id=123, options={'name': 'a'})
        with pytest.raises(ValueError, match='Invalid value type'):
            await alice.slash('greet', channel_id=123, options={'name': 'a', 'count': True})
        command = await alice.slash('greet', channel_id=123, options={'name': 'hi', 'count': 2})
        response = await command.expect_response()
        assert response.content == 'HIHI'
        assert calls == [('check', 456), ('transform', 'hi')]


@pytest.mark.asyncio
async def test_real_command_routing_and_local_response():
    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def hello(interaction: discord.Interaction):
            await interaction.response.send_message('hello')

        return bot

    async with Session(factory) as session:
        interaction_id = session.inject_slash('hello', channel_id=123, user_id=456)
        observation = await session.transcript.expect(
            lambda item: item.kind == 'interaction_acknowledged' and item.action_id == interaction_id)
        message = await session.bot.get_partial_messageable(123).fetch_message(
            int(observation.payload['message_id']))
        assert message.content == 'hello'
        with pytest.raises(ValueError, match='Unknown application command'):
            session.inject_slash('missing', channel_id=123, user_id=456)


@pytest.mark.asyncio
async def test_waiting_command_is_owned_and_cancelled_without_touching_other_tasks():
    started = asyncio.Event()
    stopped = asyncio.Event()

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def waiting(interaction: discord.Interaction):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()

        return bot

    unrelated = asyncio.create_task(asyncio.Event().wait())
    async with Session(factory) as session:
        session.inject_slash('waiting', channel_id=123, user_id=456)
        await asyncio.wait_for(started.wait(), 1)
        assert session.runtime.pending
    assert stopped.is_set()
    assert not unrelated.done()
    unrelated.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unrelated


@pytest.mark.asyncio
async def test_interleaved_commands_use_their_own_webhook_adapter():
    gate = asyncio.Event()

    def factory(content):
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def hello(interaction: discord.Interaction):
            await gate.wait()
            await interaction.response.send_message(content)

        return bot

    async with Session(lambda: factory('first')) as first:
        async with Session(lambda: factory('second')) as second:
            first_id = first.inject_slash('hello', channel_id=123, user_id=456)
            second_id = second.inject_slash('hello', channel_id=123, user_id=456)
            gate.set()
            await asyncio.gather(
                first.transcript.expect(lambda item: item.kind == 'interaction_acknowledged'
                                        and item.action_id == first_id),
                second.transcript.expect(lambda item: item.kind == 'interaction_acknowledged'
                                         and item.action_id == second_id),
            )
            assert first.transcript.query(kind='message_created')[0].payload['content'] == 'first'
            assert second.transcript.query(kind='message_created')[0].payload['content'] == 'second'


@pytest.mark.asyncio
async def test_command_button_opens_real_modal():
    class Report(discord.ui.Modal, title='Report'):
        description = discord.ui.TextInput(label='Description', custom_id='description')

        async def on_submit(self, interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            await interaction.edit_original_response(content=f'Received: {self.description.value}')
            await interaction.followup.send('Reference: R-001', ephemeral=True)

    class Controls(discord.ui.View):
        @discord.ui.button(label='Report', custom_id='report:open')
        async def open_report(self, interaction, button):
            await interaction.response.send_modal(Report(custom_id='report:modal'))

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def report(interaction: discord.Interaction):
            await interaction.response.send_message('Open report', view=Controls())

        return bot

    async with Session(factory) as session:
        command = session.inject_slash('report', channel_id=123, user_id=456)
        response = await session.transcript.expect(
            lambda item: item.kind == 'interaction_acknowledged' and item.action_id == command)
        message_id = int(response.payload['message_id'])
        with pytest.raises(ValueError, match='Button'):
            session.inject_click(message_id, channel_id=123, user_id=456, custom_id='missing')
        click = session.inject_click(message_id, channel_id=123, user_id=456, custom_id='report:open')
        modal = await session.transcript.expect(lambda item: item.kind == 'modal_opened' and item.action_id == click)
        assert modal.payload['title'] == 'Report'
        assert modal.payload['custom_id'] == 'report:modal'
        with pytest.raises(ValueError, match='required field'):
            session.inject_modal_submit(click, user_id=456, fields={})
        with pytest.raises(ValueError, match='unavailable'):
            session.inject_modal_submit(click, user_id=999, fields={'description': 'broken'})
        submission = session.inject_modal_submit(click, user_id=456, fields={'description': 'broken'})
        result = await session.transcript.expect(
            lambda item: item.kind == 'interaction_deferred' and item.action_id == submission)
        followup = await session.transcript.expect(lambda item: item.kind == 'followup_sent')
        edited = session.transcript.query(kind='message_edited')[-1]
        assert result.payload['ephemeral'] is True
        assert edited.payload['id'] == result.payload['message_id']
        assert edited.payload['content'] == 'Received: broken'
        assert edited.visibility == 'user:456'
        assert followup.payload['content'] == 'Reference: R-001'
        assert followup.visibility == 'user:456'
        with pytest.raises(discord.NotFound):
            await session.bot.get_partial_messageable(123).fetch_message(int(result.payload['message_id']))
