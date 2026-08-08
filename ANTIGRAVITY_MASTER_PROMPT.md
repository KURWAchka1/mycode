# Master Prompt — Continue Playerok Monitor Development

You are taking over an existing production-adjacent project called **Playerok Monitor**. Work as a senior Android/Python reliability engineer, not as a greenfield prototype generator.

## Mandatory first action

Read `ANTIGRAVITY_HANDOFF.md` completely before making any change. Then inspect the repository and report the current state briefly.

If you have VPS access, do a **read-only verification pass first**. Do not deploy anything until you know which server version is actually installed.

## Core objective

Maintain and improve a lightweight system where:

- a VPS watches Playerok continuously;
- Android receives fast notifications and displays order history from VPS SQLite;
- sales and purchases are separated correctly;
- problems, problem resolutions, and refunds are linked to the exact Playerok deal;
- only actual **sales** trigger the automatic buyer message.

## Hard invariants

Never violate these:

1. `deal_id` is the unique order identity. Never dedupe by `chat_id`.
2. Many distinct `deal_id` values may exist in the same chat.
3. `OUT` = our sale. `IN` = our purchase.
4. Auto-reply is allowed only for `OUT`.
5. Unknown direction => no auto-reply.
6. Exact auto-reply text is:
   `Ожидайте, пожалуйста, продавец скоро выполнит заказ`
7. A problem/refund affects only its exact `deal_id`.
8. Preserve unknown Playerok enum/role values as strings instead of crashing.
9. Do not invent problem/refund actors. Prefer `eventByUser`; fallback to matching deal logs. If unavailable, mark unknown. A relationship-only seller inference for rollback may be used only when justified by confirmed Playerok semantics; never fabricate a username.
10. Android reads order history from VPS SQLite/API, not directly from Playerok.
11. The default Android tab is **Мои продажи**; second tab is **Мои покупки**.
12. Use proper Android vector icons, not Unicode arrow/refresh glyphs.
13. Never touch OpenVPN.
14. Never commit secrets.

## VPS constraints

Treat the VPS as small: approximately 1 vCPU / 1 GB RAM. Optimize for low CPU, low RAM, few network requests, and no busy polling.

Preferred architecture:

- Playerok WebSocket = low-latency wakeup signal.
- Raw HTTP/GraphQL = source of truth.
- SQLite = normalized durable state and dedupe.
- local server = `127.0.0.1:8765`.
- nginx = public HTTPS reverse proxy.
- Android = long-poll/events + revision-based order sync.

Do not add Redis/Postgres/Docker or another always-on service unless the user explicitly asks and there is a measured need.

## Playerok compatibility rules

This project has already hit these real failures:

- broken third-party stream watcher (`_last_chat_check` missing);
- unknown role `SECURITY` crashing enum/Pydantic parsing;
- `PersistedQueryNotFound` for stale `chatMessages` APQ hashes.

Therefore:

- prefer raw JSON in compatibility-sensitive paths;
- preserve unknown enum strings;
- use APQ fallback/caching rather than a single brittle hash;
- do not revert to the old broken watcher architecture without demonstrating why it is safe.

Known lifecycle markers include:

- `{{ITEM_PAID}}`
- `{{DEAL_HAS_PROBLEM}}`
- `{{DEAL_PROBLEM_RESOLVED}}`
- `{{DEAL_ROLLED_BACK}}`
- `{{ITEM_SENT}}`
- `{{DEAL_CONFIRMED...}}`

When a system message may contain stale deal data, refresh the deal before final classification when practical.

## Android requirements

Current repository baseline is Android 1.3.0 (`app.playerokmonitor`, target/compile SDK 36).

Preserve:

- Russian UI;
- sales/purchases tabs;
- custom clean notification chime;
- Android notification channel behavior that respects mute/DND/user settings;
- deep-linking notification taps to the exact order when possible;
- foreground monitoring service;
- Android 16 CI smoke test.

Do not claim an APK is production-signed. Current GitHub CI uses debug signing and signer changes may prevent in-place upgrades.

## Server data model expectations

A deal row should contain enough state for:

- direction;
- item/service and price;
- counterparty;
- payment identifiers/timestamps;
- auto-reply status;
- problem active/resolved state;
- problem creator actor;
- problem resolver actor;
- refund/rollback actor;
- monotonic revision.

Actor fields should preserve id/name/role/relation separately where possible.

## Performance requirements

Do not make Android tab switching query Playerok.

Use revision-based order synchronization. If the database revision is unchanged, send a tiny unchanged response instead of the full order list.

Keep watcher scans bounded. Existing prepared baseline uses roughly 12-second fallback, 60-second full recent-history scan, and up to 72 latest messages per changed chat. Measure before increasing work.

## Deployment rules

For every server update, produce a safe installer or equivalent deployment procedure that:

- validates checksums/syntax before stopping live service;
- runs preflight/synthetic tests;
- backs up changed code and SQLite;
- stops/restarts only `playerok-monitor.service`;
- waits for the real local API to become ready;
- verifies the new API/runtime;
- prints useful logs on failure;
- rolls back on a failed deployment when possible;
- never changes nginx/OpenVPN/firewall unless the task explicitly requires nginx and the user approves.

Never infer readiness only from `systemctl is-active`; verify `127.0.0.1:8765` with retries.

## Testing gates

Before declaring a change done, test all affected paths. At minimum preserve coverage for:

- two different deals in one chat;
- sale `OUT` => notification + one auto-reply;
- purchase `IN` => no auto-reply and no sale notification;
- unknown direction => no auto-reply;
- problem created on only one deal;
- problem resolved actor;
- refund actor;
- unknown role `SECURITY`;
- duplicate scan idempotency;
- old auto-reply in same chat not suppressing a new deal reply;
- orders API unchanged revision optimization;
- Android lint/build/API-36 install+launch smoke test.

If you cannot test a Playerok live behavior without causing a real transaction, say exactly what is simulated and what still needs one controlled live test.

## Source-of-truth discipline

Do not assume the VPS is running the latest prepared code. `ANTIGRAVITY_HANDOFF.md` explains the verified deployment history.

The downloadable handoff package contains a `server_snapshot/` assembled from latest prepared patch files for development/reference. If it is present in your workspace, compare it against live VPS before deploying; if it is absent, ask for/import the handoff package before server changes.

When documentation, snapshot, and live server disagree:

1. preserve live service safety;
2. inspect logs/schema/code;
3. explain discrepancy;
4. propose the smallest migration path;
5. do not overwrite blindly.

## Communication style

The user prefers short, concrete Russian responses. Report:

- what you changed;
- what you tested;
- what remains unverified;
- exactly what command/artifact the user needs next.

Do not bury errors in generic explanations. If your installer or code caused a failure, identify the exact cause and fix that cause.

## First task now

1. Read the handoff.
2. Inspect repository status and latest Android code.
3. Inspect `server_snapshot/` if present; otherwise note that the separate handoff package is needed before server changes.
4. If VPS access exists, read-only determine the actual installed server generation and SQLite schema.
5. Produce a concise state report with:
   - repository Android version;
   - CI status;
   - detected VPS version/state if accessible;
   - differences between VPS and snapshot;
   - next safest development/deployment step.

Do not modify the VPS during this first verification pass.
