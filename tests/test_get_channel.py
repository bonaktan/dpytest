import pytest
import discord
import discord.ext.test as dpytest  # noqa: F401


@pytest.mark.asyncio
async def test_fetch_channels(bot: discord.Client) -> None:
    guild = bot.guilds[0]
    channels = await guild.fetch_channels()

    assert len(channels) == len(guild.channels)
    assert all(c.guild.id == guild.id for c in channels)


@pytest.mark.asyncio
async def test_fetch_channels_contains_text(bot: discord.Client) -> None:
    guild = bot.guilds[0]
    channels = await guild.fetch_channels()

    text_channels = [c for c in channels if isinstance(c, discord.TextChannel)]
    assert len(text_channels) == len(guild.text_channels)


@pytest.mark.asyncio
async def test_fetch_channels_contains_voice(bot: discord.Client) -> None:
    guild = bot.guilds[0]
    channels = await guild.fetch_channels()

    voice_channels = [c for c in channels if isinstance(c, discord.VoiceChannel)]
    assert len(voice_channels) == len(guild.voice_channels)


@pytest.mark.asyncio
async def test_fetch_channels_after_create(bot: discord.Client) -> None:
    guild = bot.guilds[0]
    await guild.create_text_channel("new-channel")

    channels = await guild.fetch_channels()
    names = [c.name for c in channels]
    assert "new-channel" in names