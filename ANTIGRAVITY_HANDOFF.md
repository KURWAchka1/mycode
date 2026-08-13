# Playerok Monitor — Engineering Handoff for Antigravity

> **Purpose:** preserve the exact architecture, invariants, known Playerok quirks, deployment constraints, and verification status so development can continue without regressing already-solved edge cases.
>
> **Important:** distinguish **repository state**, **prepared server patches**, and **actually verified VPS deployment**. Do not assume they are the same.

## 1. Product goal

Build and maintain a lightweight Playerok monitoring system consisting of:

1. An Android app that shows Playerok orders and receives near-real-time notifications.
2. A small VPS service that watches Playerok, stores normalized order state in SQLite, exposes an HTTPS API to Android, and sends one automatic buyer message after a **sale** is paid.
3. Strong handling for problems/disputes, problem resolution, refunds/rollbacks, and multiple independent deals inside the same Playerok chat.

User-facing UI and notifications should be in **Russian**.

## 2. Non-negotiable business rules

These are invariants. Do not weaken them for convenience.

### 2.1 Deal identity

- The unique identity of an order is **`deal_id`**.
- Never deduplicate by `chat_id`.
- One buyer can make many separate purchases in the **same Playerok chat**.
- Repeated `chat_id` with different `deal_id` values is normal and expected.
- Problems, resolutions, refunds, Android notifications, and auto-replies must all attach to the exact `deal_id`.

### 2.2 Direction: sales vs purchases

Playerok deal direction is authoritative:

- `OUT` = **our sale**: another user paid for our item/service.
- `IN` = **our purchase**: we paid another seller.

Android must have two tabs:

- **Мои продажи** — default tab.
- **Мои покупки**.

The app may filter cached orders locally by direction; switching tabs must not cause Playerok API traffic.

### 2.3 Auto-reply safety

Exact auto-reply text:

`Ожидайте, пожалуйста, продавец скоро выполнит заказ`

Rules:

- Send this only for **`direction == OUT`**.
- Never send it for `IN` purchases.
- If direction is unknown, fail closed: **do not auto-reply** until direction is resolved reliably.
- Keep a second direction guard inside the actual send path, not only at the event dispatcher.
- Auto-reply must be idempotent per `deal_id`.
- If retry logic checks chat history, it must scope the check to this deal's interval and must not treat an older auto-reply from another order in the same chat as proof that this order was replied to.

### 2.4 Problems and refunds

Relevant Playerok system markers observed in maintained/open implementations:

- `{{ITEM_PAID}}`
- `{{DEAL_HAS_PROBLEM}}`
- `{{DEAL_PROBLEM_RESOLVED}}`
- `{{DEAL_ROLLED_BACK}}`
- `{{ITEM_SENT}}`
- `{{DEAL_CONFIRMED...}}` variants

For a problem/refund event:

- Always link to the exact `deal_id` carried by the system message/deal.
- Store event timestamp.
- Store the actor when Playerok exposes it.
- Preferred actor source: `eventByUser` / `event_by_user` on the system message.
- Fallback actor source: the matching `ItemDeal.logs` entry (`event` + `user`), choosing the entry closest in time to the system message.
- If an actor cannot be determined, report it as unknown; never invent a username.
- Current v12 snapshot contains one semantic fallback for `DEAL_ROLLED_BACK`: because the public/open client semantics describe rollback as a seller refund, it infers only the **relationship** (seller side) from direction when actor metadata is absent. It does **not** invent a username. Re-evaluate this against live Playerok before expanding actor inference.

The app should show fields such as:

- `Проблему создал`
- `Проблему решил`
- `Возврат оформил`
- timestamps for each event

For Playerok staff/moderation actors, preserve role strings such as `SECURITY` instead of crashing on unknown enums.

## 3. Architecture

### 3.1 Data flow

```text
Playerok
   ↓
VPS watcher (WebSocket = low-latency wakeup, HTTP = source of truth)
   ↓
SQLite /var/lib/playerok-monitor/orders.sqlite3
   ↓
local HTTP server 127.0.0.1:8765
   ↓
nginx public HTTPS :443
   ↓
Android foreground long-poll + orders sync
```

Android must not query Playerok directly for the order list. It reads normalized state from the VPS SQLite API.

### 3.2 VPS layout

Known layout:

- Project: `/opt/playerok-monitor`
- Config: `/etc/playerok-monitor`
- Environment file: `/etc/playerok-monitor/playerok.env`
- Database: `/var/lib/playerok-monitor/orders.sqlite3`
- systemd unit: `playerok-monitor.service`
- service user/group: `playerokmon`
- local HTTP listener: `127.0.0.1:8765`

The service has historically used:

- WorkingDirectory `/opt/playerok-monitor`
- EnvironmentFile `/etc/playerok-monitor/playerok.env`
- ExecStart `/opt/playerok-monitor/.venv/bin/python -m app.main`
- restart always
- resource limits suitable for a 1 GB VPS

### 3.3 OpenVPN is off-limits

The same VPS also runs OpenVPN.

**Never:**

- inspect OpenVPN config unless the user explicitly asks;
- alter its routes;
- restart OpenVPN;
- bind this project to the VPN interface;
- rewrite firewall rules that could affect OpenVPN.

Public access is via nginx HTTPS. If firewall changes are ever needed, add only the smallest required web rules and never enable/rebuild the firewall automatically.

## 4. API contract used by Android

The original pairing URL format is preserved:

```text
https://<public-host>/poll?token=<API_TOKEN>&after=
```

Do not ask the user to paste API tokens or Playerok tokens into chat/issues/commits.

Server versions after the orders feature use the same `/poll` endpoint with additional modes, including:

- order list sync (`mode=orders`, revision-based)
- richer long-poll events (`mode=eventsv2`)

The Android code builds these URLs from the saved pairing URL.

### Revision optimization

Orders API should expose a monotonic database `revision` and support an unchanged response, so a phone refresh does not require serializing the whole order list when nothing changed.

Desired shape is conceptually:

```json
{"revision":123,"unchanged":true,"orders":[]}
```

This is important for the small VPS.

## 5. Playerok monitoring strategy

Do not return to the broken `PyPlayerokAPI.stream.DealWatcher` implementation without a very good reason.

A previously observed library bug was:

```text
AttributeError: 'DealWatcher' object has no attribute '_last_chat_check'
```

The current custom watcher architecture intentionally avoids depending on that stream implementation.

### 5.1 Hybrid watcher

Current prepared v12 snapshot uses approximately:

- WebSocket for fast change notification / wakeup.
- HTTP raw chat/message reads as the source of truth.
- fallback scan every ~12 seconds.
- full recent-history scan every ~60 seconds.
- payment lookback ~15 minutes.
- problem/refund alert lookback ~2 hours.
- up to 3 pages / 72 latest messages per changed chat.

These values are a load/reliability compromise for a 1 vCPU / 1 GB VPS. Change only with measurements.

### 5.2 Raw JSON over fragile enum models

A previous Playerok response contained role `SECURITY`, while a Pydantic enum only knew `USER`, `MODERATOR`, `BOT`, `ADMIN`, causing validation failure.

Therefore:

- raw GraphQL JSON is preferred in compatibility-sensitive paths;
- preserve unknown enum strings;
- do not crash on new Playerok roles/statuses.

### 5.3 APQ / persisted-query compatibility

Playerok persisted-query hashes can change or be unavailable for a client/library version.

Previously observed:

- an installed `chatMessages` persisted query returned `PersistedQueryNotFound`;
- compatibility hash `1cabd4aee7c22353f49eaaff78ca82355e182f33a723d0fd92ccd36092917784` was accepted at that time;
- v9 introduced candidate-hash fallback and caches the working hash.

Other compatibility hashes used during development included:

- `userChats`: `c1ddbcd7c8b87160ac25e0734f9dc32fc945287b056f4b14abf1473bfb1ad11a`
- `deals`: `591b0e6d036c2120c8f95b97dbfdf5635df3747cd901f4895e009935229417ef`
- `deal`: `e572582c52871c15c3278d46c649c7ec70dd4711d80661a4aa3cc67b48823e3e`
- `chatMessages`: `1cabd4aee7c22353f49eaaff78ca82355e182f33a723d0fd92ccd36092917784`

Treat these as **historical compatibility values, not permanent truth**. If Playerok rejects all candidates, discover/refresh safely rather than repeatedly hammering the endpoint.

## 6. Android application

Repository: `KURWAchka1/mycode`

At handoff time, repository `main` includes Android **1.3.0**:

- package: `app.playerokmonitor`
- versionCode: `6`
- versionName: `1.3.0`
- minSdk: `26`
- targetSdk: `36`
- compileSdk: `36`

Known latest Android commit at handoff: `aa7e812281825a7b56e10f5dc34556de76b0a73a`.

CI run `31252147279` completed successfully, including:

- Gradle build
- lint
- Android 16 / API 36 emulator install+launch smoke test
- APK metadata validation
- signature validation
- artifact upload

### 6.1 UI expectations

- Default order tab: **Мои продажи**.
- Second tab: **Мои покупки**.
- Use proper Android vector drawables for navigation/actions.
- Do not use UTF-8 text glyphs such as `↻` or `←` as icons.
- Order card should clearly distinguish sale/purchase/problem/resolved/refund state.
- Tapping an event notification should open the exact order when `deal_id` is known.

### 6.2 Notification behavior

- Order paid: alert only for our sales (`OUT`).
- Problem created: urgent alert.
- Refund/rollback: urgent alert.
- Problem resolved: update state without an unnecessary second loud notification.
- Respect Android channel mute, silent/vibrate, DND, and user settings.
- Existing pleasant short custom notification chime should remain unless the user requests a change.

Android long-poll foreground service is intentionally Firebase-free. Be aware OEM/Doze/force-stop can limit client reliability; the VPS remains the 24/7 monitor.

### 6.3 Signing caveat

Current CI APKs are debug-signed using runner-generated debug keys. Different workflow runs may produce different signer certificates. Android may refuse an in-place update; uninstall/reinstall may be required.

Do not present this as a production release-signing setup. A stable signing solution is a future task if the user wants seamless updates.

## 7. Server state: verified vs prepared

This distinction is critical.

### 7.1 Last server version positively verified by user logs

**v9.1** was successfully installed and showed:

```text
Playerok raw HTTP scan OK; enum-model bypass active; chats=24
Playerok APQ OK operation=chatMessages hash=1cabd4aee7c2...
Playerok websocket connected; update subscriptions active
LIVE SERVICE CHECK: OK — chatMessages APQ принят Playerok.
```

### 7.2 Later server work

- v10: attempted, installer raced local listener readiness and rolled back.
- v10.1: server itself started, installer had a Python quoting bug (`NameError: revision`) and rolled back.
- v10.1-r2: prepared to fix installer check; no successful installation log is preserved in this handoff.
- v11: prepared sales/purchases separation and `OUT`-only auto-reply.
- v12: prepared actor/refund tracking.

**Do not assume v11 or v12 is currently installed on the VPS.**

First Antigravity task on a connected VPS should be to inspect the actual `playerok-monitor` files/schema/status and report what is installed **without changing anything**.

## 8. Server snapshot supplied with the handoff package

A separate `server_snapshot/` directory is supplied in the downloadable handoff package as a development reference. The GitHub handoff branch may contain only the two handoff Markdown files; if the snapshot is not present in the workspace, import it from the handoff ZIP before server work.

It is assembled from:

- `main.py` from the v7 custom-watcher generation;
- `playerok_raw.py` from the v9 APQ compatibility generation;
- `db.py`, `event_bus.py`, `processor.py`, `playerok_watcher.py` from the prepared v12 patch;
- v12 installer and patch notes.

This snapshot is **not evidence of what is deployed**. Treat it as the latest prepared source baseline for comparison and reconstruction.

Before deploying it, compare it against the VPS and run compatibility tests.

## 9. SQLite requirements

Core table design should support at least:

- `deal_id` primary identity
- `chat_id`
- `direction` (`IN`/`OUT`/unknown)
- item/service name
- price
- counterparty/buyer info
- buyer comment
- payment message id/time
- auto-reply attempted/sent state
- problem active flag
- problem reported time + actor id/name/role/relation
- problem resolved time + actor id/name/role/relation
- rollback/refund flag + time + actor id/name/role/relation
- updated timestamp
- monotonic revision

Indexes should support direction filtering, revision updates, and unresolved reply work without expensive scans.

Schema migration must preserve historical data.

## 10. Event semantics expected by Android

Server should produce rich events tied to a `deal_id`, conceptually:

- `ORDER_PAID`
- `PROBLEM_CREATED`
- `PROBLEM_RESOLVED`
- `DEAL_ROLLED_BACK` / refund event

A real sale test should eventually show server logs analogous to:

```text
ITEM_PAID deal=<unique-deal-id> chat=<chat-id> direction=OUT payment_message=<id>
Android event queued ... deal=<unique-deal-id>
Auto-reply sent deal=<unique-deal-id> ...
```

A purchase test should show `direction=IN` and **must not** show `Auto-reply sent` or a new-sale alert.

Two purchases by the same buyer in the same chat must produce two independent `deal_id` records and independent lifecycle state.

## 11. Deployment safety rules

Every VPS patch should:

1. validate archive checksums and Python syntax before stopping service;
2. run imports/preflight as the service user when practical;
3. perform synthetic tests before touching live files;
4. stop/restart **only** `playerok-monitor.service`;
5. back up every changed file and SQLite before mutation;
6. use SQLite backup API or another safe DB backup mechanism;
7. install files atomically where practical;
8. restart service;
9. wait for the local listener rather than checking it immediately once;
10. perform local API smoke tests;
11. show service status + fresh logs on failure;
12. rollback both code and DB/schema-affecting state when feasible;
13. never touch OpenVPN.

Installer readiness checks previously failed because they assumed `systemctl active` meant port 8765 was already listening. Always wait/retry the actual local API.

## 12. Security and secrets

Never commit or expose:

- Playerok `token` cookie value;
- pairing/API token;
- TLS private keys;
- stable signing keys or keystores;
- server `.env` contents;
- user credentials.

Playerok authentication token is taken from browser cookie `.playerok.com` named `token` and stored only in server configuration/environment.

The pairing URL contains a secret token. The user should paste it only into the app, not into public GitHub issues/logs.

## 13. Recommended first Antigravity workflow

Before implementing any new feature:

1. Read this file and `ANTIGRAVITY_MASTER_PROMPT.md` completely.
2. Inspect repository `main`, current Android version, and CI.
3. Run local Android build/lint if the environment supports it.
4. If VPS access is available, **read-only inspect**:
   - `systemctl status playerok-monitor`
   - current `/opt/playerok-monitor/app/` file hashes/version markers
   - SQLite schema only
   - recent monitor journal
   - local `127.0.0.1:8765` API behavior
5. Do not touch nginx/OpenVPN/firewall while identifying installed version.
6. Compare live server against `server_snapshot/`.
7. Report discrepancies before deploying anything.
8. Add automated tests for any bug before or alongside a fix.

## 14. Acceptance tests that must not regress

At minimum, preserve tests for:

1. **Two deals, one chat:** same `chat_id`, different `deal_id`; both stored.
2. **OUT sale:** one Android new-order event + one auto-reply.
3. **IN purchase:** stored under purchases tab; zero auto-reply; zero new-sale alert.
4. **Unknown direction:** zero auto-reply.
5. **Problem on deal B only:** deal A remains normal even in same chat.
6. **Problem resolved:** exact deal updated; resolver preserved when available.
7. **Refund:** exact deal updated; actor preserved when available.
8. **Unknown Playerok role:** e.g. `SECURITY`; no enum crash.
9. **Duplicate scan:** no duplicate Android event or auto-reply for same `deal_id` lifecycle event.
10. **Old reply in same chat:** must not suppress auto-reply for a later new deal.
11. **Orders revision unchanged:** returns lightweight unchanged response.
12. Android build + lint + Android 16 install/launch smoke test.

## 15. Known future improvements

These are not mandatory unless requested, but are reasonable backlog items:

- stable Android release signing so upgrades install over previous APKs;
- proper Gradle wrapper checked into repo;
- unit/integration tests for Android JSON parsing and tab filtering;
- server test suite committed alongside snapshot instead of only installer synthetic tests;
- formal OpenAPI-like documentation for `/poll` modes;
- explicit schema version table / migrations;
- more robust Playerok persisted-query discovery strategy;
- instrumentation/metrics with strict low overhead;
- optional FCM path only if user later wants higher Android delivery reliability.

## 16. User priorities / working style

The user wants:

- ready-to-run code/artifacts rather than long compile instructions;
- concise explanations;
- minimal VPS load;
- fast reaction to paid orders/problems/refunds;
- no regressions in existing behavior;
- direct ownership of bugs and concrete fixes;
- installers that replace only necessary files and include rollback.

When a bug appears, inspect exact logs first. Do not guess and do not make the user repeatedly reinstall unrelated components.

---

**Handoff status:** Android 1.3.0 is present in repository and its CI run succeeded. The latest prepared server baseline is v12, but actual VPS deployment after v9.1 must be verified before assuming v12 functionality is live.
