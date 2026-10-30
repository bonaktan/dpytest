"""Lifecycle for an isolated, locally connected discord.py client.

The simulator transport implements a small set of local message routes and
rejects other requests. It never delegates ordinary HTTP requests to Discord.
"""
from __future__ import annotations

import inspect
import asyncio
import copy
import json
import re
import secrets
import time
import sys
from urllib.parse import unquote
from typing import Any, Callable, Coroutine, Optional

import discord
from discord.webhook.async_ import AsyncWebhookAdapter, async_context

from . import legacy
from .observations import Transcript
from .runtime import Runtime
from .server import MessageServer, _Response


class UnsupportedOperation(NotImplementedError):
    """A Discord operation that the simulator does not yet implement."""


class _BadRequest:
    status = 400
    reason = 'Bad Request'


class _LocalWebhookAdapter(AsyncWebhookAdapter):
    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    async def request(self, route: Any, *args: Any, **kwargs: Any) -> Any:
        if self.session._closed:
            raise RuntimeError('session is closed')
        payload = kwargs.get('payload') or {}
        multipart = kwargs.get('multipart') or []
        if multipart:
            payload_json = next((part['value'] for part in multipart if part.get('name') == 'payload_json'), None)
            if payload_json is None:
                raise UnsupportedOperation('Multipart request is missing payload_json')
            payload = json.loads(payload_json)
        files = kwargs.get('files') or []
        if route.path == '/interactions/{webhook_id}/{webhook_token}/callback':
            interaction = self.session._interactions.get(route.webhook_id)
            if interaction is None or route.webhook_token != interaction['token']:
                self._unknown_interaction(route)
            age = self.session.clock() - interaction['created_at']
            if age >= 900 or (age >= 3 and not interaction.get('acknowledged')):
                self._unknown_interaction(route)
            if interaction.get('acknowledged'):
                self._reject_callback(route, 40060, 'Interaction has already been acknowledged')
            response_type = payload.get('type')
            allowed = {2: {4, 5, 9}, 3: {4, 5, 6, 7, 9}, 4: {8}, 5: {4, 5}}
            if response_type not in allowed.get(interaction['type'], set()):
                self._reject_callback(route, 50035, 'Incompatible interaction response type')
            if response_type == 8:
                choices = (payload.get('data') or {}).get('choices', [])
                if len(choices) > 25:
                    self._reject_callback(route, 50035, 'Autocomplete accepts at most 25 choices')
                interaction['acknowledged'] = True
                self.session.transcript.record('out', 'autocomplete_choices', {'choices': choices},
                                               action_id=route.webhook_id)
                return {'interaction': {'id': str(route.webhook_id)}}
            if response_type in (6, 7):
                message_id = interaction['source_message_id']
                message_route = discord.http.Route(
                    'PATCH' if response_type == 7 else 'GET', '/channels/{channel_id}/messages/{message_id}',
                    channel_id=interaction['channel_id'], message_id=message_id)
                message = self.session.server.request(message_route, json=payload.get('data') or {},
                                                      files=files, internal=True)
                if message is NotImplemented:
                    raise UnsupportedOperation('Unsupported component message update')
                interaction.update(acknowledged=True, original_id=message_id)
                private = (interaction['channel_id'], message_id) in self.session.server.private
                if response_type == 7 and not private:
                    self.session.bot._connection.parse_message_update(message)
                kind = 'interaction_deferred' if response_type == 6 else 'interaction_updated'
                self.session.transcript.record('out', kind, {
                    'interaction_id': str(route.webhook_id), 'message_id': str(message_id),
                    'ephemeral': private,
                }, action_id=route.webhook_id)
                result = {'interaction': {'id': str(route.webhook_id), 'response_message_id': str(message_id)}}
                if response_type == 7:
                    result['resource'] = {'type': 7, 'message': message}
                return result
            if (interaction is not None and route.webhook_token == interaction['token']
                    and payload.get('type') == 5):
                flags = (payload.get('data') or {}).get('flags', 0)
                if flags & ~64:
                    self._reject_callback(route, 50035, 'Invalid deferred response flags')
                message_route = discord.http.Route('POST', '/channels/{channel_id}/messages',
                                                   channel_id=interaction['channel_id'])
                message = self.session.server.request(message_route, json={'flags': flags | 128},
                                                      private_owner=interaction['user_id'] if flags & 64 else None)
                interaction.update(acknowledged=True, original_id=int(message['id']), deferred_pending=True)
                if not flags & 64:
                    self.session.bot._connection.parse_message_create(message)
                self.session.transcript.record('out', 'interaction_deferred', {
                    'interaction_id': str(route.webhook_id), 'message_id': message['id'], 'ephemeral': bool(flags & 64),
                }, action_id=route.webhook_id)
                return {'interaction': {'id': str(route.webhook_id), 'response_message_id': message['id'],
                                        'response_message_loading': True,
                                        'response_message_ephemeral': bool(flags & 64)}}
            if (interaction is not None and route.webhook_token == interaction['token']
                    and payload.get('type') == 9):
                interaction['acknowledged'] = True
                interaction['modal'] = payload['data']
                self.session.transcript.record('out', 'modal_opened', payload['data'],
                                               action_id=route.webhook_id)
                return {'interaction': {'id': str(route.webhook_id)}}
            if interaction is not None and route.webhook_token == interaction['token'] and payload.get('type') == 4:
                data = payload.get('data') or {}
                ephemeral = bool(data.get('flags', 0) & 64)
                message_route = discord.http.Route('POST', '/channels/{channel_id}/messages',
                                                   channel_id=interaction['channel_id'])
                message = self.session.server.request(message_route, json=data, files=files,
                                                      private_owner=interaction['user_id'] if ephemeral else None)
                if message is not NotImplemented:
                    interaction['acknowledged'] = True
                    interaction['original_id'] = int(message['id'])
                    if not ephemeral:
                        self.session.bot._connection.parse_message_create(message)
                    self.session.transcript.record('out', 'interaction_acknowledged', {
                        'interaction_id': str(route.webhook_id), 'message_id': message['id'],
                    }, action_id=route.webhook_id)
                    return {'interaction': {'id': str(route.webhook_id), 'response_message_id': message['id'],
                                            'response_message_ephemeral': ephemeral},
                            'resource': {'type': 4, 'message': message}}
        if route.webhook_id == 1 and route.path in (
                '/webhooks/{webhook_id}/{webhook_token}/messages/@original',
                '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}',
                '/webhooks/{webhook_id}/{webhook_token}'):
            match = next(((key, item) for key, item in self.session._interactions.items()
                          if item['token'] == route.webhook_token), None)
            interaction_id, interaction = match if match is not None else (None, None)
            if (interaction is None or self.session.clock() - interaction['created_at'] >= 900
                    or not interaction.get('acknowledged')):
                self._unknown_interaction(route)
            if interaction is not None and interaction.get('acknowledged'):
                data = payload
                if (route.path.endswith('/@original') and route.method in ('GET', 'PATCH', 'DELETE')
                        and 'original_id' in interaction):
                    message_route = discord.http.Route(route.method, '/channels/{channel_id}/messages/{message_id}',
                                                       channel_id=interaction['channel_id'],
                                                       message_id=interaction['original_id'])
                    key = interaction['channel_id'], interaction['original_id']
                    private = key in self.session.server.private
                    if route.method == 'PATCH' and interaction.get('deferred_pending'):
                        data = dict(data)
                        data['flags'] = data.get('flags', self.session.server.messages[key]['flags']) & ~128
                    result = self.session.server.request(message_route, json=data, files=files, internal=True)
                    if result is not NotImplemented:
                        if route.method == 'PATCH':
                            interaction['deferred_pending'] = False
                        if route.method == 'PATCH' and not private:
                            self.session.bot._connection.parse_message_update(result)
                        elif route.method == 'DELETE' and not private:
                            self.session.bot._connection.parse_message_delete({
                                'id': str(key[1]), 'channel_id': str(key[0])})
                        return result
                if (route.path.endswith('/{message_id}') and route.method in ('GET', 'PATCH', 'DELETE')):
                    message_id = int(route.url.rsplit('/', 1)[-1])
                    if message_id not in interaction.get('followups', set()):
                        raise discord.NotFound(_Response(), {'message': 'Unknown Message', 'code': 10008})
                    key = interaction['channel_id'], message_id
                    private = key in self.session.server.private
                    message_route = discord.http.Route(route.method, '/channels/{channel_id}/messages/{message_id}',
                                                       channel_id=key[0], message_id=key[1])
                    result = self.session.server.request(message_route, json=data, files=files, internal=True)
                    if result is not NotImplemented:
                        if route.method == 'PATCH' and not private:
                            self.session.bot._connection.parse_message_update(result)
                        elif route.method == 'DELETE':
                            interaction['followups'].discard(message_id)
                            if not private:
                                self.session.bot._connection.parse_message_delete({
                                    'id': str(message_id), 'channel_id': str(key[0])})
                        return result
                if route.path == '/webhooks/{webhook_id}/{webhook_token}' and route.method == 'POST':
                    flags = data.get('flags', 0)
                    if interaction.get('deferred_pending'):
                        message_route = discord.http.Route(
                            'PATCH', '/channels/{channel_id}/messages/{message_id}',
                            channel_id=interaction['channel_id'], message_id=interaction['original_id'])
                        original_data = {key: value for key, value in data.items() if key != 'flags'}
                        key = interaction['channel_id'], interaction['original_id']
                        original_data['flags'] = self.session.server.messages[key]['flags'] & ~128
                        result = self.session.server.request(message_route, json=original_data, files=files,
                                                             internal=True)
                        if result is not NotImplemented:
                            interaction['deferred_pending'] = False
                            if key not in self.session.server.private:
                                self.session.bot._connection.parse_message_update(result)
                            return result
                    message_route = discord.http.Route('POST', '/channels/{channel_id}/messages',
                                                       channel_id=interaction['channel_id'])
                    result = self.session.server.request(message_route, json=data, files=files,
                                                         private_owner=interaction['user_id'] if flags & 64 else None)
                    if result is not NotImplemented:
                        interaction.setdefault('followups', set()).add(int(result['id']))
                        visibility = f"user:{interaction['user_id']}" if flags & 64 else 'public'
                        if not flags & 64:
                            self.session.bot._connection.parse_message_create(result)
                        self.session.transcript.record('out', 'followup_sent', result,
                                                       action_id=interaction_id, visibility=visibility)
                        return result
        # The route template deliberately avoids exposing webhook tokens.
        raise UnsupportedOperation(f"Unsupported Discord request: {route.method} {route.path}")

    def _unknown_interaction(self, route: Any) -> None:
        self.session.transcript.record('out', 'request_rejected', {'method': route.method, 'path': route.path})
        raise discord.NotFound(_Response(), {'message': 'Unknown interaction', 'code': 10062})

    def _reject_callback(self, route: Any, code: int, message: str) -> None:
        self.session.transcript.record('out', 'request_rejected', {
            'method': route.method, 'path': route.path, 'code': code,
        }, action_id=route.webhook_id)
        raise discord.HTTPException(_BadRequest(), {'message': message, 'code': code})


class Session:
    """Own a fresh client, its local transport, transcript and event tasks.

    ``configure`` runs after the client is initialized and before setup_hook.
    The bot is marked ready after setup_hook completes, without logging in.
    """

    def __init__(self, bot_factory: Callable[[], Any], *,
                 configure: Optional[Callable[[Session], Any]] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.bot_factory = bot_factory
        self.configure = configure
        self.clock = clock
        self.transcript = Transcript(clock=clock)
        self.runtime = Runtime()
        self.server = MessageServer(self.transcript)
        self.bot: Any = None
        self._entered = False
        self._closed = False
        self._webhook = _LocalWebhookAdapter(self)
        self._interactions: dict[int, dict[str, Any]] = {}
        self._next_interaction_id = 1100000000000000000
        self._entity_id = 1200000000000000000
        self._guilds: dict[str, Any] = {}
        self._users: dict[int, Any] = {}
        self._reactions = self.server.reactions
        self._reaction_emoji = self.server.reaction_emoji
        self._errors: list[tuple[int, BaseException]] = []
        self._error_sequence = 0
        self._views: dict[int, Any] = {}

    async def __aenter__(self) -> Session:
        if self._entered:
            raise RuntimeError("a session can only be entered once")
        self._entered = True
        legacy.register(self)
        try:
            bot = self.bot_factory()
            if inspect.isawaitable(bot):
                bot = await bot
            if not isinstance(bot, discord.Client):
                raise TypeError("bot_factory must return a discord.Client")
            self.bot = bot
            if bot.is_closed() or bot.is_ready():
                raise ValueError("bot_factory must return a fresh, unstarted client")
            bot.http.request = self._request
            bot.http.get_from_cdn = self._get_from_cdn
            await bot._async_setup_hook()
            bot._connection.user = discord.ClientUser(state=bot._connection, data={
                "id": "1", "username": "dpytest", "discriminator": "0000",
                "avatar": None, "bot": True,
            })
            bot._connection.application_id = 1
            original_event_error = bot.on_error

            async def event_error(event: str, *args: Any, **kwargs: Any) -> None:
                error = sys.exc_info()[1]
                if error is not None:
                    self._record_error(error, event)
                await original_event_error(event, *args, **kwargs)

            bot.on_error = event_error
            tree = getattr(bot, 'tree', None)
            if tree is not None:
                original_tree_error = tree.on_error

                async def tree_error(interaction: Any, error: Exception) -> None:
                    self._record_error(error, 'application_command', interaction.id)
                    await original_tree_error(interaction, error)

                tree.on_error = tree_error

            store_view = bot._connection.store_view

            def observe_view(view: Any) -> None:
                if id(view) not in self._views:
                    self._views[id(view)] = view
                    original_view_error = view.on_error

                    async def view_error(interaction: Any, error: Exception, *args: Any) -> None:
                        self._record_error(error, 'modal' if isinstance(view, discord.ui.Modal) else 'view',
                                           interaction.id)
                        await original_view_error(interaction, error, *args)

                    view.on_error = view_error

            for view in bot.persistent_views:
                observe_view(view)

            def track_view(view: Any, message_id: Optional[int] = None) -> None:
                observe_view(view)
                store_view(view, message_id)

            bot._connection.store_view = track_view
            schedule = bot._schedule_event

            def schedule_event(*args: Any, **kwargs: Any) -> Any:
                token = async_context.set(self._webhook)
                try:
                    return self.runtime.track(schedule(*args, **kwargs))
                finally:
                    async_context.reset(token)

            bot._schedule_event = schedule_event
            token = async_context.set(self._webhook)
            try:
                if self.configure is not None:
                    result = self.configure(self)
                    if inspect.isawaitable(result):
                        await result
                await bot.setup_hook()
            finally:
                async_context.reset(token)
            bot._ready.set()
            return self
        except BaseException:
            await self.close()
            raise

    async def _request(self, route: Any, **kwargs: Any) -> Any:
        if self._closed:
            raise RuntimeError('session is closed')
        reaction = re.fullmatch(r'https://discord\.com/api/v\d+/channels/(\d+)/messages/(\d+)/reactions'
                                r'(?:/([^/]+))?(?:/([^/]+))?', route.url)
        if reaction:
            channel_id, message_id = int(reaction[1]), int(reaction[2])
            emoji = unquote(reaction[3]) if reaction[3] is not None else None
            target = reaction[4]
            if route.method == 'PUT' and emoji is not None and target == '@me':
                self._change_reaction(channel_id, message_id, 1, emoji, add=True, direction='out')
                return None
            if route.method == 'DELETE' and emoji is not None and target is not None:
                user_id = 1 if target == '@me' else int(target)
                self._change_reaction(channel_id, message_id, user_id, emoji, add=False, direction='out')
                return None
            if route.method == 'DELETE' and target is None:
                self._clear_reactions(channel_id, message_id, emoji)
                return None
        checkpoint = self.transcript.checkpoint()
        result = self.server.request(route, **kwargs)
        if result is not NotImplemented:
            if (route.method == 'POST' and route.path == '/channels/{channel_id}/messages'
                    and self.transcript.query(after=checkpoint, kind='message_created')):
                self.bot._connection.parse_message_create(result)
            elif route.path == '/channels/{channel_id}/messages/{message_id}':
                if route.method == 'PATCH':
                    self.bot._connection.parse_message_update(result)
                elif route.method == 'DELETE':
                    deleted = self.transcript.query(after=checkpoint, kind='message_deleted')[0]
                    self.bot._connection.parse_message_delete({
                        'id': deleted.payload['id'], 'channel_id': deleted.payload['channel_id']})
            return result
        self.transcript.record("out", "request_rejected", {
            "method": route.method, "path": route.path,
        })
        raise UnsupportedOperation(f"Unsupported Discord request: {route.method} {route.path}")

    async def _get_from_cdn(self, url: str) -> bytes:
        if self._closed:
            raise RuntimeError('session is closed')
        if url not in self.server.attachments:
            raise discord.NotFound(_Response(), {'message': 'Unknown attachment', 'code': 10015})
        return self.server.attachments[url]

    def _record_error(self, error: BaseException, source: str, action_id: Optional[int] = None) -> None:
        self._error_sequence += 1
        self._errors.append((self._error_sequence, error))
        self.transcript.record('internal', 'callback_failure', {
            'error_id': self._error_sequence, 'source': source, 'type': type(error).__name__,
        }, action_id=action_id)

    def create_task(self, coroutine: Coroutine[Any, Any, Any], *, name: Optional[str] = None) -> asyncio.Task[Any]:
        """Register application background work for teardown and error reporting."""
        task = self.runtime.create_task(coroutine, name=name)

        def report(done: asyncio.Task[Any]) -> None:
            if not done.cancelled():
                error = done.exception()
                if error is not None:
                    self._record_error(error, 'background_task')

        task.add_done_callback(report)
        return task

    async def expect_error(self, error_type: type, *, timeout: float = 1.0) -> BaseException:
        """Acknowledge and return a callback failure of the requested type."""
        def matching(item: Any) -> bool:
            return item.kind == 'callback_failure' and any(
                number == item.payload['error_id'] and isinstance(error, error_type)
                for number, error in self._errors)

        record = await self.transcript.expect(matching, timeout=timeout)
        for index, (number, error) in enumerate(self._errors):
            if number == record.payload['error_id']:
                self._errors.pop(index)
                return error
        raise RuntimeError('callback failure was already acknowledged')

    async def _expect_observation(self, predicate: Callable[[Any], bool], *, action_id: int,
                                  expected: str, timeout: float) -> Any:
        try:
            return await self.transcript.expect(predicate, timeout=timeout)
        except TimeoutError as exc:
            failures = self.transcript.query(kind='callback_failure', action_id=action_id)
            pending = [task.get_name() for task in self.runtime.pending]
            error_ids = {item.payload['error_id'] for item in failures}
            relevant_errors = [error for number, error in self._errors if number in error_ids]
            details = [type(error).__name__ for error in relevant_errors]
            message = (f'Action {action_id}: timed out expecting {expected}; '
                       f'callback errors: {details}; pending owned tasks: {pending}; '
                       f'recent observations: {self.transcript.query()[-5:]!r}')
            raise TimeoutError(message) from (relevant_errors[-1] if relevant_errors else exc)

    def inject_slash(self, name: str, *, channel_id: int, user_id: int,
                     options: Optional[dict[str, Any]] = None, focused: Optional[str] = None) -> int:
        """Dispatch a registered slash command through discord.py."""
        if self.bot is None or not self.bot.is_ready():
            raise RuntimeError('session is not ready')
        tree = getattr(self.bot, 'tree', None)
        parts = name.split()
        command = tree.get_command(parts[0]) if tree is not None and parts else None
        for part in parts[1:]:
            command = command.get_command(part) if isinstance(command, discord.app_commands.Group) else None
        if command is None:
            raise ValueError(f'Unknown application command: {name}')
        if not isinstance(command, discord.app_commands.Command):
            raise ValueError(f'Application command requires a subcommand: {name}')
        supplied = options or {}
        parameters = {parameter.display_name: parameter for parameter in command.parameters}
        unknown = supplied.keys() - parameters.keys()
        if unknown:
            raise ValueError(f'Unknown command options: {sorted(unknown)}')
        if focused is not None and (focused not in supplied or focused not in parameters
                                    or not parameters[focused].autocomplete):
            raise ValueError('Focused option must have a value and autocomplete handler')
        missing = [parameter.display_name for parameter in command.parameters
                   if parameter.required and parameter.display_name not in supplied]
        if missing and focused is None:
            raise ValueError(f'Missing required command options: {missing}')
        option_payloads = []
        resolved_users: dict[str, Any] = {}
        for option_name, value in supplied.items():
            parameter = parameters[option_name]
            option_type = parameter.type
            if option_type == discord.AppCommandOptionType.user:
                from .actors import Actor
                if not isinstance(value, Actor) or value._session is not self or value.id not in self._users:
                    raise ValueError(f'Option {option_name} must be an actor in this session')
                target_id = str(value.id)
                resolved_users[target_id] = {'id': target_id, 'username': f'actor-{target_id}',
                                             'discriminator': '0000', 'avatar': None}
                option_payloads.append({'name': option_name, 'type': option_type.value, 'value': target_id})
                continue
            types = {discord.AppCommandOptionType.string: str, discord.AppCommandOptionType.integer: int,
                     discord.AppCommandOptionType.boolean: bool, discord.AppCommandOptionType.number: (int, float)}
            expected = types.get(option_type)
            if expected is None:
                raise UnsupportedOperation(f'Command option type {option_type.name} is not yet supported')
            if (not isinstance(value, expected) or
                    (isinstance(value, bool) and option_type != discord.AppCommandOptionType.boolean)):
                raise ValueError(f'Invalid value type for option {option_name}')
            if (focused != option_name and parameter.choices
                    and value not in [choice.value for choice in parameter.choices]):
                raise ValueError(f'Invalid choice for option {option_name}')
            comparable = len(value) if isinstance(value, str) else value
            if focused != option_name and parameter.min_value is not None and comparable < parameter.min_value:
                raise ValueError(f'Option {option_name} is below its minimum')
            if focused != option_name and parameter.max_value is not None and comparable > parameter.max_value:
                raise ValueError(f'Option {option_name} is above its maximum')
            option_payloads.append({'name': option_name, 'type': option_type.value, 'value': value})
            if option_name == focused:
                option_payloads[-1]['focused'] = True
        self._next_interaction_id += 1
        interaction_id = self._next_interaction_id
        token_value = secrets.token_urlsafe(24)
        for index in range(len(parts) - 1, 0, -1):
            option_payloads = [{'name': parts[index], 'type': 1 if index == len(parts) - 1 else 2,
                                'options': option_payloads}]
        payload = {'id': str(interaction_id), 'application_id': '1', 'type': 4 if focused is not None else 2,
                   'token': token_value, 'version': 1, 'attachment_size_limit': 10485760,
                   'channel_id': str(channel_id),
                   'user': {'id': str(user_id), 'username': 'actor', 'discriminator': '0000', 'avatar': None},
                   'data': {'id': '1', 'name': parts[0], 'type': 1, 'options': option_payloads}}
        if resolved_users:
            payload['data']['resolved'] = {'users': resolved_users}
        self._dispatch_interaction(payload, channel_id, user_id)
        return interaction_id

    def _next_entity_id(self) -> int:
        self._entity_id += 1
        return self._entity_id

    def create_guild(self, name: str) -> Any:
        """Configure a guild before or after startup; names are unique per session."""
        if self.bot is None or self._closed:
            raise RuntimeError('session is not initialized')
        if name in self._guilds:
            raise ValueError(f'Guild already exists: {name}')
        from .guilds import GuildSetup
        guild = GuildSetup(self, name, self._next_entity_id())
        self._guilds[name] = guild
        return guild

    def guild(self, name: str) -> Any:
        return self._guilds[name]

    def actor(self, user_id: int, *, name: Optional[str] = None) -> Any:
        """Return a simulated user for the currently supported interaction actions."""
        from .actors import Actor
        if self.bot is None or self._closed:
            raise RuntimeError('session is not initialized')
        if user_id not in self._users:
            self._users[user_id] = self.bot._connection.store_user({
                'id': str(user_id), 'username': name or f'actor-{user_id}',
                'discriminator': '0000', 'avatar': None})
        return Actor(self, user_id)

    def inject_context_menu(self, name: str, *, channel_id: int, user_id: int,
                            target_id: int, target_type: discord.AppCommandType) -> int:
        """Dispatch a registered user or message context menu with resolved data."""
        if self.bot is None or not self.bot.is_ready():
            raise RuntimeError('session is not ready')
        if target_type not in (discord.AppCommandType.user, discord.AppCommandType.message):
            raise ValueError('Expected a user or message context menu')
        tree = getattr(self.bot, 'tree', None)
        if tree is None or tree.get_command(name, type=target_type) is None:
            raise ValueError(f'Unknown context menu: {name}')
        target = str(target_id)
        if target_type == discord.AppCommandType.user:
            if target_id not in self._users:
                raise ValueError('Unknown target user')
            resolved = {'users': {target: {'id': target, 'username': f'actor-{target_id}',
                                           'discriminator': '0000', 'avatar': None}}}
        else:
            key = channel_id, target_id
            message = self.server.messages.get(key)
            owner = self.server.private.get(key)
            if message is None or (owner is not None and owner != user_id):
                raise ValueError('Unknown target message')
            resolved = {'messages': {target: copy.deepcopy(message)}}
        self._next_interaction_id += 1
        interaction_id = self._next_interaction_id
        payload = {'id': str(interaction_id), 'application_id': '1', 'type': 2,
                   'token': secrets.token_urlsafe(24), 'version': 1, 'attachment_size_limit': 10485760,
                   'channel_id': str(channel_id),
                   'user': {'id': str(user_id), 'username': 'actor', 'discriminator': '0000', 'avatar': None},
                   'data': {'id': '1', 'name': name, 'type': target_type.value,
                            'target_id': target, 'resolved': resolved}}
        self._dispatch_interaction(payload, channel_id, user_id)
        return interaction_id

    def inject_message(self, *, channel_id: int, user_id: int, content: str) -> Any:
        """Create a user message in server state and dispatch its Gateway event."""
        if self.bot is None or not self.bot.is_ready():
            raise RuntimeError('session is not ready')
        if user_id not in self._users:
            raise ValueError('Unknown actor')
        guild_id = self.server.channel_guilds.get(channel_id)
        if guild_id is not None and self.bot.get_guild(guild_id).get_member(user_id) is None:
            raise ValueError('Actor is not a member of this guild')
        if not isinstance(content, str):
            raise TypeError('message content must be a string')
        route = discord.http.Route('POST', '/channels/{channel_id}/messages', channel_id=channel_id)
        checkpoint = self.transcript.checkpoint()
        data = self.server.request(route, json={'content': content}, direction='in',
                                   author={'id': str(user_id), 'username': self._users[user_id].name,
                                           'discriminator': '0000', 'avatar': None})
        self.bot._connection.parse_message_create(data)
        return self.transcript.query(after=checkpoint, kind='message_created')[0]

    def change_actor_message(self, *, channel_id: int, message_id: int, user_id: int,
                             content: Optional[str] = None, delete: bool = False) -> Any:
        if self._closed:
            raise RuntimeError('session is closed')
        message = self.server.messages.get((channel_id, message_id))
        if message is None or int(message['author']['id']) != user_id:
            raise ValueError('Message not owned by actor')
        if not delete and not isinstance(content, str):
            raise TypeError('message content must be a string')
        route = discord.http.Route('DELETE' if delete else 'PATCH', '/channels/{channel_id}/messages/{message_id}',
                                   channel_id=channel_id, message_id=message_id)
        checkpoint = self.transcript.checkpoint()
        data = self.server.request(route, json={} if delete else {'content': content}, direction='in')
        if delete:
            self.bot._connection.parse_message_delete({'id': str(message_id), 'channel_id': str(channel_id)})
        else:
            self.bot._connection.parse_message_update(data)
        kind = 'message_deleted' if delete else 'message_edited'
        return self.transcript.query(after=checkpoint, kind=kind)[0]

    def evict_message(self, message_id: int) -> None:
        """Evict the client cache projection without deleting server state."""
        messages = self.bot._connection._messages
        if messages is not None:
            for message in tuple(messages):
                if message.id == message_id:
                    messages.remove(message)
                    return

    def add_reaction(self, *, channel_id: int, message_id: int, user_id: int, emoji: Any) -> None:
        self._change_reaction(channel_id, message_id, user_id, emoji, add=True, direction='in')

    def remove_reaction(self, *, channel_id: int, message_id: int, user_id: int, emoji: Any) -> None:
        self._change_reaction(channel_id, message_id, user_id, emoji, add=False, direction='in')

    def _change_reaction(self, channel_id: int, message_id: int, user_id: int, emoji: Any, *,
                         add: bool, direction: str) -> None:
        if self._closed:
            raise RuntimeError('session is closed')
        if (channel_id, message_id) not in self.server.messages:
            raise ValueError('Unknown message')
        owner = self.server.private.get((channel_id, message_id))
        if owner is not None:
            raise ValueError('Reactions on ephemeral messages are not supported')
        guild_id = self.server.channel_guilds.get(channel_id)
        member = None
        if guild_id is not None:
            member = self.bot.get_guild(guild_id).get_member(user_id)
            if member is None:
                raise ValueError('User is not a member of this guild')
        if isinstance(emoji, discord.Emoji):
            partial = discord.PartialEmoji(name=emoji.name, id=emoji.id, animated=emoji.animated)
        else:
            partial = discord.PartialEmoji.from_str(emoji) if isinstance(emoji, str) else emoji
        if not isinstance(partial, discord.PartialEmoji):
            raise TypeError('emoji must be a string, Emoji or PartialEmoji')
        identity = f'id:{partial.id}' if partial.id is not None else f'unicode:{partial.name}'
        key = channel_id, message_id, identity
        if not add and key not in self._reactions:
            return
        members = self._reactions.setdefault(key, set())
        if add:
            if user_id in members:
                return
            members.add(user_id)
        else:
            if user_id not in members:
                return
            members.remove(user_id)
            if not members:
                del self._reactions[channel_id, message_id, identity]
        payload = {'channel_id': str(channel_id), 'message_id': str(message_id), 'user_id': str(user_id),
                   'emoji': {'id': str(partial.id) if partial.id else None, 'name': partial.name,
                             'animated': partial.animated}, 'type': 0, 'burst': False}
        if guild_id is not None:
            payload['guild_id'] = str(guild_id)
            if add:
                payload['member'] = {
                    'user': {'id': str(user_id), 'username': member.name, 'discriminator': '0000',
                             'avatar': None, 'bot': member.bot},
                    'roles': [], 'flags': 0, 'joined_at': None, 'deaf': False, 'mute': False,
                }
        if key in self._reactions:
            self._reaction_emoji[key] = payload['emoji']
        else:
            self._reaction_emoji.pop(key, None)
        self._sync_reactions(channel_id, message_id)
        self.transcript.record(direction, 'reaction_added' if add else 'reaction_removed', payload,
                               visibility=f'user:{owner}' if owner is not None else 'public')
        parser = (self.bot._connection.parse_message_reaction_add if add
                  else self.bot._connection.parse_message_reaction_remove)
        parser(payload)

    def _clear_reactions(self, channel_id: int, message_id: int, emoji: Any) -> None:
        if (channel_id, message_id) not in self.server.messages:
            raise ValueError('Unknown message')
        if (channel_id, message_id) in self.server.private:
            raise ValueError('Reactions on ephemeral messages are not supported')
        partial = discord.PartialEmoji.from_str(emoji) if emoji is not None else None
        identity = (f'id:{partial.id}' if partial.id is not None else f'unicode:{partial.name}') if partial else None
        keys = [key for key in self._reactions if key[:2] == (channel_id, message_id)
                and (identity is None or key[2] == identity)]
        for key in keys:
            del self._reactions[key]
            self._reaction_emoji.pop(key, None)
        self._sync_reactions(channel_id, message_id)
        payload: dict[str, Any] = {'channel_id': str(channel_id), 'message_id': str(message_id)}
        guild_id = self.server.channel_guilds.get(channel_id)
        if guild_id is not None:
            payload['guild_id'] = str(guild_id)
        if partial is not None:
            payload['emoji'] = {'id': str(partial.id) if partial.id else None, 'name': partial.name,
                                'animated': partial.animated}
        owner = self.server.private.get((channel_id, message_id))
        self.transcript.record('out', 'reaction_cleared', payload,
                               visibility=f'user:{owner}' if owner is not None else 'public')
        parser = (self.bot._connection.parse_message_reaction_remove_emoji if partial
                  else self.bot._connection.parse_message_reaction_remove_all)
        parser(payload)

    def _sync_reactions(self, channel_id: int, message_id: int) -> None:
        self.server.messages[channel_id, message_id]['reactions'] = [
            {'emoji': self._reaction_emoji[key], 'count': len(users), 'me': 1 in users,
             'count_details': {'normal': len(users), 'burst': 0}}
            for key, users in self._reactions.items() if key[:2] == (channel_id, message_id)
        ]

    def inject_click(self, message_id: int, *, channel_id: int, user_id: int, custom_id: str) -> int:
        """Dispatch a button click after validating the server's message components."""
        return self._inject_component(message_id, channel_id, user_id, custom_id, 2, None)

    def inject_select(self, message_id: int, *, channel_id: int, user_id: int,
                      custom_id: str, values: list[str]) -> int:
        """Dispatch a string select using options from the sent message."""
        return self._inject_component(message_id, channel_id, user_id, custom_id, 3, values)

    def _inject_component(self, message_id: int, channel_id: int, user_id: int, custom_id: str,
                          component_type: int, values: Optional[list[str]]) -> int:
        if self._closed:
            raise RuntimeError('session is closed')
        message = self.server.messages.get((channel_id, message_id))
        owner = self.server.private.get((channel_id, message_id))
        if message is None or (owner is not None and owner != user_id):
            raise ValueError('Unknown message')
        components = [component for row in message.get('components', [])
                      for component in row.get('components', []) if component.get('custom_id') == custom_id]
        name = 'Button' if component_type == 2 else 'Select'
        if len(components) != 1 or components[0].get('disabled') or components[0].get('type') != component_type:
            raise ValueError(f'{name} is missing, ambiguous, disabled, or unsupported')
        if component_type == 3:
            component = components[0]
            allowed = {option['value'] for option in component.get('options', [])}
            if (not isinstance(values, list) or any(not isinstance(value, str) for value in values)
                    or len(values) != len(set(values)) or not set(values) <= allowed
                    or not component.get('min_values', 1) <= len(values) <= component.get('max_values', 1)):
                raise ValueError('Invalid select values')
        self._next_interaction_id += 1
        interaction_id = self._next_interaction_id
        payload = {'id': str(interaction_id), 'application_id': '1', 'type': 3,
                   'token': secrets.token_urlsafe(24), 'version': 1, 'attachment_size_limit': 10485760,
                   'channel_id': str(channel_id), 'message': message,
                   'user': {'id': str(user_id), 'username': 'actor', 'discriminator': '0000', 'avatar': None},
                   'data': {'custom_id': custom_id, 'component_type': component_type}}
        if values is not None:
            payload['data']['values'] = values
        self._dispatch_interaction(payload, channel_id, user_id)
        return interaction_id

    def inject_modal_submit(self, opened_by: int, *, user_id: int, fields: dict[str, str]) -> int:
        """Submit text fields from a modal opened for this user."""
        if self._closed:
            raise RuntimeError('session is closed')
        origin = self._interactions.get(opened_by)
        if origin is None or origin.get('user_id') != user_id or 'modal' not in origin or origin.get('submitted'):
            raise ValueError('Modal is unavailable for this user')
        modal = origin['modal']
        components = [component for row in modal['components'] for component in row.get('components', [])]
        if any(component.get('type') != 4 for component in components):
            raise ValueError('Unsupported modal field type')
        allowed = {component['custom_id']: component for component in components}
        if len(allowed) != len(components) or set(fields) - set(allowed):
            raise ValueError('Unknown or ambiguous modal field')
        for custom_id, component in allowed.items():
            value = fields.get(custom_id, '')
            if not isinstance(value, str) or (component.get('required', True) and not value):
                raise ValueError(f'Invalid required field: {custom_id}')
            if len(value) < component.get('min_length', 0) or len(value) > component.get('max_length', 4000):
                raise ValueError(f'Invalid field length: {custom_id}')
        self._next_interaction_id += 1
        interaction_id = self._next_interaction_id
        payload = {'id': str(interaction_id), 'application_id': '1', 'type': 5,
                   'token': secrets.token_urlsafe(24), 'version': 1, 'attachment_size_limit': 10485760,
                   'channel_id': str(origin['channel_id']),
                   'user': {'id': str(user_id), 'username': 'actor', 'discriminator': '0000', 'avatar': None},
                   'data': {'custom_id': modal['custom_id'], 'components': [
                       {'type': 1, 'components': [{'type': 4, 'custom_id': custom_id,
                                                   'value': fields.get(custom_id, '')}]}
                       for custom_id in allowed]}}
        self._dispatch_interaction(payload, origin['channel_id'], user_id)
        origin['submitted'] = True
        return interaction_id

    def _dispatch_interaction(self, payload: dict[str, Any], channel_id: int, user_id: int) -> None:
        interaction_id = int(payload['id'])
        guild_id = self.server.channel_guilds.get(channel_id)
        if guild_id is None:
            payload.setdefault('channel', {'id': str(channel_id), 'type': 1, 'recipients': [payload['user']]})
        else:
            guild = self.bot.get_guild(guild_id)
            member = guild.get_member(user_id)
            if member is None:
                raise ValueError('Actor is not a member of this guild')
            user_data = payload.pop('user')
            user_data['username'] = member.name
            payload['guild_id'] = str(guild_id)
            payload['channel'] = {'id': str(channel_id), 'type': 0, 'name': guild.get_channel(channel_id).name,
                                  'position': 0, 'permission_overwrites': []}
            payload['member'] = {'user': user_data, 'roles': [], 'flags': 0,
                                 'permissions': str(discord.Permissions.all().value), 'joined_at': None,
                                 'deaf': False, 'mute': False}
            resolved = payload.get('data', {}).get('resolved', {})
            members = {}
            for target_id in resolved.get('users', {}):
                target = guild.get_member(int(target_id))
                if target is not None:
                    members[target_id] = {'roles': [], 'flags': 0, 'joined_at': None, 'deaf': False, 'mute': False}
            if members:
                resolved['members'] = members
        self._interactions[interaction_id] = {'token': payload['token'], 'channel_id': channel_id,
                                              'user_id': user_id, 'created_at': self.clock(), 'type': payload['type']}
        if payload['type'] == 3:
            self._interactions[interaction_id]['source_message_id'] = int(payload['message']['id'])
        self.transcript.record('in', 'input_accepted', {'interaction_id': str(interaction_id)},
                               action_id=interaction_id)
        token = async_context.set(self._webhook)
        loop = asyncio.get_running_loop()
        previous_factory = loop.get_task_factory()

        def track_dispatch_task(task_loop: Any, coroutine: Any, **kwargs: Any) -> Any:
            if previous_factory is None:
                task = asyncio.Task(coroutine, loop=task_loop, **kwargs)
            else:
                task = previous_factory(task_loop, coroutine, **kwargs)
            return self.runtime.track(task)

        try:
            # Parsing schedules command, view, modal and event callbacks synchronously.
            # Restrict the factory to that synchronous call; never scan loop tasks.
            loop.set_task_factory(track_dispatch_task)
            self.bot._connection.parse_interaction_create(payload)
        finally:
            loop.set_task_factory(previous_factory)
            async_context.reset(token)

    async def close(self) -> None:
        self._closed = True
        for view in self._views.values():
            view.stop()
        self._views.clear()
        try:
            await self.runtime.close()
        finally:
            try:
                if self.bot is not None:
                    await self.bot.close()
            finally:
                self.server.attachments.clear()
                legacy.unregister(self)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()
        if exc is None and self._errors:
            raise RuntimeError(f'{len(self._errors)} unexpected callback failure(s); '
                               f'recent transcript: {self.transcript.query()[-5:]!r}') from self._errors[0][1]
