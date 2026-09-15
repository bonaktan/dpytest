from pathlib import Path

import discord.ext.commands as commands
import pytest

import discord
import discord.ext.test as dpytest  # noqa: F401


@pytest.mark.asyncio
async def test_edit(bot: commands.Bot) -> None:
    guild = bot.guilds[0]
    channel = guild.channels[0]
    assert isinstance(channel, discord.TextChannel)

    mes = await channel.send("Test Message")
    persisted_mes1 = await channel.fetch_message(mes.id)
    edited_mes = await mes.edit(content="New Message")
    persisted_mes2 = await channel.fetch_message(mes.id)

    assert edited_mes.content == "New Message"
    assert persisted_mes1.content == "Test Message"
    assert persisted_mes2.content == "New Message"


@pytest.mark.asyncio
async def test_edit_message_with_attachment(bot: discord.Client) -> None:
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    # Send initial message
    message = await channel.send("Refreshing...")

    # Edit with embed and file attachment
    embed = discord.Embed(title="Leaderboard")
    embed.add_field(name="Player", value="Score")

    path_ = Path(__file__).resolve().parent / "data/loremimpsum.txt"
    file_ = discord.File(path_, filename="leaderboard.txt")

    await message.edit(content="", embed=embed, attachments=[file_])

    edited = await channel.fetch_message(message.id)
    assert edited.content == ""
    assert len(edited.embeds) == 1
    assert edited.embeds[0].title == "Leaderboard"
    assert len(edited.attachments) == 1
    assert edited.attachments[0].filename == "leaderboard.txt"
