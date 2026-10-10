---
name: pace-setup
description: Set up PACE once with verified Gmail, ongoing profile-upload consent and native connection.matched event monitoring.
---

# PACE setup

PACE serves personal agents on event-capable platforms. Initial targets are
ChatGPT Work on web or desktop Cloud, and dots. Use the platform's native OAuth
and event-monitoring flow; do not invent a callback URL or signing secret.

1. Connect the packaged PACE MCP server through OAuth with both `pace:sync`
   and `pace:connect`. The PACE consent page combines Google Gmail registration,
   ongoing PA profile uploads before connections, matching-related disclosure,
   and Gmail notifications. The user completes this initial flow in their browser.
   Across hosts, use the same verified Gmail; do not ask for a separate PACE signup.
2. Establish native monitoring of `connection.matched` for this account. The
   response instruction is: notify the user of the request and the supplied
   requester information. Do not reply to another agent or initiate agent chat.
   Let the platform supply and verify the webhook destination and secret, store
   the subscription, and refresh it before expiry. Subscription refresh is
   transport maintenance; it does not schedule profile uploads.
3. Initialize the complete O/D/S profile once from the PA's existing memory using
   the connections skill and `sync_entity`, without making a `connect` request.
   Save the ready version; the user can then be found without initiating a search.
4. Report setup complete only after OAuth, event subscription and initial sync succeed. If
   external events cannot trigger the user's PA in this environment, report the
   limitation and stop setup. PACE has no polling or platform-specific fallback.

The platform may require its own monitoring or tool permission approval; respect
it. PACE ongoing consent does not override platform permissions or guarantee
unattended execution. Do not claim that installing the package by itself has
created a subscription. Gmail is sent by PACE's system account; the user grants
only `openid email` for login, not permission to read their mailbox.

After this one-time initialization, update only immediately before each new
`connect`. Do not schedule uploads or create background profile tasks. Never expose OAuth tokens or webhook secrets.
