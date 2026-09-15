import pytest
import discord
import discord.ext.test as dpytest


@pytest.mark.asyncio
async def test_create_thread_from_message(bot: discord.Client) -> None:
    """Thread is created from a message and attached to it"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("QOTD: What is your favorite color?")
    thread = await message.create_thread(name="QOTD Thread")

    assert thread is not None
    assert thread.name == "QOTD Thread"
    assert thread.parent_id == channel.id


@pytest.mark.asyncio
async def test_create_thread_type(bot: discord.Client) -> None:
    """Thread is a public thread by default"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="My Thread")

    assert thread.type == discord.ChannelType.public_thread


@pytest.mark.asyncio
async def test_create_thread_auto_archive_duration(bot: discord.Client) -> None:
    """Auto archive duration is stored correctly"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="My Thread", auto_archive_duration=60)

    assert thread.auto_archive_duration == 60


@pytest.mark.asyncio
async def test_create_thread_slowmode(bot: discord.Client) -> None:
    """Rate limit per user (slowmode) is stored correctly"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="My Thread", slowmode_delay=10)

    assert thread.slowmode_delay == 10


@pytest.mark.asyncio
async def test_thread_is_accessible_from_guild(bot: discord.Client) -> None:
    """Thread shows up in guild.threads after creation"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="Guild Thread")

    assert guild.get_thread(thread.id) is not None
    assert any(t.id == thread.id for t in guild.threads)


@pytest.mark.asyncio
async def test_thread_parent_is_channel(bot: discord.Client) -> None:
    """Thread's parent resolves to the correct channel"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="Child Thread")

    assert thread.parent_id == channel.id
    assert thread.parent == channel


@pytest.mark.asyncio
async def test_thread_not_archived_by_default(bot: discord.Client) -> None:
    """Newly created thread is not archived"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="Active Thread")

    assert thread.archived is False
    assert thread.locked is False


@pytest.mark.asyncio
async def test_send_message_in_thread(bot: discord.Client) -> None:
    """Messages can be sent inside the thread"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    message = await channel.send("Test")
    thread = await message.create_thread(name="Convo Thread")
    await thread.send("Hello from thread!")

    assert dpytest.verify().message().content("Test")
    assert dpytest.verify().message().content("Hello from thread!")


@pytest.mark.asyncio
async def test_multiple_threads_unique_ids(bot: discord.Client) -> None:
    """Each thread gets a unique ID"""
    guild = bot.guilds[0]
    channel = guild.text_channels[0]

    msg1 = await channel.send("First")
    msg2 = await channel.send("Second")
    thread1 = await msg1.create_thread(name="Thread 1")
    thread2 = await msg2.create_thread(name="Thread 2")

    assert thread1.id != thread2.id