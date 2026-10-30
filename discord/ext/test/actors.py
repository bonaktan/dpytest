"""Experimental user actions and scoped interaction expectations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import discord

from .observations import Observation


@dataclass(frozen=True)
class MessageResult:
    observation: Observation
    _session: Any

    @property
    def id(self) -> int:
        return int(self.observation.payload['id'])

    @property
    def channel_id(self) -> int:
        return int(self.observation.payload['channel_id'])

    @property
    def content(self) -> str:
        return self.observation.payload['content']

    def visible_to(self, actor: Actor) -> bool:
        return (actor._session is self._session and
                (self.observation.visibility == 'public' or self.observation.visibility == f'user:{actor.id}'))


@dataclass(frozen=True)
class ModalResult:
    interaction_id: int
    title: str
    _session: Any


class InteractionHandle:
    def __init__(self, session: Any, interaction_id: int) -> None:
        self._session = session
        self.id = interaction_id

    async def _expect(self, kind: str, *, timeout: float = 1.0) -> Observation:
        return await self._session._expect_observation(
            lambda item: item.kind == kind and item.action_id == self.id,
            action_id=self.id, expected=kind, timeout=timeout)

    async def expect_response(self, *, timeout: float = 1.0) -> MessageResult:
        acknowledgement = await self._expect('interaction_acknowledged', timeout=timeout)
        message_id = acknowledgement.payload['message_id']
        message = await self._session._expect_observation(
            lambda item: item.kind == 'message_created' and item.payload['id'] == message_id,
            action_id=self.id, expected='initial message', timeout=timeout)
        return MessageResult(message, self._session)

    async def expect_modal(self, *, title: Optional[str] = None, timeout: float = 1.0) -> ModalResult:
        modal = await self._expect('modal_opened', timeout=timeout)
        if title is not None and modal.payload['title'] != title:
            raise AssertionError(f"Expected modal title {title!r}, got {modal.payload['title']!r}")
        return ModalResult(self.id, modal.payload['title'], self._session)

    async def expect_deferred(self, *, ephemeral: Optional[bool] = None, timeout: float = 1.0) -> Observation:
        deferred = await self._expect('interaction_deferred', timeout=timeout)
        if ephemeral is not None and deferred.payload['ephemeral'] != ephemeral:
            raise AssertionError(f'Expected ephemeral={ephemeral}')
        return deferred

    async def expect_original(self, *, content: Optional[str] = None, timeout: float = 1.0) -> MessageResult:
        acknowledgement = await self._session._expect_observation(
            lambda item: item.action_id == self.id and item.kind in (
                'interaction_deferred', 'interaction_acknowledged', 'interaction_updated'),
            action_id=self.id, expected='original response acknowledgement', timeout=timeout)
        message_id = acknowledgement.payload['message_id']
        kinds = ('message_created', 'message_edited') if acknowledgement.kind == 'interaction_acknowledged' else (
            'message_edited',)
        message = await self._session._expect_observation(
            lambda item: item.kind in kinds and item.payload['id'] == message_id
            and (content is None or item.payload['content'] == content),
            action_id=self.id, expected=f'original message content={content!r}', timeout=timeout)
        return MessageResult(message, self._session)

    async def expect_followup(self, *, content: Optional[str] = None, timeout: float = 1.0) -> MessageResult:
        message = await self._session._expect_observation(
            lambda item: item.kind == 'followup_sent' and item.action_id == self.id
            and (content is None or item.payload['content'] == content),
            action_id=self.id, expected=f'followup content={content!r}', timeout=timeout)
        return MessageResult(message, self._session)

    async def expect_choices(self, *, timeout: float = 1.0) -> tuple[Any, ...]:
        result = await self._expect('autocomplete_choices', timeout=timeout)
        return result.payload['choices']


class Actor:
    def __init__(self, session: Any, user_id: int) -> None:
        self._session = session
        self.id = user_id

    async def message(self, content: str, *, channel_id: int) -> MessageResult:
        return MessageResult(self._session.inject_message(channel_id=channel_id, user_id=self.id, content=content),
                             self._session)

    def _check_message(self, message: MessageResult) -> None:
        if message._session is not self._session:
            raise ValueError('Message belongs to another session')

    async def edit_message(self, message: MessageResult, *, content: str) -> MessageResult:
        self._check_message(message)
        return MessageResult(self._session.change_actor_message(
            channel_id=message.channel_id, message_id=message.id, user_id=self.id, content=content), self._session)

    async def delete_message(self, message: MessageResult) -> None:
        self._check_message(message)
        self._session.change_actor_message(channel_id=message.channel_id, message_id=message.id,
                                           user_id=self.id, delete=True)

    async def slash(self, name: str, *, channel_id: int,
                    options: Optional[dict[str, Any]] = None) -> InteractionHandle:
        return InteractionHandle(self._session, self._session.inject_slash(
            name, channel_id=channel_id, user_id=self.id, options=options))

    async def autocomplete(self, name: str, *, channel_id: int, focused: str,
                           options: dict[str, Any]) -> InteractionHandle:
        return InteractionHandle(self._session, self._session.inject_slash(
            name, channel_id=channel_id, user_id=self.id, options=options, focused=focused))

    async def user_command(self, name: str, target: Actor, *, channel_id: int) -> InteractionHandle:
        if target._session is not self._session:
            raise ValueError('Target belongs to another session')
        return InteractionHandle(self._session, self._session.inject_context_menu(
            name, channel_id=channel_id, user_id=self.id, target_id=target.id,
            target_type=discord.AppCommandType.user))

    async def message_command(self, name: str, target: MessageResult) -> InteractionHandle:
        self._check_message(target)
        return InteractionHandle(self._session, self._session.inject_context_menu(
            name, channel_id=target.channel_id, user_id=self.id, target_id=target.id,
            target_type=discord.AppCommandType.message))

    async def click(self, message: MessageResult, *, custom_id: str) -> InteractionHandle:
        self._check_message(message)
        return InteractionHandle(self._session, self._session.inject_click(
            message.id, channel_id=message.channel_id, user_id=self.id, custom_id=custom_id))

    async def select(self, message: MessageResult, *, custom_id: str, values: list[str]) -> InteractionHandle:
        self._check_message(message)
        return InteractionHandle(self._session, self._session.inject_select(
            message.id, channel_id=message.channel_id, user_id=self.id, custom_id=custom_id, values=values))

    async def submit(self, modal: ModalResult, *, fields: dict[str, str]) -> InteractionHandle:
        if modal._session is not self._session:
            raise ValueError('Modal belongs to another session')
        return InteractionHandle(self._session, self._session.inject_modal_submit(
            modal.interaction_id, user_id=self.id, fields=fields))

    async def react(self, message: Any, emoji: Any) -> None:
        if isinstance(message, MessageResult):
            self._check_message(message)
        elif isinstance(message, discord.Message) and message._state is not self._session.bot._connection:
            raise ValueError('Message belongs to another session')
        channel_id = message.channel_id if isinstance(message, MessageResult) else message.channel.id
        self._session.add_reaction(channel_id=channel_id, message_id=message.id, user_id=self.id, emoji=emoji)

    async def remove_reaction(self, message: Any, emoji: Any) -> None:
        if isinstance(message, MessageResult):
            self._check_message(message)
        elif isinstance(message, discord.Message) and message._state is not self._session.bot._connection:
            raise ValueError('Message belongs to another session')
        channel_id = message.channel_id if isinstance(message, MessageResult) else message.channel.id
        self._session.remove_reaction(channel_id=channel_id, message_id=message.id, user_id=self.id, emoji=emoji)
