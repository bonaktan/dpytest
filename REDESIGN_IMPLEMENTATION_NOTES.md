# Redesign implementation notes

## Baseline (2026-10-31)

Before redesign changes, `python -m pytest tests/ -q` passed: 82 tests,
with two existing `VerifyMessage dropped without being used` warnings. The
installed pytest-asyncio also emitted a fixture loop scope deprecation warning.

Project metadata declares Python >=3.8 and `discord.py ~= 2.3`. These are
declared compatibility ranges, not evidence that the redesign works across the
entire range. The adapter and lifecycle proofs in T0 remain outstanding.

## Transcript foundation

`observations.Transcript` provides isolated immutable JSON-like snapshots,
sequence checkpoints, non-consuming queries and bounded asynchronous waits.
Queries can filter direction, channel, author, message, interaction and visibility;
unfiltered queries are administrative. `expect_none` observes a bounded real-time
window after an explicit checkpoint.
It is connected to the experimental session and transport. The focused observation tests
pass on the current interpreter; lifecycle, routing and version-matrix evidence
are still required before claiming the redesign works.

`runtime.Runtime` tracks explicitly registered tasks, retains their exceptions,
and cancels only owned work with a bounded shutdown. It tracks client events and
tasks scheduled during interaction injection. Focused runtime and transcript tests pass. The current
environment reports discord.py `2.8.0a`; this is not a compatibility matrix.

An experimental `session.Session` now initializes a fresh client without login,
runs configuration before `setup_hook`, preserves its connection state and
command tree, releases readiness, and tracks scheduled client events. Its HTTP
adapter supports basic ordinary message create/get/edit/delete; other requests
and most webhook operations are rejected locally. An experimental actor API is available.
Focused lifecycle and message tests cover startup, cleanup, isolation and a real
discord.py message round trip on
the installed version. Interaction routing, webhook ownership across sessions,
other scheduling paths and the supported version matrix remain unverified.

An experimental slash injection now exercises the real command tree
and can intercept a public initial message response. This is a narrow routing
spike, not a complete interaction ledger: some response transitions,
other callback types and resolved entity options are
not yet supported. The focused command-routing test passes on the installed
version.

The injection boundary temporarily installs a task factory while discord.py
parses an interaction, registering synchronously scheduled work with the owning
runtime. Tests exercise cancellation of a waiting command and interleaved
command responses from two sessions. A real registered view button can now open
a modal, and a validated text-field submission reaches its real callback. These
are exposed through experimental actor and scoped expectation helpers. The scenario now
also exercises a deferred ephemeral response, original edit and ephemeral
followup through discord.py, checking identity, transcript visibility and denial
of ordinary channel fetch. This is not a complete visibility model or interaction
ledger: other callback transitions, custom task
factories, other UI types, and supported versions remain unverified or unimplemented.

Initial ephemeral responses are now stored with actor-only visibility and are
excluded from ordinary channel fetches and Gateway message events. Public initial
responses and public followups emit message events. A focused test checks the
private response and its original-response expectation.

Component callbacks can update their source message directly or defer an update
and edit it later. Focused tests verify original message identity and public
Gateway edit dispatch for both paths. Modal-originated update variants and the
complete interaction transition/error table remain outstanding.

Interaction original deletion and followup retrieval/edit/deletion are routed
locally with token ownership checks. The first followup after an unedited defer
updates the original and preserves its visibility, matching Discord's documented
compatibility behavior. Public deferred placeholders now emit message and edit
events, retain identity, and clear their loading flag on completion.

String selects now validate the sent options, count and duplicate selections
before dispatching through the real view callback. Entity selects remain open.

The current full test suite passed on the installed interpreter: 95 tests, with
the two baseline verification warnings and pytest-asyncio deprecation warning.
This does not establish the required version matrix.

An initial reaction scenario now exercises a cached `wait_for('reaction_add')`,
duplicate membership, cache eviction, the uncached raw event, and a subsequent
server fetch. Normal reaction add and removal, bot HTTP operations, and clearing
one or all emojis now update membership and the fetched message projection.
Reaction membership now belongs to the message server and is cleared on message
deletion. A focused test covers equivalent custom emoji string/partial forms
and count deduplication. Burst reactions, comprehensive custom emoji coverage
and modeled HTTP errors remain outstanding.

Ordinary message multipart uploads store attachment bytes in session memory;
attachment reads use a local-only CDN adapter and teardown clears that storage.
Message attachment removal and subsequent fetches are covered by a focused test.
Interaction and webhook multipart uploads use the same storage; focused tests
cover initial response, followup and followup-edit uploads and reads on the
installed development version and discord.py 2.7.1.

Actor text messages now enter the server and real Gateway parser, including
actor-owned edits and deletes. Focused tests exercise a real prefix command,
cached edit/delete callbacks and rejection of another actor's deletion. Bot
ordinary message edits and deletes now emit the corresponding Gateway events.

After these changes the full suite passed (107 tests, two baseline warnings).
Focused flake8 passed with `--jobs 1`; its default multiprocessing mode was
denied access to a Windows pipe in this environment.

The full suite subsequently passed 119 tests on the default interpreter, with
the same two baseline warnings. Focused flake8 passed with `--jobs 1`.

Legacy public helpers now reject use while multiple sessions overlap, and the
guard unregisters sessions after teardown or startup failure. A compatibility
session wrapper is still outstanding. The latest full suite passed 128 tests
on the default interpreter, with the same two baseline warnings.

The session tutorial includes an executable pytest fixture example, which
passes, as do the guild and reaction examples. Sphinx 9.2.0 on Python 3.14
previously failed when formatting runtime `OpenNamespace` annotation placeholders.
The documentation configuration now handles special-attribute introspection and
renders those placeholders as `DiscordPayload`; a clean full HTML build passed
with warnings treated as errors.

Compatibility check: the full current suite passed with Python 3.14.7 and the
locally cached discord.py 2.7.1 (114 tests; deprecation and baseline warnings).
The import paths were checked to confirm discord.py came from the cache and
dpytest from this worktree. This does not verify Python 3.8-3.13 or the earlier
discord.py versions permitted by project metadata. The environment's default
discord.py remains the 2.8.0 development build.

The session accepts an injected monotonic clock. Initial callback deadlines and
token expiry are checked at the local adapter boundary, with rejected requests
recorded without tokens. Focused tests exercise both limits without sleeping.
Discord's interaction documentation was checked on 2026-10-31 and specifies
three seconds for the initial response and fifteen minutes for token validity.
Interaction tokens are independently generated, and a focused test rejects a
token from another session even when their interaction IDs match. Closed
sessions also reject subsequent adapter requests.

Slash commands accept registry-validated primitive options. A focused integration
test demonstrates the real command check and custom transformer running before
the callback. Autocomplete now routes to registered handlers and records their
choices. User and message context menus route real resolved discord.py objects;
slash commands also support grouped subcommands and session actor user options.
Other slash-option entity resolution remains open. Actor message
and modal handles are bound to their originating session to prevent ID collisions
from resolving to another session's entities.

Experimental guild setup can create a guild, text channel and named member in
the pre-setup configuration callback. A focused integration test exercises
guild prefix and slash commands and member option resolution on discord.py
2.7.1 and the installed development version. Guild entities still rely on
discord.py cache objects; authoritative server-side guild state, roles and
permission modeling remain outstanding.
Guild reaction add/remove and clear events now include guild identity; cached
and raw add paths include a real member for guild actors. Ephemeral messages
reject reaction operations instead of generating public Gateway events.

Session captures event, command-tree, view and modal error callbacks while
preserving application handlers. `expect_error` acknowledges expected failures;
unacknowledged callback failures fail context-manager exit. Focused tests cover
event, application-command and view paths. `Session.create_task` registers
background work for cleanup and error reporting; a focused test acknowledges a
background failure. Modal error behavior still needs verification.
Scoped interaction expectation timeouts now include the action ID, relevant
callback error types, pending owned task names and recent observations, and
chain a matching callback exception when available.

Session teardown stops views registered in the factory or setup hook before
cancelling owned tasks. A focused lifecycle test covers persistent and timed
views plus a pending application task.
