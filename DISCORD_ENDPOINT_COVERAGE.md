# Discord API endpoint coverage audit

Snapshot: 2026-10-31. Baseline: Discord API v10 [stable OpenAPI specification](https://github.com/discord/discord-api-spec/blob/main/specs/openapi.json), SHA-256 `281a2bff563d77a19e51fc3bf8bbe3ebcef28e3dc86684ae395b06ac51ba7484`; local dpytest working tree; locally installed discord.py **2.7.1** (the project declares `discord.py ~= 2.3`, so other allowed versions may differ). The spec repository describes this specification itself as a public preview and says its documentation takes precedence on discrepancies. The experimental `openapi_preview.json` is excluded.

This is an audit of HTTP method and exact path coverage, not a claim of complete functional compatibility. Each spec operation is listed once below. Results are static analysis candidates: request parameters, API permissions, response shapes, behavioral fidelity, and high-level public method reachability were not exhaustively verified. Equivalent or legacy endpoints may provide similar behavior, but do not constitute an exact route match.

## Results

- 250 stable-spec operations examined; 71 have no exact discord.py route found, 130 have an HTTPClient route without a matching dpytest override, 13 are handled by a separate discord.py webhook/interaction adapter, and 36 have a corresponding FakeHttp override.
- The dpytest override count is an upper bound on potentially supported operations, not a guarantee that every request, option, or caller works. The remaining operations are missing an identified dpytest fake; adapter routes require separate interception and do not automatically hit FakeHttp.request.
- discord.py is a bot library, so OAuth, partner SDK, webhook ingestion, and other specialized endpoints may be intentionally outside its scope. “No exact route” is not a judgment that upstream should implement it.

## How to read the inventory

- **Fake override**: a matching discord.py HTTPClient route has a same-named method in [FakeHttp](discord/ext/test/backend.py). That method is present, but may be incomplete or incompatible.
- **No fake**: discord.py has an HTTPClient route, but FakeHttp has no corresponding override. If that inherited HTTP method calls FakeHttp.request, it raises `NotImplementedError` ([source](discord/ext/test/backend.py#L102)).
- **Adapter**: discord.py has an exact route in its webhook or interaction adapter. FakeHttp is not the adapter, and no dpytest adapter fake was identified; runtime behavior should be checked separately.
- **No route found**: no matching route was found in the inspected discord.py HTTPClient or webhook adapters. dpytest has no identified exact-route implementation either. This is a scoped static finding, not proof that functionality cannot be reached through another API or equivalent route.

Routes were extracted from literal and formatted `Route(method, path)` calls in the installed `discord/http.py`, `discord/webhook/async_.py`, and `discord/webhook/sync.py`; HTTP method and path segments were matched after replacing parameter names with placeholders. The OpenAPI operation ID is included to make each entry easy to trace. The adapter classification does not prove interception or actual network behavior. Fake methods were matched by name; operations with multiple routes or conditional method logic need manual checks. The HTTP inventory excludes CDN URLs, OAuth browser flows, undocumented routes, and all behavior absent from the stable spec. Gateway coverage is assessed separately below.

## Known caveats and partial implementations

- `FakeHttp.create_channel` handles text, category, and voice branches, but explicitly raises for other channel types ([source](discord/ext/test/backend.py#L125)).
- Pin and unpin fake methods invoke backend helpers that emit a pins update event; the helpers do not model a persistent pinned-message collection ([source](discord/ext/test/backend.py#L1248)). An override therefore does not establish full pin behavior.
- `GET /applications/@me` has no exact matching route in this discord.py version: its `application_info` uses the older `/oauth2/applications/@me` route, which dpytest overrides. Similarly, deprecated pin routes and their replacements should be considered separately.
- Webhook and interaction requests use discord.py adapter classes rather than the normal HTTPClient; configuring FakeHttp alone does not establish that these requests are simulated.
- The installed discord.py source is version-specific. This report does not audit the current upstream development branch or every version accepted by the dependency declaration.

## Gateway events and control opcodes

Baseline: Discord [Gateway Events](https://docs.discord.com/developers/events/gateway-events) and [Gateway opcodes](https://docs.discord.com/developers/topics/opcodes-and-status-codes#gateway) as reviewed on 2026-10-31, alongside the same local discord.py 2.7.1 and dpytest working tree. These are Gateway events, not HTTP endpoints. The separate voice Gateway protocol is covered after the main Gateway inventory.

For dispatch events, discord.py maps an event name to a `ConnectionState.parse_<event>` method; `READY` and `RESUMED` also receive special gateway processing. The parser column identifies a method, not a guarantee of full payload, cache, intent, or public callback support. “No parser found” means no corresponding method in the inspected `ConnectionState`; raw socket access or an equivalent feature may still exist.

dpytest inherits discord.py parsers but does not thereby simulate all events: its backend generates selected payloads by direct parser calls. “Direct call” names an observed source call, not proof all use cases are supported. “No direct call found” means no matching `parse_*` call in `discord/ext/test`; it does not rule out manual parser invocation, generic dispatch, or other indirect ways to stimulate callbacks. Setup and event payload validity, intents, cache conditions, edge cases, and behavior were not comprehensively tested. Direct calls bypass actual Gateway framing, session lifecycle, and network delivery.

The fake websocket overrides `send` and `change_presence` ([source](discord/ext/test/websocket.py#L31)); an unrecognized send raises `ValueError`. [FakeState](discord/ext/test/state.py#L24) inherits discord.py parsing, substitutes its own channel creation parser, and stubs member chunk/query behavior. This is distinct from a fully simulated Gateway connection.

### Receive dispatch events

| Discord dispatch event | discord.py 2.7.1 | dpytest source evidence |
| --- | --- | --- |
| `APPLICATION_COMMAND_PERMISSIONS_UPDATE` | `parse_application_command_permissions_update` (state.py:1659) | No direct parser call found |
| `AUTO_MODERATION_RULE_CREATE` | `parse_auto_moderation_rule_create` (state.py:1210) | No direct parser call found |
| `AUTO_MODERATION_RULE_UPDATE` | `parse_auto_moderation_rule_update` (state.py:1220) | No direct parser call found |
| `AUTO_MODERATION_RULE_DELETE` | `parse_auto_moderation_rule_delete` (state.py:1230) | No direct parser call found |
| `AUTO_MODERATION_ACTION_EXECUTION` | `parse_auto_moderation_action_execution` (state.py:1240) | No direct parser call found |
| `CHANNEL_CREATE` | `parse_channel_create` (state.py:917) | [discord/ext/test/backend.py:838](discord/ext/test/backend.py#L838); [discord/ext/test/backend.py:855](discord/ext/test/backend.py#L855); [discord/ext/test/backend.py:877](discord/ext/test/backend.py#L877) |
| `CHANNEL_UPDATE` | `parse_channel_update` (state.py:890) | [discord/ext/test/backend.py:905](discord/ext/test/backend.py#L905) |
| `CHANNEL_DELETE` | `parse_channel_delete` (state.py:869) | [discord/ext/test/backend.py:886](discord/ext/test/backend.py#L886) |
| `CHANNEL_INFO` | No parser found | No direct parser call found |
| `CHANNEL_PINS_UPDATE` | `parse_channel_pins_update` (state.py:934) | [discord/ext/test/backend.py:1254](discord/ext/test/backend.py#L1254); [discord/ext/test/backend.py:1263](discord/ext/test/backend.py#L1263) |
| `THREAD_CREATE` | `parse_thread_create` (state.py:955) | [discord/ext/test/backend.py:927](discord/ext/test/backend.py#L927) |
| `THREAD_UPDATE` | `parse_thread_update` (state.py:974) | No direct parser call found |
| `THREAD_DELETE` | `parse_thread_delete` (state.py:996) | No direct parser call found |
| `THREAD_LIST_SYNC` | `parse_thread_list_sync` (state.py:1011) | No direct parser call found |
| `THREAD_MEMBER_UPDATE` | `parse_thread_member_update` (state.py:1047) | No direct parser call found |
| `THREAD_MEMBERS_UPDATE` | `parse_thread_members_update` (state.py:1063) | No direct parser call found |
| `ENTITLEMENT_CREATE` | `parse_entitlement_create` (state.py:1727) | No direct parser call found |
| `ENTITLEMENT_UPDATE` | `parse_entitlement_update` (state.py:1731) | No direct parser call found |
| `ENTITLEMENT_DELETE` | `parse_entitlement_delete` (state.py:1735) | No direct parser call found |
| `GUILD_CREATE` | `parse_guild_create` (state.py:1314) | [discord/ext/test/backend.py:695](discord/ext/test/backend.py#L695) |
| `GUILD_UPDATE` | `parse_guild_update` (state.py:1336) | [discord/ext/test/backend.py:715](discord/ext/test/backend.py#L715) |
| `GUILD_DELETE` | `parse_guild_delete` (state.py:1345) | No direct parser call found |
| `GUILD_AUDIT_LOG_ENTRY_CREATE` | `parse_guild_audit_log_entry_create` (state.py:1192) | No direct parser call found |
| `GUILD_BAN_ADD` | `parse_guild_ban_add` (state.py:1367) | No direct parser call found |
| `GUILD_BAN_REMOVE` | `parse_guild_ban_remove` (state.py:1383) | No direct parser call found |
| `GUILD_EMOJIS_UPDATE` | `parse_guild_emojis_update` (state.py:1166) | No direct parser call found |
| `GUILD_STICKERS_UPDATE` | `parse_guild_stickers_update` (state.py:1179) | No direct parser call found |
| `GUILD_INTEGRATIONS_UPDATE` | `parse_guild_integrations_update` (state.py:1451) | No direct parser call found |
| `GUILD_MEMBER_ADD` | `parse_guild_member_add` (state.py:1097) | [discord/ext/test/backend.py:960](discord/ext/test/backend.py#L960) |
| `GUILD_MEMBER_REMOVE` | `parse_guild_member_remove` (state.py:1118) | [discord/ext/test/backend.py:982](discord/ext/test/backend.py#L982) |
| `GUILD_MEMBER_UPDATE` | `parse_guild_member_update` (state.py:1137) | [discord/ext/test/backend.py:974](discord/ext/test/backend.py#L974) |
| `GUILD_MEMBERS_CHUNK` | `parse_guild_members_chunk` (state.py:1426) | No direct parser call found |
| `GUILD_ROLE_CREATE` | `parse_guild_role_create` (state.py:1389) | [discord/ext/test/backend.py:758](discord/ext/test/backend.py#L758) |
| `GUILD_ROLE_UPDATE` | `parse_guild_role_update` (state.py:1413) | [discord/ext/test/backend.py:808](discord/ext/test/backend.py#L808) |
| `GUILD_ROLE_DELETE` | `parse_guild_role_delete` (state.py:1400) | [discord/ext/test/backend.py:820](discord/ext/test/backend.py#L820) |
| `GUILD_SCHEDULED_EVENT_CREATE` | `parse_guild_scheduled_event_create` (state.py:1534) | No direct parser call found |
| `GUILD_SCHEDULED_EVENT_UPDATE` | `parse_guild_scheduled_event_update` (state.py:1543) | No direct parser call found |
| `GUILD_SCHEDULED_EVENT_DELETE` | `parse_guild_scheduled_event_delete` (state.py:1556) | No direct parser call found |
| `GUILD_SCHEDULED_EVENT_USER_ADD` | `parse_guild_scheduled_event_user_add` (state.py:1564) | No direct parser call found |
| `GUILD_SCHEDULED_EVENT_USER_REMOVE` | `parse_guild_scheduled_event_user_remove` (state.py:1583) | No direct parser call found |
| `GUILD_SOUNDBOARD_SOUND_CREATE` | `parse_guild_soundboard_sound_create` (state.py:1602) | No direct parser call found |
| `GUILD_SOUNDBOARD_SOUND_UPDATE` | `parse_guild_soundboard_sound_update` (state.py:1617) | No direct parser call found |
| `GUILD_SOUNDBOARD_SOUND_DELETE` | `parse_guild_soundboard_sound_delete` (state.py:1630) | No direct parser call found |
| `GUILD_SOUNDBOARD_SOUNDS_UPDATE` | `parse_guild_soundboard_sounds_update` (state.py:1644) | No direct parser call found |
| `SOUNDBOARD_SOUNDS` | No parser found | No direct parser call found |
| `INTEGRATION_CREATE` | `parse_integration_create` (state.py:1458) | No direct parser call found |
| `INTEGRATION_UPDATE` | `parse_integration_update` (state.py:1468) | No direct parser call found |
| `INTEGRATION_DELETE` | `parse_integration_delete` (state.py:1478) | No direct parser call found |
| `INTERACTION_CREATE` | `parse_interaction_create` (state.py:814) | No direct parser call found |
| `INVITE_CREATE` | `parse_invite_create` (state.py:861) | No direct parser call found |
| `INVITE_DELETE` | `parse_invite_delete` (state.py:865) | No direct parser call found |
| `MESSAGE_CREATE` | `parse_message_create` (state.py:682) | [discord/ext/test/backend.py:1014](discord/ext/test/backend.py#L1014) |
| `MESSAGE_UPDATE` | `parse_message_update` (state.py:716) | No direct parser call found |
| `MESSAGE_DELETE` | `parse_message_delete` (state.py:693) | [discord/ext/test/backend.py:1100](discord/ext/test/backend.py#L1100) |
| `MESSAGE_DELETE_BULK` | `parse_message_delete_bulk` (state.py:702) | No direct parser call found |
| `MESSAGE_REACTION_ADD` | `parse_message_reaction_add` (state.py:744) | [discord/ext/test/backend.py:1149](discord/ext/test/backend.py#L1149) |
| `MESSAGE_REACTION_REMOVE` | `parse_message_reaction_remove` (state.py:780) | [discord/ext/test/backend.py:1207](discord/ext/test/backend.py#L1207) |
| `MESSAGE_REACTION_REMOVE_ALL` | `parse_message_reaction_remove_all` (state.py:770) | [discord/ext/test/backend.py:1240](discord/ext/test/backend.py#L1240) |
| `MESSAGE_REACTION_REMOVE_EMOJI` | `parse_message_reaction_remove_emoji` (state.py:798) | No direct parser call found |
| `PRESENCE_UPDATE` | `parse_presence_update` (state.py:833) | No direct parser call found |
| `STAGE_INSTANCE_CREATE` | `parse_stage_instance_create` (state.py:1500) | No direct parser call found |
| `STAGE_INSTANCE_UPDATE` | `parse_stage_instance_update` (state.py:1509) | No direct parser call found |
| `STAGE_INSTANCE_DELETE` | `parse_stage_instance_delete` (state.py:1522) | No direct parser call found |
| `SUBSCRIPTION_CREATE` | `parse_subscription_create` (state.py:1775) | No direct parser call found |
| `SUBSCRIPTION_UPDATE` | `parse_subscription_update` (state.py:1779) | No direct parser call found |
| `SUBSCRIPTION_DELETE` | `parse_subscription_delete` (state.py:1783) | No direct parser call found |
| `TYPING_START` | `parse_typing_start` (state.py:1705) | No direct parser call found |
| `USER_UPDATE` | `parse_user_update` (state.py:857) | No direct parser call found |
| `VOICE_CHANNEL_EFFECT_SEND` | `parse_voice_channel_effect_send` (state.py:1689) | No direct parser call found |
| `VOICE_CHANNEL_START_TIME_UPDATE` | No parser found | No direct parser call found |
| `VOICE_CHANNEL_STATUS_UPDATE` | No parser found | No direct parser call found |
| `VOICE_STATE_UPDATE` | `parse_voice_state_update` (state.py:1663) | No direct parser call found |
| `VOICE_SERVER_UPDATE` | `parse_voice_server_update` (state.py:1697) | No direct parser call found |
| `WEBHOOKS_UPDATE` | `parse_webhooks_update` (state.py:1487) | No direct parser call found |
| `MESSAGE_POLL_VOTE_ADD` | `parse_message_poll_vote_add` (state.py:1739) | No direct parser call found |
| `MESSAGE_POLL_VOTE_REMOVE` | `parse_message_poll_vote_remove` (state.py:1757) | No direct parser call found |
| `READY` | `parse_ready` (state.py:654); special handling in gateway.py | No direct parser call found |
| `RESUMED` | Special handling in gateway.py:581; no state parser required | No direct parser call found |
| `RATE_LIMITED` | No parser found | No direct parser call found |

### Gateway connection and send opcodes

The following table covers the documented main Gateway opcode list. “Not simulated” is limited to the checked fake websocket and fake state; it does not mean a developer cannot manually construct a payload. The rate-limited receive event is listed above because the events page lists it, while the opcode table does not assign it a number.

| Opcode | Direction / operation | discord.py | dpytest |
| --- | --- | --- | --- |
| 0 | Receive: Dispatch | `received_message` routes to state parsers | Selected backend calls invoke parsers directly; no full dispatch stream simulation found. |
| 1 | Send/receive: Heartbeat | Heartbeat handling in `gateway.py` | No heartbeat lifecycle simulation found. |
| 2 | Send: Identify | `DiscordWebSocket.identify` | No handshake simulation found; generic fake send is unhandled without a configured callback. |
| 3 | Send: Presence Update | `DiscordWebSocket.change_presence` | `FakeWebSocket.change_presence` supplies a callback; partial simulation. |
| 4 | Send: Voice State Update | `DiscordWebSocket.voice_state` | No corresponding fake websocket override found; fake voice facilities do not establish Gateway opcode simulation. |
| 6 | Send: Resume | `DiscordWebSocket.resume` | No session-resume simulation found. |
| 7 | Receive: Reconnect | `received_message` handles reconnect | No reconnect lifecycle simulation found. |
| 8 | Send: Request Guild Members | `DiscordWebSocket.request_chunks` | FakeState `query_members` returns cached members and `chunk_guild` returns an empty result; no matching Gateway exchange. |
| 9 | Receive: Invalid Session | `received_message` handles invalid sessions | No invalid-session lifecycle simulation found. |
| 10 | Receive: Hello | `received_message` sets up heartbeats | No hello/heartbeat lifecycle simulation found. |
| 11 | Receive: Heartbeat ACK | `received_message` acknowledges heartbeats | No ACK lifecycle simulation found. |
| 31 | Send: Request Soundboard Sounds | No matching send implementation found in the main DiscordWebSocket | No simulation found. |
| 43 | Send: Request Channel Info | No matching send implementation found in the main DiscordWebSocket | No simulation found. |

Main Gateway close codes, intent validation, rate limiting, reconnect timing, sharding, and Gateway payload field-level conformance were not audited.

## Voice Gateway and audio

Baseline: Discord's [voice opcode and close-code reference](https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice) and [voice connection guide](https://docs.discord.com/developers/topics/voice-connections), reviewed 2026-10-31; locally installed discord.py 2.7.1 and this dpytest working tree. These opcodes belong to the **separate voice WebSocket**, not the main Gateway; an identical opcode number can have a different meaning. The comparison below covers the 23 opcodes in Discord's published voice opcode table, including DAVE. It is a static source review, not a voice connection or cryptographic interoperability test.

discord.py's [`DiscordVoiceWebSocket`](https://github.com/Rapptz/discord.py/blob/v2.7.1/discord/gateway.py#L787) has send and receive paths for the voice handshake and DAVE, with DAVE operations delegated to `davey`. The normal voice client requires that dependency; see [`voice_client.py`](https://github.com/Rapptz/discord.py/blob/v2.7.1/discord/voice_client.py#L221) and [`voice_state.py`](https://github.com/Rapptz/discord.py/blob/v2.7.1/discord/voice_state.py#L268). A constant, handler, or send path establishes source-level coverage only, not full protocol correctness or successful negotiation.

dpytest's [`FakeVoiceClient.connect`](discord/ext/test/voice.py#L15) simply sets the connection's connected flag; [`FakeVoiceChannel.connect`](discord/ext/test/voice.py#L26) supplies that client. The existing [voice tests](tests/test_voice.py) check client join/leave bookkeeping and member movement, not a voice server exchange. No fake voice WebSocket, voice opcode exchange, UDP transport, or DAVE session was identified in the project. Thus **no voice opcode in this table is demonstrated as simulated by dpytest**; inherited methods and manual test injection do not establish end-to-end simulation. This finding is distinct from main Gateway voice-state events, which appear in the preceding tables.

| Opcode | Direction and event | discord.py 2.7.1 source finding | dpytest finding |
| --- | --- | --- | --- |
| 0 | Client: Identify | `DiscordVoiceWebSocket.identify` sends identify, including supported DAVE version. | No voice handshake simulation found. |
| 1 | Client: Select Protocol | `select_protocol` sends the selected UDP protocol. | No UDP negotiation simulation found. |
| 2 | Server: Ready | `received_message` calls `initial_connection`, including UDP connection and IP discovery. | No voice Ready simulation found. |
| 3 | Client: Heartbeat | `VoiceKeepAliveHandler` sends heartbeat payloads including `seq_ack`. | No voice heartbeat simulation found. |
| 4 | Server: Session Description | `received_message` loads mode and secret key and initializes DAVE when requested. | No session-key or DAVE negotiation simulation found. |
| 5 | Both: Speaking | `speak` sends it; no built-in receive-specific branch was found in `received_message`, although the message is passed to a hook. | No speaking opcode simulation found. |
| 6 | Server: Heartbeat ACK | `received_message` acknowledges the keepalive. | No voice ACK simulation found. |
| 7 | Client: Resume | `resume` sends session details and sequence acknowledgment. | No voice resume simulation found. |
| 8 | Server: Hello | `received_message` starts the voice keepalive. | No voice Hello simulation found. |
| 9 | Server: Resumed | `received_message` recognizes and logs it. | No voice resumed-event simulation found. |
| 11 | Server: Clients Connect | Constant exists; no built-in receive-specific branch found, but JSON frames reach a hook. | No clients-connect opcode simulation found. |
| 13 | Server: Client Disconnect | Constant exists; no built-in receive-specific branch found, but JSON frames reach a hook. | No client-disconnect opcode simulation found. |
| 21 | Server: DAVE Prepare Transition | `received_message` records a transition and handles readiness/downgrade when a DAVE session exists. | No DAVE transition simulation found. |
| 22 | Server: DAVE Execute Transition | `received_message` invokes the connection state's transition logic when a DAVE session exists. | No DAVE transition simulation found. |
| 23 | Client: DAVE Transition Ready | `send_transition_ready` sends an acknowledgment. | No DAVE acknowledgment simulation found. |
| 24 | Server: DAVE Prepare Epoch | `received_message` can reinitialize the DAVE session for a new epoch. | No DAVE epoch simulation found. |
| 25 | Server: DAVE MLS External Sender | `received_binary_message` passes the external sender to `davey`. | No MLS simulation found. |
| 26 | Client: DAVE MLS Key Package | `VoiceConnectionState.reinit_dave_session` sends a serialized key package. | No MLS simulation found. |
| 27 | Server: DAVE MLS Proposals | `received_binary_message` processes proposals via `davey`. | No MLS simulation found. |
| 28 | Client: DAVE MLS Commit Welcome | `received_binary_message` sends a commit/welcome returned by proposal processing. | No MLS simulation found. |
| 29 | Server: DAVE MLS Announce Commit Transition | `received_binary_message` processes the commit and acknowledges or recovers from failure. | No MLS simulation found. |
| 30 | Server: DAVE MLS Welcome | `received_binary_message` processes the welcome and acknowledges or recovers from failure. | No MLS simulation found. |
| 31 | Client: DAVE MLS Invalid Commit Welcome | `_recover_from_invalid_commit` sends the error and reinitializes the session. | No MLS recovery simulation found. |

### Voice transport and close behavior

- **Voice Gateway version and resume:** discord.py connects with voice Gateway v8, tracks `seq_ack`, and includes it in heartbeat and resume messages. Buffered replay behavior was not tested against Discord. dpytest does not simulate this connection lifecycle.
- **Audio:** discord.py has UDP IP discovery, transport mode negotiation, Opus packet sending, transport encryption, and conditional DAVE Opus encryption. A source path does not establish that every audio mode, decoder, platform dependency, or voice receive feature is supported. dpytest's connected flag does not create a simulated UDP or audio stream.
- **Close codes:** Discord documents `4001`, `4002`, `4003`, `4004`, `4005`, `4006`, `4009`, `4011`, `4012`, `4014`, `4015`, `4016`, `4017`, `4020`, `4021`, and `4022`. discord.py's voice state loop contains explicit branches for `4014`/`4022` and `4015`; other codes require examining the generic close/reconnect path and were not individually validated. dpytest has no identified voice close-code simulation. See the [official close-code definitions](https://docs.discord.com/developers/topics/opcodes-and-status-codes#voice).
- **Scope:** payload fields, timeout and reconnection behavior, close-code policy, audio codec fidelity, DAVE cryptographic conformance, and dependency availability were not exercised in a live test. The separate `VOICE_STATE_UPDATE` and `VOICE_SERVER_UPDATE` events on the main Gateway are covered above.

## Endpoint inventory

| Method and path | OpenAPI operation | discord.py / dpytest finding |
| --- | --- | --- |
| `GET /applications/@me` | `get_my_application` | No route found |
| `PATCH /applications/@me` | `update_my_application` | No fake: `HTTPClient.edit_application_info` (http.py:2684) |
| `GET /applications/{application_id}` | `get_application` | No route found |
| `PATCH /applications/{application_id}` | `update_application` | No route found |
| `GET /applications/{application_id}/activity-instances/{instance_id}` | `applications_get_activity_instance` | No route found |
| `POST /applications/{application_id}/attachment` | `upload_application_attachment` | No route found |
| `GET /applications/{application_id}/commands` | `list_application_commands` | No fake: `HTTPClient.get_global_commands` (http.py:2224) |
| `PUT /applications/{application_id}/commands` | `bulk_set_application_commands` | No fake: `HTTPClient.bulk_upsert_global_commands` (http.py:2273) |
| `POST /applications/{application_id}/commands` | `create_application_command` | No fake: `HTTPClient.upsert_global_command` (http.py:2238) |
| `GET /applications/{application_id}/commands/{command_id}` | `get_application_command` | No fake: `HTTPClient.get_global_command` (http.py:2227) |
| `DELETE /applications/{application_id}/commands/{command_id}` | `delete_application_command` | No fake: `HTTPClient.delete_global_command` (http.py:2262) |
| `PATCH /applications/{application_id}/commands/{command_id}` | `update_application_command` | No fake: `HTTPClient.edit_global_command` (http.py:2253) |
| `GET /applications/{application_id}/emojis` | `list_application_emojis` | No fake: `HTTPClient.get_application_emojis` (http.py:2687) |
| `POST /applications/{application_id}/emojis` | `create_application_emoji` | No fake: `HTTPClient.create_application_emoji` (http.py:2708) |
| `GET /applications/{application_id}/emojis/{emoji_id}` | `get_application_emoji` | No fake: `HTTPClient.get_application_emoji` (http.py:2691) |
| `DELETE /applications/{application_id}/emojis/{emoji_id}` | `delete_application_emoji` | No fake: `HTTPClient.delete_application_emoji` (http.py:2729) |
| `PATCH /applications/{application_id}/emojis/{emoji_id}` | `update_application_emoji` | No fake: `HTTPClient.edit_application_emoji` (http.py:2718) |
| `GET /applications/{application_id}/entitlements` | `get_entitlements` | No fake: `HTTPClient.get_entitlements` (http.py:2507) |
| `POST /applications/{application_id}/entitlements` | `create_entitlement` | No fake: `HTTPClient.create_entitlement` (http.py:2540) |
| `GET /applications/{application_id}/entitlements/{entitlement_id}` | `get_entitlement` | No fake: `HTTPClient.get_entitlement` (http.py:2512) |
| `DELETE /applications/{application_id}/entitlements/{entitlement_id}` | `delete_entitlement` | No fake: `HTTPClient.delete_entitlement` (http.py:2550) |
| `POST /applications/{application_id}/entitlements/{entitlement_id}/consume` | `consume_entitlement` | No fake: `HTTPClient.consume_entitlement` (http.py:2522) |
| `GET /applications/{application_id}/guilds/{guild_id}/commands` | `list_guild_application_commands` | No fake: `HTTPClient.get_guild_commands` (http.py:2281) |
| `PUT /applications/{application_id}/guilds/{guild_id}/commands` | `bulk_set_guild_application_commands` | No fake: `HTTPClient.bulk_upsert_guild_commands` (http.py:2361) |
| `POST /applications/{application_id}/guilds/{guild_id}/commands` | `create_guild_application_command` | No fake: `HTTPClient.upsert_guild_command` (http.py:2310) |
| `GET /applications/{application_id}/guilds/{guild_id}/commands/permissions` | `list_guild_application_command_permissions` | No fake: `HTTPClient.get_guild_application_command_permissions` (http.py:2374) |
| `GET /applications/{application_id}/guilds/{guild_id}/commands/{command_id}` | `get_guild_application_command` | No fake: `HTTPClient.get_guild_command` (http.py:2295) |
| `DELETE /applications/{application_id}/guilds/{guild_id}/commands/{command_id}` | `delete_guild_application_command` | No fake: `HTTPClient.delete_guild_command` (http.py:2346) |
| `PATCH /applications/{application_id}/guilds/{guild_id}/commands/{command_id}` | `update_guild_application_command` | No fake: `HTTPClient.edit_guild_command` (http.py:2331) |
| `GET /applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions` | `get_guild_application_command_permissions` | No fake: `HTTPClient.get_application_command_permissions` (http.py:2388) |
| `PUT /applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions` | `set_guild_application_command_permissions` | No fake: `HTTPClient.edit_application_command_permissions` (http.py:2404) |
| `GET /applications/{application_id}/role-connections/metadata` | `get_application_role_connections_metadata` | No route found |
| `PUT /applications/{application_id}/role-connections/metadata` | `update_application_role_connections_metadata` | No route found |
| `GET /channels/{channel_id}` | `get_channel` | Fake override: `HTTPClient.get_channel` (http.py:1018) |
| `DELETE /channels/{channel_id}` | `delete_channel` | Fake override: `HTTPClient.delete_channel` (http.py:1291) |
| `PATCH /channels/{channel_id}` | `update_channel` | No fake: `HTTPClient.edit_channel` (http.py:1202) |
| `POST /channels/{channel_id}/followers` | `follow_channel` | No fake: `HTTPClient.follow_webhook` (http.py:1449) |
| `GET /channels/{channel_id}/invites` | `list_channel_invites` | No fake: `HTTPClient.invites_from_channel` (http.py:1901) |
| `POST /channels/{channel_id}/invites` | `create_channel_invite` | No fake: `HTTPClient.create_invite` (http.py:1859) |
| `GET /channels/{channel_id}/messages` | `list_messages` | Fake override: `HTTPClient.logs_from` (http.py:1040) |
| `POST /channels/{channel_id}/messages` | `create_message` | Fake override: `HTTPClient.send_message` (http.py:883) |
| `POST /channels/{channel_id}/messages/bulk-delete` | `bulk_delete_messages` | No fake: `HTTPClient.delete_messages` (http.py:916) |
| `GET /channels/{channel_id}/messages/pins` | `list_pins` | No fake: `HTTPClient.pins_from` (http.py:1082) |
| `PUT /channels/{channel_id}/messages/pins/{message_id}` | `create_pin` | Fake override: `HTTPClient.pin_message` (http.py:1053) |
| `DELETE /channels/{channel_id}/messages/pins/{message_id}` | `delete_pin` | Fake override: `HTTPClient.unpin_message` (http.py:1062) |
| `GET /channels/{channel_id}/messages/{message_id}` | `get_message` | Fake override: `HTTPClient.get_message` (http.py:1014) |
| `DELETE /channels/{channel_id}/messages/{message_id}` | `delete_message` | Fake override: `HTTPClient.delete_message` (http.py:904) |
| `PATCH /channels/{channel_id}/messages/{message_id}` | `update_message` | Fake override: `HTTPClient.edit_message` (http.py:926) |
| `POST /channels/{channel_id}/messages/{message_id}/crosspost` | `crosspost_message` | No fake: `HTTPClient.publish_message` (http.py:1044) |
| `DELETE /channels/{channel_id}/messages/{message_id}/reactions` | `delete_all_message_reactions` | Fake override: `HTTPClient.clear_reactions` (http.py:994) |
| `GET /channels/{channel_id}/messages/{message_id}/reactions/{emoji_name}` | `list_message_reactions_by_emoji` | No fake: `HTTPClient.get_reaction_users` (http.py:974) |
| `DELETE /channels/{channel_id}/messages/{message_id}/reactions/{emoji_name}` | `delete_all_message_reactions_by_emoji` | No fake: `HTTPClient.clear_single_reaction` (http.py:1004) |
| `PUT /channels/{channel_id}/messages/{message_id}/reactions/{emoji_name}/@me` | `add_my_message_reaction` | Fake override: `HTTPClient.add_reaction` (http.py:933) |
| `DELETE /channels/{channel_id}/messages/{message_id}/reactions/{emoji_name}/@me` | `delete_my_message_reaction` | Fake override: `HTTPClient.remove_own_reaction` (http.py:956) |
| `DELETE /channels/{channel_id}/messages/{message_id}/reactions/{emoji_name}/{user_id}` | `delete_user_message_reaction` | Fake override: `HTTPClient.remove_reaction` (http.py:945) |
| `POST /channels/{channel_id}/messages/{message_id}/threads` | `create_thread_from_message` | Fake override: `HTTPClient.start_thread_with_message` (http.py:1311) |
| `GET /channels/{channel_id}/permissions/member/{user_id}` | `get_channel_member_permissions` | No route found |
| `GET /channels/{channel_id}/permissions/role/{role_id}` | `get_channel_role_permissions` | No route found |
| `PUT /channels/{channel_id}/permissions/{overwrite_id}` | `set_channel_permission_overwrite` | Fake override: `HTTPClient.edit_channel_permissions` (http.py:1988) |
| `DELETE /channels/{channel_id}/permissions/{overwrite_id}` | `delete_channel_permission_overwrite` | Fake override: `HTTPClient.delete_channel_permissions` (http.py:1994) |
| `GET /channels/{channel_id}/pins` | `deprecated_list_pins` | No route found |
| `PUT /channels/{channel_id}/pins/{message_id}` | `deprecated_create_pin` | No route found |
| `DELETE /channels/{channel_id}/pins/{message_id}` | `deprecated_delete_pin` | No route found |
| `GET /channels/{channel_id}/polls/{message_id}/answers/{answer_id}` | `get_answer_voters` | No fake: `HTTPClient.get_poll_answer_voters` (http.py:2756) |
| `POST /channels/{channel_id}/polls/{message_id}/expire` | `poll_expire` | No fake: `HTTPClient.end_poll` (http.py:2768) |
| `PUT /channels/{channel_id}/recipients/{user_id}` | `add_group_dm_user` | No route found |
| `DELETE /channels/{channel_id}/recipients/{user_id}` | `delete_group_dm_user` | No route found |
| `POST /channels/{channel_id}/send-soundboard-sound` | `send_soundboard_sound` | No fake: `HTTPClient.send_soundboard_sound` (http.py:2661) |
| `GET /channels/{channel_id}/thread-members` | `list_thread_members` | No fake: `HTTPClient.get_thread_members` (http.py:1408) |
| `PUT /channels/{channel_id}/thread-members/@me` | `join_thread` | No fake: `HTTPClient.join_thread` (http.py:1353) |
| `DELETE /channels/{channel_id}/thread-members/@me` | `leave_thread` | No fake: `HTTPClient.leave_thread` (http.py:1361) |
| `GET /channels/{channel_id}/thread-members/{user_id}` | `get_thread_member` | No fake: `HTTPClient.get_thread_member` (http.py:1404) |
| `PUT /channels/{channel_id}/thread-members/{user_id}` | `add_thread_member` | No fake: `HTTPClient.add_user_to_thread` (http.py:1357) |
| `DELETE /channels/{channel_id}/thread-members/{user_id}` | `delete_thread_member` | No fake: `HTTPClient.remove_user_from_thread` (http.py:1364) |
| `POST /channels/{channel_id}/threads` | `create_thread` | No fake: `HTTPClient.start_thread_without_message` (http.py:1335), `HTTPClient.start_thread_in_forum` (http.py:1346) |
| `GET /channels/{channel_id}/threads/archived/private` | `list_private_archived_threads` | No fake: `HTTPClient.get_private_archived_threads` (http.py:1381) |
| `GET /channels/{channel_id}/threads/archived/public` | `list_public_archived_threads` | No fake: `HTTPClient.get_public_archived_threads` (http.py:1370) |
| `GET /channels/{channel_id}/threads/search` | `thread_search` | No route found |
| `POST /channels/{channel_id}/typing` | `trigger_typing_indicator` | Fake override: `HTTPClient.send_typing` (http.py:890) |
| `GET /channels/{channel_id}/users/@me/threads/archived/private` | `list_my_private_archived_threads` | No fake: `HTTPClient.get_joined_private_archived_threads` (http.py:1392) |
| `PUT /channels/{channel_id}/voice-status` | `update_voice_channel_status` | No fake: `HTTPClient.edit_voice_channel_status` (http.py:1236) |
| `GET /channels/{channel_id}/webhooks` | `list_channel_webhooks` | No fake: `HTTPClient.channel_webhooks` (http.py:1431) |
| `POST /channels/{channel_id}/webhooks` | `create_webhook` | No fake: `HTTPClient.create_webhook` (http.py:1427) |
| `GET /gateway` | `get_gateway` | No route found |
| `GET /gateway/bot` | `get_bot_gateway` | No fake: `HTTPClient.get_bot_gateway` (http.py:2823) |
| `GET /guilds/templates/{code}` | `get_guild_template` | No fake: `HTTPClient.get_template` (http.py:1531) |
| `GET /guilds/{guild_id}` | `get_guild` | Fake override: `HTTPClient.get_guild` (http.py:1478) |
| `PATCH /guilds/{guild_id}` | `update_guild` | No fake: `HTTPClient.edit_guild` (http.py:1522) |
| `GET /guilds/{guild_id}/audit-logs` | `list_guild_audit_log_entries` | No fake: `HTTPClient.get_audit_logs` (http.py:1829) |
| `GET /guilds/{guild_id}/auto-moderation/rules` | `list_auto_moderation_rules` | No fake: `HTTPClient.get_auto_moderation_rules` (http.py:2414) |
| `POST /guilds/{guild_id}/auto-moderation/rules` | `create_auto_moderation_rule` | No fake: `HTTPClient.create_auto_moderation_rule` (http.py:2438) |
| `GET /guilds/{guild_id}/auto-moderation/rules/{rule_id}` | `get_auto_moderation_rule` | No fake: `HTTPClient.get_auto_moderation_rule` (http.py:2418) |
| `DELETE /guilds/{guild_id}/auto-moderation/rules/{rule_id}` | `delete_auto_moderation_rule` | No fake: `HTTPClient.delete_auto_moderation_rule` (http.py:2466) |
| `PATCH /guilds/{guild_id}/auto-moderation/rules/{rule_id}` | `update_auto_moderation_rule` | No fake: `HTTPClient.edit_auto_moderation_rule` (http.py:2457) |
| `GET /guilds/{guild_id}/bans` | `list_guild_bans` | No fake: `HTTPClient.get_bans` (http.py:1578) |
| `GET /guilds/{guild_id}/bans/{user_id}` | `get_guild_ban` | No fake: `HTTPClient.get_ban` (http.py:1597) |
| `PUT /guilds/{guild_id}/bans/{user_id}` | `ban_user_from_guild` | Fake override: `HTTPClient.ban` (http.py:1097) |
| `DELETE /guilds/{guild_id}/bans/{user_id}` | `unban_user_from_guild` | Fake override: `HTTPClient.unban` (http.py:1105) |
| `POST /guilds/{guild_id}/bulk-ban` | `bulk_ban_users_from_guild` | No fake: `HTTPClient.bulk_ban` (http.py:1115) |
| `GET /guilds/{guild_id}/channels` | `list_guild_channels` | Fake override: `HTTPClient.get_all_guild_channels` (http.py:1607) |
| `POST /guilds/{guild_id}/channels` | `create_guild_channel` | Fake override: `HTTPClient.create_channel` (http.py:1283) |
| `PATCH /guilds/{guild_id}/channels` | `bulk_update_guild_channels` | No fake: `HTTPClient.bulk_channel_update` (http.py:1247) |
| `GET /guilds/{guild_id}/emojis` | `list_guild_emojis` | No fake: `HTTPClient.get_all_custom_emojis` (http.py:1729) |
| `POST /guilds/{guild_id}/emojis` | `create_guild_emoji` | No fake: `HTTPClient.create_custom_emoji` (http.py:1749) |
| `GET /guilds/{guild_id}/emojis/{emoji_id}` | `get_guild_emoji` | No fake: `HTTPClient.get_custom_emoji` (http.py:1732) |
| `DELETE /guilds/{guild_id}/emojis/{emoji_id}` | `delete_guild_emoji` | No fake: `HTTPClient.delete_custom_emoji` (http.py:1759) |
| `PATCH /guilds/{guild_id}/emojis/{emoji_id}` | `update_guild_emoji` | No fake: `HTTPClient.edit_custom_emoji` (http.py:1770) |
| `PUT /guilds/{guild_id}/incident-actions` | `update_guild_incident_actions` | No fake: `HTTPClient.edit_incident_actions` (http.py:1841) |
| `GET /guilds/{guild_id}/integrations` | `list_guild_integrations` | No fake: `HTTPClient.get_all_integrations` (http.py:1774) |
| `DELETE /guilds/{guild_id}/integrations/{integration_id}` | `delete_guild_integration` | No fake: `HTTPClient.delete_integration` (http.py:1804) |
| `GET /guilds/{guild_id}/invites` | `list_guild_invites` | No fake: `HTTPClient.invites_from` (http.py:1898) |
| `GET /guilds/{guild_id}/members` | `list_guild_members` | Fake override: `HTTPClient.get_members` (http.py:1618) |
| `PATCH /guilds/{guild_id}/members/@me` | `update_my_guild_member` | No fake: `HTTPClient.edit_my_member` (http.py:1151) |
| `GET /guilds/{guild_id}/members/search` | `search_guild_members` | No route found |
| `GET /guilds/{guild_id}/members/{user_id}` | `get_guild_member` | Fake override: `HTTPClient.get_member` (http.py:1622) |
| `PUT /guilds/{guild_id}/members/{user_id}` | `add_guild_member` | No route found |
| `DELETE /guilds/{guild_id}/members/{user_id}` | `delete_guild_member` | Fake override: `HTTPClient.kick` (http.py:1087) |
| `PATCH /guilds/{guild_id}/members/{user_id}` | `update_guild_member` | Fake override: `HTTPClient.edit_member` (http.py:1184) |
| `PUT /guilds/{guild_id}/members/{user_id}/roles/{role_id}` | `add_guild_member_role` | Fake override: `HTTPClient.add_role` (http.py:1956) |
| `DELETE /guilds/{guild_id}/members/{user_id}/roles/{role_id}` | `delete_guild_member_role` | Fake override: `HTTPClient.remove_role` (http.py:1968) |
| `GET /guilds/{guild_id}/messages/search` | `guild_search` | No route found |
| `GET /guilds/{guild_id}/new-member-welcome` | `get_guild_new_member_welcome` | No route found |
| `GET /guilds/{guild_id}/onboarding` | `get_guilds_onboarding` | No fake: `HTTPClient.get_guild_onboarding` (http.py:2561) |
| `PUT /guilds/{guild_id}/onboarding` | `put_guilds_onboarding` | No fake: `HTTPClient.edit_guild_onboarding` (http.py:2588) |
| `GET /guilds/{guild_id}/permissions/member/{user_id}` | `get_guild_member_permissions` | No route found |
| `GET /guilds/{guild_id}/permissions/role/{role_id}` | `get_guild_role_permissions` | No route found |
| `GET /guilds/{guild_id}/preview` | `get_guild_preview` | No fake: `HTTPClient.get_guild_preview` (http.py:1481) |
| `GET /guilds/{guild_id}/prune` | `preview_prune_guild` | No fake: `HTTPClient.estimate_pruned_members` (http.py:1654) |
| `POST /guilds/{guild_id}/prune` | `prune_guild` | No fake: `HTTPClient.prune_members` (http.py:1640) |
| `GET /guilds/{guild_id}/regions` | `list_guild_voice_regions` | No route found |
| `GET /guilds/{guild_id}/requests` | `get_guild_join_requests` | No route found |
| `PATCH /guilds/{guild_id}/requests/{request_id}` | `action_guild_join_request` | No route found |
| `GET /guilds/{guild_id}/roles` | `list_guild_roles` | No fake: `HTTPClient.get_roles` (http.py:1909) |
| `POST /guilds/{guild_id}/roles` | `create_guild_role` | Fake override: `HTTPClient.create_role` (http.py:1940) |
| `PATCH /guilds/{guild_id}/roles` | `bulk_update_guild_roles` | Fake override: `HTTPClient.move_role_position` (http.py:1950) |
| `GET /guilds/{guild_id}/roles/member-counts` | `guild_role_member_counts` | No fake: `HTTPClient.get_role_member_counts` (http.py:1915) |
| `GET /guilds/{guild_id}/roles/{role_id}` | `get_guild_role` | No fake: `HTTPClient.get_role` (http.py:1912) |
| `DELETE /guilds/{guild_id}/roles/{role_id}` | `delete_guild_role` | Fake override: `HTTPClient.delete_role` (http.py:1926) |
| `PATCH /guilds/{guild_id}/roles/{role_id}` | `update_guild_role` | Fake override: `HTTPClient.edit_role` (http.py:1920) |
| `GET /guilds/{guild_id}/scheduled-events` | `list_guild_scheduled_events` | No fake: `HTTPClient.get_scheduled_events` (http.py:2061) |
| `POST /guilds/{guild_id}/scheduled-events` | `create_guild_scheduled_event` | No fake: `HTTPClient.create_guild_scheduled_event` (http.py:2080) |
| `GET /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}` | `get_guild_scheduled_event` | No fake: `HTTPClient.get_scheduled_event` (http.py:2105) |
| `DELETE /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}` | `delete_guild_scheduled_event` | No fake: `HTTPClient.delete_scheduled_event` (http.py:2150) |
| `PATCH /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}` | `update_guild_scheduled_event` | No fake: `HTTPClient.edit_scheduled_event` (http.py:2132) |
| `POST /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/exceptions` | `create_guild_scheduled_event_exception` | No route found |
| `DELETE /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/exceptions/{exception_id}` | `delete_guild_scheduled_event_exception` | No route found |
| `PATCH /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/exceptions/{exception_id}` | `update_guild_scheduled_event_exception` | No route found |
| `GET /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/users` | `list_guild_scheduled_event_users` | No fake: `HTTPClient.get_scheduled_event_users` (http.py:2212) |
| `GET /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/users/counts` | `count_guild_scheduled_event_users` | No route found |
| `GET /guilds/{guild_id}/scheduled-events/{guild_scheduled_event_id}/{guild_scheduled_event_exception_id}/users` | `list_guild_scheduled_event_exception_users` | No route found |
| `GET /guilds/{guild_id}/soundboard-sounds` | `list_guild_soundboard_sounds` | No fake: `HTTPClient.get_soundboard_sounds` (http.py:2604) |
| `POST /guilds/{guild_id}/soundboard-sounds` | `create_guild_soundboard_sound` | No fake: `HTTPClient.create_soundboard_sound` (http.py:2620) |
| `GET /guilds/{guild_id}/soundboard-sounds/{sound_id}` | `get_guild_soundboard_sound` | No fake: `HTTPClient.get_soundboard_sound` (http.py:2600) |
| `DELETE /guilds/{guild_id}/soundboard-sounds/{sound_id}` | `delete_guild_soundboard_sound` | No fake: `HTTPClient.delete_soundboard_sound` (http.py:2648) |
| `PATCH /guilds/{guild_id}/soundboard-sounds/{sound_id}` | `update_guild_soundboard_sound` | No fake: `HTTPClient.edit_soundboard_sound` (http.py:2636) |
| `GET /guilds/{guild_id}/stickers` | `list_guild_stickers` | No fake: `HTTPClient.get_all_guild_stickers` (http.py:1666) |
| `POST /guilds/{guild_id}/stickers` | `create_guild_sticker` | No fake: `HTTPClient.create_guild_sticker` (http.py:1706) |
| `GET /guilds/{guild_id}/stickers/{sticker_id}` | `get_guild_sticker` | No fake: `HTTPClient.get_guild_sticker` (http.py:1670) |
| `DELETE /guilds/{guild_id}/stickers/{sticker_id}` | `delete_guild_sticker` | No fake: `HTTPClient.delete_guild_sticker` (http.py:1724) |
| `PATCH /guilds/{guild_id}/stickers/{sticker_id}` | `update_guild_sticker` | No fake: `HTTPClient.modify_guild_sticker` (http.py:1717) |
| `GET /guilds/{guild_id}/templates` | `list_guild_templates` | No fake: `HTTPClient.guild_templates` (http.py:1534) |
| `POST /guilds/{guild_id}/templates` | `create_guild_template` | No fake: `HTTPClient.create_template` (http.py:1537) |
| `PUT /guilds/{guild_id}/templates/{code}` | `sync_guild_template` | No fake: `HTTPClient.sync_template` (http.py:1540) |
| `DELETE /guilds/{guild_id}/templates/{code}` | `delete_guild_template` | No fake: `HTTPClient.delete_template` (http.py:1553) |
| `PATCH /guilds/{guild_id}/templates/{code}` | `update_guild_template` | No fake: `HTTPClient.edit_template` (http.py:1549) |
| `GET /guilds/{guild_id}/threads/active` | `get_active_guild_threads` | No fake: `HTTPClient.get_active_threads` (http.py:1400) |
| `GET /guilds/{guild_id}/vanity-url` | `get_guild_vanity_url` | No fake: `HTTPClient.get_vanity_code` (http.py:1600) |
| `GET /guilds/{guild_id}/voice-states/@me` | `get_self_voice_state` | No fake: `HTTPClient.get_my_voice_state` (http.py:1188) |
| `PATCH /guilds/{guild_id}/voice-states/@me` | `update_self_voice_state` | No fake: `HTTPClient.edit_my_voice_state` (http.py:1169) |
| `GET /guilds/{guild_id}/voice-states/{user_id}` | `get_voice_state` | No fake: `HTTPClient.get_voice_state` (http.py:1191) |
| `PATCH /guilds/{guild_id}/voice-states/{user_id}` | `update_voice_state` | No fake: `HTTPClient.edit_voice_state` (http.py:1173) |
| `GET /guilds/{guild_id}/webhooks` | `get_guild_webhooks` | No fake: `HTTPClient.guild_webhooks` (http.py:1434) |
| `GET /guilds/{guild_id}/welcome-screen` | `get_guild_welcome_screen` | No fake: `HTTPClient.get_welcome_screen` (http.py:1581) |
| `PATCH /guilds/{guild_id}/welcome-screen` | `update_guild_welcome_screen` | No fake: `HTTPClient.edit_welcome_screen` (http.py:1593) |
| `GET /guilds/{guild_id}/widget` | `get_guild_widget_settings` | No route found |
| `PATCH /guilds/{guild_id}/widget` | `update_guild_widget_settings` | No fake: `HTTPClient.edit_widget` (http.py:1838) |
| `GET /guilds/{guild_id}/widget.json` | `get_guild_widget` | No fake: `HTTPClient.get_widget` (http.py:1833) |
| `GET /guilds/{guild_id}/widget.png` | `get_guild_widget_png` | No route found |
| `POST /interactions/{interaction_id}/{interaction_token}/callback` | `create_interaction_response` | Adapter: `AsyncWebhookAdapter.create_interaction_response` (webhook/async_.py:445) |
| `GET /invites/{code}` | `invite_resolve` | No fake: `HTTPClient.get_invite` (http.py:1895) |
| `DELETE /invites/{code}` | `invite_revoke` | No fake: `HTTPClient.delete_invite` (http.py:1904) |
| `GET /invites/{code}/target-users` | `get_invite_target_users` | No route found |
| `PUT /invites/{code}/target-users` | `update_invite_target_users` | No route found |
| `POST /invites/{code}/target-users/bulk-add` | `bulk_add_invite_target_users` | No route found |
| `POST /invites/{code}/target-users/bulk-delete` | `bulk_remove_invite_target_users` | No route found |
| `GET /invites/{code}/target-users/job-status` | `get_invite_target_users_job_status` | No route found |
| `PUT /invites/{code}/target-users/{user_id}` | `add_invite_target_user` | No route found |
| `DELETE /invites/{code}/target-users/{user_id}` | `remove_invite_target_user` | No route found |
| `PUT /lobbies` | `create_or_join_lobby` | No route found |
| `POST /lobbies` | `create_lobby` | No route found |
| `GET /lobbies/{lobby_id}` | `get_lobby` | No route found |
| `DELETE /lobbies/{lobby_id}` | `delete_lobby` | No route found |
| `PATCH /lobbies/{lobby_id}` | `edit_lobby` | No route found |
| `PATCH /lobbies/{lobby_id}/channel-linking` | `edit_lobby_channel_link` | No route found |
| `DELETE /lobbies/{lobby_id}/members/@me` | `leave_lobby` | No route found |
| `POST /lobbies/{lobby_id}/members/@me/invites` | `create_linked_lobby_guild_invite_for_self` | No route found |
| `POST /lobbies/{lobby_id}/members/bulk` | `bulk_update_lobby_members` | No route found |
| `PUT /lobbies/{lobby_id}/members/{user_id}` | `add_lobby_member` | No route found |
| `DELETE /lobbies/{lobby_id}/members/{user_id}` | `delete_lobby_member` | No route found |
| `POST /lobbies/{lobby_id}/members/{user_id}/invites` | `create_linked_lobby_guild_invite_for_user` | No route found |
| `GET /lobbies/{lobby_id}/messages` | `get_lobby_messages` | No route found |
| `POST /lobbies/{lobby_id}/messages` | `create_lobby_message` | No route found |
| `PUT /lobbies/{lobby_id}/messages/{message_id}/moderation-metadata` | `update_lobby_message_external_moderation_metadata` | No route found |
| `GET /oauth2/@me` | `get_my_oauth2_authorization` | No route found |
| `GET /oauth2/applications/@me` | `get_my_oauth2_application` | Fake override: `HTTPClient.application_info` (http.py:2667) |
| `GET /oauth2/keys` | `get_public_keys` | No route found |
| `GET /oauth2/userinfo` | `get_openid_connect_userinfo` | No route found |
| `PUT /partner-sdk/dms/{user_id_1}/{user_id_2}/messages/{message_id}/moderation-metadata` | `update_user_message_external_moderation_metadata` | No route found |
| `POST /partner-sdk/provisional-accounts/unmerge` | `partner_sdk_unmerge_provisional_account` | No route found |
| `POST /partner-sdk/provisional-accounts/unmerge/bot` | `bot_partner_sdk_unmerge_provisional_account` | No route found |
| `POST /partner-sdk/token` | `partner_sdk_token` | No route found |
| `POST /partner-sdk/token/bot` | `bot_partner_sdk_token` | No route found |
| `GET /skus/{sku_id}/subscriptions` | `get_sku_subscriptions` | No fake: `HTTPClient.list_sku_subscriptions` (http.py:2801) |
| `GET /skus/{sku_id}/subscriptions/{subscription_id}` | `get_sku_subscription` | No fake: `HTTPClient.get_sku_subscription` (http.py:2811) |
| `GET /soundboard-default-sounds` | `get_soundboard_default_sounds` | No fake: `HTTPClient.get_soundboard_default_sounds` (http.py:2596) |
| `POST /stage-instances` | `create_stage_instance` | No fake: `HTTPClient.create_stage_instance` (http.py:2024) |
| `GET /stage-instances/{channel_id}` | `get_stage_instance` | No fake: `HTTPClient.get_stage_instance` (http.py:2012) |
| `DELETE /stage-instances/{channel_id}` | `delete_stage_instance` | No fake: `HTTPClient.delete_stage_instance` (http.py:2038) |
| `PATCH /stage-instances/{channel_id}` | `update_stage_instance` | No fake: `HTTPClient.edit_stage_instance` (http.py:2034) |
| `GET /sticker-packs` | `list_sticker_packs` | No fake: `HTTPClient.list_premium_sticker_packs` (http.py:1663) |
| `GET /sticker-packs/{pack_id}` | `get_sticker_pack` | No fake: `HTTPClient.get_sticker_pack` (http.py:1660) |
| `GET /stickers/{sticker_id}` | `get_sticker` | No fake: `HTTPClient.get_sticker` (http.py:1657) |
| `GET /users/@me` | `get_my_user` | No fake: `HTTPClient.static_login` (http.py:844) |
| `PATCH /users/@me` | `update_my_user` | No fake: `HTTPClient.edit_profile` (http.py:1142) |
| `GET /users/@me/applications/{application_id}/entitlements` | `get_current_user_application_entitlements` | No route found |
| `GET /users/@me/applications/{application_id}/role-connection` | `get_application_user_role_connection` | No route found |
| `PUT /users/@me/applications/{application_id}/role-connection` | `update_application_user_role_connection` | No route found |
| `DELETE /users/@me/applications/{application_id}/role-connection` | `delete_application_user_role_connection` | No route found |
| `POST /users/@me/channels` | `create_dm` | Fake override: `HTTPClient.start_private_message` (http.py:875) |
| `GET /users/@me/connections` | `list_my_connections` | No route found |
| `GET /users/@me/guilds` | `list_my_guilds` | Fake override: `HTTPClient.get_guilds` (http.py:1471) |
| `DELETE /users/@me/guilds/{guild_id}` | `leave_guild` | No fake: `HTTPClient.leave_guild` (http.py:1474) |
| `GET /users/@me/guilds/{guild_id}/member` | `get_my_guild_member` | No route found |
| `GET /users/{user_id}` | `get_user` | Fake override: `HTTPClient.get_user` (http.py:2830) |
| `GET /voice/regions` | `list_voice_regions` | No route found |
| `GET /webhooks/{webhook_id}` | `get_webhook` | No fake: `HTTPClient.get_webhook` (http.py:1437) |
| `DELETE /webhooks/{webhook_id}` | `delete_webhook` | Adapter: `AsyncWebhookAdapter.delete_webhook` (webhook/async_.py:251), `WebhookAdapter.delete_webhook` (webhook/sync.py:245) |
| `PATCH /webhooks/{webhook_id}` | `update_webhook` | Adapter: `AsyncWebhookAdapter.edit_webhook` (webhook/async_.py:278), `WebhookAdapter.edit_webhook` (webhook/sync.py:268) |
| `GET /webhooks/{webhook_id}/{webhook_token}` | `get_webhook_by_token` | Adapter: `AsyncWebhookAdapter.fetch_webhook_with_token` (webhook/async_.py:432), `WebhookAdapter.fetch_webhook_with_token` (webhook/sync.py:382) |
| `POST /webhooks/{webhook_id}/{webhook_token}` | `execute_webhook` | Adapter: `AsyncWebhookAdapter.execute_webhook` (webhook/async_.py:321), `WebhookAdapter.execute_webhook` (webhook/sync.py:299) |
| `DELETE /webhooks/{webhook_id}/{webhook_token}` | `delete_webhook_by_token` | Adapter: `AsyncWebhookAdapter.delete_webhook_with_token` (webhook/async_.py:264), `WebhookAdapter.delete_webhook_with_token` (webhook/sync.py:256) |
| `PATCH /webhooks/{webhook_id}/{webhook_token}` | `update_webhook_by_token` | Adapter: `AsyncWebhookAdapter.edit_webhook_with_token` (webhook/async_.py:300), `WebhookAdapter.edit_webhook_with_token` (webhook/sync.py:280) |
| `POST /webhooks/{webhook_id}/{webhook_token}/github` | `execute_github_compatible_webhook` | No route found |
| `GET /webhooks/{webhook_id}/{webhook_token}/messages/@original` | `get_original_webhook_message` | Adapter: `AsyncWebhookAdapter.get_original_interaction_response` (webhook/async_.py:482) |
| `DELETE /webhooks/{webhook_id}/{webhook_token}/messages/@original` | `delete_original_webhook_message` | Adapter: `AsyncWebhookAdapter.delete_original_interaction_response` (webhook/async_.py:527) |
| `PATCH /webhooks/{webhook_id}/{webhook_token}/messages/@original` | `update_original_webhook_message` | Adapter: `AsyncWebhookAdapter.edit_original_interaction_response` (webhook/async_.py:502) |
| `GET /webhooks/{webhook_id}/{webhook_token}/messages/{message_id}` | `get_webhook_message` | Adapter: `AsyncWebhookAdapter.get_webhook_message` (webhook/async_.py:344), `WebhookAdapter.get_webhook_message` (webhook/sync.py:311) |
| `DELETE /webhooks/{webhook_id}/{webhook_token}/messages/{message_id}` | `delete_webhook_message` | Adapter: `AsyncWebhookAdapter.delete_webhook_message` (webhook/async_.py:401), `WebhookAdapter.delete_webhook_message` (webhook/sync.py:355) |
| `PATCH /webhooks/{webhook_id}/{webhook_token}/messages/{message_id}` | `update_webhook_message` | Adapter: `AsyncWebhookAdapter.edit_webhook_message` (webhook/async_.py:369), `WebhookAdapter.edit_webhook_message` (webhook/sync.py:334) |
| `POST /webhooks/{webhook_id}/{webhook_token}/slack` | `execute_slack_compatible_webhook` | No route found |
