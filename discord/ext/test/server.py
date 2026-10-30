"""Session-owned simulated server operations for ordinary messages."""
from __future__ import annotations

import copy
import datetime
import json
import re
from typing import Any

import discord

from .observations import Transcript


class _Response:
    status = 404
    reason = "Not Found"


class MessageServer:
    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript
        self.messages: dict[tuple[int, int], dict[str, Any]] = {}
        self.private: dict[tuple[int, int], int] = {}
        self.channel_guilds: dict[int, int] = {}
        self._next_id = 1000000000000000000
        self.attachments: dict[str, bytes] = {}
        self.reactions: dict[tuple[int, int, str], set[int]] = {}
        self.reaction_emoji: dict[tuple[int, int, str], dict[str, Any]] = {}

    def request(self, route: Any, **kwargs: Any) -> Any:
        match = re.fullmatch(r"https://discord\.com/api/v\d+/channels/(\d+)/messages(?:/(\d+))?", route.url)
        if match is None:
            return NotImplemented
        channel_id = int(match.group(1))
        message_id = int(match.group(2)) if match.group(2) else None
        method = route.method
        form = kwargs.get("form") or []
        if form:
            payload_json = next((item['value'] for item in form if item.get('name') == 'payload_json'), None)
            if payload_json is None:
                return NotImplemented
            payload = json.loads(payload_json)
        else:
            payload = copy.deepcopy(kwargs.get("json") or {})
        files = kwargs.get('files') or []
        supported = {"content", "embeds", "components", "flags", "tts", "nonce", "enforce_nonce", "attachments"}
        if set(payload) - supported:
            return NotImplemented
        if method == "POST" and message_id is None:
            if payload.get("enforce_nonce") and payload.get("nonce") is not None:
                for (stored_channel, _), stored in self.messages.items():
                    if stored_channel == channel_id and stored.get("nonce") == payload["nonce"]:
                        return copy.deepcopy(stored)
            self._next_id += 1
            message_id = self._next_id
            attachments = self._attachments(payload.get('attachments', []), files, [])
            message = {
                "id": str(message_id), "channel_id": str(channel_id),
                "author": kwargs.get('author') or {
                    "id": "1", "username": "dpytest", "discriminator": "0000", "avatar": None, "bot": True},
                "content": payload.get("content") or "", "timestamp": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(), "edited_timestamp": None,
                "tts": payload.get("tts", False), "mention_everyone": False,
                "mentions": [], "mention_roles": [], "attachments": attachments,
                "embeds": payload.get("embeds", []), "pinned": False, "type": 0,
                "components": payload.get("components", []), "flags": payload.get("flags", 0),
            }
            if channel_id in self.channel_guilds:
                message['guild_id'] = str(self.channel_guilds[channel_id])
            if "nonce" in payload:
                message["nonce"] = payload["nonce"]
            self.messages[channel_id, message_id] = message
            owner = kwargs.get("private_owner")
            if owner is not None:
                self.private[channel_id, message_id] = owner
            self.transcript.record(kwargs.get('direction', 'out'), "message_created", message,
                                   visibility=f"user:{owner}" if owner is not None else "public")
            return copy.deepcopy(message)
        if message_id is None or method not in ("GET", "PATCH", "DELETE"):
            return NotImplemented
        key = channel_id, message_id
        if key not in self.messages or (key in self.private and not kwargs.get("internal")):
            raise discord.NotFound(_Response(), {"message": "Unknown Message", "code": 10008})
        message = self.messages[key]
        if method == "GET":
            return copy.deepcopy(message)
        if method == "DELETE":
            del self.messages[key]
            owner = self.private.pop(key, None)
            for reaction_key in [item for item in self.reactions if item[:2] == key]:
                del self.reactions[reaction_key]
                self.reaction_emoji.pop(reaction_key, None)
            self.transcript.record(kwargs.get('direction', 'out'), "message_deleted", message,
                                   visibility=f"user:{owner}" if owner is not None else "public")
            return None
        if 'attachments' in payload:
            message['attachments'] = self._attachments(payload['attachments'], files, message['attachments'])
        for field in ("content", "embeds", "components", "flags"):
            if field in payload:
                if field == 'flags' and key in self.private:
                    message[field] = (payload[field] or 0) | 64
                else:
                    message[field] = payload[field] if payload[field] is not None else (
                        "" if field == "content" else [])
        message["edited_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        owner = self.private.get(key)
        self.transcript.record(kwargs.get('direction', 'out'), "message_edited", message,
                               visibility=f"user:{owner}" if owner is not None else "public")
        return copy.deepcopy(message)

    def _attachments(self, entries: list[dict[str, Any]], files: Any,
                     existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for entry in entries:
            identifier = int(entry['id'])
            prior = next((item for item in existing if int(item['id']) == identifier), None)
            if prior is not None:
                result.append(copy.deepcopy(prior))
                continue
            if identifier < 0 or identifier >= len(files):
                raise ValueError('Unknown attachment')
            file = files[identifier]
            content = file.fp.read()
            self._next_id += 1
            attachment_id = self._next_id
            url = f'https://dpytest.invalid/attachments/{attachment_id}'
            self.attachments[url] = content
            result.append({'id': str(attachment_id), 'filename': file.filename, 'size': len(content),
                           'url': url, 'proxy_url': url, 'description': entry.get('description')})
        return result
