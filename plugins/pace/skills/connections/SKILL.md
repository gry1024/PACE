---
name: pace-connections
description: Use personal-agent memory to prepare a rich complete O/D/S profile, sync immediately before each PACE connection, and receive connection requests through native events.
---

# PACE connections

Use this after PACE setup: verified Gmail OAuth with `pace:sync pace:connect`,
ongoing upload consent, and native `connection.matched` monitoring. Respect the
platform's actual memory, connector and tool permissions. PACE does not require
another human confirmation for each upload within this consent.

## Prepare a complete profile

During initial setup and before every new connection request, use your existing understanding of the
user, available memory and authorized context. A terse user request is not the
profile: independently supply relevant background, capabilities, preferences,
interests, constraints, location, languages, availability and ongoing intentions
that you actually know. Do not ask the user to rewrite their biography. Ask a
focused question only if a missing essential request constraint prevents matching.

Submit the complete `ontology` text, `demands` list and `supplies` list. PACE stores
these directly and does not use another LLM to extract them. D/S contain known
explicit long-term wishes or offers; do not convert the instant request into a
long-term wish without evidence. Preserve dates, uncertainty and hard constraints;
do not fabricate facts or upload credentials, secrets or unrelated third-party
private material. Prefer concise information-dense statements over raw transcripts.

All three fields are mandatory and replace the previous complete profile.
An empty ontology and empty lists explicitly clear it. Maximum combined O/D/S
text is 4000 UTF-8 bytes; each list has at most 20 unique nonblank strings. Keep
as much useful known information as fits; do not silently drop hard constraints.
There is no file collection protocol and PACE never reads the PA's memory itself.

## Sync, then connect

1. Call `sync_entity` with a fresh UUID `request_id` and the full O/D/S. If you
   know the last accepted version, include `expected_entity_version`; first-ever
   sync may use 0, otherwise omit when genuinely unknown.
2. Successful sync returns `entity_status: ready`, `entity_version` and `changed`.
   It is immediately usable; no Worker or building wait is required. Identical
   content preserves the version. Do not connect if sync failed.
3. Call `connect` with a different fresh UUID, that returned `entity_version`,
   the user's instant `request_text`, and `context` containing current timezone-
   aware `observed_at` and IANA `timezone`; add a known relevant location if useful.
4. For `matched`, present the supplied related information and verified Gmail.
   `queued` means delivery is pending. For `no_match`, state that no suitable
   candidate was selected. Errors are not No Match.

Retry an operation after uncertain transport failure with the same ID and exact
payload. Never change content under that ID. For `version_conflict`, prepare a
fresh sync and a new connection operation; do not reuse the failed old payload.
A full profile replacement revokes older snapshots for new disclosure: an old
matched receipt or pending notification may be refused after either party updates.
An empty complete profile is stored but does not participate in matching.

No sync after a connection, on event receipt, or on a schedule. No polling inbox,
agent-to-agent conversation, reply tool or background memory collector. On a
`connection.matched` event, notify this user only; de-duplicate the stable event ID
through the platform. PACE also sends a separate Gmail notification to the user.
