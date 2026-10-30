"""Experimental guild configuration backed by discord.py cache objects."""
from __future__ import annotations

from typing import Any

import discord

from . import factories


class GuildSetup:
    def __init__(self, session: Any, name: str, guild_id: int) -> None:
        self._session = session
        self.id = guild_id
        role = factories.make_role_dict('@everyone', id_num=guild_id, position=0,
                                        permissions=str(discord.Permissions.all().value))
        data = factories.make_guild_dict(name, owner_id=1, roles=[role], id_num=guild_id)
        self.guild = discord.Guild(data=data, state=session.bot._connection)
        session.bot._connection._add_guild(self.guild)
        self._channels: dict[str, discord.TextChannel] = {}
        self._members: dict[str, Any] = {}
        self._add_member(session.bot.user)

    def _add_member(self, user: Any) -> None:
        data = factories.make_member_dict(user, roles=[], flags=0, permissions=str(discord.Permissions.all().value))
        self.guild._add_member(discord.Member(data=data, guild=self.guild, state=self._session.bot._connection))

    def text_channel(self, name: str) -> discord.TextChannel:
        if name not in self._channels:
            channel_id = self._session._next_entity_id()
            data = factories.make_text_channel_dict(name, id_num=channel_id, guild_id=self.id,
                                                    position=len(self._channels), permission_overwrites=[])
            channel = discord.TextChannel(state=self._session.bot._connection, guild=self.guild, data=data)
            self.guild._add_channel(channel)
            self._channels[name] = channel
            self._session.server.channel_guilds[channel_id] = self.id
        return self._channels[name]

    def member(self, name: str) -> Any:
        if name not in self._members:
            actor = self._session.actor(self._session._next_entity_id(), name=name)
            self._add_member(self._session._users[actor.id])
            self._members[name] = actor
        return self._members[name]
