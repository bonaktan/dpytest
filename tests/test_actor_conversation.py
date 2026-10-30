import discord
import pytest
from discord.ext import commands
import discord.ext.test as dpytest


@pytest.mark.asyncio
async def test_actor_conversation():
    class Report(discord.ui.Modal, title='Report'):
        description = discord.ui.TextInput(label='Description', custom_id='description')

        async def on_submit(self, interaction):
            await interaction.response.defer(thinking=True, ephemeral=True)
            await interaction.edit_original_response(content='Report received.')
            await interaction.followup.send('Reference: R-001', ephemeral=True)

    class Controls(discord.ui.View):
        @discord.ui.button(label='Report', custom_id='report:open')
        async def open_report(self, interaction, button):
            await interaction.response.send_modal(Report())

    def factory():
        bot = commands.Bot(command_prefix='!', intents=discord.Intents.none())

        @bot.tree.command()
        async def report(interaction: discord.Interaction):
            await interaction.response.send_message('Open report', view=Controls())

        return bot

    async with dpytest.Session(factory) as session:
        alice, bob = session.actor(456), session.actor(789)
        command = await alice.slash('report', channel_id=123)
        reply = await command.expect_response()
        click = await alice.click(reply, custom_id='report:open')
        modal = await click.expect_modal(title='Report')
        submission = await alice.submit(modal, fields={'description': 'Broken'})
        await submission.expect_deferred(ephemeral=True)
        original = await submission.expect_original(content='Report received.')
        followup = await submission.expect_followup(content='Reference: R-001')
        assert original.visible_to(alice) and not original.visible_to(bob)
        assert followup.visible_to(alice) and not followup.visible_to(bob)
        assert original.id != followup.id
        assert original.observation.sequence < followup.observation.sequence
